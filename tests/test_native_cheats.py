import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import build_menus
import delivery
import menu_bindings
import native_cheats


class NativeCheats(unittest.TestCase):
    def test_roundtrip_all_widths_and_invalid_identity(self):
        for platform,(_,_,bits,low,_) in native_cheats.PLATFORMS.items():
            address=0x8000 if platform=='snes' else low
            codes=[{'type':'read_replace','address':address,'value':(1<<bits)-1,'compare':7}]
            raw=native_cheats.encode(platform,'7'*64,codes)
            self.assertEqual(native_cheats.decode(raw,platform,'7'*64),codes)
            with self.assertRaises(ValueError):native_cheats.decode(raw,platform,'8'*64)
            with self.assertRaises(ValueError):native_cheats.decode(raw[:-1],platform,'7'*64)
            damaged=bytearray(raw);damaged[-1]^=1
            with self.assertRaises(ValueError):native_cheats.decode(bytes(damaged),platform,'7'*64)

    def test_parser_refuses_crc_valid_unsafe_records(self):
        cases=[('genesis',1,0),('snes',0x7e8000,0),('nes',0x7000,0),('pce',0,256)]
        for platform,address,value in cases:
            body=bytes.fromhex('7'*64)+struct.pack('<4I',0,address,0,value)
            raw=struct.pack('<4I',0x48434c50,0x10000|native_cheats.PLATFORMS[platform][0],1,zlib.crc32(body))+body
            with self.assertRaises(ValueError):native_cheats.decode(raw,platform,'7'*64)
        with self.assertRaises(ValueError):
            native_cheats.encode('nes','7'*64,[{'type':'read_replace','address':0x8000,'value':1}]*2)

    def test_four_real_library_schemas_and_retained_codes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);card=root/'card';card.mkdir()
            sfc=bytearray(131072);p=0x7fc0
            sfc[p+0x15:p+0x1b]=bytes((0x20,2,7,3,1,0x33))
            struct.pack_into('<HH',sfc,p+0x1c,0xedcb,0x1234)
            struct.pack_into('<H',sfc,p+0x3c,0x8000)
            md=bytearray(65536);md[0x100:0x104]=b'SEGA';md[0x1f0]=ord('U')
            games={'NES':('nes','nes',b'NES\x1a'+bytes([1])+bytes(11)+bytes(16384),0x8000),
                   'PCE':('pce','pce',bytes(32768),0),
                   'MD':('genesis','gen',md,0), 'SFC':('snes','sfc',sfc,0x8000)}
            profiles=[]
            for system,(platform,suffix,raw,address) in games.items():
                path=card/f'Assets/{platform}/common/测试/Game.{suffix}'
                path.parent.mkdir(parents=True);path.write_bytes(raw)
                profiles.append({'platform':platform,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
                    'source':{'url':'https://example.org/synthetic','license':'CC0'},
                    'effects':[{'title':'Synthetic fixture','enabled':True,
                        'codes':[{'type':'read_replace','address':address,'value':17,'compare':0}]}]})
            index=root/'profiles.json';delivery.write(index,{'format':'POCKET-CHEATS1','profiles':profiles})
            build_menus.build(card,root/'first',list(games))
            old_pages={}
            for system,(platform,*_) in games.items():
                lib=root/'first/libraries'/system
                old_pages[system]={p.relative_to(lib).as_posix():p.read_bytes() for p in lib.rglob('*.bin')}
                manifest=native_cheats.bind_library(card,lib,platform,index)
                menu_bindings.validate(lib,manifest,system,'GBAF2')
                self.assertEqual(len(manifest['cheats']),1)
                for rel,previous in old_pages[system].items():
                    current=(lib/rel).read_bytes();count=int.from_bytes(current[8:12],'little')
                    for i in range(count):
                        offset=64+i*1024
                        self.assertEqual(current[offset:offset+16],previous[offset:offset+16])
                        self.assertEqual(current[offset+32:offset+544],previous[offset+32:offset+544])
                        if platform!='nes':self.assertEqual(current[offset+16:offset+32],previous[offset+16:offset+32])
                for row in manifest['files']:
                    if '/cheat/' in row['path']:
                        target=card/row['path'];target.parent.mkdir(parents=True)
                        target.write_bytes((lib/row['path']).read_bytes())
            build_menus.build(card,root/'second',list(games))
            for system,(platform,*_) in games.items():
                lib=root/'second/libraries'/system
                manifest=native_cheats.bind_library(card,lib,platform)
                menu_bindings.validate(lib,manifest,system,'GBAF2')
                self.assertEqual(len(manifest['cheats']),1)
                self.assertEqual(len(manifest['cheat_source_refs']),1)
                row=manifest['cheats'][0]
                self.assertEqual((lib/row['path']).read_bytes(),(card/row['path']).read_bytes())

    def test_gb_keeps_suspend_paths_and_binds_only_exact_roms(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);card=root/'card'
            rows=[]
            for platform, suffix, marker in [('gb','gb',1), ('gbc','gbc',2), ('gbc','gbc',3)]:
                rom=card/f'Assets/{platform}/common/{marker}/Same title.{suffix}'
                rom.parent.mkdir(parents=True)
                raw=bytes([marker])*32768
                rom.write_bytes(raw)
                rows.append({'platform':platform, 'bytes':len(raw), 'sha256':hashlib.sha256(raw).hexdigest(),
                             'source':{'url':'https://example.org/synthetic','license':'CC0'},
                             'effects':[{'title':'Synthetic fixture','enabled':True,
                                         'codes':[{'type':'read_replace','address':0x4567,'value':17,'compare':marker}]}]})
            index=root/'profiles.json'
            delivery.write(index,{'format':'POCKET-CHEATS1','profiles':rows[:2]})
            build_menus.build(card,root/'library',['GB-GBC'])
            lib=root/'library/libraries/GB-GBC'
            prior={p:p.read_bytes() for p in lib.rglob('*.bin')}
            manifest=native_cheats.bind_library(card,lib,'gb-family',index)
            menu_bindings.validate(lib,manifest,'GB-GBC')
            found=[]
            for path, old in prior.items():
                raw=path.read_bytes()
                old_entries=menu_bindings.page(old,'GB-GBC',None)
                entries=menu_bindings.page(raw,'GB-GBC',None,True)
                self.assertEqual([e['paths'] for e in entries],[e['paths'] for e in old_entries])
                found.extend(e['paths'][0] for e in entries if e['cheat_bytes'])
            self.assertEqual(sorted(found),['/Assets/gb/common/1/Same title.gb','/Assets/gbc/common/2/Same title.gbc'])
            cheat=lib/manifest['cheats'][0]['path']
            other=lib/manifest['cheats'][1]['path']
            cheat.write_bytes(other.read_bytes())
            with self.assertRaises(ValueError):
                menu_bindings.validate(lib,manifest,'GB-GBC')


if __name__=='__main__':unittest.main()
