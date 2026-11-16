#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Local, cached title/artwork matching. Never upload ROMs or alter their names."""
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

from PIL import Image
import build_menus
import delivery

DATABASE_REF = 'c4e17d41ec1bb744fb064f7cefeb61b878fc5d64'
CHINESE_REF = 'f1f3a28a7d92f6354913cc0398f22c220971f757'
PLATFORMS = {
    'gb': 'Nintendo - Game Boy', 'gbc': 'Nintendo - Game Boy Color',
    'gba': 'Nintendo - Game Boy Advance', 'nes': 'Nintendo - Nintendo Entertainment System',
    'gg': 'Sega - Game Gear', 'sms': 'Sega - Master System - Mark III',
    'sg1000': 'Sega - SG-1000', 'genesis': 'Sega - Mega Drive - Genesis',
    'snes': 'Nintendo - Super Nintendo Entertainment System',
    'pce': 'NEC - PC Engine - TurboGrafx 16', 'sgx': 'NEC - PC Engine SuperGrafx',
    'jtcps1': 'FBNeo - Arcade Games', 'jtcps15': 'FBNeo - Arcade Games',
    'jtcps2': 'FBNeo - Arcade Games', 'ng': 'FBNeo - Arcade Games',
    '2600': 'Atari - 2600', '7800': 'Atari - 7800',
    'wonderswan': 'Bandai - WonderSwan', 'wonderswan_color': 'Bandai - WonderSwan Color',
    'supervision': 'Watara - Supervision', 'poke_mini': 'Nintendo - Pokemon Mini',
    'arduboy': 'Arduboy',
}
CSV_NAMES = {'pce': 'NEC - PC Engine - TurboGrafx-16', 'jtcps2': 'Arcade - CPS2',
             'jtcps1': 'Arcade - CPS1', 'jtcps15': 'Arcade - CPS1', 'ng': 'Arcade - NEOGEO',
             '2600': 'Atari - Atari 2600', '7800': 'Atari - Atari 7800'}
ARCADE = frozenset(('jtcps1', 'jtcps15', 'jtcps2', 'ng'))


class OfflineCacheMiss(FileNotFoundError):
    """An intentional offline run has no cached copy of the requested data."""


def key(value):
    return ''.join(c for c in unicodedata.normalize('NFKC', value).casefold() if c.isalnum())


def base(value):
    return re.sub(r'\s*[\[(].*', '', value).strip()


def chinese(value):
    return bool(re.search('[\u3400-\u9fff]', value))


