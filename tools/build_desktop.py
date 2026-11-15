#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build a relocatable Windows assistant with public tools and reviewed native packages."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import PIL
import core_candidates
import delivery
import additional_menus
from apf_metadata import check_core, check_candidate_bitstream

ROOT = Path(__file__).resolve().parents[1]
ADDED = ['tools/library_catalog.py', 'tools/progress_import.py', 'tools/assistant_workflow.py',
         'tools/pocket_assistant.py', 'tools/build_desktop.py', 'tools/core_candidates.py', 'tools/native_cheats.py',
         'tools/compatibility.py', 'tools/platform_frontend.py',
         'tools/additional_menus.py','tools/additional_candidates.json','tools/group_cn_menus.py',
         'LICENSES/GPL-2.0.txt', 'docs/PREVIEW-SOURCES.md', 'docs/ADDITIONAL-CORES.md',
         'tests/test_additional_menus.py', 'tests/test_atari_coverflow.py', 'tests/test_arcade_menus.py',
         'tests/test_library_catalog.py', 'tests/test_native_cheats.py', 'tests/test_platform_frontend.py',
         'tests/test_progress_import.py', 'tests/test_build_desktop.py']

# These retained Sega builds use the separately bundled corresponding-source ZIP.
COMPANION_RECEIPTS = {
    'GG': 'fa9450046f69f663a4b7484b0bd5c8c2a5d84916c4cc9b002dd342b885cfc11b',
    'SMS': '05487b006e1d71f8b03a6d5c328caf52809a7a10c0ac3a6fe7580cd95b1370dc',
    'SG1000': 'cedc0bbd0203c003384de16b8a99dd93941b12e6d74b038efe2bff7700994046',
}
COMPANION_SHA256 = 'c8bd00b9b8a2c344e628ed1ee9ee9dfc2e8581d9cd598de6ccef9fba412a3b46'


def validate_gba(package):
    """Check the separately reviewed GBA receipt and its corresponding source."""
    receipt = delivery.read(package/'build-receipt.json')
    if delivery.sha(package/'build-receipt.json') != '0e3c069f2694fd7a4d100c5e0876ef6408b8eb9f8013381552798a189cfaa54e':
        raise ValueError('GBA receipt is not the reviewed repair build')
    core = package/'core/Cores/pocketlab.GBA'
    metadata = check_core(core)
    if (check_candidate_bitstream(core/'gba.rbf_r') != receipt['bitstream_sha256']
            or metadata['metadata']['version'] != receipt['version']
            or receipt['minimum_reported_slack_ns'] < 0):
        raise ValueError('GBA repair identity or timing differs')
    for row in receipt['files']:
        delivery.check_record(package/'core', row, 'GBA')
    for rel, expected in receipt['source_files'].items():
        if delivery.sha(delivery.safe_path(package/'sources',rel)) != expected:
            raise ValueError('GBA corresponding source differs: '+rel)
    return receipt


def reviewed_files(package, system):
    """The same reviewed inventory governs explicit and inherited packages."""
    package = Path(package)
    if system in additional_menus.PROFILES:
        receipt = additional_menus.registered(package, system)
    elif system == 'GBA':
        receipt = validate_gba(package)
    elif system in COMPANION_RECEIPTS:
        if delivery.sha(package/'build-receipt.json') != COMPANION_RECEIPTS[system]:
            raise ValueError('Sega receipt is not the reviewed companion build: '+system)
        receipt = delivery.read(package/'build-receipt.json')
        short = delivery.PROFILES[system][0]
        core = package/'core'/('Cores/pocketlab.'+short)
        check_core(core)
        for row in receipt['files']:
            delivery.check_record(package/'core', row, system)
    else:
        core_candidates.validate(package, system)
        receipt = delivery.read(package/'build-receipt.json')
    files = ['build-receipt.json']
    core_files = {row['path'] for row in receipt['files']}
    if len(core_files) != len(receipt['files']):
        raise ValueError('Duplicate reviewed core path: '+system)
    if system == 'GB-GBC':
        manifest = delivery.read(package/'core/release-manifest.json')
        if any(manifest.get(k) != receipt[k] for k in ('files', 'features', 'version', 'bitstream_sha256')):
            raise ValueError('GB/GBC release manifest differs from the reviewed build')
        core_files.add('release-manifest.json')
    actual = {p.relative_to(package/'core').as_posix() for p in (package/'core').rglob('*') if p.is_file()}
    if actual != core_files:
        raise ValueError('Unexpected core package files: '+system)
    files.extend('core/'+rel for rel in sorted(core_files))
    if system not in COMPANION_RECEIPTS:
        files.extend('sources/'+rel for rel in receipt['source_files' if system == 'GBA' else 'source_inputs'])
    return {rel: delivery.safe_path(package, rel) for rel in files}


