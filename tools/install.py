#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Plan or apply a confined, backed-up installation; never writes saves/firmware."""
import argparse
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from build_library import sha

PREFIXES = ('Cores/pocketlab.CoverFlow/', 'Assets/gbclab/common/')
EXACT = ('Platforms/gbclab.json','Platforms/_images/gbclab.bin')

def safe_path(root, rel):
    parts = PurePosixPath(rel).parts
    if not parts or rel.startswith('/') or '\\' in rel or '..' in parts or ':' in rel or '\0' in rel:
        raise ValueError(f'Unsafe relative path: {rel}')
    target = root/rel
    cursor=root
    for part in parts:
        cursor=cursor/part
        if cursor.is_symlink() or getattr(cursor,'is_junction',lambda:False)():
            raise ValueError(f'Links are not allowed in installation paths: {rel}')
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError(f'Path resolves outside root: {rel}')
    return target

def confined(root, rel):
    target=safe_path(root,rel)
    if not (rel in EXACT or any(rel.startswith(p) for p in PREFIXES)):
        raise ValueError(f'Path outside menu installation scope: {rel}')
    return target

def identity(card):
    marker=card/'Analogue_Pocket.json'
    if json.loads(marker.read_text(encoding='utf-8-sig')).get('product')!='Analogue Pocket':
        raise ValueError('Expected an Analogue Pocket card root or its local copy')
    device=str(card.stat().st_dev)
    if os.name=='nt':
        serial=ctypes.c_uint32()
        ok=ctypes.windll.kernel32.GetVolumeInformationW(str(card.anchor),None,0,ctypes.byref(serial),None,None,None,0)
        if not ok: raise OSError('Cannot identify Windows target volume')
        device=f'{serial.value:08X}'
    return {'root':str(card),'device':device,'marker_sha256':sha(marker)}

def read_manifest(root, filename):
    value=json.loads((root/filename).read_text(encoding='utf-8'))
    paths=set()
    for item in value['files']:
        rel=item['path'];path=confined(root,rel)
        if rel.casefold() in paths: raise ValueError('Duplicate manifest path')
        paths.add(rel.casefold())
        if not path.is_file() or path.stat().st_size!=item['bytes'] or sha(path)!=item['sha256']:
            raise ValueError(f'Package/library checksum mismatch: {rel}')
    return value

def plan(card, package, library):
    card,package,library=map(lambda p:Path(p).resolve(),(card,package,library))
    ident=identity(card)
    for source in (package,library):
        if source.is_relative_to(card) or card.is_relative_to(source):
            raise ValueError('Package and library must be separate local folders outside the card')
    p=read_manifest(package,'release-manifest.json')
    lib=read_manifest(library,'library-manifest.json')
    if 'source_packs' in lib:
        if lib['identity']!=ident:
            raise ValueError('Styled library belongs to a different card/copy')
        for item in lib['source_packs']:
            rel=item['path']
            if not rel.startswith('Assets/gbclab/common/') or not rel.endswith('.bin'):
                raise ValueError('Unexpected source pack path')
            if sha(confined(card,rel))!=item['sha256']:
                raise ValueError('Menu changed after styling; rebuild the staged library')
    for suffix in ('','meta','folders'):safe_path(card,'Saves/gbclab/common/'+suffix)
    required={'Cores/pocketlab.CoverFlow/core.json','Cores/pocketlab.CoverFlow/gbc.rbf_r',
              'Cores/pocketlab.CoverFlow/data.json','Cores/pocketlab.CoverFlow/video.json',
              'Cores/pocketlab.CoverFlow/input.json','Cores/pocketlab.CoverFlow/interact.json',
              'Cores/pocketlab.CoverFlow/audio.json','Platforms/gbclab.json','Platforms/_images/gbclab.bin'}
    if not required.issubset({x['path'] for x in p['files']}):raise ValueError('Incomplete core package')
    if not {'Assets/gbclab/common/covers.bin','Assets/gbclab/common/gbc_bios.bin'}.issubset({x['path'] for x in lib['files']}):
        raise ValueError('Incomplete library/BIOS manifest')
    metadata=json.loads((package/'Cores/pocketlab.CoverFlow/core.json').read_text(encoding='utf-8'))
    if metadata['core']['metadata']['platform_ids']!=['gbclab','gb','gbc']:
        raise ValueError('Unexpected platform mapping')
    bios=library/'Assets/gbclab/common/gbc_bios.bin'
    if not bios.is_file() or bios.stat().st_size!=2304:
        raise ValueError('Stage your own 2304-byte GBC BIOS with --bios before installation')
    for ref in lib['source_refs']:
        path=card/ref['path']
        if not path.resolve().is_relative_to(card) or not ref['path'].startswith(('Assets/gb/common/','Assets/gbc/common/')):
            raise ValueError('ROM reference escapes the GB/GBC platform')
        if path.stat().st_size!=ref['bytes'] or sha(path)!=ref['sha256']:
            raise ValueError(f'ROM changed since library generation: {ref["path"]}')
    changes=[];seen=set()
    for source,manifest in ((package,p),(library,lib)):
        for item in manifest['files']:
            rel=item['path'];target=confined(card,rel)
            if rel.casefold() in seen: raise ValueError('Package and library overlap')
            seen.add(rel.casefold())
            previous=sha(target) if target.is_file() else None
            if target.exists() and not target.is_file(): raise ValueError('Destination is not a file')
            if previous!=item['sha256']:
                changes.append({**item,'source':str(source),'previous_sha256':previous})
    # Publish new child pages before changing parent links, then Home and core metadata.
    changes.sort(key=lambda x:(x['path'].endswith('/core.json'),x['path'].endswith('/covers.bin'),x['previous_sha256'] is not None,x['path']))
    return {'identity':ident,'version':p['version'],'changes':changes,'save_writes':0,'firmware_writes':0}

