import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import platform_frontend as frontend


class PlatformFrontend(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.card=self.root/'card';self.card.mkdir()
        (self.card/'Analogue_Pocket.json').write_text('{"product":"Analogue Pocket"}')
        for rel in frontend.GUARDS:
            path=self.card/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'synthetic core guard')
        for key in frontend.PLATFORMS:
            path=self.card/f'Platforms/{key}.json';path.parent.mkdir(exist_ok=True)
            path.write_text(json.dumps({'platform':{'name':'Before '+key,'category':'Handheld','manufacturer':'Example','year':2026}}))
            path=self.card/f'Platforms/_images/{key}.bin';path.parent.mkdir(exist_ok=True)
            path.write_bytes(b'original platform graphic')
        self.save=self.card/'Saves/gba/common/MinishCap.sav';self.save.parent.mkdir(parents=True)
        self.save.write_bytes(b'synthetic current progress')
        self.package=self.root/'package';self.backup=self.root/'backup'
        frontend.stage(self.card,self.package)

    def tearDown(self):self.temp.cleanup()

    def hashes(self):return {p.relative_to(self.card).as_posix():frontend.lib.sha(p) for p in self.card.rglob('*') if p.is_file()}

    def test_format_known_asymmetric_pixel_offsets(self):
        image=Image.new('L',(521,165),0)
        image.putpixel((0,0),255);image.putpixel((520,164),17)
        raw=frontend.encode(image)
        self.assertEqual(raw[520*165*2:520*165*2+2],b'\xff\0')
        self.assertEqual(raw[164*2:164*2+2],b'\x11\0')
        self.assertEqual(len(raw),171930)
        self.assertFalse(any(raw[1::2]))

    def test_install_rollback_preserve_core_and_latest_save(self):
        before=self.hashes();frontend.plan(self.card,self.package);self.assertEqual(before,self.hashes())
        result=frontend.apply(self.card,self.package,self.backup)
        after=self.hashes();changed={n for n in before if before[n]!=after[n]}
        self.assertEqual(changed,frontend.ALLOWED)
        self.assertEqual(result['status'],'installed_sha256_verified')
        self.assertEqual((self.backup/'protected'/self.save.relative_to(self.card)).read_bytes(),b'synthetic current progress')
        self.save.write_bytes(b'new progress after installation')
        frontend.rollback(self.card,self.backup,True)
        self.assertEqual(self.save.read_bytes(),b'new progress after installation')
        for rel in frontend.ALLOWED:self.assertEqual(frontend.lib.sha(self.card/rel),before[rel])

    def test_interrupted_install_can_restore_first_replacement(self):
        before=self.hashes();publish=frontend.publish;calls=0
        def interrupted(*args):
            nonlocal calls
            calls+=1
            if calls==2:raise OSError('synthetic disconnect')
            return publish(*args)
        with patch.object(frontend,'publish',side_effect=interrupted):
            with self.assertRaises(OSError):frontend.apply(self.card,self.package,self.backup)
        self.assertTrue((self.backup/'journal.jsonl').is_file())
        frontend.rollback(self.card,self.backup,True)
        self.assertEqual(before,self.hashes())

    def test_tampered_save_destination_rejected_before_writes(self):
        path=self.package/'platform-manifest.json';data=json.loads(path.read_text())
        data['files'][0]['path']='Saves/gba/common/MinishCap.sav'
        path.write_text(json.dumps(data));before=self.hashes()
        with self.assertRaises(ValueError):frontend.apply(self.card,self.package,self.backup)
        self.assertEqual(before,self.hashes());self.assertFalse(self.backup.exists())

    def test_changed_core_or_rollback_target_refused(self):
        core=self.card/'Cores/pocketlab.GBA/gba.rbf_r';previous=core.read_bytes();core.write_bytes(b'changed core')
        before=self.hashes()
        with self.assertRaises(ValueError):frontend.apply(self.card,self.package,self.backup)
        self.assertEqual(before,self.hashes());core.write_bytes(previous)
        frontend.apply(self.card,self.package,self.backup)
        target=self.card/'Platforms/gbalab.json';target.write_text('user changed display metadata')
        before=self.hashes()
        with self.assertRaises(ValueError):frontend.rollback(self.card,self.backup,True)
        self.assertEqual(before,self.hashes())
