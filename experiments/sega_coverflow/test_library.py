# SPDX-License-Identifier: MIT
import copy,hashlib,json,struct,tempfile,unittest,zlib
from pathlib import Path
import library


def profile(raw):
    return {'sha256':hashlib.sha256(raw).hexdigest(),'sha1':hashlib.sha1(raw).hexdigest(),
        'crc32':f'{zlib.crc32(raw)&0xffffffff:08x}','bytes':len(raw),
        'source':{'url':'https://example.org/synthetic-fixture','commit':'1'*40,'license':'CC0-1.0'},
        'effects':[{'title':'测试辅助','codes':[{'type':'par','address':0xc123,'value':0x7f}]}]}


def snapshot(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}


class Library(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.card=self.root/'card';self.card.mkdir()
        (self.card/'Analogue_Pocket.json').write_text('{"product":"Analogue Pocket"}')
        self.raw=b'\x11'*32768;self.tag=hashlib.sha256(self.raw).hexdigest()[:20]
        for rel,raw in [('0.FAVORITES/first.gg',self.raw),('RPG/copy.gg',self.raw),('ACT/second.gg',b'\x22'*32768)]:
            p=self.card/'Assets/gg/common'/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        save=self.card/'Saves/ggclab/common'/(self.tag+'.sav');save.parent.mkdir(parents=True);save.write_bytes(b'P'*32768)
        self.index=self.root/'profiles.json';self.row=profile(self.raw);self.write_index()

    def tearDown(self):self.tmp.cleanup()

    def write_index(self):self.index.write_text(json.dumps({'format':'SEGA-CHEATS1','profiles':[self.row]}))

    def test_whole_library_identity_graph_and_existing_progress_preserved(self):
        before=snapshot(self.card);out=self.root/'stage';r=library.build(self.card,out,'gg',cheats=self.index)
        self.assertEqual(before,snapshot(self.card));self.assertEqual(r['unique_games'],2);self.assertEqual(len(r['cheats']),1)
        self.assertFalse((out/'Saves/ggclab/common'/(self.tag+'.sav')).exists())
        seed=next((out/'Saves/ggclab/common').glob('*.sav'));self.assertEqual(seed.read_bytes(),b'\xff'*32768)
        pages={p['path'] for p in r['files'] if p['path'].endswith('.bin')};matched=0;unmatched=0
        for rel in pages:
            raw=(out/rel).read_bytes();magic,version,count,base,pause,stride=struct.unpack_from('<4s5I',raw)
            self.assertEqual((magic,version,stride),(b'GBAF',2,65536));self.assertEqual(len(raw),pause+153600)
            for i in range(count):
                row=raw[64+i*1024:64+(i+1)*1024]
                rom=row[32:288].split(b'\0',1)[0].decode();cht=row[544:800].split(b'\0',1)[0].decode()
                if row[4]:self.assertIn(rom.lstrip('/'),pages)
                else:
                    size=int.from_bytes(row[16:20],'little')
                    if 'second' in rom:
                        unmatched+=1;self.assertEqual(size,0);self.assertFalse((out/cht.lstrip('/')).exists())
                    else:
                        matched+=1;self.assertGreater(size,0);self.assertEqual((out/cht.lstrip('/')).stat().st_size,size)
        self.assertEqual((matched,unmatched),(2,1))

    def test_every_identity_field_must_match_before_staging(self):
        before=snapshot(self.card)
        for field,bad in [('sha1','0'*40),('crc32','00000000'),('bytes',32764)]:
            with self.subTest(field=field):
                self.row=profile(self.raw);self.row[field]=bad;self.write_index();out=self.root/field
                with self.assertRaises(ValueError):library.build(self.card,out,'gg',cheats=self.index)
                self.assertFalse(out.exists());self.assertEqual(before,snapshot(self.card))

    def test_conflicting_ram_or_unsupported_effects_rejected(self):
        row=profile(self.raw)
        row['effects'].append({'title':'冲突辅助','codes':[{'type':'par','address':0xc123,'value':1}]})
        with self.assertRaises(ValueError):library.cheat_payload(row,self.raw)
        for address in [0xbfff,0xe000]:
            row=profile(self.raw);row['effects'][0]['codes'][0]['address']=address
            with self.assertRaises(ValueError):library.cheat_payload(row,self.raw)
        for path in ['/Assets/gba/common/x.gba','/Saves/ggclab/common/../x.sav']:
            with self.assertRaises(ValueError):library.path_field(path,'gg')

    def test_offline_backup_without_card_marker_is_read_only(self):
        (self.card/'Analogue_Pocket.json').unlink();before=snapshot(self.card)
        with self.assertRaises(FileNotFoundError):library.build(self.card,self.root/'denied','gg')
        result=library.build(self.card,self.root/'offline','gg',offline_source=True)
        self.assertEqual(snapshot(self.card),before);self.assertEqual(result['source_writes'],0)
        self.assertIn('final card',result['identity']['scope'])

    def test_imported_codes_keep_native_ram_and_rom_mechanisms(self):
        from import_profiles import decode
        self.assertEqual(decode('00C1-237F + 058-BA8-E66'),[{'type':'par','address':0xc123,'value':127},{'type':'game_genie','code':'058-BA8-E66'}])
        for code in ('00E0-0001','00C123-7F','ZZZ-ZZZ','000-000'):
            with self.assertRaises(ValueError):decode(code)


if __name__=='__main__':unittest.main()
