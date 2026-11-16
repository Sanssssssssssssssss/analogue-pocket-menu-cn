# SPDX-License-Identifier: MIT
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.error import HTTPError

from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import library_catalog as catalog


class LibraryCatalog(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.card, self.cache = self.root/'card', self.root/'cache'
        self.rel = 'Assets/gba/common/renamed.gba'
        path = self.card/self.rel
        path.parent.mkdir(parents=True)
        self.rom = b'a public synthetic cartridge'
        path.write_bytes(self.rom)
        image = io.BytesIO()
        Image.new('RGB', (32, 40), '#253247').save(image, format='PNG')
        self.png = image.getvalue()
        self.calls = []

    def fetch(self, url, limit):
        self.calls.append(url)
        if url.endswith('.csv'):
            return 'Name EN,Name CN\nDemo (USA),演示游戏\n'.encode()
        if url.endswith('.dat'):
            return ('game (\n name "Demo (USA)"\n rom ( name "demo.gba" size '+str(len(self.rom))+
                    ' sha1 '+hashlib.sha1(self.rom).hexdigest()+' )\n)\n').encode()
        if '/git/trees/' in url:
            return json.dumps({'sha': 'a'*40, 'truncated': False,
                               'tree': [{'type': 'blob', 'path': 'Named_Boxarts/Demo (USA).png'}]}).encode()
        if url.endswith('.png'):
            return self.png
        raise AssertionError(url)

    def test_content_match_rename_chinese_title_and_offline_cache(self):
        result = catalog.enrich(self.card, self.root/'first', self.cache, fetch=self.fetch)
        self.assertEqual(result['matched_covers'], 1)
        self.assertTrue(result['games'][0]['content_identity_confirmed'])
        self.assertEqual(result['games'][0]['title'], '演示游戏 (USA)')
        self.assertEqual((self.card/self.rel).read_bytes(), self.rom)
        first_calls = len(self.calls)
        offline = catalog.enrich(self.card, self.root/'second', self.cache, online=False, fetch=self.fetch)
        self.assertEqual(first_calls, len(self.calls))
        self.assertEqual(offline['matched_covers'], 1)
        self.assertIn('/'+'a'*40+'/', offline['games'][0]['cover'])

    def test_ambiguous_title_or_art_is_not_guessed(self):
        table = catalog.translations('Name EN,Name CN\nDemo (US),演示甲\nDemo (JP),演示乙\n'.encode())
        self.assertEqual(catalog.resolve_name('Demo', *table)[0], 'Demo')
        index = ('repo', 'a'*40, {}, {'demo': {'Named_Boxarts/Demo (US).png', 'Named_Boxarts/Demo (JP).png'}})
        self.assertEqual(list(catalog.thumbnail_urls(index, ['Demo'])), [])
        self.assertEqual(catalog.resolve_name('Demo 2', *table)[0], 'Demo 2')

    def test_arcade_short_identifiers_use_the_arcade_csv_schema(self):
        table = catalog.translations('MAME Name,EN Name,CN Name\navsp,Alien vs. Predator (Euro 940520),异形对铁血战士\n'.encode())
        title, art, match = catalog.resolve_name('avsp', *table)
        self.assertEqual(title, '异形对铁血战士')
        self.assertEqual(art, 'Alien vs. Predator (Euro 940520)')
        self.assertEqual(match, 'exact_name')

    def test_artwork_preserves_edition_punctuation_before_loose_matching(self):
        wanted = 'Demo _ Japanese title (NGM-044 ~ NGH-044)'
        different = 'Demo _ Japanese title (NGM-044)(NGH-044)'
        self.assertEqual(catalog.key(wanted),catalog.key(different))
        def fetch(url, limit):
            return json.dumps({'sha':'b'*40,'truncated':False,'tree':[
                {'type':'blob','path':'Named_Boxarts/'+name+'.png'} for name in (wanted,different)]}).encode()
        index = catalog.thumbnail_index(catalog.Cache(self.cache, fetch=fetch),'ng')
        urls = list(catalog.thumbnail_urls(index,['Demo / Japanese title (NGM-044 ~ NGH-044)']))
        self.assertEqual(urls,[catalog.raw_url('libretro-thumbnails/FBNeo_-_Arcade_Games','b'*40,'Named_Boxarts/'+wanted+'.png')])

    def test_corrupt_cache_is_rejected_and_reported(self):
        catalog.enrich(self.card, self.root/'first', self.cache, fetch=self.fetch)
        url = next(url for url in self.calls if url.endswith('.csv'))
        (self.cache/hashlib.sha256(url.encode()).hexdigest()).write_bytes(b'corrupt')
        result = catalog.enrich(self.card, self.root/'second', self.cache, online=False)
        self.assertTrue(any(e['kind'] == 'names' and 'checksum' in e['message'] for e in result['errors']))

    def test_missing_files_are_not_downloaded_for_every_rom(self):
        calls = []
        def missing(url, limit):
            calls.append(url)
            raise HTTPError(url, 404, 'absent', {}, None)
        store = catalog.Cache(self.cache, fetch=missing)
        for _ in range(3):
            with self.assertRaises(OSError):
                store.get('https://raw.githubusercontent.com/owner/repo/main/absent.png')
        self.assertEqual(len(calls), 1)

    def test_chinese_alias_finds_work_art_without_claiming_rom_identity(self):
        aliases = self.root/'titles.json'
        aliases.write_text(json.dumps({self.rel: '演示游戏 (汉化版)'}), encoding='utf8')
        def fetch(url, limit):
            return b'' if url.endswith('.dat') else self.fetch(url, limit)
        result = catalog.enrich(self.card, self.root/'hinted', self.cache,
                                local_titles=aliases, fetch=fetch)
        row = result['games'][0]
        self.assertEqual(result['matched_covers'], 1)
        self.assertEqual(row['local_artwork_hint'], 'Demo')
        self.assertEqual(row['title'], '演示游戏 (汉化版)')
        self.assertFalse(row['content_identity_confirmed'])
        self.assertEqual((self.card/self.rel).read_bytes(), self.rom)

    def test_ambiguous_chinese_alias_does_not_choose_a_work(self):
        aliases = self.root/'titles.json'
        aliases.write_text(json.dumps({self.rel: '演示游戏'}), encoding='utf8')
        def fetch(url, limit):
            if url.endswith('.dat'):
                return b''
            if url.endswith('.csv'):
                return 'Name EN,Name CN\nDemo,演示游戏\nDifferent sequel,演示游戏\n'.encode()
            return self.fetch(url, limit)
        result = catalog.enrich(self.card, self.root/'ambiguous', self.cache,
                                local_titles=aliases, fetch=fetch)
        self.assertEqual(result['matched_covers'], 0)
        self.assertIsNone(result['games'][0]['local_artwork_hint'])
        self.assertFalse(any(url.endswith('.png') for url in self.calls))

    def test_local_display_alias_cannot_override_a_content_identified_work(self):
        aliases = self.root/'titles.json'
        aliases.write_text(json.dumps({self.rel: '另一个游戏'}), encoding='utf8')
        def fetch(url, limit):
            if url.endswith('.csv'):
                return 'Name EN,Name CN\nDemo (USA),演示游戏\nOther game,另一个游戏\n'.encode()
            if '/git/trees/' in url:
                return json.dumps({'sha':'b'*40,'truncated':False,'tree':[
                    {'type':'blob','path':'Named_Boxarts/Other game.png'}]}).encode()
            return self.fetch(url, limit)
        result = catalog.enrich(self.card, self.root/'content-first', self.cache,
                                local_titles=aliases, fetch=fetch)
        self.assertTrue(result['games'][0]['content_identity_confirmed'])
        self.assertIsNone(result['games'][0]['local_artwork_hint'])
        self.assertEqual(result['matched_covers'], 0)

    def test_local_display_alias_preserves_a_catalog_recognized_filename(self):
        recognized = 'Assets/gba/common/Demo (USA).gba'
        (self.card/self.rel).rename(self.card/recognized)
        aliases = self.root/'titles.json'
        aliases.write_text(json.dumps({recognized: '另一个游戏'}), encoding='utf8')
        def fetch(url, limit):
            if url.endswith('.csv'):
                return 'Name EN,Name CN\nDemo (USA),演示游戏\nOther game,另一个游戏\n'.encode()
            if '/git/trees/' in url:
                return json.dumps({'sha':'b'*40,'truncated':False,'tree':[
                    {'type':'blob','path':'Named_Boxarts/Other game.png'}]}).encode()
            return self.fetch(url, limit)
        result = catalog.enrich(self.card, self.root/'filename-first', self.cache,
                                local_titles=aliases, fetch=fetch)
        self.assertIsNone(result['games'][0]['local_artwork_hint'])
        self.assertEqual(result['matched_covers'], 0)

    def test_conflicting_catalog_translations_do_not_make_a_known_file_unknown(self):
        recognized = 'Assets/gba/common/Demo (USA).gba'
        (self.card/self.rel).rename(self.card/recognized)
        aliases = self.root/'titles.json'
        aliases.write_text(json.dumps({recognized: '另一个游戏'}), encoding='utf8')
        def fetch(url, limit):
            if url.endswith('.dat'):
                return b''
            if url.endswith('.csv'):
                return 'Name EN,Name CN\nDemo (USA),演示甲\nDemo (USA),演示乙\nOther game,另一个游戏\n'.encode()
            if '/git/trees/' in url:
                return json.dumps({'sha':'b'*40,'truncated':False,'tree':[
                    {'type':'blob','path':'Named_Boxarts/Other game.png'}]}).encode()
            return self.fetch(url, limit)
        result = catalog.enrich(self.card, self.root/'conflicting-cn', self.cache,
                                local_titles=aliases, fetch=fetch)
        self.assertIsNone(result['games'][0]['local_artwork_hint'])
        self.assertEqual(result['matched_covers'], 0)

    def test_conflicting_chinese_work_names_do_not_enable_a_different_alias(self):
        recognized = 'Assets/gba/common/演示游戏.gba'
        (self.card/self.rel).rename(self.card/recognized)
        aliases = self.root/'titles.json'
        aliases.write_text(json.dumps({recognized: '另一个游戏'}), encoding='utf8')
        def fetch(url, limit):
            if url.endswith('.dat'):
                return b''
            if url.endswith('.csv'):
                return 'Name EN,Name CN\nDemo,演示游戏\nDifferent sequel,演示游戏\nOther game,另一个游戏\n'.encode()
            if '/git/trees/' in url:
                return json.dumps({'sha':'b'*40,'truncated':False,'tree':[
                    {'type':'blob','path':'Named_Boxarts/Other game.png'}]}).encode()
            return self.fetch(url, limit)
        result = catalog.enrich(self.card, self.root/'conflicting-work', self.cache,
                                local_titles=aliases, fetch=fetch)
        self.assertIsNone(result['games'][0]['local_artwork_hint'])
        self.assertEqual(result['matched_covers'], 0)


if __name__ == '__main__':
    unittest.main()
