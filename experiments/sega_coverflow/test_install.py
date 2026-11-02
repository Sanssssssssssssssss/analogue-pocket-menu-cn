# SPDX-License-Identifier: MIT
import hashlib,importlib.util,json,tempfile,unittest
from pathlib import Path
import library
from controller import PROFILES
from test_library import snapshot,profile

spec=importlib.util.spec_from_file_location('sega_installer',Path(__file__).with_name('install.py'))
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)


class Install(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()

    def fixture(self,platform='gg',with_cheat=False):
        root=self.root/platform;card=root/'card';ns,slot,address,_=PROFILES[platform];short=installer.SHORT[platform]
        rom=card/f'Assets/{platform}/common/RPG/game.{"sg" if platform=="sg1000" else platform}';rom.parent.mkdir(parents=True);raw=b'\x11'*32768;rom.write_bytes(raw)
        (card/'Analogue_Pocket.json').write_text('{"product":"Analogue Pocket"}')
        save=card/'Saves/gba/common/important.sav';save.parent.mkdir(parents=True);save.write_bytes(b'protected GBA progress')
        index=root/'cheats.json';index.write_text(json.dumps({'format':'SEGA-CHEATS1','profiles':[profile(raw)]}))
        stage=root/'library';library.build(card,stage,platform,cheats=index if with_cheat else None)
        package=root/'package';core=package/'core'/('Cores/pocketlab.'+short);core.mkdir(parents=True)
        metadata=dict(platform_ids=[ns,platform],shortname=short,author='pocketlab',description='Synthetic installer fixture',url='https://example.org',version='test',date_release='2026-11-02')
        contents={'core':{'core':{'magic':'APF_VER_1','metadata':metadata,'framework':{'sleep_supported':False,'hardware':{'cartridge_adapter':-1}},'cores':[{'filename':platform+'.rbf_r'}]}},
            'data':{'data':{'magic':'APF_VER_1','data_slots':[{'id':100},{'id':slot,'address':hex(address)},{'id':2,'size_maximum':'0x8000'},{'id':3}]}},
            'video':{'video':{'magic':'APF_VER_1','scaler_modes':[{}]*4+[{'width':320,'height':288},{'width':256,'height':240}]}},
            'audio':{'audio':{'magic':'APF_VER_1'}},'input':{'input':{'magic':'APF_VER_1'}},'interact':{'interact':{'magic':'APF_VER_1'}},
            'variants':{'variants':{'magic':'APF_VER_1','variant_list':[]}}}
        for key,value in contents.items():(core/(key+'.json')).write_text(json.dumps(value))
        (core/(platform+'.rbf_r')).write_bytes(b'synthetic fixture, never a device bitstream')
        p=package/'core/Platforms'/('_images/'+ns+'.bin');p.parent.mkdir(parents=True);p.write_bytes(b'synthetic fixture')
        (p.parent.parent/(ns+'.json')).write_text('{}')
        receipt={'core':'pocketlab.'+short,'platform':platform,'namespace':ns,'version':'test','menu_format':'GBAF2/Sega','minimum_slack_ns':1,'timing_records':72}
        self.refresh(package,receipt)
        return card,package,stage,root

    def test_variants_must_be_in_the_install_manifest(self):
        card,package,stage,root=self.fixture();path=package/'build-receipt.json';receipt=json.loads(path.read_text())
        receipt['files']=[x for x in receipt['files'] if not x['path'].endswith('/variants.json')];path.write_text(json.dumps(receipt))
        before=snapshot(card)
        with self.assertRaisesRegex(ValueError,'Incomplete entry'):installer.plan(card,package,stage,'gg')
        self.assertEqual(before,snapshot(card))

    def refresh(self,package,receipt=None):
        if receipt is None:receipt=json.loads((package/'build-receipt.json').read_text())
        receipt['files']=[{'path':p.relative_to(package/'core').as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in (package/'core').rglob('*') if p.is_file()]
        (package/'build-receipt.json').write_text(json.dumps(receipt))

    def test_each_native_profile_install_and_rollback_preserves_progress(self):
        for platform in PROFILES:
            with self.subTest(platform=platform):
                card,package,stage,root=self.fixture(platform,True);before=snapshot(card)
                installer.plan(card,package,stage,platform);self.assertEqual(snapshot(card),before)
                installer.apply(card,package,stage,root/'backup',platform)
                self.assertEqual((root/'backup/progress/Saves/gba/common/important.sav').read_bytes(),b'protected GBA progress')
                save=next((card/f'Saves/{PROFILES[platform][0]}/common').glob('*.sav'));save.write_bytes(b'new played progress')
                installer.rollback(card,root/'backup',True)
                for key,value in before.items():self.assertEqual(snapshot(card)[key],value)
                self.assertEqual(save.read_bytes(),b'new played progress')
                self.assertFalse((card/('Cores/pocketlab.'+installer.SHORT[platform])/'core.json').exists())

    def test_changed_rom_and_native_slot_are_rejected_without_writes(self):
        card,package,stage,root=self.fixture();rom=next((card/'Assets/gg/common').rglob('*.gg'));rom.write_bytes(b'\x22'*32768)
        before=snapshot(card)
        with self.assertRaises(ValueError):installer.apply(card,package,stage,root/'backup','gg')
        self.assertEqual(snapshot(card),before);self.assertFalse((root/'backup').exists())
        rom.write_bytes(b'\x11'*32768);p=package/'core/Cores/pocketlab.GG/data.json';data=json.loads(p.read_text());data['data']['data_slots'][1]['id']=4;p.write_text(json.dumps(data));self.refresh(package)
        with self.assertRaises(ValueError):installer.plan(card,package,stage,'gg')

    def test_cheat_size_or_identity_binding_cannot_be_reassigned(self):
        card,package,stage,root=self.fixture(with_cheat=True);p=next((stage/'Assets/ggclab/common/libs').glob('*.bin'));raw=bytearray(p.read_bytes())
        raw[544:800]=('/Assets/ggclab/cheat/'+('f'*20)+'.cht').encode().ljust(256,b'\0');p.write_bytes(raw)
        manifest=stage/'library-manifest.json';value=json.loads(manifest.read_text())
        for row in value['files']:
            if row['path']==p.relative_to(stage).as_posix():row['sha256']=hashlib.sha256(raw).hexdigest()
        manifest.write_text(json.dumps(value));before=snapshot(card)
        with self.assertRaises(ValueError):installer.apply(card,package,stage,root/'backup','gg')
        self.assertEqual(snapshot(card),before);self.assertFalse((root/'backup').exists())

    def test_preexisting_destination_and_changed_rollback_file_are_preserved(self):
        card,package,stage,root=self.fixture();target=card/'Cores/pocketlab.GG/core.json';target.parent.mkdir(parents=True);target.write_bytes(b'existing entry')
        before=snapshot(card)
        with self.assertRaises(ValueError):installer.plan(card,package,stage,'gg')
        self.assertEqual(snapshot(card),before);target.unlink()
        installer.apply(card,package,stage,root/'backup','gg');target.write_bytes(b'manually revised entry');before=snapshot(card)
        with self.assertRaises(ValueError):installer.rollback(card,root/'backup',True)
        self.assertEqual(snapshot(card),before)

    def test_offline_preflight_cannot_apply_to_an_unidentified_archive(self):
        card,package,stage,root=self.fixture(with_cheat=True);(card/'Analogue_Pocket.json').unlink();before=snapshot(card)
        result=installer.plan(card,package,stage,'gg',True)
        self.assertEqual(result['status'],'offline_validation_only')
        with self.assertRaises(FileNotFoundError):installer.apply(card,package,stage,root/'backup','gg')
        self.assertEqual(before,snapshot(card));self.assertFalse((root/'backup').exists())


if __name__=='__main__':unittest.main()
