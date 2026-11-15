import json
from pathlib import Path
import struct
import tempfile
import unittest

import library


def rom(flash=False):
    raw=bytearray(32768)
    raw[0xA0:0xAC]=b'LAB FIXTURE '
    raw[0xAC:0xB0]=b'TEST'
    raw[0xB2]=0x96
    raw[0xBD]=(-sum(raw[0xA0:0xBD])-0x19)&255
    if flash:raw[0x100:0x109]=b'FLASH1M_V'
    return raw


class Library(unittest.TestCase):
    def test_graph_records_and_source_preservation(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);card=root/'card';base=card/'Assets/gba/common'
            (base/'3.FTG').mkdir(parents=True)
            (base/'First.gba').write_bytes(rom())
            (base/'3.FTG/Second.gba').write_bytes(rom(True))
            save=card/'Saves/gba/common/First.sav';save.parent.mkdir(parents=True);save.write_bytes(b'latest progress')
            before={p.relative_to(card).as_posix():library.gb.sha(p) for p in card.rglob('*') if p.is_file()}
            out=root/'out';r=library.build(card,out)
            self.assertEqual(before,{p.relative_to(card).as_posix():library.gb.sha(p) for p in card.rglob('*') if p.is_file()})
            self.assertEqual(r['save_writes'],0);self.assertEqual(r['rom_copies'],0)
            todo=[library.ASSETS+'/menu.bin'];seen=set();games=set()
            while todo:
                rel=todo.pop()
                if rel in seen:continue
                seen.add(rel);raw=(out/rel).read_bytes()
                magic,version,count,frames,pause,unused=struct.unpack_from('<4s5I',raw)
                self.assertEqual((magic,version,frames,pause,unused),(b'GBAF',1,64+count*1024,64+count*(1024+76800),0))
                self.assertEqual(len(raw),pause+2*76800)
                for i in range(count):
                    record=raw[64+i*1024:64+(i+1)*1024]
                    kind,flags,size,_=struct.unpack_from('<4s3I',record)
                    self.assertEqual(kind,b'ENT1')
                    paths=[record[32+j*256:32+(j+1)*256].split(b'\0')[0].decode() for j in range(3)]
                    if flags&1:todo.append(paths[0].lstrip('/'))
                    else:
                        self.assertTrue((card/paths[0].lstrip('/')).is_file());games.add(paths[0])
                        self.assertTrue(paths[1].startswith('/Saves/gbalab/common/'))
                        self.assertEqual(len(paths[1]),45);self.assertEqual(len(paths[2]),45)
                        self.assertEqual(size,32768)
                    if i==count-1:self.assertEqual(flags&1,1)
            self.assertEqual(len(games),2);self.assertEqual(len(seen),len(r['files']))

    def test_bad_header_and_output_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);card=root/'card';base=card/'Assets/gba/common';base.mkdir(parents=True)
            data=rom();data[0xBD]^=1;(base/'Bad.gba').write_bytes(data)
            for out in (card/'new',root/'out'):
                with self.assertRaises(ValueError):library.build(card,out)
                self.assertFalse(out.exists())

    def test_forbidden_apf_paths(self):
        for path in ('/Assets/gba/common/../x','/Saves/gba/common/progress.sav',
                     '/Assets/gb/common/a.gb','/Assets/gba/common/'+'中'*90+'.gba'):
            with self.assertRaises(ValueError):library.path_field(path)

    def test_explicit_exclusion_preserves_file_and_records_reason(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);card=root/'card';base=card/'Assets/gba/common';base.mkdir(parents=True)
            (base/'First.gba').write_bytes(rom());bad=base/'Truncated.gba';bad.write_bytes(rom()[:-1])
            before=bad.read_bytes();r=library.build(card,root/'out',skip_invalid=True)
            self.assertEqual(len(r['roms']),1);self.assertEqual(r['skipped'][0]['path'],'Assets/gba/common/Truncated.gba')
            self.assertEqual(bad.read_bytes(),before)


if __name__=='__main__':unittest.main()