def build(preview, out, sources=None, candidates=None):
    preview, out = Path(preview).resolve(), Path(out).resolve()
    if out.exists() or out.is_relative_to(preview) or preview.is_relative_to(out):
        raise ValueError('A fresh output separate from the reviewed preview is required')
    required = next(line.split('==', 1)[1] for line in (ROOT/'requirements.txt').read_text().splitlines() if line.startswith('Pillow=='))
    if PIL.__version__ != required:
        raise ValueError('Install requirements.txt in the isolated build environment first')
    candidates = {system: Path(path).resolve() for system, path in (candidates or {}).items()}
    package_files = {}
    inherited = {}
    seen = set()
    for line in (preview/'SHA256SUMS.txt').read_text(encoding='utf8').splitlines():
        digest, rel = line.split('  ', 1)
        if not rel.startswith('packages/'):
            continue
        source = delivery.safe_path(preview, rel)
        parts = Path(rel).parts
        if len(parts) < 3 or parts[1] not in delivery.PROFILES or rel in seen:
            raise ValueError('Unexpected reviewed package path: '+rel)
        seen.add(rel)
        if delivery.sha(source) != digest:
            raise ValueError('Reviewed package checksum differs: '+rel)
        if parts[1] not in candidates:
            inherited.setdefault(parts[1], set()).add(rel)
    for system, inventory in inherited.items():
        prefix = 'packages/'+system+'/'
        approved = {prefix+rel: source for rel, source in reviewed_files(preview/'packages'/system, system).items()}
        if inventory != set(approved):
            raise ValueError('Inherited package manifest has unreviewed or missing files: '+system)
        package_files.update(approved)
    for system, candidate in candidates.items():
        if system not in delivery.PROFILES:
            raise ValueError('Unknown candidate system: '+system)
        delivery.separate(out, candidate)
        for rel, source in reviewed_files(candidate, system).items():
            package_files[f'packages/{system}/{rel}'] = source
    included = {Path(rel).parts[1] for rel in package_files}
    baseline = set(delivery.PROFILES) - set(additional_menus.PROFILES)
    if not baseline <= included or included - set(delivery.PROFILES):
        raise ValueError('Expected baseline packages and only supported reviewed additions')
    if included & COMPANION_RECEIPTS.keys():
        if sources is None or delivery.sha(Path(sources)) != COMPANION_SHA256:
            raise ValueError('The retained Sega packages require their reviewed corresponding-source companion')
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--version'], check=True)
    work = out.with_name(out.name+'-build')
    if work.exists():
        raise ValueError('Retain the previous build directory and choose a new output')
    work.mkdir(parents=True)
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--windowed',
               '--name', 'PocketLab', '--distpath', str(work/'dist'), '--workpath', str(work/'work'),
               '--specpath', str(work), '--paths', str(ROOT/'tools'), '--collect-all', 'PIL',
               '--hidden-import', 'platform', '--hidden-import', 'gzip', '--hidden-import', 'struct',
               str(ROOT/'tools/pocket_assistant.py')]
    with (work/'build.log').open('w', encoding='utf8') as log:
        subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
    shutil.copytree(work/'dist/PocketLab', out)
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    # Include public runtime sources, not private inventories, caches, ROMs or compiled projects.
    extra = [p.relative_to(ROOT).as_posix()
             for name in ('console_coverflow', 'native_features', 'gb_features',
                          *sorted({row['family'] for row in additional_menus.PROFILES.values()}))
             if (ROOT/'experiments'/name).is_dir()
             for p in (ROOT/'experiments'/name).iterdir() if p.suffix in ('.py', '.sv', '.md', '.json')]
    for rel in sorted(set(filter(None, tracked+ADDED+extra))):
        source = ROOT/rel
        if not source.is_file() or source.is_symlink():
            raise ValueError('Unexpected public input: '+rel)
        target = out/rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for rel, source in package_files.items():
        target = delivery.safe_path(out, rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    if sources:
        source = Path(sources).resolve()
        shutil.copy2(source, out/source.name)
    (out/'开始使用.txt').write_text(
        '运行 PocketLab.exe。选择卡或卡副本与电脑工作目录，识别机种，然后准备游戏库。\n'
        '查看结果后点击“备份并安装”。备份核对通过才会更新文件；恢复菜单会保留新进度。\n'
        'ROM、BIOS、存档均由你自备。普通存档和即时存档不同，助手不会猜测转换即时存档。\n'
        '这是开发预览。各核心功能以文档中的已实现范围为准，硬件体验仍需验收。\n'
        '整个文件夹应一起移动；无需另装 Python。\n\n'
        'Run PocketLab.exe, select the card and a local workspace, inspect systems, then prepare.\n'
        'Review the result and use Backup and install. Restore preserves newly created progress.\n'
        'Supply your own games and BIOS. This development preview needs hardware acceptance.\n'
        'Move the whole folder together. Python is included.\n', encoding='utf8')
    receipt = {'python': sys.version, 'reviewed_package_files': len(package_files),
               'updated_candidates': sorted(candidates), 'frozen': True,
               'ROMs_included': False, 'BIOS_included': False, 'personal_saves_included': False,
               'hardware_acceptance': 'pending', 'build_command': command}
    # Build command paths are local evidence only, not part of the distributed receipt.
    (work/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf8')
    hashes = {p.relative_to(out).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in out.rglob('*') if p.is_file()}
    (out/'SHA256SUMS.txt').write_text(''.join(f'{digest}  {rel}\n' for rel,digest in sorted(hashes.items())), encoding='utf8')
    return {'path': str(out), 'files': len(hashes), 'bytes': sum(p.stat().st_size for p in out.rglob('*') if p.is_file())}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--sources', type=Path)
    parser.add_argument('--candidate', action='append', default=[], metavar='SYSTEM=DIR',
                        help='Replace a bundled core with a registered, reviewed candidate')
    args = parser.parse_args()
    candidates = {}
    for value in args.candidate:
        system, sep, path = value.partition('=')
        if not sep or not path or system in candidates:
            parser.error('--candidate requires a unique SYSTEM=DIR')
        candidates[system] = path
    print(json.dumps(build(args.preview, args.out, args.sources, candidates), indent=2))
