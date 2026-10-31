import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from import_saves import prepare


class SaveImport(unittest.TestCase):
    def test_copies_body_footer_and_preserves_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);card=root/'card';original=card/'Saves/gba/common/First.sav'
            original.parent.mkdir(parents=True);raw=bytes(range(256))*256+bytes(range(16));original.write_bytes(raw)
            save='Saves/gbalab/common/'+'a'*20+'.sav';rtc=save[:-3]+'rtc'
            lib=root/'library.json';lib.write_text(json.dumps({'roms':[{'path':'Assets/gba/common/First.gba','save_bytes':65536,'save':save,'rtc':rtc}]}))
            r=prepare(card,lib,root/'out')
            self.assertEqual(original.read_bytes(),raw)
            self.assertEqual((root/'out'/save).read_bytes(),raw[:65536])
            self.assertEqual((root/'out'/rtc).read_bytes(),raw[-16:])
            self.assertEqual((len(r['imports']),r['source_writes']),(1,0))

    def test_conflicting_progress_is_not_selected_or_truncated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);card=root/'card';base=card/'Saves/gba/common';base.mkdir(parents=True)
            (base/'First.sav').write_bytes(b'1'*32768);(base/'Second.sav').write_bytes(b'2'*32768)
            (base/'Large.sav').write_bytes(b'3'*131072)
            save='Saves/gbalab/common/'+'a'*20+'.sav'
            lib=root/'library.json';lib.write_text(json.dumps({'roms':[{'path':'Assets/gba/common/'+name+'.gba','save_bytes':65536,'save':save,'rtc':save[:-3]+'rtc'} for name in ('First','Second','Large')]}))
            r=prepare(card,lib,root/'out')
            self.assertEqual(r['files'],[]);self.assertEqual(len(r['skipped']),2)
            r=prepare(card,lib,root/'preferred',['Saves/gba/common/First.sav'])
            self.assertEqual((root/'preferred'/save).read_bytes(),b'1'*32768+b'\xff'*32768)
            self.assertTrue(r['imports'][0]['explicit_preference'])
            self.assertEqual((base/'Second.sav').read_bytes(),b'2'*32768)


if __name__=='__main__':unittest.main()
