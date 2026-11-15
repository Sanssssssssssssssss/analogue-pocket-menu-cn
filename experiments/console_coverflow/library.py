#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build native console menu pages against ROMs at their existing paths."""

import argparse
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path, PurePosixPath

spec = importlib.util.spec_from_file_location('console_prepare', Path(__file__).with_name('prepare.py'))
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)
EXPERIMENTS, PROFILES, load = adapter.EXPERIMENTS, adapter.PROFILES, adapter.load

shared = load('console_atlas', EXPERIMENTS/'nes_coverflow/library.py')
sfc = load('console_sfc_headers', Path(__file__).with_name('sfc_headers.py'))
cps2 = load('console_cps2', Path(__file__).with_name('cps2.py'))
LABELS = {'pce':'PC Engine', 'genesis':'世嘉 MD', 'snes':'超级任天堂', 'jtcps2':'卡普空街机'}
EXTENSIONS = {'pce': {'.pce', '.sgx'}, 'genesis': {'.md', '.gen', '.bin'}, 'snes': {'.sfc','.smc','.bin'}, 'jtcps2': {'.json'}}


def cart_config(platform, path, length, allow_pal=False):
    if length < 512 or length > PROFILES[platform][2] or length % 4:
        raise ValueError('Cartridge size is outside the supported range')
    if platform=='snes':
        return sfc.cartridge(path,length)
    if platform == 'pce':
        if length % 8192 not in (0,512):
            raise ValueError('Expected a HuCard size with an optional 512-byte header')
        return {'rom_config':int(path.suffix.lower()=='.sgx')}
    with path.open('rb') as source:
        header = source.read(512)
    if header[0x100:0x104] != b'SEGA':
        raise ValueError('Expected a linear Genesis ROM with a SEGA header')
    region = header[0x1f0:0x200].strip(b'\0 ').upper()
    pal_only = (region in (b'EUROPE', b'EUR', b'PAL', b'8', b'A')
                or region[:1] == b'E' and not any(c in region[:3] for c in (b'J', b'U')))
    if pal_only and not allow_pal:
        raise ValueError('PAL-only cartridge needs a PAL-capable core')
    return {'rom_config':int(pal_only)}


