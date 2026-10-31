import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('gba_install',Path(__file__).with_name('install.py'))
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)


class InstallSafety(unittest.TestCase):
    def test_allowlist_excludes_existing_games_progress_and_firmware(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for rel in ('Cores/mincer_ray.GBA/core.json','Assets/gba/common/game.gba',
                        'Saves/gba/common/game.sav','pocket_firmware.bin','../Cores/pocketlab.GBA/core.json',
                        'Assets/gbalab/common/../escape.bin','Saves/gbalab/common/arbitrary.sav'):
                with self.assertRaises(ValueError):installer.allowed(root,rel)
            self.assertEqual(installer.allowed(root,'Cores/pocketlab.GBA/core.json'),root/'Cores/pocketlab.GBA/core.json')

    def test_rollback_preserves_played_progress_and_refuses_changed_core(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);card=root/'card';card.mkdir()
            (card/'Analogue_Pocket.json').write_text(json.dumps({'product':'Analogue Pocket'}))
            backup=root/'backup';backup.mkdir()
            changes=[]
            for rel in ('Cores/pocketlab.GBA/core.json','Assets/gbalab/common/menu.bin','Saves/gbalab/common/'+'a'*20+'.sav'):
                p=installer.allowed(card,rel);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'original')
                changes.append({'path':rel,'sha256':installer.sha(p)})
            receipt={'identity':installer.identity(card),'changes':changes}
            (backup/'install-receipt.json').write_text(json.dumps(receipt))
            save=card/changes[-1]['path'];save.write_bytes(b'new gameplay')
            core=card/changes[0]['path'];core.write_bytes(b'different core')
            with self.assertRaises(ValueError):installer.rollback(card,backup,True)
            self.assertTrue((card/changes[1]['path']).exists())
            core.write_bytes(b'original');r=installer.rollback(card,backup,True)
            self.assertEqual(r['removed_files'],2);self.assertEqual(save.read_bytes(),b'new gameplay')


if __name__=='__main__':unittest.main()
