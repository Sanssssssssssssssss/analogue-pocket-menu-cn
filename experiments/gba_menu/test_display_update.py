from pathlib import Path
import hashlib
import json
import tempfile
import unittest
from PIL import Image
from library import pack,FRAME_BYTES,ASSETS
from display_update import stage,unpack

class DisplayUpdate(unittest.TestCase):
    def test_art_and_footer_keep_all_records_captions_and_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);card=root/'card';page=card/ASSETS/'menu.bin';page.parent.mkdir(parents=True)
            entries=[{'title':'测试游戏','folder':False,'rom':'/Assets/gba/common/Test.gba','bytes':32768,'id':'a'*20},
                     {'title':'返回首页','folder':True,'rom':'/'+ASSETS+'/menu.bin','id':'b'*20}]
            raw=bytearray(pack(entries));_,base,pause=unpack(raw)
            raw[base+144*480:base+FRAME_BYTES]=b'\xff'*16*480
            raw[pause+140*480:pause+FRAME_BYTES]=b'\xff'*20*480
            raw=bytes(raw);page.write_bytes(raw);before=hashlib.sha256(raw).hexdigest()
            art=root/'covers/Assets/gba/common/Test.png';art.parent.mkdir(parents=True);Image.new('RGB',(64,96),'red').save(art)
            receipt=stage(card,root/'staged',root/'covers');changed=(root/'staged'/ASSETS/'menu.bin').read_bytes()
            rows,base,pause=unpack(changed)
            self.assertEqual(changed[:base],raw[:base]);self.assertEqual(receipt['matched_covers'],1)
            self.assertEqual(changed[base+106*480:base+144*480],raw[base+106*480:base+144*480])
            self.assertEqual(changed[base+144*480:base+FRAME_BYTES],bytes(16*480))
            self.assertEqual(changed[pause+140*480:pause+FRAME_BYTES],bytes(20*480))
            self.assertEqual(changed[base+50*480+120*2:base+50*480+120*2+2],b'\x00\xf8')
            self.assertEqual(hashlib.sha256(page.read_bytes()).hexdigest(),before)
            mapping=root/'titles.json';mapping.write_text(json.dumps({'Assets/gba/common/Test.gba':'中文新名称'}),encoding='utf8')
            translated=stage(card,root/'translated',root/'covers',mapping)
            new=(root/'translated'/ASSETS/'menu.bin').read_bytes()
            self.assertEqual(new[:base],raw[:base]);self.assertGreater(translated['captions_updated'],0)
            self.assertNotEqual(new[base+106*480:base+144*480],raw[base+106*480:base+144*480])
            page.write_bytes(raw[:-1])
            with self.assertRaises(ValueError):stage(card,root/'invalid')
            self.assertFalse((root/'invalid').exists())

if __name__=='__main__':unittest.main()
