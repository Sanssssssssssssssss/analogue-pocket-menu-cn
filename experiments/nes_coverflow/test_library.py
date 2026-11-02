# SPDX-License-Identifier: MIT
import hashlib,json,struct,tempfile,unittest
from pathlib import Path
from library import build,ASSETS,SAVES,pack,folder


def rom(value):
    raw=bytearray(16400);raw[:4]=b'NES\x1a';raw[4]=1;raw[16:]=bytes([value])*16384;return raw


def snapshot(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}


class Library(unittest.TestCase):
    def test_whole_library_graph_shared_progress_and_read_only_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);card=root/'card';card.mkdir();(card/'Analogue_Pocket.json').write_text('{"product":"Analogue Pocket"}')
            for rel,value in [('0.FAVORITES/01.Zelda/first.nes',1),('RPG/copy.nes',1),('格斗/second.nes',2),('格斗/duplicate.nes',2)]:
                p=card/'Assets/nes/common'/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(rom(value))
            tag=hashlib.sha256(rom(1)).hexdigest()[:20]
            progress=card/SAVES/(tag+'.sav');progress.parent.mkdir(parents=True);progress.write_bytes(b'P'*262144)
            before=snapshot(card);out=root/'stage';r=build(card,out)
            self.assertEqual(snapshot(card),before)
            self.assertEqual(r['unique_games'],2)
            self.assertEqual(r['source_writes'],0)
            self.assertFalse((out/progress.relative_to(card)).exists())
            pages={p['path'] for p in r['files'] if p['path'].endswith('.bin')}
            self.assertGreater(len(pages),2)
            rom_rows=[]
            for rel in pages:
                raw=(out/rel).read_bytes();magic,ver,n,base,pause,stride=struct.unpack_from('<4s5I',raw)
                self.assertEqual((magic,ver,stride),(b'GBAF',2,65536));self.assertEqual(len(raw),pause+153600)
                for i in range(n):
                    row=raw[64+i*1024:64+(i+1)*1024]
                    path=row[32:288].split(b'\0',1)[0].decode()
                    if int.from_bytes(row[4:8],'little'):
                        self.assertIn(path.lstrip('/'),pages)
                    else:
                        self.assertTrue((card/path.lstrip('/')).is_file());rom_rows.append(row)
            first=[r[288:544] for r in rom_rows if b'first.nes' in r or b'copy.nes' in r]
            self.assertEqual(len(first),2);self.assertEqual(first[0],first[1])
            self.assertEqual(len(rom_rows),3)

    def test_rom_fields_are_not_reused_for_unicode_widths(self):
        entry=folder('/'+ASSETS+'/menu.bin','测试')
        entry.update(rom_offset=512,rom_config=7)
        raw,_,_=pack([entry]);row=raw[64:1088]
        self.assertEqual(struct.unpack_from('<II',row,16),(512,7))
        self.assertGreater(int.from_bytes(row[24:28],'little'),0)

    def test_foreign_namespace_and_bad_existing_progress_rejected(self):
        with self.assertRaises(ValueError):pack([folder('/Assets/gba/common/a.gba','错误')])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);card=root/'card';p=card/'Assets/nes/common/a.nes';p.parent.mkdir(parents=True);p.write_bytes(rom(1))
            (card/'Analogue_Pocket.json').write_text('{"product":"Analogue Pocket"}')
            tag=hashlib.sha256(rom(1)).hexdigest()[:20];save=card/SAVES/(tag+'.sav');save.parent.mkdir(parents=True);save.write_bytes(b'progress')
            before=snapshot(card)
            with self.assertRaises(ValueError):build(card,root/'stage')
            self.assertEqual(before,snapshot(card))

    def test_offline_archive_needs_explicit_flag_and_stays_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);card=root/'archive';p=card/'Assets/nes/common/game.nes';p.parent.mkdir(parents=True);p.write_bytes(rom(1));before=snapshot(card)
            with self.assertRaises(FileNotFoundError):build(card,root/'denied')
            result=build(card,root/'stage',offline_source=True)
            self.assertEqual(before,snapshot(card));self.assertIn('final card',result['identity']['scope'])


if __name__=='__main__':unittest.main()
