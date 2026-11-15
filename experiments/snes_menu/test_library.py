# SPDX-License-Identifier: MIT
import hashlib,json,struct,tempfile,unittest
from pathlib import Path
import library
class Library(unittest.TestCase):
    def setup_card(self,root):
        card=root/'card';card.mkdir();(card/'Analogue_Pocket.json').write_text('{"product":"Analogue Pocket"}')
        rows=[]
        for name,size,chip,pal,ram,offset in [('basic.sfc',32768,0,0,3,0),('no-ram.sfc',32768,1,0,0,0),('copier.smc',33280,0,0,2,512),('fx.sfc',32768,0x70,0,3,0),('pal.sfc',32768,0,1,3,0)]:
            rel='Assets/snes/common/0.FAVORITES/01.Zelda/'+name
            p=card/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(bytes([len(rows)])*size)
            rows.append({'path':rel,'bytes':size,'sha256':library.nes.sha(p),'core':0,'chip':chip,'rom_size':6,'ram_size':ram,'pal':pal,'rom_offset':offset})
        meta=root/'decisions.json';meta.write_text(json.dumps({'identity':library.nes.identity(card),'loader_sha256':library.LOADER_SHA,'rows':rows}))
        return card,meta,rows
    def test_mapping_offset_save_sizes_and_unsupported_exclusion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);card,meta,rows=self.setup_card(root)
            before={p.relative_to(card).as_posix():library.nes.sha(p) for p in card.rglob('*') if p.is_file()}
            out=root/'stage';r=library.build(card,meta,out)
            self.assertEqual((r['unique_games'],r['pages'],len(r['excluded'])),(3,2,2))
            saves=[p for p in r['files'] if p['path'].endswith('.sav')]
            self.assertEqual(sorted(p['bytes'] for p in saves),[4096,8192])
            for p in saves:self.assertFalse(any((out/p['path']).read_bytes()))
            page=next((out/library.ASSETS/'libs').glob('*.bin')).read_bytes()
            records=[struct.unpack_from('<4s7I',page,64+i*1024) for i in range(3)]
            self.assertEqual([(r[2],r[3],r[4]) for r in records],[(32768,8192,0),(32768,0,0),(32768,4096,512)])
            self.assertEqual(before,{p.relative_to(card).as_posix():library.nes.sha(p) for p in card.rglob('*') if p.is_file()})
    def test_changed_rom_and_existing_preview_progress_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);card,meta,rows=self.setup_card(root)
            save=card/library.SAVES/(rows[0]['sha256'][:20]+'.sav');save.parent.mkdir(parents=True);save.write_bytes(b'latest progress')
            with self.assertRaises(ValueError):library.build(card,meta,root/'stage')
            self.assertEqual(save.read_bytes(),b'latest progress')
            (card/rows[0]['path']).write_bytes(bytes(32768-1))
            with self.assertRaises(ValueError):library.build(card,meta,root/'changed')
    def test_foreign_save_namespace_refused(self):
        with self.assertRaises(ValueError):library.nes.path_bytes('/Saves/neslab/common/progress.sav','snes','snescn')
if __name__=='__main__':unittest.main()
