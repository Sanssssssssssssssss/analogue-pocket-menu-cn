#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Add a new, isolated GBA entry with progress backup; never overwrite an entry."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import shutil
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
# Import generic path/publication primitives without changing the GB/GBC allowlist.
import importlib.util
spec=importlib.util.spec_from_file_location('gb_install',ROOT/'tools/install.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
sha,safe_path,identity,publish=base.sha,base.safe_path,base.identity,base.publish


def allowed(root,rel):
    if not (re.fullmatch(r'Cores/pocketlab\.GBA/(?:core|data|audio|input|interact|variants|video)\.json',rel)
            or rel=='Cores/pocketlab.GBA/gba.rbf_r'
            or rel in ('Platforms/gbalab.json','Platforms/_images/gbalab.bin','Assets/gbalab/common/menu.bin')
            or re.fullmatch(r'Assets/gbalab/common/libs/[0-9a-f]{16}\.bin',rel)
            or re.fullmatch(r'Saves/gbalab/common/[0-9a-f]{20}\.(sav|rtc)',rel)):
        raise ValueError('Outside new GBA namespace: '+rel)
    return safe_path(root,rel)


def plan(card,package,library,saves=None):
    card,package,library=map(lambda x:Path(x).resolve(),(card,package,library))
    ident=identity(card)
    receipt=json.loads((package/'build-receipt.json').read_text(encoding='utf-8'))
    if receipt['core']!='pocketlab.GBA' or receipt['minimum_reported_slack_ns']<0:raise ValueError('Unreviewed build receipt')
    lib=json.loads((library/'library-manifest.json').read_text(encoding='utf-8'))
    components=[(package/'core',receipt),(library,lib)]
    if saves:components.append((Path(saves).resolve(),json.loads((Path(saves)/'save-manifest.json').read_text(encoding='utf-8'))))
    changes=[];seen=set()
    for source,manifest in components:
        if source.is_relative_to(card) or card.is_relative_to(source):raise ValueError('Staging must be outside card')
        for item in manifest['files']:
            rel=item['path'];p=allowed(source,rel);target=allowed(card,rel)
            if rel.casefold() in seen:raise ValueError('Overlapping staging paths')
            seen.add(rel.casefold())
            if target.exists():raise ValueError('First-install tool refuses existing destination: '+rel)
            if p.stat().st_size!=item['bytes'] or sha(p)!=item['sha256']:raise ValueError('Staging differs: '+rel)
            changes.append({**item,'source':str(source)})
    if not {'cores/pocketlab.gba/core.json','assets/gbalab/common/menu.bin'}.issubset(seen):raise ValueError('Incomplete package')
    meta=json.loads((package/'core/Cores/pocketlab.GBA/core.json').read_text())['core']
    if meta['metadata']['platform_ids']!=['gbalab','gba'] or meta['framework']['sleep_supported']:
        raise ValueError('Unexpected core platform/sleep settings')
    slots=json.loads((package/'core/Cores/pocketlab.GBA/data.json').read_text())['data']['data_slots']
    if [s['id'] for s in slots]!=[100,4,1,10,11]:raise ValueError('Slot order disagrees with hardware datatable')
    bios=safe_path(card,'Assets/gba/common/gba_bios.bin')
    if bios.stat().st_size!=16384:raise ValueError('Provide your own 16384-byte BIOS in existing GBA assets')
    # Full read-only ROM verification immediately before the installation.
    for row in lib['roms']:
        if not row['path'].startswith('Assets/gba/common/'):raise ValueError('ROM outside original GBA assets')
        p=safe_path(card,row['path'])
        if p.stat().st_size!=row['bytes'] or sha(p)!=row['sha256']:raise ValueError('ROM changed: '+row['path'])
    for _,m in components:
        for row in m.get('imports',[]):
            if not row['source'].startswith('Saves/gba/common/') or sha(safe_path(card,row['source']))!=row['source_sha256']:
                raise ValueError('Original save changed since staging')
    changes.sort(key=lambda x:(x['path']=='Cores/pocketlab.GBA/core.json',x['path']=='Platforms/gbalab.json',x['path']))
    return {'identity':ident,'changes':changes,'roms':len(lib['roms']),'pages':len(lib['files']),
            'ordinary_save_imports':sum(len(m.get('imports',[])) for _,m in components),
            'original_save_writes':0,'firmware_writes':0,'hardware_playtest':'pending'}


def protect(card,backup):
    selected=('Saves','Memories','Settings','Presets','System','Cores/pocketlab.CoverFlow','Cores/mincer_ray.GBA','Cores/Spiritualized.GBA','Analogue_Pocket.json')
    paths={p for name in selected for p in ([card/name] if (card/name).is_file() else (card/name).rglob('*')) if p.is_file()}
    if shutil.disk_usage(backup).free<sum(p.stat().st_size for p in paths)+1024**2:raise ValueError('Insufficient backup space')
    records=[]
    for p in sorted(paths):
        rel=p.relative_to(card).as_posix();safe_path(card,rel);target=safe_path(backup/'protected',rel)
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
        digest=sha(p)
        if sha(target)!=digest:raise ValueError('Protected backup mismatch')
        records.append({'path':rel,'sha256':digest,'bytes':p.stat().st_size})
    return records


def apply(card,package,library,saves,backup):
    card,backup=Path(card).resolve(),Path(backup).resolve()
    if backup.exists() or backup.is_relative_to(card) or card.is_relative_to(backup):raise ValueError('Use fresh external backup')
    result=plan(card,package,library,saves)
    needed=sum(x['bytes'] for x in result['changes'])
    if shutil.disk_usage(card).free<needed+32*1024**2:raise ValueError('Not enough card space')
    backup.mkdir(parents=True)
    protected=protect(card,backup)
    result.update(status='backup_verified_install_pending',protected=protected,created_utc=datetime.now(timezone.utc).isoformat())
    receipt=backup/'install-receipt.json';receipt.write_text(json.dumps(result,indent=2)+'\n')
    for c in result['changes']:
        if identity(card)!=result['identity']:raise ValueError('Card identity changed')
        target=allowed(card,c['path'])
        if target.exists():raise ValueError('Card destination appeared during install')
        publish(allowed(Path(c['source']),c['path']),target,c['sha256'])
    safe_path(card,'Saves/gbalab/common').mkdir(parents=True,exist_ok=True)
    for item in protected:
        if sha(safe_path(card,item['path']))!=item['sha256']:raise ValueError('Protected original changed')
    result['status']='installed_sha256_verified_originals_unchanged'
    receipt.write_text(json.dumps(result,indent=2)+'\n')
    return result


def rollback(card,backup,execute=False):
    card,backup=Path(card).resolve(),Path(backup).resolve()
    result=json.loads((backup/'install-receipt.json').read_text())
    if identity(card)!=result['identity']:raise ValueError('Different card')
    changes=[]
    for c in result['changes']:
        if c['path'].startswith('Saves/'):continue # retain all imported/newly played progress
        p=allowed(card,c['path'])
        if not p.exists():continue
        if sha(p)!=c['sha256']:raise ValueError('Changed file; manual review required')
        changes.append(c)
    if execute:
        for c in reversed(changes):
            p=allowed(card,c['path'])
            if identity(card)!=result['identity'] or sha(p)!=c['sha256']:raise ValueError('Card changed')
            p.unlink()
    return {'removed_files':len(changes),'applied':execute,'save_writes':0,'firmware_writes':0}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--card',required=True)
    p.add_argument('--package');p.add_argument('--library');p.add_argument('--saves');p.add_argument('--backup')
    p.add_argument('--apply',action='store_true');p.add_argument('--rollback',action='store_true');a=p.parse_args()
    try:
        if a.rollback:
            if not a.backup:p.error('Rollback needs --backup')
            result=rollback(a.card,a.backup,a.apply)
        else:
            if not a.package or not a.library:p.error('Need --package and --library')
            if a.apply and not a.backup:p.error('Applying needs --backup')
            result=apply(a.card,a.package,a.library,a.saves,a.backup) if a.apply else plan(a.card,a.package,a.library,a.saves)
        print(json.dumps({k:v for k,v in result.items() if k not in ('changes','protected','identity')},indent=2))
    except (OSError,ValueError) as e:p.exit(2,str(e)+'\n')
