# SPDX-License-Identifier: MIT
"""Synthetic integration checks for HEX compatibility and safe EEPROM staging."""
import hashlib,importlib.util,json,struct,tempfile,unittest
from pathlib import Path
s=importlib.util.spec_from_file_location('test_ard_library',Path(__file__).with_name('library.py'))
lib=importlib.util.module_from_spec(s);s.loader.exec_module(lib)
def record(address,data,kind=0):
    b=bytes([len(data),address>>8,address&255,kind])+data
    return ':'+(b+bytes([-sum(b)&255])).hex().upper()+'\n'
def program(n=0):return (record(0,bytes([n&255,0]))+record(256,b'\x12\x34')+record(0,b'',1)+'\n').encode()

class LibraryTest(unittest.TestCase):
    def test_rejects_native_parser_unsupported_and_corrupt_records(self):
        self.assertEqual(lib.hexfile.validate(program())['program_bytes'],4)
        invalid=[program()[:-4],program().replace(b':02000000',b':02000001'),
            (record(0,b'\0\0',4)+program().decode()).encode(),
            (record(0,b'\0\0')+record(0,b'\x12\x34')+record(0,b'',1)).encode(),
            (record(0,b'\0\0')+record(32767,b'\x12\x34')+record(0,b'',1)).encode()]
        for raw in invalid:
            with self.assertRaises(ValueError):lib.hexfile.validate(raw)

    def test_titles_existing_save_and_legacy_are_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source';roms=source/'Assets/arduboy/common/冒险';roms.mkdir(parents=True)
            first=roms/'中文.hex';first.write_bytes(program());second=roms/'新游戏.hex';second.write_bytes(program(2))
            digest=hashlib.sha256(program()).hexdigest();path=f'Saves/ardlab/common/{digest[:20]}.sav'
            saved=source/path;saved.parent.mkdir(parents=True);saved.write_bytes(bytes(range(256))*4)
            legacy=source/'Saves/arduboy/common/arduboy_eeprom.sav';legacy.parent.mkdir(parents=True);legacy.write_bytes(b'L'*1024)
            before={p.relative_to(source):p.read_bytes() for p in source.rglob('*') if p.is_file()}
            result=lib.build(source,root/'out')
            self.assertEqual((result['game_refs'],result['save_existing'],result['save_seeds']),(2,1,1))
            self.assertTrue(all(r['path'].startswith('Assets/') and r['save_bytes']==1024 and r['program_bytes']==4 for r in result['source_refs']))
            self.assertEqual(result['save_refs'][0]['path'],path)
            self.assertFalse((root/'out'/path).exists());self.assertEqual(before,{p.relative_to(source):p.read_bytes() for p in source.rglob('*') if p.is_file()})
            seed=[f for f in result['files'] if f['path'].startswith('Saves/')][0]
            self.assertEqual((root/'out'/seed['path']).read_bytes(),b'\xff'*1024)
            page=next((root/'out/Assets/ardlab/common/libs').glob('*.bin')).read_bytes()
            self.assertEqual(page[4:8],struct.pack('<I',2));self.assertIn('/Assets/arduboy/common/冒险/中文.hex'.encode(),page)
            self.assertIn(('/'+path).encode(),page)

    def test_pagination_and_invalid_image_exclusion(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source';roms=source/'Assets/arduboy/common';roms.mkdir(parents=True)
            for i in range(128):(roms/f'{i:03}.hex').write_bytes(program(i))
            (roms/'损坏.hex').write_bytes(b':oops')
            r=lib.build(source,root/'out')
            self.assertEqual((r['game_refs'],r['pages'],len(r['excluded'])),(128,3,1))
            for f in r['files']:
                if not f['path'].endswith('.bin'):continue
                raw=(root/'out'/f['path']).read_bytes();count=struct.unpack_from('<I',raw,8)[0]
                self.assertLessEqual(count,128);self.assertEqual(struct.unpack_from('<I',raw,64+(count-1)*1024+4)[0],1)
                self.assertEqual(hashlib.sha256(raw).hexdigest(),f['sha256'])

if __name__=='__main__':unittest.main()
