# SPDX-License-Identifier: MIT
import hashlib,importlib.util,json,tempfile,unittest
from pathlib import Path
import library
import delivery
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
            if key=='video':value['scaler_modes']=[{'width':256,'height':240},{'width':320,'height':288}]
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

    def test_batch_refresh_updates_filenames_and_preserves_metadata_and_played_saves(self):
        installer.apply(self.card,self.package,self.library,self.root/'first-backup')
        save=next((self.card/'Saves/neslab/common').glob('*.sav'))
        played=bytearray(save.read_bytes());played[:4]=b'PLAY';save.write_bytes(played)
        video_path=self.card/'Cores/pocketlab.NES/video.json'
        video=delivery.read(video_path);video['video']['defaults']={'sharpness':3};delivery.write(video_path,video)
        protected={p.relative_to(self.card).as_posix():p.read_bytes() for p in (self.card/'Cores/pocketlab.NES').iterdir()}
        extra=self.card/'Assets/nes/common/RPG/新的游戏.nes';extra.write_bytes(rom(2))
        aliases=self.root/'aliases.json';delivery.write(aliases,{'Assets/nes/common/RPG/game.nes':'新的显示名'})
        fresh=self.root/'fresh';library.build(self.card,fresh,titles=aliases)
        config=self.root/'config/delivery.json';delivery.write(config,{'components':[{'id':'NES','package':str(self.package),'library':str(fresh)}]})
        before=snapshot(self.card);staging=self.root/'refresh';backup=self.root/'refresh-backup'
        result=delivery.prepare(self.card,config,staging)
        self.assertEqual(before,snapshot(self.card))
        self.assertEqual(result['components']['NES']['operation'],'library_refresh_same_bitstream')
        self.assertFalse(any(x['path'].startswith(('Cores/','Platforms/')) for x in result['changes']))
        self.assertTrue(any(x['previous_sha256'] for x in result['changes']))
        delivery.apply(self.card,staging,backup)
        self.assertEqual(save.read_bytes(),played)
        for rel,data in protected.items():self.assertEqual((self.card/rel).read_bytes(),data)
        new_save=next(x for x in (self.card/'Saves/neslab/common').glob('*.sav') if x!=save)
        new_play=bytearray(new_save.read_bytes());new_play[0]=7;new_save.write_bytes(new_play)
        delivery.rollback(self.card,backup,execute=True)
        for rel,digest in before.items():self.assertEqual(snapshot(self.card)[rel],digest)
        self.assertEqual(new_save.read_bytes(),new_play)

    def test_refresh_rejects_other_bitstreams_bindings_or_post_plan_metadata_edits(self):
        installer.apply(self.card,self.package,self.library,self.root/'first-backup')
        for suffix,change in [('nes.rbf_r',lambda b:b+b'other core'),
                              ('data.json',lambda b:b.replace(b'100',b'101')),
                              ('video.json',lambda b:b.replace(b'320',b'321'))]:
            p=self.card/'Cores/pocketlab.NES'/suffix;original=p.read_bytes();p.write_bytes(change(original));before=snapshot(self.card)
            with self.assertRaises(ValueError):installer.plan(self.card,self.package,self.library,refresh=True)
            self.assertEqual(before,snapshot(self.card));p.write_bytes(original)
        config=self.root/'config/delivery.json';delivery.write(config,{'components':[{'id':'NES','package':str(self.package),'library':str(self.library)}]})
        staging=self.root/'refresh';delivery.prepare(self.card,config,staging)
        p=self.card/'Cores/pocketlab.NES/input.json';p.write_bytes(p.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError,'identity changed'):delivery.apply(self.card,staging,self.root/'refresh-backup')
        self.assertFalse((self.root/'refresh-backup').exists())

    def test_prebuilt_seed_cannot_replace_existing_progress_with_wrong_size(self):
        installer.apply(self.card,self.package,self.library,self.root/'first-backup')
        save=next((self.card/'Saves/neslab/common').glob('*.sav'));save.write_bytes(b'unsupported imported format')
        before=snapshot(self.card)
        with self.assertRaisesRegex(ValueError,'unsupported size'):
            installer.plan(self.card,self.package,self.library,refresh=True)
        self.assertEqual(before,snapshot(self.card))


if __name__=='__main__':unittest.main()