class Cache:
    def __init__(self, root, online=True, fetch=None):
        self.root = Path(root).resolve()
        self.online = online
        self.fetch = fetch or self.download
        self.provenance = []

    @staticmethod
    def download(url, limit):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'https' or parsed.hostname not in ('raw.githubusercontent.com', 'api.github.com'):
            raise ValueError('Metadata downloads must use the configured HTTPS source')
        request = urllib.request.Request(url, headers={'User-Agent': 'Pocket-CoverFlow-Assistant/1'})
        with urllib.request.urlopen(request, timeout=20) as response:
            if urllib.parse.urlsplit(response.url).hostname != parsed.hostname:
                raise ValueError('Unexpected metadata redirect')
            raw = response.read(limit + 1)
        if len(raw) > limit:
            raise ValueError('Metadata download exceeds its size limit')
        return raw

    def get(self, url, limit=16*1024*1024):
        name = hashlib.sha256(url.encode()).hexdigest()
        path = self.root/name
        receipt = self.root/(name + '.json')
        missing = self.root/(name + '.missing.json')
        if path.is_file() and receipt.is_file():
            row = delivery.read(receipt)
            raw = path.read_bytes()
            if row.get('url') != url or row.get('sha256') != hashlib.sha256(raw).hexdigest() or len(raw) > limit:
                raise ValueError('Cached metadata checksum differs')
        else:
            if missing.is_file():
                negative = delivery.read(missing)
                if negative.get('url') == url and time.time() - negative.get('time', 0) < 86400:
                    raise FileNotFoundError('Metadata source has no matching entry')
            if not self.online:
                raise OfflineCacheMiss('Metadata not cached while offline')
            try:
                raw = self.fetch(url, limit)
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    delivery.write(missing, {'url': url, 'time': time.time()})
                raise
            if len(raw) > limit:
                raise ValueError('Metadata exceeds its size limit')
            self.root.mkdir(parents=True, exist_ok=True)
            temp = self.root/(name + '.part')
            temp.write_bytes(raw)
            temp.replace(path)
            row = {'url': url, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
            delivery.write(receipt, row)
        self.provenance.append(row)
        return raw


def raw_url(repo, ref, path):
    return 'https://raw.githubusercontent.com/' + repo + '/' + ref + '/' + urllib.parse.quote(path, safe='/')


def parse_dat(raw):
    """Only single-ROM cartridge entries are eligible for content matching."""
    text = raw.decode('utf-8-sig')
    hashes = {}
    for block in re.findall(r'(?ms)^game\s*\(\s*\n(.*?)^\)', text):
        names = re.findall(r'(?m)^\s*name\s+"([^"]+)"', block)
        roms = re.findall(r'\brom\s*\(([^\n]*)\)', block)
        if len(names) != 1 or len(roms) != 1:
            continue
        digest = re.search(r'\bsha1\s+([0-9a-fA-F]{40})\b', roms[0])
        size = re.search(r'\bsize\s+(\d+)\b', roms[0])
        if digest and size:
            hashes.setdefault((digest[1].lower(), int(size[1])), set()).add(names[0])
    return {k: next(iter(v)) for k, v in hashes.items() if len(v) == 1}


def translations(raw):
    exact, stems, inverse = {}, {}, {}
    for row in csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))):
        en = row.get('Name EN', row.get('EN Name', '')).strip()
        cn = row.get('Name CN', row.get('CN Name', '')).strip()
        if not en or not cn or not chinese(cn):
            continue
        exact.setdefault(key(en), set()).add((en, cn))
        if row.get('MAME Name', '').strip():
            exact.setdefault(key(row['MAME Name']), set()).add((en, cn))
        stems.setdefault(key(base(en)), set()).add(cn)
        inverse.setdefault(key(base(cn)), set()).add(base(en))
    return exact, stems, inverse


def resolve_name(filename, exact, stems, inverse, canonical=None):
    chosen = canonical or filename
    rows = exact.get(key(chosen), set())
    values = {cn for _, cn in rows}
    if len(values) == 1:
        title = next(iter(values))
        # Keep region/revision labels visible even when the alias omits them.
        tags = chosen[len(base(chosen)):].strip()
        if tags and not all(tag in title for tag in re.findall(r'\([^)]*\)', tags)):
            title += ' ' + tags
        return title, (next(iter(rows))[0] if len(rows) == 1 else chosen), 'content' if canonical else 'exact_name'
    values = stems.get(key(base(chosen)), set())
    if len(values) == 1 and not chinese(filename):
        suffix = filename[len(base(filename)):].strip()
        return next(iter(values)) + (' ' + suffix if suffix else ''), chosen, 'unique_title_family'
    english = inverse.get(key(base(filename)), set())
    return filename, (next(iter(english)) if len(english) == 1 else chosen), 'filename'


def image_bytes(raw):
    with Image.open(io.BytesIO(raw)) as im:
        if im.format != 'PNG' or im.width*im.height > 8_000_000:
            raise ValueError('Unsupported artwork')
        im.verify()
    return raw


def arcade_name_hint(path, platform):
    """Read display-only short names from an APF instance, without executing it."""
    try:
        instance = json.loads(path.read_text(encoding='utf-8-sig'))['instance']
        if platform == 'ng':
            value = instance.get('data_path', '').rstrip('/').rsplit('/', 1)[-1]
        else:
            filenames = [r['filename'] for r in instance.get('data_slots', [])
                         if r.get('id') in (1, '1', '0x1', '0x01', '0x0001', '0x00000001')]
            value = Path(filenames[0]).stem if len(filenames) == 1 else ''
        return value if re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value) else None
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def thumbnail_index(store, platform):
    repo = 'libretro-thumbnails/' + PLATFORMS[platform].replace(' ', '_')
    url = 'https://api.github.com/repos/' + repo + '/git/trees/master?recursive=1'
    tree = json.loads(store.get(url))
    if tree.get('truncated') or not re.fullmatch('[0-9a-f]{40}', tree.get('sha', '')):
        raise ValueError('Incomplete artwork index')
    exact, families, preferred, literal = {}, {}, {}, {}
    priorities = {'Named_Boxarts': 0, 'Named_Titles': 1, 'Named_Snaps': 2}
    for row in tree['tree']:
        path = row['path']
        if row['type'] != 'blob' or not path.endswith('.png'):
            continue
        if len(Path(path).parts) != 2:
            continue
        category = Path(path).parts[0]
        if category not in priorities:
            continue
        stem = Path(path).stem
        previous = preferred.get(stem)
        if previous is None or priorities[category] < previous[0]:
            preferred[stem] = priorities[category], path
    for stem, (_, path) in preferred.items():
        exact.setdefault(key(stem), set()).add(path)
        families.setdefault(key(base(stem)), set()).add(path)
        literal.setdefault(artwork_name(stem), set()).add(path)
    return repo, tree['sha'], exact, families, literal


