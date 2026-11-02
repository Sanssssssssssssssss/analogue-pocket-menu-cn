import importlib.util,json,shutil,struct,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'experiments/gba_menu'))
from test_library import rom

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

old=module('f1_library',ROOT/'experiments/gba_menu/library.py')
new=module('f2_library',Path(__file__).with_name('library.py'))
updater=module('f2_update',Path(__file__).with_name('update.py'))

class UpdateSafety(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.card=self.root/'card';self.card.mkdir()
        (self.card/'Analogue_Pocket.json').write_text(json.dumps({'product':'Analogue Pocket'}))
        games=self.card/'Assets/gba/common';games.mkdir(parents=True);(games/'Synthetic.gba').write_bytes(rom())
        self.f1=self.root/'f1';old.build(self.card,self.f1)
        shutil.copytree(self.f1/'Assets',self.card/'Assets',dirs_exist_ok=True)
        self.f2=self.root/'f2';new.upgrade(self.f1,self.f2)
        self.package=self.root/'package';folder=self.package/'core'/updater.CORE;folder.mkdir(parents=True)
        candidate=folder/'gba.rbf_r';candidate.write_bytes(b'synthetic-new-core')
        meta=json.loads((ROOT/'packaging/Cores/pocketlab.CoverFlow/core.json').read_text())
        meta['core']['metadata'].update(author='pocketlab',shortname='GBA',platform_ids=['gbalab','gba'],version='0.2.0-gba.3')
        meta['core']['cores']=[{'name':'default','id':0,'filename':'gba.rbf_r'}]
        installed=self.card/updater.CORE;installed.mkdir(parents=True)
        (installed/'core.json').write_text(json.dumps(meta));(installed/'gba.rbf_r').write_bytes(b'synthetic-accepted-core')
        (installed/'data.json').write_text(json.dumps({'data':{'data_slots':[{'id':v} for v in [100,4,1,10,11]]}}))
        self.video={'video':{'magic':'APF_VER_1','scaler_modes':[{'width':240,'height':160,'aspect_w':3,'aspect_h':2,'rotation':0,'mirror':0}],
            'display_modes':[{'id':'0x41'},{'id':'0x42'}]}}
        (installed/'video.json').write_text(json.dumps(self.video))
        build={'core':'pocketlab.GBA','menu_format':'GBAF2','version':'0.2.0-gba.5','minimum_reported_slack_ns':0.1,
            'files':[{'path':updater.CORE+'gba.rbf_r','bytes':candidate.stat().st_size,'sha256':updater.sha(candidate)}]}
        (self.package/'build-receipt.json').write_text(json.dumps(build))
        self.save=self.card/'Saves/gba/common/MinishCap.sav';self.save.parent.mkdir(parents=True);self.save.write_bytes(b'precious progress')
        self.staging=self.root/'staging';self.backup=self.root/'backup'
        self.trust=patch.object(updater,'KNOWN_SOURCE',{updater.sha(installed/'gba.rbf_r')});self.trust.start();self.addCleanup(self.trust.stop)

    def plan(self):return updater.stage(self.card,self.package,self.f2,self.staging)

    def test_plan_apply_and_rollback_preserve_game_modes_and_new_progress(self):
        before={p.relative_to(self.card).as_posix():p.read_bytes() for p in self.card.rglob('*') if p.is_file()}
        r=self.plan();self.assertEqual(r['roms_verified'],1)
        self.assertEqual(before,{p.relative_to(self.card).as_posix():p.read_bytes() for p in self.card.rglob('*') if p.is_file()})
        updater.apply(self.card,self.staging,self.backup)
        video=json.loads((self.card/updater.CORE/'video.json').read_text())['video']
        self.assertEqual(video['scaler_modes'][0],self.video['video']['scaler_modes'][0]);self.assertEqual(video['display_modes'],self.video['video']['display_modes'])
        self.assertEqual(video['scaler_modes'][1],updater.MENU_MODE)
        self.assertEqual((self.backup/'progress/Saves/gba/common/MinishCap.sav').read_bytes(),b'precious progress')
        self.save.write_bytes(b'new gameplay');updater.rollback(self.card,self.backup,True)
        for rel,raw in before.items():
            self.assertEqual((self.card/rel).read_bytes(),b'new gameplay' if rel=='Saves/gba/common/MinishCap.sav' else raw)

    def test_rom_changed_after_staging_aborts_before_backup_or_card_writes(self):
        self.plan();game=self.card/'Assets/gba/common/Synthetic.gba';game.write_bytes(game.read_bytes()+b'changed')
        core=(self.card/updater.CORE/'gba.rbf_r').read_bytes()
        with self.assertRaisesRegex(ValueError,'ROM changed after staging'):updater.apply(self.card,self.staging,self.backup)
        self.assertFalse(self.backup.exists());self.assertEqual((self.card/updater.CORE/'gba.rbf_r').read_bytes(),core)

    def test_rollback_refuses_a_changed_file_before_restoring_anything(self):
        self.plan();updater.apply(self.card,self.staging,self.backup)
        (self.card/updater.CORE/'video.json').write_bytes(b'manual edit')
        pack=self.card/'Assets/gbalab/common/menu.bin';before=pack.read_bytes()
        with self.assertRaisesRegex(ValueError,'Changed file'):updater.rollback(self.card,self.backup,True)
        self.assertEqual(pack.read_bytes(),before);self.assertEqual(self.save.read_bytes(),b'precious progress')

    def test_changed_launch_identity_is_rejected_even_with_updated_file_hash(self):
        manifest=json.loads((self.f2/'library-manifest.json').read_text());item=manifest['files'][0];path=self.f2/item['path']
        raw=bytearray(path.read_bytes());raw[64+288+24]^=1;path.write_bytes(raw);item['sha256']=updater.sha(path)
        (self.f2/'library-manifest.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError,'identity changed'):self.plan()
        self.assertFalse(self.staging.exists())

    def test_existing_scaler_slot_is_not_overwritten(self):
        self.video['video']['scaler_modes'].append({'width':100,'height':100})
        (self.card/updater.CORE/'video.json').write_text(json.dumps(self.video))
        with self.assertRaisesRegex(ValueError,'slot 1 is occupied'):self.plan()
        self.assertFalse(self.staging.exists())

    def test_explicit_styles_change_metadata_preserving_native_geometry_and_rollback(self):
        before=(self.card/updater.CORE/'video.json').read_bytes()
        result=updater.stage(self.card,self.package,self.f2,self.staging,True)
        self.assertTrue(result['display_profile_updated']);self.assertEqual(result['OS_display_choice_writes'],0)
        updater.apply(self.card,self.staging,self.backup)
        video=json.loads((self.card/updater.CORE/'video.json').read_text())['video']
        self.assertEqual(video['scaler_modes'][0],self.video['video']['scaler_modes'][0])
        self.assertEqual(video['defaults']['sharpness'],3)
        self.assertFalse(any(int(m['id'],16) in [0,0x20] for m in video['display_modes']))
        updater.rollback(self.card,self.backup,True)
        self.assertEqual((self.card/updater.CORE/'video.json').read_bytes(),before)

    def test_oversized_pages_are_rejected_before_conversion_or_update(self):
        manifest=json.loads((self.f1/'library-manifest.json').read_text());item=manifest['files'][0];p=self.f1/item['path'];raw=p.read_bytes()
        n=129;base=64+n*1024;rows=raw[64:1088]*(n-1)+raw[1088:2112]
        oversized=struct.pack('<4s5I',b'GBAF',1,n,base,base+n*76800,0).ljust(64,b'\0')+rows+bytes(n*76800+153600)
        p.write_bytes(oversized);item.update(bytes=len(oversized),sha256=updater.sha(p));(self.f1/'library-manifest.json').write_text(json.dumps(manifest))
        output=self.root/'rejected'
        with self.assertRaisesRegex(ValueError,'128 texture'):new.upgrade(self.f1,output)
        self.assertFalse(output.exists());self.assertEqual(p.read_bytes(),oversized)
        f2=self.root/'oversized-F2.bin'
        f2.write_bytes(struct.pack('<4s5I',b'GBAF',2,n,base,base+n*65536,65536).ljust(64,b'\0')+rows+bytes(n*65536+153600))
        with self.assertRaisesRegex(ValueError,'128 texture'):updater.records(f2)

if __name__=='__main__':unittest.main()
