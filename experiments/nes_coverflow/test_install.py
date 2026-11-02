# SPDX-License-Identifier: MIT
import hashlib,importlib.util,json,tempfile,unittest
from pathlib import Path
import library
from test_library import rom,snapshot

spec=importlib.util.spec_from_file_location('nes_install_tool',Path(__file__).with_name('install.py'))
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)


class Install(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.card=self.root/'card';p=self.card/'Assets/nes/common/RPG/game.nes';p.parent.mkdir(parents=True);p.write_bytes(rom(1))
        (self.card/'Analogue_Pocket.json').write_text('{"product":"Analogue Pocket"}')
        p=self.card/'Saves/gba/common/important.sav';p.parent.mkdir(parents=True);p.write_bytes(b'keep important GBA progress')
        self.library=self.root/'library';library.build(self.card,self.library)
        self.package=self.root/'package';core=self.package/'core/Cores/pocketlab.NES';core.mkdir(parents=True)
        metadata=dict(platform_ids=['neslab','nes'],shortname='NES',author='pocketlab',description='Synthetic installer fixture',url='https://example.org',version='test',date_release='2026-11-02')
        (core/'core.json').write_text(json.dumps({'core':{'magic':'APF_VER_1','metadata':metadata,'framework':{'sleep_supported':False},'cores':[{'filename':'nes.rbf_r'}]}}))
        (core/'nes.rbf_r').write_bytes(b'synthetic FPGA installer fixture, never a release')
        (core/'data.json').write_text(json.dumps({'data':{'magic':'APF_VER_1','data_slots':[{'id':i} for i in [100,0,10,11]]}}))
        for key in ('audio','input','interact','variants','video'):
            value={'magic':'APF_VER_1'}
            if key=='variants':value['variant_list']=[]
            (core/(key+'.json')).write_text(json.dumps({key:value}))
        files=[{'path':p.relative_to(self.package/'core').as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in core.iterdir()]
        self.receipt={'core':'pocketlab.NES','version':'test','menu_format':'GBAF2/NES','minimum_slack_ns':1,'timing_records':128,'files':files}
        self.write_receipt()

    def tearDown(self):self.tmp.cleanup()

    def write_receipt(self):
        (self.package/'build-receipt.json').write_text(json.dumps(self.receipt))

    def test_variants_must_be_in_the_install_manifest(self):
        self.receipt['files']=[x for x in self.receipt['files'] if not x['path'].endswith('/variants.json')];self.write_receipt()
        before=snapshot(self.card)
        with self.assertRaisesRegex(ValueError,'required APF definitions'):installer.plan(self.card,self.package,self.library)
        self.assertEqual(before,snapshot(self.card))

    def test_install_rollback_keeps_originals_and_new_play_progress(self):
        before=snapshot(self.card);backup=self.root/'backup'
        plan=installer.plan(self.card,self.package,self.library)
        self.assertEqual(snapshot(self.card),before)
        installer.apply(self.card,self.package,self.library,backup)
        self.assertEqual((backup/'progress/Saves/gba/common/important.sav').read_bytes(),b'keep important GBA progress')
        save=next((self.card/'Saves/neslab/common').glob('*.sav'));save.write_bytes(b'new played progress')
        installer.rollback(self.card,backup,True)
        self.assertEqual(save.read_bytes(),b'new played progress')
        after=snapshot(self.card)
        for key,value in before.items():self.assertEqual(after[key],value)
        self.assertFalse((self.card/'Cores/pocketlab.NES/core.json').exists())

    def test_mismatched_format_or_altered_rom_rejected_without_writes(self):
        before=snapshot(self.card)
        self.receipt['menu_format']='GBAF1/NES';self.write_receipt()
        with self.assertRaises(ValueError):installer.plan(self.card,self.package,self.library)
        self.receipt['menu_format']='GBAF2/NES';self.write_receipt()
        (self.card/'Assets/nes/common/RPG/game.nes').write_bytes(rom(2));changed=snapshot(self.card)
        with self.assertRaises(ValueError):installer.apply(self.card,self.package,self.library,self.root/'backup')
        self.assertEqual(snapshot(self.card),changed)
        self.assertFalse((self.root/'backup').exists())

    def test_changed_rollback_file_preserved(self):
        backup=self.root/'backup';installer.apply(self.card,self.package,self.library,backup)
        core=self.card/'Cores/pocketlab.NES/core.json';core.write_bytes(b'manually revised core')
        before=snapshot(self.card)
        with self.assertRaises(ValueError):installer.rollback(self.card,backup,True)
        self.assertEqual(before,snapshot(self.card))

    def test_offline_preflight_does_not_authorize_applying_to_archive(self):
        (self.card/'Analogue_Pocket.json').unlink();before=snapshot(self.card)
        result=installer.plan(self.card,self.package,self.library,True)
        self.assertEqual(result['status'],'offline_validation_only')
        with self.assertRaises(FileNotFoundError):installer.apply(self.card,self.package,self.library,self.root/'backup')
        self.assertEqual(before,snapshot(self.card));self.assertFalse((self.root/'backup').exists())


if __name__=='__main__':unittest.main()
