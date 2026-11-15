import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import apf_metadata
from apf_metadata import REQUIRED_JSON,check_core,check_candidate_bitstream


class CoreIdentity(unittest.TestCase):
    def definitions(self,folder):
        for filename in REQUIRED_JSON[1:]:
            value={'magic':'APF_VER_1'}
            if filename=='variants.json':value['variant_list']=[]
            (folder/filename).write_text(json.dumps({Path(filename).stem:value}))

    def fixture(self,root):
        folder=root/'pocketlab.GBA';folder.mkdir();self.definitions(folder)
        (folder/'gba.rbf_r').write_bytes(b'synthetic')
        metadata=dict(shortname='GBA',author='pocketlab',description='Synthetic metadata fixture',
                      url='https://example.com',version='test',date_release='2026-11-03')
        (folder/'core.json').write_text(json.dumps({'core':{'magic':'APF_VER_1','metadata':metadata,'cores':[{'filename':'gba.rbf_r'}]}}))
        return folder

    def test_rejects_the_installed_gba_identity_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)/'pocketlab.GBA';folder.mkdir()
            (folder/'gba.rbf_r').write_bytes(b'synthetic')
            meta=dict(shortname='GBA Menu CN',author='PocketLab + mincer_ray',
                      description='Experiment',url='https://example.com',version='0.2.0',date_release='2026-10-31')
            self.definitions(folder)
            core={'core':{'magic':'APF_VER_1','metadata':meta,'cores':[{'filename':'gba.rbf_r'}]}}
            path=folder/'core.json';path.write_text(json.dumps(core))
            with self.assertRaisesRegex(ValueError,'identity mismatch'):check_core(folder)
            meta.update(author='pocketlab',shortname='GBA')
            path.write_text(json.dumps(core));check_core(folder)

    def test_each_required_definition_missing_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=self.fixture(Path(temp));check_core(folder)
            for filename in REQUIRED_JSON[1:]:
                path=folder/filename;raw=path.read_bytes();path.unlink()
                with self.subTest(file=filename),self.assertRaisesRegex(ValueError,'required APF definition'):
                    check_core(folder)
                path.write_bytes(raw)

    def test_invalid_variants_are_rejected_even_with_valid_core_and_bitstream(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=self.fixture(Path(temp));path=folder/'variants.json'
            for value in ({},{'magic':'wrong','variant_list':[]},{'magic':'APF_VER_1'}, {'magic':'APF_VER_1','variant_list':{}}):
                path.write_text(json.dumps({'variants':value}))
                with self.subTest(value=value),self.assertRaisesRegex(ValueError,'variants.json'):check_core(folder)

    def test_device_rejected_bitstream_cannot_be_a_new_candidate(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=self.fixture(Path(temp));path=folder/'gba.rbf_r';digest=check_candidate_bitstream(path)
            with patch.dict(apf_metadata.REJECTED_CANDIDATES,{digest:'synthetic device boot failure'}):
                check_core(folder)  # Existing rejected cores can still be inspected for recovery.
                with self.assertRaisesRegex(ValueError,'Device-rejected'):check_candidate_bitstream(path)


if __name__=='__main__':unittest.main()
