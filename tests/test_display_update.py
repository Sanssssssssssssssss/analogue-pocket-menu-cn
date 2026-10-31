import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import build_library as lib
import update_display as display
from style_library import decode,ROOT_PACK


class DisplayUpdate(unittest.TestCase):
    def test_titles_art_and_sort_keep_game_save_and_folder_identities(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);card=root/'card';card.mkdir()
            (card/'Analogue_Pocket.json').write_text('{"product":"Analogue Pocket"}')
            roms=card/'Assets/gb/common/1.ACT';roms.mkdir(parents=True)
            for name in ['Alpha','Zulu']:(roms/(name+'.gb')).write_bytes(bytes(32768))
            bios=root/'bios.bin';bios.write_bytes(bytes(2304))
            lib.build(card,root/'base',bios=bios)
            shutil.copytree(root/'base/Assets',card/'Assets',dirs_exist_ok=True)
            save=card/'Saves/gbclab/common/protected.sav';save.parent.mkdir(parents=True);save.write_bytes(b'important progress')
            before={p.relative_to(card).as_posix():lib.sha(p) for p in card.rglob('*') if p.is_file()}
            mapping={'/Assets/gb/common/1.ACT/'+n+'.gb':{'title':title,'fallback':True} for n,title in [('Alpha','中文甲'),('Zulu','中文乙')]}
            result=display.stage(card,root/'out',mapping)
            self.assertEqual(before,{p.relative_to(card).as_posix():lib.sha(p) for p in card.rglob('*') if p.is_file()})
            self.assertEqual(result['unique_games'],2);self.assertEqual(result['updated_games'],2)
            for source in result['source_packs']:
                rel=source['path'];old=decode((card/rel).read_bytes());target=root/'out'/rel
                new=decode((target if target.exists() else card/rel).read_bytes())
                self.assertEqual(old['tail'],new['tail'])
                original={tuple(e['paths']):e for e in old['entries']}
                self.assertEqual(set(original),{tuple(e['paths']) for e in new['entries']})
                for e in new['entries']:
                    a=original[tuple(e['paths'])]
                    if e['record'][40]&128:self.assertEqual(a,e)
                    else:
                        self.assertEqual(a['record'][40:52],e['record'][40:52])
                        self.assertEqual(a['record'][54:],e['record'][54:])
                        self.assertNotEqual(a['blob'][:45568],e['blob'][:45568])

    def test_rejects_undeclared_platform_before_reading_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);card=root/'card';card.mkdir()
            (card/'Analogue_Pocket.json').write_text('{"product":"Analogue Pocket"}')
            with self.assertRaisesRegex(ValueError,'Unexpected game path'):
                display.stage(card,root/'out',{'/Assets/gba/common/test.gba':{'title':'拒绝'}})


if __name__=='__main__':unittest.main()
