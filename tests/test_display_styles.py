# SPDX-License-Identifier: MIT
import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from display_styles import configure,MODES


class DisplayStyles(unittest.TestCase):
    def test_styles_retain_native_and_ui_scaler_bindings_without_selecting_filter(self):
        source={'video':{'magic':'APF_VER_1','scaler_modes':[{'width':240,'height':160,'aspect_w':3,'aspect_h':2},{'width':320,'height':288,'aspect_w':10,'aspect_h':9}],'display_modes':[{'id':'0x20'}]}}
        before=copy.deepcopy(source)
        for platform in MODES:
            result=configure(source,platform)['video']
            self.assertEqual(result['scaler_modes'],source['video']['scaler_modes'])
            self.assertEqual(result['defaults'],{'sharpness':3})
            self.assertTrue(all(int(m['id'],16) not in [0,0x20,0x21,0x22,0x23] for m in result['display_modes']))
        self.assertEqual(source,before)
        self.assertIn('0x30',MODES['gbc']);self.assertIn('0x51',MODES['gg'])


if __name__=='__main__':unittest.main()
