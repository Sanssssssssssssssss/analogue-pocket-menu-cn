# SPDX-License-Identifier: MIT
import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from install import identity


class CardIdentity(unittest.TestCase):
    def test_equivalent_root_paths_use_one_canonical_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);card=root/'card';card.mkdir();child=root/'alias';child.mkdir()
            (card/'Analogue_Pocket.json').write_text(json.dumps({'product':'Analogue Pocket'}))
            actual=identity(card);alias=identity(child/'..'/'card')
            self.assertEqual(actual,alias);self.assertEqual(actual['root'],str(card.resolve()))


if __name__=='__main__':unittest.main()