def publish(source, target, expected):
    target.parent.mkdir(parents=True,exist_ok=True)
    fd,temporary=tempfile.mkstemp(prefix='.pocket-menu-',dir=target.parent)
    temporary=Path(temporary)
    try:
        with os.fdopen(fd,'wb') as out, source.open('rb') as src:
            shutil.copyfileobj(src,out);out.flush();os.fsync(out.fileno())
        if sha(temporary)!=expected: raise ValueError('Temporary file readback mismatch')
        os.replace(temporary,target)
        if sha(target)!=expected: raise ValueError('Destination readback mismatch')
    finally:
        if temporary.exists(): temporary.unlink()

def apply(card, package, library, backup):
    card,backup=Path(card).resolve(),Path(backup).resolve()
    if backup.exists() or backup.is_relative_to(card) or card.is_relative_to(backup):
        raise ValueError('Backup must be a new directory outside the card')
    result=plan(card,package,library)
    changes=result['changes']
    needed=sum((confined(card,c['path']).stat().st_size if c['previous_sha256'] else 0) for c in changes)
    ancestor=backup.parent
    while not ancestor.exists():ancestor=ancestor.parent
    if shutil.disk_usage(ancestor).free<needed+1024*1024:raise ValueError('Not enough backup space')
    if shutil.disk_usage(card).free<sum(c['bytes'] for c in changes)+1024*1024:raise ValueError('Not enough card staging space')
    backup.mkdir(parents=True)
    for c in changes:
        if c['previous_sha256']:
            source=confined(card,c['path']);target=confined(backup/'previous',c['path'])
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
            if sha(target)!=c['previous_sha256']:raise ValueError('Backup checksum mismatch')
    result.update(status='backup_verified_install_pending',created_utc=datetime.now(timezone.utc).isoformat())
    receipt=backup/'install-receipt.json'
    receipt.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    # Check all destinations again before the first write, including backup data.
    for c in changes:
        target=confined(card,c['path'])
        if (sha(target) if target.is_file() else None)!=c['previous_sha256']:raise ValueError('Card changed during backup')
    with (backup/'journal.jsonl').open('x',encoding='utf-8') as journal:
        for c in changes:
            if identity(card)!=result['identity']:raise ValueError('Card identity changed')
            target=confined(card,c['path'])
            if (sha(target) if target.is_file() else None)!=c['previous_sha256']:raise ValueError('Destination changed')
            journal.write(json.dumps({'intent':c['path'],'sha256':c['sha256']})+'\n');journal.flush();os.fsync(journal.fileno())
            publish(confined(Path(c['source']),c['path']),target,c['sha256'])
    # These are empty directories, never imported or overwritten save files.
    for suffix in ('','meta','folders'):
        path=safe_path(card,'Saves/gbclab/common/'+suffix)
        path.mkdir(parents=True,exist_ok=True)
    result['status']='installed_sha256_verified'
    receipt.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result

def rollback(card, backup, execute=False):
    card,backup=Path(card).resolve(),Path(backup).resolve()
    result=json.loads((backup/'install-receipt.json').read_text(encoding='utf-8'))
    if identity(card)!=result['identity']:raise ValueError('Rollback card identity differs')
    changes=[]
    for c in result['changes']:
        target=confined(card,c['path'])
        actual=sha(target) if target.is_file() else None
        if actual==c['previous_sha256']:continue
        if actual!=c['sha256']:raise ValueError(f'File changed since install; refusing rollback: {c["path"]}')
        if c['previous_sha256'] and sha(confined(backup/'previous',c['path']))!=c['previous_sha256']:
            raise ValueError('Rollback backup checksum mismatch')
        changes.append(c)
    if execute:
        for c in changes:
            if identity(card)!=result['identity']:raise ValueError('Card identity changed')
            target=confined(card,c['path'])
            if sha(target)!=c['sha256']:raise ValueError('File changed during rollback')
            if c['previous_sha256']:publish(confined(backup/'previous',c['path']),target,c['previous_sha256'])
            else:target.unlink()
    return {'rollback_files':len(changes),'applied':execute,'save_writes':0,'firmware_writes':0}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--card',required=True);p.add_argument('--package');p.add_argument('--library')
    p.add_argument('--backup',help='New local backup folder for install; existing backup for rollback')
    p.add_argument('--apply',action='store_true');p.add_argument('--rollback',action='store_true')
    a=p.parse_args()
    try:
        if a.rollback:
            if not a.backup:p.error('--rollback requires --backup')
            result=rollback(a.card,a.backup,a.apply)
        else:
            if not a.package or not a.library:p.error('--package and --library are required')
            if a.apply and not a.backup:p.error('--apply requires --backup')
            result=apply(a.card,a.package,a.library,a.backup) if a.apply else plan(a.card,a.package,a.library)
        print(json.dumps({k:v for k,v in result.items() if k!='changes'},ensure_ascii=False,indent=2))
        if 'changes' in result: print(f'Files to install/update: {len(result["changes"])}. Saves/firmware writes: 0.')
    except (OSError,ValueError,KeyError) as error:p.exit(2,str(error)+'\n')

if __name__=='__main__':main()
