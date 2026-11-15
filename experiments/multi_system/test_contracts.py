# SPDX-License-Identifier: MIT
import unittest
from fixtures import gba, nes, snes
from launch_plan import inspect_rom, make_plan


class Contracts(unittest.TestCase):
    def test_gba_header_and_rtc_separation(self):
        p = make_plan('gba', gba())
        self.assertEqual(p['rom']['slot'], 1)
        self.assertIn('SRAM_V113', p['rom']['save_markers'])
        self.assertTrue(p['experimental_rtc'].endswith('.rtc'))
        self.assertNotEqual(p['experimental_save'], p['experimental_rtc'])

    def test_gba_bad_checksum_rejected(self):
        data = gba(); data[0xA0] ^= 1
        with self.assertRaisesRegex(ValueError, 'checksum'): inspect_rom('gba', data)

    def test_gba_truncated_header_rejected(self):
        with self.assertRaises(ValueError): inspect_rom('gba', bytes(128))

    def test_gba_bad_magic_rejected(self):
        data = gba(); data[0xB2] = 0
        with self.assertRaises(ValueError): inspect_rom('gba', data)

    def test_nes_trainer_preserved_in_transfer(self):
        data = nes(trainer=True); p = inspect_rom('nes', data)
        self.assertEqual(p['trainer_bytes'], 512)
        self.assertEqual(p['file_offset'], 0)
        self.assertEqual(p['transfer_bytes'], len(data))

    def test_nes2_mapper_bits(self):
        data = nes(nes2=True); data[6] = 0x10; data[7] |= 0x20; data[8] = 3
        self.assertEqual(inspect_rom('nes', data)['mapper'], 0x321)

    def test_nes_truncation_rejected(self):
        with self.assertRaises(ValueError): inspect_rom('nes', nes()[:-1])

    def test_nes_declared_size_rejected(self):
        data = nes(); data[4] = 2
        with self.assertRaises(ValueError): inspect_rom('nes', data)

    def test_nes_exponent_size_is_not_guessed(self):
        data = nes(nes2=True); data[9] = 15
        with self.assertRaisesRegex(ValueError, 'separate adapter'): inspect_rom('nes', data)

    def test_nes_unknown_container_rejected(self):
        data = nes(); data[:4] = b'UNIF'
        with self.assertRaises(ValueError): inspect_rom('nes', data)

    def test_snes_copier_header_removed_once(self):
        data = snes(copier=True); p = inspect_rom('snes', data)
        self.assertEqual(p['file_offset'], 512)
        self.assertEqual(p['transfer_bytes'], len(data)-512)

    def test_snes_all_header_locations(self):
        for kind, name in [('lorom','LoROM'), ('hirom','HiROM'), ('exhirom','ExHiROM')]:
            with self.subTest(kind=kind):
                self.assertEqual(inspect_rom('snes', snes(kind))['header_candidates'][0]['location'], name)

    def test_snes_loader_cannot_be_bypassed(self):
        for data in (snes(), snes(pal=True), snes(chip=0x43), snes(chip=0xF9)):
            self.assertEqual(make_plan('snes', data)['launch_route'], 'upstream-chip32-required')

    def test_snes_bad_checksum_pair_rejected(self):
        data = snes(); data[0x7FDE] ^= 1
        with self.assertRaises(ValueError): inspect_rom('snes', data)

    def test_snes_bad_length_rejected(self):
        with self.assertRaises(ValueError): inspect_rom('snes', snes()[:-1])

    def test_each_platform_save_namespace_is_isolated(self):
        plans = [make_plan(p, f()) for p, f in [('gba',gba),('nes',nes),('snes',snes)]]
        for p in plans:
            self.assertTrue(p['experimental_save'].startswith('Saves/cn'+p['platform']+'/'))
            self.assertFalse(p['deployable']); self.assertEqual(p['file_writes'], 0)

    def test_titles_do_not_determine_save_identity(self):
        a = make_plan('gba', gba(), '原名'); b = make_plan('gba', gba(), '中文显示名')
        self.assertEqual(a['experimental_save'], b['experimental_save'])

    def test_different_roms_have_different_save_identity(self):
        a = gba(); b = gba(); b[500] = 1
        self.assertNotEqual(make_plan('gba', a)['experimental_save'], make_plan('gba', b)['experimental_save'])


if __name__ == '__main__': unittest.main()