def artwork_name(value):
    # Keep edition punctuation. Slash is represented by '_' in these filenames.
    return unicodedata.normalize('NFKC', value).replace('/', '_').casefold()


def thumbnail_urls(index, names):
    repo, ref, exact, families = index[:4]
    literal = index[4] if len(index) > 4 else {}
    for name in filter(None, names):
        paths = literal.get(artwork_name(name), set())
        if len(paths) == 1:
            yield raw_url(repo, ref, next(iter(paths)))
    for collection in (exact, families):
        for name in filter(None, names):
            lookup = key(name if collection is exact else base(name))
            paths = collection.get(lookup, set())
            if len(paths) == 1:
                yield raw_url(repo, ref, next(iter(paths)))


def enrich(card, out, cache, systems=None, *, online=True, local_titles=None, local_covers=None, progress=None, fetch=None):
    card, out, cache = map(lambda p: Path(p).resolve(), (card, out, cache))
    for a, b in ((card, out), (card, cache), (out, cache)):
        delivery.separate(a, b)
    if out.exists():
        raise ValueError('Use a new metadata output directory')
    found = build_menus.discover(card)
    selected = list(found) if systems is None else list(systems)
    if not selected or any(s not in found for s in selected):
        raise ValueError('Selected system has no supported files')
    aliases = delivery.read(local_titles) if local_titles else {}
    if not isinstance(aliases, dict) or any(not isinstance(v, str) or not v.strip() for v in aliases.values()):
        raise ValueError('Invalid local title aliases')
    covers = Path(local_covers).resolve() if local_covers else None
    for path in (Path(local_titles).resolve() if local_titles else None, covers):
        if path:
            delivery.separate(out, path)
    store = Cache(cache, online, fetch)
    out.mkdir(parents=True)
    rows, titles, errors, catalogs, artwork = [], {}, [], {}, {}
    offline_misses = set()
    recorded_errors = set()

    def source_issue(platform, kind, exc):
        if isinstance(exc, OfflineCacheMiss):
            offline_misses.add((platform, kind))
            return
        issue = (platform, kind, str(exc))
        if issue not in recorded_errors:
            recorded_errors.add(issue)
            errors.append({'platform': platform, 'kind': kind, 'message': str(exc)})

    total = sum(len(found[s]) for s in selected)
    for system in selected:
        for relative in found[system]:
            rom = delivery.safe_path(card, relative)
            platform = Path(relative).parts[1]
            if rom.suffix.lower() == '.sgx':
                platform = 'sgx'
            if platform == 'wonderswan' and rom.suffix.lower() == '.wsc':
                platform = 'wonderswan_color'
            if platform not in catalogs:
                name = PLATFORMS[platform]
                table, dat = ({}, {}, {}), {}
                if platform not in ('sg1000','arduboy'):
                    url = raw_url('yingw/rom-name-cn', CHINESE_REF, CSV_NAMES.get(platform, name) + '.csv')
                    try:
                        table = translations(store.get(url))
                    except (OSError, ValueError) as exc:
                        source_issue(platform, 'names', exc)
                if platform not in ARCADE | {'arduboy'}:
                    url = raw_url('libretro/libretro-database', DATABASE_REF, 'metadat/no-intro/' + name + '.dat')
                    try:
                        dat = parse_dat(store.get(url))
                    except (OSError, ValueError) as exc:
                        source_issue(platform, 'database', exc)
                catalogs[platform] = table, dat
            (exact, stems, inverse), dat = catalogs[platform]
            canonical = None
            # Avoid reading every cartridge twice when its full title is known.
            if platform not in ARCADE and key(rom.stem) not in exact and dat:
                digest = hashlib.sha1()
                with rom.open('rb') as source:
                    for chunk in iter(lambda: source.read(1024*1024), b''):
                        digest.update(chunk)
                canonical = dat.get((digest.hexdigest(), rom.stat().st_size))
            title, art_name, match = resolve_name(rom.stem, exact, stems, inverse, canonical)
            if platform in ARCADE:
                hint = arcade_name_hint(rom, platform)
                if hint and len(exact.get(key(hint), set())) == 1:
                    hinted_title, art_name, _ = resolve_name(hint, exact, stems, inverse)
                    if not chinese(rom.stem):
                        title, match = hinted_title, 'instance_name'
            # Conflicting translations still identify a known catalog name;
            # ambiguity must not enable a different local-alias artwork match.
            unresolved_name = (match == 'filename' and art_name == rom.stem
                               and key(rom.stem) not in exact
                               and key(base(rom.stem)) not in stems
                               and key(base(rom.stem)) not in inverse)
            if relative in aliases:
                title, match = aliases[relative], 'local_alias'
            # A retained Chinese display name can identify a representative
            # cover even when the original filename is romanized. Only use a
            # unique catalog work, and never contradict a content match.
            local_art_hint = None
            if relative in aliases and canonical is None and unresolved_name:
                works = inverse.get(key(base(title)), set())
                if len(works) == 1:
                    local_art_hint = next(iter(works))
            titles[relative] = title
            destination = delivery.safe_path(out/'covers', str(Path(relative).with_suffix('.png')).replace('\\', '/'))
            cover_source = None
            local = delivery.safe_path(covers, str(Path(relative).with_suffix('.png')).replace('\\', '/')) if covers else None
            if local and local.is_file():
                image_bytes(local.read_bytes())
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(local, destination)
                cover_source = 'local'
            else:
                if platform not in artwork:
                    try:
                        artwork[platform] = None if platform=='arduboy' else thumbnail_index(store, platform)
                    except (OSError, ValueError, KeyError) as exc:
                        artwork[platform] = None
                        source_issue(platform, 'artwork_index', exc)
                # Exact or unique-title-family matches; ambiguous editions stay visible in the report.
                names = list(dict.fromkeys([art_name, canonical, rom.stem]))
                # Exhaust filename/content matches before considering the
                # local display hint; a box image is not ROM identification.
                urls = list(thumbnail_urls(artwork[platform], names)) if artwork[platform] else []
                if artwork[platform] and local_art_hint:
                    urls.extend(thumbnail_urls(artwork[platform], [local_art_hint]))
                for url in dict.fromkeys(urls):
                    try:
                        raw = image_bytes(store.get(url, 4*1024*1024))
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_bytes(raw)
                        cover_source = url
                        break
                    except OfflineCacheMiss as exc:
                        source_issue(platform, 'artwork', exc)
                    except FileNotFoundError:
                        continue
                    except urllib.error.HTTPError as exc:
                        if exc.code != 404:
                            source_issue(platform, 'artwork', exc)
                    except (OSError, ValueError) as exc:
                        source_issue(platform, 'artwork', exc)
            rows.append({'path': relative, 'title': title, 'match': match, 'cover': cover_source,
                         'content_identity_confirmed': bool(canonical),
                         'local_artwork_hint': local_art_hint})
            if progress:
                progress(len(rows), total, title)
    (out/'covers').mkdir(exist_ok=True)
    delivery.write(out/'titles.json', titles)
    receipt = {'games': rows, 'matched_titles': sum(r['title'] != Path(r['path']).stem for r in rows),
               'matched_covers': sum(bool(r['cover']) for r in rows), 'missing_covers': [r['path'] for r in rows if not r['cover']],
               'errors': errors, 'offline_cache_misses': [
                   {'platform': platform, 'kind': kind} for platform, kind in sorted(offline_misses)
               ], 'sources': store.provenance, 'ROM_uploads': 0, 'card_writes': 0,
               'scope': 'Display metadata only. Name matches never select cheats or establish save compatibility.'}
    delivery.write(out/'metadata-report.json', receipt)
    return receipt
