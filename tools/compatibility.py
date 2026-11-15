#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Install the original, pinned disc and special-cartridge cores as companions."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import urllib.request
from zipfile import ZipFile

from apf_metadata import REQUIRED_JSON
import delivery


@dataclass(frozen=True)
class Release:
    platform: str
    core: str
    url: str
    sha256: str
    size: int
    core_files: tuple
    assets: tuple = ()

    @property
    def paths(self):
        return tuple(f'Cores/{self.core}/{name}' for name in self.core_files) + self.assets + (
            f'Platforms/{self.platform}.json', f'Platforms/_images/{self.platform}.bin')


COMMON = ('core.json', 'data.json', 'video.json', 'audio.json', 'input.json',
          'interact.json', 'variants.json', 'icon.bin', 'info.txt')
RELEASES = {
    'SFC-COMPAT': Release('snes', 'agg23.SNES',
        'https://github.com/agg23/openfpga-SNES/releases/download/0.4.4/agg23.SNES_0.4.4_2024-09-16.zip',
        'f0c5d4dcec244cc55e0b4f6096be92555eb6f309602045685963600d6653d511', 2872291,
        COMMON+('loader.bin', 'snes_main.rev', 'snes_pal.rev', 'snes_spc.rev')),
    'PCE-CD': Release('pcecd', 'Mazamars312.PC Engine CD',
        'https://github.com/Mazamars312/openfpga-pcengine-cd/releases/download/Mazamars312.PCECD.0.2.3-BETA/OPENFPGA-PCECD-0.2.3-BETA.zip',
        'c4e1b7e7bea48f7f8d682f255f3b6f6a2897ca45febcd6c78f9c828eec7d831b', 852943,
        COMMON+('pce.rev', 'instance-packager.json'),
        ('Assets/pcecd/Mazamars312.PC Engine CD/pce_mpu_bios.bin',
         'Assets/pcecd/Mazamars312.PC Engine CD/image_template.json')),
    'MD-PAL': Release('genesis', 'Spiritualized.Genesis',
        'https://github.com/spiritualized1997/openFPGA-Genesis/releases/download/1.0.8/Spiritualized_Genesis_1.0.8_2022_11_08.zip',
        'f6d48b55e17b3a4a8d923f994a24e21be292c5422c21d4ffb12345051a38439b', 875517,
        COMMON+('gen_chip32.bin', 'genesis.rev')),
    'GBA-MEMORIES': Release('gba', 'mincer_ray.GBA',
        'https://github.com/mincer-ray/openfpga-GBA/releases/download/v1.0.1/mincer_ray.GBA_1.0.1.zip',
        'f7ff9e2fdf3e696037632db8f2dee2b0e822cace33de994e0b756388dd0e57ba', 948420,
        COMMON+('bitstream.rbf_r',)),
    'GBA-CHEATS': Release('gba', 'kroy.GBA',
        'https://github.com/kroy-the-rabbit/openfpga-GBA-cheats/releases/download/v0.9999.20260915/kroy.GBA_0.9999.20260915.zip',
        '9751dd61a159fe2a6fe189636ae97945b1265838765326d34cbf298ba3f0b05e', 916476,
        COMMON+('bitstream.rbf_r',)),
}
BIOS_NAMES = ('bios_3_0_usa.pce', 'bios_3_0_jap.pce', 'bios_2_0_usa.pce', 'bios_2_0_jap.pce', 'bios_1_0_jap.pce')
GBA_BIOS = 'Assets/gba/common/gba_bios.bin'
GBA_MODES = ('GBA-MEMORIES', 'GBA-CHEATS')


