# SPDX-License-Identifier: MIT
import hashlib,json,struct,tempfile,unittest
from pathlib import Path
import library

def rom(value=0):
    data=bytearray(16+16384);data[:4]=b'NES\x1a';data[4]=1;data[16:]=bytes([value])*16384
    return bytes(data)

class Library(unittest.TestCase):
    def card(self,root):
        p=root/'card';p.mkdir();(p/'Analogue_Pocket.json').write_text('{"product":"Analogue Pocket"}')
        base=p/'Assets/nes/common/0.FAVORITES/01.Zelda';base.mkdir(parents=True)
        (base/'first.nes').write_bytes(rom());return p,base

    def test_graph_records_seeded_saves_and_originals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);card,base=self.card(root)
            (base/'copy.nes').write_bytes(rom())
            alt=base/'90.Variants';alt.mkdir();(alt/'second.nes').write_bytes(rom(1))
            before={p.relative_to(card).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in card.rglob('*') if p.is_file()}
            out=root/'stage';r=library.build(card,out)
            self.assertEqual((r['unique_games'],r['pages']),(1,2))
            for row in r['files']:
                data=(out/row['path']).read_bytes()
                if row['path'].endswith('.sav'):
                    self.assertEqual(len(data),262144);self.assertFalse(any(data));continue
                magic,version,count,base,pause,_=struct.unpack_from('<4s5I',data)
                self.assertEqual((magic,version),(b'GBAF',1));self.assertEqual(len(data),pause+2*76800)
                self.assertEqual(base,64+1024*count)
                self.assertEqual(int.from_bytes(data[64+(count-1)*1024+4:64+(count-1)*1024+8],'little'),1)
            after={p.relative_to(card).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in card.rglob('*') if p.is_file()}
            self.assertEqual(before,after)

    def test_existing_progress_is_not_staged_or_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);card,_=self.card(root);tag=hashlib.sha256(rom()).hexdigest()[:20]
            save=card/library.SAVES/(tag+'.sav');save.parent.mkdir(parents=True);save.write_bytes(b'Z'*262144)
            r=library.build(card,root/'stage')
            self.assertFalse(any(x['path'].endswith('.sav') for x in r['files']))
            self.assertEqual(save.read_bytes(),b'Z'*262144)
            save.write_bytes(b'latest progress')
            with self.assertRaises(ValueError):library.build(card,root/'bad-stage')
            self.assertEqual(save.read_bytes(),b'latest progress')

    def test_foreign_platform_and_escape_paths_rejected(self):
        for path in ['/Assets/gba/common/a.gba','/Saves/gbclab/common/a.sav','/Assets/nes/common/../../x','/Assets/nes/common/x:y']:
            with self.subTest(path=path),self.assertRaises(ValueError):library.path_bytes(path)

if __name__=='__main__':unittest.main()
