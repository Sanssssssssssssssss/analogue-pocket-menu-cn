import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from apf_metadata import check_core


class CoreIdentity(unittest.TestCase):
    def test_rejects_the_installed_gba_identity_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)/'pocketlab.GBA';folder.mkdir()
            (folder/'gba.rbf_r').write_bytes(b'synthetic')
            meta=dict(shortname='GBA Menu CN',author='PocketLab + mincer_ray',
                      description='Experiment',url='https://example.com',version='0.2.0',date_release='2026-10-31')
            core={'core':{'metadata':meta,'cores':[{'filename':'gba.rbf_r'}]}}
            path=folder/'core.json';path.write_text(json.dumps(core))
            with self.assertRaisesRegex(ValueError,'identity mismatch'):check_core(folder)
            meta.update(author='pocketlab',shortname='GBA')
            path.write_text(json.dumps(core));check_core(folder)


if __name__=='__main__':unittest.main()