def cue_tracks(card, cue):
    rel = cue.relative_to(card).as_posix()
    if cue.stat().st_size > 16384:
        raise ValueError('CUE 文件超过核心的 16 KiB 限制')
    raw = cue.read_bytes()
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ValueError('CUE 需要 UTF-8 编码') from exc
    if text.startswith('\ufeff') or '\0' in text:
        raise ValueError('CUE 需要无 BOM 的 UTF-8 文本')
    tracks = []
    track_count = 0
    current_file = None
    current_size = 0
    sector_size = 0
    active_track = False
    previous_index = -1
    index_zero = None
    pregap = 0
    has_pregap = False
    previous_file_sectors = {}
    sector_sizes = {'MODE1/2048': 2048, 'MODE1/2352': 2352, 'AUDIO': 2352, 'CDG': 2448}
    for original in text.splitlines():
        if len(original.encode('utf-8')) >= 128:
            raise ValueError('CUE 单行超过核心读取限制')
        line = original.strip(' ')
        command = line.split(maxsplit=1)[0] if line else ''
        if command.upper() in ('FILE', 'TRACK', 'INDEX', 'PREGAP') and (command != command.upper() or '\t' in original):
            raise ValueError('CUE 关键字需要大写，并使用空格分隔')
        if command == 'FILE':
            match = re.fullmatch(r'FILE (?:"([^"]+)"|([^ ]+)) +BINARY', line)
            if not match:
                raise ValueError('光盘核心需要 CUE 引用 BIN 音轨')
            if active_track:
                raise ValueError('上一条音轨缺少 INDEX 01')
            file = match[1] or match[2]
            if not file.lower().endswith('.bin') or '/' in file or '\\' in file:
                raise ValueError('CUE 音轨必须是同一游戏目录下的 BIN')
            path = delivery.safe_path(card, rel.rsplit('/', 1)[0]+'/'+file)
            if not path.is_file() or not path.stat().st_size:
                raise ValueError('CUE 缺少对应 BIN 音轨')
            current_file = path.relative_to(card).as_posix()
            current_size = path.stat().st_size
            previous_index = -1
            pregap = 0
        elif command == 'TRACK':
            match = re.fullmatch(r'TRACK +(\d{1,2}) +([^ ]+)', line)
            if (current_file is None or active_track or not match or int(match[1]) != track_count+1
                    or int(match[1]) > 99 or match[2] not in sector_sizes):
                raise ValueError('CUE 音轨必须从 01 连续编号，并使用支持的格式')
            sector_size = sector_sizes[match[2]]
            previous = previous_file_sectors.setdefault(current_file, sector_size)
            if previous != sector_size or current_size % sector_size:
                raise ValueError('BIN 长度或混合音轨的扇区大小不匹配')
            active_track = True
            index_zero = None
            has_pregap = False
        elif command in ('INDEX', 'PREGAP'):
            pattern = r'INDEX +(0?0|0?1) +(\d{2}):(\d{2}):(\d{2})' if command == 'INDEX' else r'PREGAP +(\d{2}):(\d{2}):(\d{2})'
            match = re.fullmatch(pattern, line)
            if not active_track or not match:
                raise ValueError('CUE 缺少有效的轨道时间')
            minute, second, frame = map(int, match.groups()[-3:])
            if second >= 60 or frame >= 75:
                raise ValueError('CUE 音轨时间越界')
            position = (minute*60+second)*75+frame
            if command == 'PREGAP':
                if has_pregap or index_zero is not None:
                    raise ValueError('CUE PREGAP 重复或顺序错误')
                pregap += position
                has_pregap = True
                continue
            if position <= previous_index or (position+1)*sector_size > current_size:
                raise ValueError('CUE INDEX 超出对应 BIN 或顺序错误')
            if int(match[1]) == 0:
                if index_zero is not None:
                    raise ValueError('CUE INDEX 00 重复')
                index_zero = position
                continue
            if index_zero is not None and index_zero > position:
                raise ValueError('CUE INDEX 00 必须在 INDEX 01 之前或与其相同')
            # The original loader adds the accumulated pregap to offsets in a shared BIN.
            if (track_count == 0 or previous_index >= 0) and (position+pregap+1)*sector_size > current_size:
                raise ValueError('CUE PREGAP 让音轨起点超出 BIN')
            previous_index = position
            track_count += 1
            tracks.append(current_file)
            active_track = False
    if not tracks or active_track:
        raise ValueError('CUE 需要 1 至 99 个有效音轨')
    return list(dict.fromkeys(tracks))