def build(platform, source, out, titles=None, covers=None, groups=None):
    source, out = Path(source).resolve(), Path(out).resolve()
    if out.exists() or source.is_relative_to(out) or out.is_relative_to(source):
        raise ValueError('Use a fresh local staging directory outside the input')
    aliases = shared.mapping(titles)
    groups = {} if groups is None else groups
    if not isinstance(groups, dict):
        raise ValueError('Display groups must map existing cartridge paths to menu folders')
    for rel, group in groups.items():
        if (not isinstance(rel, str) or not isinstance(group, str)
                or any(c in group for c in ('\\', ':', '\0')) or group.startswith('/')
                or any(p in ('.', '..') or p.startswith('@page') for p in group.split('/') if p)
                or (group and '/'.join(PurePosixPath(group).parts) != group)):
            raise ValueError('Invalid virtual menu folder')
        shared.safe_path(source, rel)
    cover_root = Path(covers).resolve() if covers else None
    if cover_root is not None and not cover_root.is_dir():
        raise ValueError('Cover root is missing')
    namespace, capacity, _, _, _ = PROFILES[platform]
    assets, saves = f'Assets/{namespace}/common', f'Saves/{namespace}/common'
    directory = shared.safe_path(source, f'Assets/{platform}/common')
    refs, excluded, ids, instances = {}, [], {}, []
    grouped_paths, duplicate_paths, seen_entries = set(), [], set()
    nodes = {'': {'name': LABELS[platform], 'parent': '', 'children': [], 'games': []}}

    def ensure(key):
        if key in nodes:
            return
        parent, _, leaf = key.rpartition('/')
        ensure(parent)
        nodes[parent]['children'].append(key)
        nodes[key] = {'name': shared.folder_label(leaf), 'parent': parent, 'children': [], 'games': []}

    candidates = cps2.instance_files(source) if platform == 'jtcps2' else sorted(directory.rglob('*'))
    for path in candidates:
        if not path.is_file() or path.suffix.lower() not in EXTENSIONS[platform]:
            continue
        rel = path.relative_to(source).as_posix()
        shared.safe_path(source, rel)
        size = path.stat().st_size
        try:
            if platform=='jtcps2':
                instance = cps2.plan(source,rel)
                rom = instance['rom']
                config = {key:instance[key] for key in ('core_mode','button_map','dip_switches')}
                rom_rel,size,digest = rom['path'],rom['bytes'],rom['sha256']
            else:
                config = cart_config(platform,path,size)
                rom_rel = rel
                digest = shared.gb.sha(path)
            shared.old.path_bytes('/'+rom_rel,platform,namespace)
        except (ValueError, KeyError, TypeError, FileNotFoundError) as error:
            excluded.append({'path':rel,'reason':str(error)})
            continue
        tag = cps2.save_id(digest,**config) if platform=='jtcps2' else digest[:20]
        save_bytes = config.get('save_bytes',capacity)
        if tag in ids and ids[tag] != (digest,save_bytes):
            raise ValueError('Conflicting cartridge identities for one save')
        ids[tag] = digest, save_bytes
        ref = {'path':rom_rel,'bytes':size,'sha256':digest}
        if platform=='jtcps2':
            instances.append({'path':rel,'bytes':path.stat().st_size,'sha256':instance['instance_sha256'],
                              'rom_path':rom_rel,'save_tag':tag,**config})
        else:
            ref.update(config=config['rom_config'],rom_offset=config.get('rom_offset',0),save_bytes=save_bytes)
        refs[rom_rel] = ref
        key = groups.get(rel, '/'.join(path.relative_to(source).parts[3:-1]))
        if rel in groups:
            grouped_paths.add(rel)
        entry_identity = (key, tag, tuple(sorted(config.items())))
        if entry_identity in seen_entries:
            duplicate_paths.append(rel)
            continue
        seen_entries.add(entry_identity)
        ensure(key)
        nodes[key]['games'].append({'title':aliases.get(rel,path.stem),'folder':False,'rom':'/'+rom_rel,'cover_key':'/'+rel,
            'bytes':size-config.get('rom_offset',0),**config,'save':f'/{saves}/{tag}.sav','rtc':f'/{saves}/{tag}.rtc'})
    if not refs:
        raise ValueError('No supported cartridges')
    if set(groups) != grouped_paths:
        raise ValueError('Display group references a missing or unsupported cartridge')

    # Every page has one reserved Back slot and at most 128 texture slots.
    for key, node in list(nodes.items()):
        items = len(node['games']) + len(node['children'])
        if items <= 127:
            continue
        games = node['games']
        node['games'] = []
        for index in range(0,len(games),127):
            sub = f'{key}/@page{index//127+1}' if key else f'@page{index//127+1}'
            if sub in nodes:
                raise ValueError('Pagination collides with a real folder')
            nodes[sub] = {'name':f'第 {index//127+1} 页','parent':key,'children':[],'games':games[index:index+127]}
            node['children'].append(sub)
        if len(node['children']) > 127:
            raise ValueError('Too many folders at one level')

    pending_seeds=[]
    for tag, (_, size) in ids.items():
        if not size:
            continue
        rel = f'{saves}/{tag}.sav'
        existing = shared.safe_path(source,rel)
        if existing.exists():
            if not existing.is_file() or existing.stat().st_size != size:
                raise ValueError(f'Existing isolated save has unexpected size: {rel}')
        else:
            pending_seeds.append((rel,size))
    ancestor=out.parent
    while not ancestor.exists():
        ancestor=ancestor.parent
    needed=sum(64+(len(n['games'])+len(n['children'])+1)*66560+153600 for n in nodes.values())
    if shutil.disk_usage(ancestor).free < needed+sum(size for _,size in pending_seeds)+1024**2:
        raise ValueError('Insufficient local staging capacity')
    out.mkdir(parents=True)
    files=[]
    warnings=[]
    def write(rel, data):
        dest=shared.safe_path(out,rel)
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(data)
        files.append({'path':rel,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    def page(key):
        return f'/{assets}/libs/{hashlib.sha256(key.encode()).hexdigest()[:16]}.bin' if key else f'/{assets}/menu.bin'
    def folder(key, title):
        return {'title':title,'folder':True,'rom':page(key),'save':f'/{saves}/'+('0'*20)+'.sav',
                'rtc':f'/{saves}/'+('0'*20)+'.rtc'}
    if len({page(key) for key in nodes})!=len(nodes):
        raise ValueError('Page identity collision')
    matched, missing = 0, []
    for key,node in nodes.items():
        entries=[folder(child,nodes[child]['name']) for child in sorted(node['children'])]+node['games']
        entries.append(folder(node['parent'],'返回上级' if key else '返回首页'))
        raw,hits,misses=shared.pack(entries,cover_root,platform,LABELS[platform],namespace=namespace,warnings=warnings)
        write(page(key)[1:],raw)
        matched+=hits
        missing.extend(misses)
    # PCE's original BRAM starts with four initialized 16-bit words.
    blank = b'HUBM\x00\x88\x10\x80' if platform=='pce' else b''
    for rel,size in pending_seeds:
        write(rel,blank.ljust(size,b'\xff' if platform=='jtcps2' else b'\0'))
    result={'format':'GBAF2/SNES' if platform=='snes' else 'GBAF2/'+platform,'files':files,'source_refs':list(refs.values()),'excluded':excluded,'warnings':warnings,
            'pages':len(nodes),'game_refs':len(instances) if platform=='jtcps2' else len(refs),'cover_hits':matched,'fallback_covers':len(missing),
            'source_writes':0,'rom_copies':0,'save_imports':0,'hardware_acceptance':'pending',
            'display_groups':groups,'duplicate_menu_paths':duplicate_paths}
    if platform=='jtcps2':
        result['instances']=instances
        # All source instances remain available for guards and native NVRAM
        # selection, even when several aliases share one menu/runtime identity.
        from menu_bindings import cps_bindings
        result['runtime_bindings']=cps_bindings(result)
    (out/'library-manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return result


if __name__ == '__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('platform',choices=EXTENSIONS)
    for arg in ('source','out'):
        cli.add_argument('--'+arg,type=Path,required=True)
    cli.add_argument('--titles',type=Path)
    cli.add_argument('--covers',type=Path)
    args=cli.parse_args()
    result=build(args.platform,args.source,args.out,args.titles,args.covers)
    print(json.dumps({key:result[key] for key in ('format','pages','game_refs','cover_hits','fallback_covers')}))
