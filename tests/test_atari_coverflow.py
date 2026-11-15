import hashlib
import importlib.util
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'experiments/atari_coverflow'))
spec = importlib.util.spec_from_file_location('atari_test_library', ROOT/'experiments/atari_coverflow/library.py')
library = importlib.util.module_from_spec(spec)
spec.loader.exec_module(library)


class AtariLibraryTests(unittest.TestCase):
    def test_chinese_subfolders_reference_rom_and_preserve_shared_saves(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            card, out = base/'source', base/'stage'
            rom = card/'Assets/2600/common/动作/测试.a26'
            rom.parent.mkdir(parents=True)
            rom.write_bytes(bytes(range(256))*16)
            save = card/'Saves/2600/common/savekey.sav'
            save.parent.mkdir(parents=True)
            save.write_bytes(bytes(range(256))*128)
            before = hashlib.sha256(save.read_bytes()).hexdigest()
            report = library.build('2600', card, out)
            self.assertEqual((report['pages'], report['game_refs'], report['rom_copies']), (2, 1, 0))
            self.assertFalse((out/'Saves').exists())
            self.assertEqual(hashlib.sha256(save.read_bytes()).hexdigest(), before)
            records = [f for f in report['files'] if '/libs/' in f['path']]
            raw = (out/records[0]['path']).read_bytes()
            self.assertEqual(struct.unpack_from('<4s5I', raw), (b'GBAF', 2, 2, 2112, 133184, 65536))
            record = raw[64:1088]
            self.assertEqual(record[32:288].split(b'\0')[0].decode(), '/Assets/2600/common/动作/测试.a26')
            self.assertEqual(struct.unpack_from('<I', record, 12)[0], 0)
            self.assertGreater(struct.unpack_from('<I', record, 16)[0], 0)
            self.assertEqual(raw[1088+32:1088+288].split(b'\0')[0], b'/Assets/atclab/common/menu.bin')

    def test_rejects_foreign_and_overlong_apf_paths(self):
        for value in ('/Assets/gba/common/test.gba', '/Assets/2600/common/../save.bin', '/Assets/2600/common/C:test.bin',
                      '/Assets/2600/common/'+'中'*90+'.a26'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                library.path_bytes(value, '2600')

    def test_validates_a78_length_before_install(self):
        with tempfile.TemporaryDirectory() as directory:
            rom = Path(directory)/'fixture.a78'
            header = bytearray(128)
            header[1:10] = b'ATARI7800'
            header[49:53] = (4096).to_bytes(4, 'big')
            header[100:128] = b'ACTUAL CART DATA STARTS HERE'
            rom.write_bytes(header+bytes(4096))
            self.assertEqual(library.cartridge('7800', rom), 4224)
            rom.write_bytes(header+bytes(4092))
            with self.assertRaisesRegex(ValueError, 'payload length'):
                library.cartridge('7800', rom)


if __name__ == '__main__':
    unittest.main()