def scan(card, systems):
    special, invalid_sfc = [], []
    standard = 0
    sfc = delivery.module('experiments/console_coverflow/sfc_headers.py')
    for rel in systems.get('SFC', []):
        path = delivery.safe_path(card, rel)
        try:
            info = sfc.identify(path, path.stat().st_size, allow_special=True)
        except ValueError:
            invalid_sfc.append(rel)
            continue
        if info['pal'] or info['kind'] not in (0, 1, 2) or info['ram'] > 7:
            special.append(rel)
        else:
            standard += 1
    pal_md, invalid_md = [], []
    standard_md = 0
    if systems.get('MD'):
        md = delivery.module('experiments/console_coverflow/library.py')
        for rel in systems['MD']:
            path = delivery.safe_path(card, rel)
            try:
                info = md.cart_config('genesis', path, path.stat().st_size, allow_pal=True)
            except ValueError:
                invalid_md.append(rel)
                continue
            if info['rom_config']:
                pal_md.append(rel)
            else:
                standard_md += 1
    discs, unsupported = [], []
    for path in sorted(delivery.safe_path(card, 'Assets/pcecd/common').rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(card).as_posix()
        delivery.safe_path(card, rel)
        if path.suffix.lower() == '.chd':
            unsupported.append({'path': rel, 'reason': '该原生核心需要 CUE/BIN'})
        elif path.suffix.lower() == '.cue':
            try:
                discs.append({'path': rel, 'tracks': cue_tracks(card, path)})
            except ValueError as exc:
                unsupported.append({'path': rel, 'reason': str(exc)})
    return {'special_sfc': special, 'standard_sfc': standard, 'invalid_sfc': invalid_sfc,
            'pal_md': pal_md, 'standard_md': standard_md, 'invalid_md': invalid_md,
            'pcecd': discs, 'unsupported_discs': unsupported}


def bios_files(card):
    files = []
    for name in BIOS_NAMES:
        path = delivery.safe_path(card, 'Assets/pcecd/common/'+name)
        if path.exists():
            if not path.is_file() or path.stat().st_size not in (0x20000, 0x40000):
                raise ValueError('System Card BIOS 容量不正确 · '+name)
            files.append(path)
    return files


def legacy_md_interact(raw):
    # The pinned original has two extra commas in its Region option list.
    return raw.replace(b'"Japan",', b'"Japan"').replace(b'"Europe",', b'"Europe"')


def existing_core(card, release):
    path = delivery.safe_path(card, f'Cores/{release.core}')
    if not path.exists() or (path.is_dir() and not any(path.iterdir())):
        return 'absent'
    try:
        definitions = {}
        for name in REQUIRED_JSON:
            source = delivery.safe_path(path, name)
            key = Path(name).stem
            if release.core == 'Spiritualized.Genesis' and name == 'interact.json':
                definitions[key] = json.loads(legacy_md_interact(source.read_bytes()))[key]
            else:
                definitions[key] = delivery.read(source)[key]
        if any(value.get('magic') != 'APF_VER_1' for value in definitions.values()):
            return 'partial'
        meta = definitions['core']
        metadata = meta['metadata']
        if release.platform not in metadata['platform_ids'] or metadata['author']+'.'+metadata['shortname'] != release.core:
            return 'partial'
        if any(not delivery.safe_path(card, rel).is_file() for rel in release.assets):
            return 'partial'
        if not meta['cores']:
            return 'partial'
        filenames = [item['filename'] for item in meta['cores']]
        vm = meta['framework'].get('chip32_vm')
        if vm:
            filenames.append(vm)
        for name in filenames:
            binary = delivery.safe_path(path, name)
            if Path(name).name != name or not binary.is_file() or not binary.stat().st_size:
                return 'partial'
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return 'partial'
    return 'available'


def release_zip(system, cache, online):
    release = RELEASES[system]
    archive = cache/(system+'.zip')
    if archive.is_file():
        if archive.stat().st_size != release.size or delivery.sha(archive) != release.sha256:
            raise ValueError('Compatibility release cache checksum differs')
        return archive
    if not online:
        return None
    request = urllib.request.Request(release.url, headers={'User-Agent': 'Pocket-Lab-Assistant/1'})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read(release.size+1)
    if len(raw) != release.size or hashlib.sha256(raw).hexdigest() != release.sha256:
        raise ValueError('Downloaded compatibility release checksum differs')
    cache.mkdir(parents=True, exist_ok=True)
    temp = archive.with_suffix('.part')
    temp.write_bytes(raw)
    temp.replace(archive)
    return archive


def prepare(card, scan_result, cache, online, systems, *, detected=True, gba_modes=()):
    wanted = []
    if detected and scan_result['special_sfc'] and 'SFC' in systems:
        wanted.append('SFC-COMPAT')
    if detected and scan_result['pal_md'] and 'MD' in systems:
        wanted.append('MD-PAL')
    if detected and scan_result['pcecd']:
        wanted.append('PCE-CD')
    if 'GBA' in systems:
        wanted.extend(name for name in GBA_MODES if name in gba_modes)
    components, report = [], {}
    for system in wanted:
        release = RELEASES[system]
        if system == 'PCE-CD':
            try:
                if not bios_files(card):
                    raise ValueError('需要在 Assets/pcecd/common 放入自己的 System Card BIOS')
            except ValueError as exc:
                report[system] = str(exc)
                continue
        existing = existing_core(card, release)
        if existing != 'absent':
            report[system] = ('保留卡上现有原版核心' if existing == 'available'
                              else '卡上原版核心文件不完整，保留现有文件')
            continue
        try:
            archive = release_zip(system, cache, online)
        except (OSError, ValueError) as exc:
            report[system] = '暂未下载核心 · '+str(exc)
            continue
        if archive is None:
            report[system] = '离线缓存中没有这个核心'
            continue
        components.append({'id': system, 'package': str(archive)})
        report[system] = '准备补装原作者的入口'
    return components, report


def stage(card, system, archive, out):
    release = RELEASES[system]
    if archive.stat().st_size != release.size or delivery.sha(archive) != release.sha256:
        raise ValueError('Compatibility release checksum differs')
    if existing_core(card, release) != 'absent':
        raise ValueError('An existing original core appeared after preparation')
    guards = []
    bios_paths = []
    if system == 'PCE-CD':
        paths = bios_files(card)
        if not paths:
            raise ValueError('PCE CD needs a user-supplied System Card BIOS')
        bios_paths = [path.relative_to(card).as_posix() for path in paths]
        guards.extend(delivery.snapshot(path, rel) for path, rel in zip(paths, bios_paths))
    elif system in GBA_MODES:
        path = delivery.safe_path(card, GBA_BIOS)
        if not path.is_file() or path.stat().st_size != 16384:
            raise ValueError('Provide your own 16384-byte GBA BIOS in '+GBA_BIOS)
        bios_paths = [GBA_BIOS]
        guards.append(delivery.snapshot(path, GBA_BIOS))
    changes, adjusted = [], []
    with ZipFile(archive) as package:
        for rel in release.paths:
            target = delivery.safe_path(card, rel)
            previous = delivery.digest(target)
            if previous is not None:
                if rel.startswith('Platforms/') or (rel in release.assets and hashlib.sha256(package.read(rel)).hexdigest() == previous):
                    guards.append(delivery.snapshot(target, rel))
                    continue
                raise ValueError('Original companion file already exists: '+rel)
            dest = delivery.safe_path(out, rel)
            dest.parent.mkdir(parents=True, exist_ok=True)
            raw = package.read(rel)
            if system == 'MD-PAL' and rel.endswith('/interact.json'):
                raw = legacy_md_interact(raw)
                json.loads(raw)
                adjusted.append(rel)
            if system == 'MD-PAL' and rel.endswith('/data.json'):
                definition = json.loads(raw)
                slot = definition['data']['data_slots'][0]
                if slot['extensions'] != ['md', 'bin']:
                    raise ValueError('Original MD cartridge extensions differ')
                slot['extensions'].append('gen')
                raw = (json.dumps(definition, indent=2)+'\n').encode()
                adjusted.append(rel)
            dest.write_bytes(raw)
            changes.append({**delivery.snapshot(dest, rel), 'source': str(out), 'previous_sha256': None})
    return {'identity': delivery.identity(card), 'changes': changes, 'guards': guards,
            'summary': {'operation': 'original_compatibility_entry', 'core': release.core,
                        'release_url': release.url, 'bios_paths': bios_paths, 'adjusted_definitions': adjusted}}
