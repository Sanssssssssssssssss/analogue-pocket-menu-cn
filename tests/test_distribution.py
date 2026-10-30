import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import build_library as library
import install

def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)

def decode(path):
    raw=path.read_bytes();magic,version,count,cw,tw=struct.unpack_from('<4sHHHH',raw)
    assert (magic,version,cw,tw)==(b'GBCV',9,128,80)
    assert len(raw)==528+count*(128+65536+768)+512
    start=528+count*(128+65536)
    paths=[raw[start+i*256:start+(i+1)*256].split(b'\0')[0].decode() for i in range(count*3+2)]
    return raw,count,paths

class Distribution(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.card=self.root/'card';self.card.mkdir()
        write(self.card/'Analogue_Pocket.json',b'{"product":"Analogue Pocket","firmware":{"runtime":{"name":"2.5"}}}')
        rom=bytearray(32768);rom[0x143]=0xC0;rom[0x134:0x138]=b'TEST'
        write(self.card/'Assets/gbc/common/RPG/Example.gbc',rom)
        write(self.card/'Saves/gbc/common/Example.sav',b'original progress')
        self.bios=self.root/'local-bios.bin';self.bios.write_bytes(bytes(2304))
        self.out=self.root/'staged'
        self.backup=self.root/'backup'
        self.package=self.root/'package'
        import shutil
        shutil.copytree(ROOT/'packaging',self.package)
        # Synthetic bitstream is only used by installer tests, never a release.
        write(self.package/'Cores/pocketlab.CoverFlow/gbc.rbf_r',b'synthetic FPGA fixture')
        self.manifest()

    def tearDown(self):self.temp.cleanup()

    def manifest(self):
        files=[{'path':p.relative_to(self.package).as_posix(),'bytes':p.stat().st_size,'sha256':library.sha(p)} for p in sorted(self.package.rglob('*')) if p.is_file() and p.name!='release-manifest.json']
        (self.package/'release-manifest.json').write_text(json.dumps({'version':'test-fixture','files':files}),encoding='utf-8')

    def build(self,**kwargs):return library.build(self.card,self.out,bios=self.bios,**kwargs)

    def test_parent_last_in_every_folder_including_root(self):
        self.build()
        nodes={}
        for p in (self.out/'Assets').rglob('*.bin'):
            if p.name=='gbc_bios.bin':continue
            raw,count,paths=decode(p);nodes['/'+p.relative_to(self.out).as_posix()]=paths
            self.assertTrue(raw[528+(count-1)*128+40]&128)
            parent=paths[(count-1)*3]
            self.assertTrue((self.out/parent.lstrip('/')).exists())
            self.assertGreater(struct.unpack_from('<H',raw,528+(count-1)*128+52)[0],0)
        root='/Assets/gbclab/common/covers.bin'
        self.assertEqual(nodes[root][-5],root)
        seen=set();todo=[root]
        while todo:
            name=todo.pop()
            if name in seen:continue
            seen.add(name)
            todo.extend(p for p in nodes[name][::3] if p in nodes)
        self.assertEqual(seen,set(nodes))

    def test_source_untouched_and_saves_are_not_imported(self):
        before={p.relative_to(self.card).as_posix():library.sha(p) for p in self.card.rglob('*') if p.is_file()}
        result=self.build()
        after={p.relative_to(self.card).as_posix():library.sha(p) for p in self.card.rglob('*') if p.is_file()}
        self.assertEqual(before,after);self.assertEqual(result['rom_copies'],0)
        self.assertEqual(list(self.out.rglob('*.sav')),[])

    def test_chinese_title_alias_has_native_columns(self):
        titles=self.root/'titles.json';titles.write_text(json.dumps({'Assets/gbc/common/RPG/Example.gbc':'我们的冒险'},ensure_ascii=False),encoding='utf-8')
        result=self.build(titles=titles);self.assertEqual(result['warnings'],[])
        found=False
        for p in (self.out/'Assets/gbclab/common/libs').glob('*.bin'):
            raw,count,paths=decode(p)
            for i in range(count):
                if paths[i*3].endswith('Example.gbc'):
                    self.assertEqual(struct.unpack_from('<H',raw,528+i*128+52)[0],80)
                    self.assertTrue(any(raw[528+count*128+i*65536+45568:528+count*128+i*65536+46592]))
                    found=True
        self.assertTrue(found)

    def test_duplicate_content_shares_only_isolated_save(self):
        raw=(self.card/'Assets/gbc/common/RPG/Example.gbc').read_bytes()
        write(self.card/'Assets/gb/common/Duplicate.gb',raw)
        result=self.build();saves={x['save'] for x in result['source_refs']}
        self.assertEqual(len(saves),1);self.assertTrue(next(iter(saves)).startswith('/Saves/gbclab/common/'))

    def test_output_on_card_and_existing_output_rejected(self):
        for out in (self.card/'new',self.card,self.root):
            with self.assertRaises(ValueError):library.build(self.card,out)

    def test_unmapped_title_reference_rejected_before_output(self):
        p=self.root/'titles.json';p.write_text('{"missing.gb":"Missing"}')
        with self.assertRaises(ValueError):self.build(titles=p)
        self.assertFalse(self.out.exists())

    def test_long_utf8_apf_path_rejected(self):
        with self.assertRaises(ValueError):library.path_bytes('/Assets/gbc/common/'+'测'*90+'.gbc')

    def test_plan_only_writes_nothing(self):
        self.build();before={p:library.sha(p) for p in self.card.rglob('*') if p.is_file()}
        result=install.plan(self.card,self.package,self.out)
        self.assertGreater(len(result['changes']),0)
        self.assertEqual(before,{p:library.sha(p) for p in self.card.rglob('*') if p.is_file()})
        self.assertFalse(self.backup.exists())

    def test_install_and_rollback_preserve_latest_saves(self):
        old=self.card/'Cores/pocketlab.CoverFlow/core.json';write(old,b'old core metadata')
        save=self.card/'Saves/gbclab/common/test.sav';write(save,b'earlier progress')
        self.build();result=install.apply(self.card,self.package,self.out,self.backup)
        self.assertEqual(result['status'],'installed_sha256_verified')
        save.write_bytes(b'latest progress')
        install.rollback(self.card,self.backup,True)
        self.assertEqual(old.read_bytes(),b'old core metadata');self.assertEqual(save.read_bytes(),b'latest progress')
        self.assertEqual((self.card/'Saves/gbc/common/Example.sav').read_bytes(),b'original progress')

    def test_changed_rom_or_package_refuses_install(self):
        self.build();(self.card/'Assets/gbc/common/RPG/Example.gbc').write_bytes(b'changed')
        with self.assertRaises(ValueError):install.apply(self.card,self.package,self.out,self.backup)
        self.assertFalse(self.backup.exists())

    def test_tampered_package_checksum_rejected(self):
        self.build();(self.package/'Cores/pocketlab.CoverFlow/gbc.rbf_r').write_bytes(b'changed')
        with self.assertRaises(ValueError):install.plan(self.card,self.package,self.out)

    def test_forbidden_paths_rejected(self):
        for name in ('../firmware.bin','/System/a','Saves/gbclab/common/a.sav','Cores/original/a','Assets/gbclab/common/../../gbc/x','Cores/pocketlab.CoverFlow/a:stream'):
            with self.assertRaises(ValueError):install.confined(self.card,name)

    def test_existing_backup_refused(self):
        self.build();self.backup.mkdir()
        with self.assertRaises(ValueError):install.apply(self.card,self.package,self.out,self.backup)

    def test_rollback_refuses_changed_file(self):
        self.build();install.apply(self.card,self.package,self.out,self.backup)
        (self.card/'Cores/pocketlab.CoverFlow/core.json').write_bytes(b'new manual change')
        with self.assertRaises(ValueError):install.rollback(self.card,self.backup,True)

    def test_interrupted_install_can_restore_overwritten_files(self):
        write(self.card/'Assets/gbclab/common/covers.bin',b'previous covers')
        self.build();real=install.publish;counter=0
        def fail_after_one(*args):
            nonlocal counter
            counter+=1
            if counter==2:raise OSError('simulated unplug')
            return real(*args)
        with patch.object(install,'publish',side_effect=fail_after_one):
            with self.assertRaises(OSError):install.apply(self.card,self.package,self.out,self.backup)
        install.rollback(self.card,self.backup,True)
        self.assertEqual((self.card/'Assets/gbclab/common/covers.bin').read_bytes(),b'previous covers')

    def test_link_cannot_redirect_into_original_files(self):
        target=self.card/'Assets/gbclab/common';target.parent.mkdir(parents=True)
        try:target.symlink_to(self.card/'Assets/gbc/common',target_is_directory=True)
        except OSError:self.skipTest('Symlinks unavailable on this host')
        with self.assertRaises(ValueError):install.confined(self.card,'Assets/gbclab/common/original.gbc')

if __name__=='__main__':unittest.main()
