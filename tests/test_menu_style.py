import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import build_library as lib
import install
from menu_icons import cover_bytes, icon_image, kind
import style_library as style


class MachineMenu(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.card=self.root/'card';self.card.mkdir()
        (self.card/'Analogue_Pocket.json').write_text('{"product":"Analogue Pocket"}')
        for platform in ('gb','gbc'):
            game=self.card/f'Assets/{platform}/common/3.FTG/Example.{platform}'
            game.parent.mkdir(parents=True)
            raw=bytearray(32768);raw[0x143]=0xC0 if platform=='gbc' else 0
            game.write_bytes(raw)
        bios=self.root/'local-bios.bin';bios.write_bytes(bytes(2304))
        base=self.root/'base';lib.build(self.card,base,bios=bios)
        shutil.copytree(base/'Assets/gbclab',self.card/'Assets/gbclab')
        self.out=self.root/'style'

    def tearDown(self):
        self.temp.cleanup()

    def card_hashes(self):
        return {p.relative_to(self.card).as_posix():lib.sha(p) for p in self.card.rglob('*') if p.is_file()}

    def test_graph_and_all_game_save_metadata_retained(self):
        before=self.card_hashes()
        result=style.style(self.card,self.out)
        self.assertEqual(before,self.card_hashes())
        self.assertEqual(result['home_machines'],['gb','gbc'])
        old=style.decode((self.card/style.ROOT_PACK).read_bytes())
        new=style.decode((self.out/style.ROOT_PACK).read_bytes())
        self.assertEqual([e['paths'] for e in old['entries']],[e['paths'] for e in new['entries']])
        for rel in before:
            if not rel.endswith('.bin') or '/gbclab/' not in rel or rel.endswith('gbc_bios.bin'):
                continue
            previous=style.decode((self.card/rel).read_bytes())
            raw=(self.out/rel if (self.out/rel).exists() else self.card/rel).read_bytes()
            updated=style.decode(raw)
            self.assertEqual([e['paths'] for e in previous['entries']],[e['paths'] for e in updated['entries']])
            self.assertEqual(previous['tail'],updated['tail'])
            for i,(a,b) in enumerate(zip(previous['entries'],updated['entries'])):
                if not a['record'][40]&128:
                    self.assertEqual(a,b)
                elif rel in {x['path'] for x in result['source_packs']} and rel != style.ROOT_PACK and i < len(previous['entries'])-1:
                    self.assertEqual(b['blob'][:45568],cover_bytes('fighting'))
        self.assertEqual(result['game_entries_changed'],0)

    def test_classics_move_to_their_own_page_with_parent_link(self):
        path=self.card/style.ROOT_PACK
        root=style.decode(path.read_bytes())
        entry=style.restyle(root['entries'][0],'favorites','宝可梦')
        child_path='Assets/gbclab/common/libs/classic-fixture.bin'
        previous=style.decode((self.card/root['entries'][0]['paths'][0].lstrip('/')).read_bytes())
        (self.card/child_path).write_bytes(style.encode(previous))
        entry['paths'][0]='/'+child_path
        record=bytearray(entry['record']);record[40]|=2
        struct.pack_into('<I',record,48,0x12345678)
        entry['record']=bytes(record)
        root['entries'].insert(0,entry)
        path.write_bytes(style.encode(root))
        style.style(self.card,self.out)
        updated=style.decode((self.out/style.ROOT_PACK).read_bytes())
        self.assertEqual(len(updated['entries']),4)
        self.assertEqual(updated['entries'][2]['paths'][0],'/'+style.CLASSICS_PACK)
        classics=style.decode((self.out/style.CLASSICS_PACK).read_bytes())
        self.assertEqual(classics['entries'][0],entry)
        self.assertEqual(classics['entries'][-1]['paths'][0],'/'+style.ROOT_PACK)
        self.assertNotEqual(classics['tail'],root['tail'])
        child=style.decode((self.out/child_path).read_bytes())
        self.assertEqual(child['entries'][-1]['paths'][0],'/'+style.CLASSICS_PACK)
        self.assertEqual(child['entries'][:-1],previous['entries'][:-1])

    def test_changed_input_refused_by_installer(self):
        style.style(self.card,self.out)
        package=self.root/'package';shutil.copytree(ROOT/'packaging',package)
        core=package/'Cores/pocketlab.CoverFlow/gbc.rbf_r'
        core.write_bytes(b'synthetic bitstream fixture')
        files=[{'path':p.relative_to(package).as_posix(),'bytes':p.stat().st_size,'sha256':lib.sha(p)}
               for p in sorted(package.rglob('*')) if p.is_file()]
        (package/'release-manifest.json').write_text(json.dumps({'version':'fixture','files':files}))
        plan=install.plan(self.card,package,self.out)
        self.assertTrue(plan['changes'][-1]['path'].endswith('/core.json'))
        raw=bytearray((self.card/style.ROOT_PACK).read_bytes());raw[540]^=1
        (self.card/style.ROOT_PACK).write_bytes(raw)
        with self.assertRaisesRegex(ValueError,'Menu changed'):
            install.plan(self.card,package,self.out)

    def test_corrupt_or_unsafe_pack_refused_before_staging(self):
        path=self.card/style.ROOT_PACK
        original=path.read_bytes()
        for raw in (original[:-1],original.replace(b'/Assets/gbclab/common/covers.bin',b'/Assets/gbclab/common/../bad.bin')):
            path.write_bytes(raw)
            with self.assertRaises(ValueError):style.style(self.card,self.out)
            self.assertFalse(self.out.exists())

    def test_repeat_style_and_output_on_card_refused(self):
        style.style(self.card,self.out)
        with self.assertRaises(ValueError):style.style(self.card,self.out)
        with self.assertRaises(ValueError):style.style(self.card,self.card/'new')

    def test_icon_machine_types_and_payload_size(self):
        self.assertEqual(kind('SNES 游戏库'),'snes')
        self.assertEqual(kind('GBC 游戏库'),'gbc')
        values=[]
        for name in ('gb','gbc','gba','nes','snes','fighting','rpg','back'):
            self.assertEqual(icon_image(name).getpixel((0,0)),(0,0,0))
            value=cover_bytes(name)
            self.assertEqual(len(value),45568)
            values.append(hashlib.sha256(value).hexdigest())
        self.assertEqual(len(set(values)),len(values))


if __name__=='__main__':unittest.main()
