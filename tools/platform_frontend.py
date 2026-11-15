#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build/install four platform display files; no core, asset, save or firmware writes."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import shutil
import struct
import zipfile
from PIL import Image,ImageDraw
import build_library as lib
from install import identity,safe_path,publish
from menu_icons import icon_image

PLATFORMS={'gbclab':'GB / GBC','gbalab':'GBA'}
ALLOWED={f'Platforms/{p}.json' for p in PLATFORMS}|{f'Platforms/_images/{p}.bin' for p in PLATFORMS}
CORES={'pocketlab.CoverFlow':'gbc.rbf_r','pocketlab.GBA':'gba.rbf_r'}
GUARDS={f'Cores/{name}/{file}' for name,rbf in CORES.items() for file in ['core.json','data.json',rbf]}


def allowed(root,rel):
    if rel not in ALLOWED:raise ValueError('Outside platform display scope: '+rel)
    return safe_path(root,rel)


def encode(image):
    if image.mode!='L' or image.size!=(521,165):raise ValueError('Expected 521x165 monochrome platform graphic')
    result=bytearray()
    for value in image.transpose(Image.Transpose.ROTATE_90).tobytes():result.extend((value,0))
    return bytes(result)


def decode(raw):
    if len(raw)!=521*165*2 or any(raw[1::2]):raise ValueError('Invalid platform image size or reserved pixel byte')
    return Image.frombytes('L',(165,521),raw[::2]).transpose(Image.Transpose.ROTATE_270)


def banner(platform):
    image=Image.new('L',(521,165),0)
    for kind,x in ([('gb',15),('gbc',120)] if platform=='gbclab' else [('gba',75)]):
        image.paste(icon_image(kind).convert('L'),(x,18))
    for title,y,scale,ink in [(PLATFORMS[platform],50,3,240),('POCKET LAB',112,1,160)]:
        width,raw,clipped,missing=lib.columns(title,lib.font())
        if clipped or missing or 270+width*scale>521:raise ValueError('Platform label does not fit')
        glyph=Image.new('L',(width,16),0);draw=ImageDraw.Draw(glyph)
        for x,value in enumerate(struct.unpack('<512H',raw)[:width]):
            for row in range(16):
                if value>>row&1:draw.point((x,row),fill=ink)
        image.paste(glyph.resize((width*scale,16*scale),Image.Resampling.NEAREST),(270,y))
    return image


def stage(source,out):
    source,out=Path(source).resolve(),Path(out).resolve()
    if out.exists() or out.is_relative_to(source) or source.is_relative_to(out):raise ValueError('Use a fresh output outside source')
    marker=safe_path(source,'Analogue_Pocket.json')
    if json.loads(marker.read_text(encoding='utf-8-sig')).get('product')!='Analogue Pocket':raise ValueError('Expected Pocket card/copy')
    guards=[]
    for rel in sorted(GUARDS):guards.append({'path':rel,'sha256':lib.sha(safe_path(source,rel))})
    files=[];out.mkdir(parents=True)
    for key,title in PLATFORMS.items():
        rel=f'Platforms/{key}.json';previous=allowed(source,rel)
        data=json.loads(previous.read_text(encoding='utf8'));data['platform']['name']=title
        assert len(title.encode('ascii'))<=31
        target=allowed(out/'files',rel);target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(data,indent=2)+'\n',encoding='utf8',newline='\n')
        files.append({'path':rel,'bytes':target.stat().st_size,'sha256':lib.sha(target),'previous_sha256':lib.sha(previous)})
        rel=f'Platforms/_images/{key}.bin';target=allowed(out/'files',rel);target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(encode(banner(key)))
        decode(target.read_bytes()).save(out/(key+'.png'))
        files.append({'path':rel,'bytes':target.stat().st_size,'sha256':lib.sha(target)})
    manifest={'version':'0.1.0-platforms','scope':'Only platform names and graphics; native OS rendering pending',
              'files':files,'guards':guards,'save_writes':0,'firmware_writes':0}
    (out/'platform-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
    with zipfile.ZipFile(out/'pocket-lab-platforms.zip','x',zipfile.ZIP_DEFLATED) as archive:
        for item in files:archive.write(allowed(out/'files',item['path']),item['path'])
    return manifest


def plan(card,package):
    card,package=Path(card).resolve(),Path(package).resolve()
    if card.is_relative_to(package) or package.is_relative_to(card):raise ValueError('Keep local package outside card')
    ident=identity(card);data=json.loads((package/'platform-manifest.json').read_text(encoding='utf8'))
    names=[x['path'] for x in data['files']]
    if len(names)!=4 or set(names)!=ALLOWED:raise ValueError('Expected exactly four platform display files')
    if len(data['guards'])!=len(GUARDS) or {x['path'] for x in data['guards']}!=GUARDS:raise ValueError('Core guards missing or unexpected')
    for item in data['guards']:
        rel=item['path']
        if lib.sha(safe_path(card,rel))!=item['sha256']:raise ValueError('Core changed since staging: '+rel)
    changes=[]
    for item in data['files']:
        rel=item['path'];source=allowed(package/'files',rel);target=allowed(card,rel)
        if source.stat().st_size!=item['bytes'] or lib.sha(source)!=item['sha256']:raise ValueError('Package checksum mismatch')
        if target.exists() and not target.is_file():raise ValueError('Expected a platform file, not a directory')
        old=lib.sha(target) if target.is_file() else None
        if rel.endswith('.json'):
            if old!=item['previous_sha256']:raise ValueError('Platform metadata changed since staging')
            before=json.loads(target.read_text(encoding='utf8'));after=json.loads(source.read_text(encoding='utf8'))
            before['platform']['name']=PLATFORMS[Path(rel).stem]
            if before!=after:raise ValueError('Only platform name may change')
        else:decode(source.read_bytes())
        if old!=item['sha256']:changes.append({**item,'previous_sha256':old})
    return {'identity':ident,'changes':changes,'guards':data['guards'],'save_writes':0,'firmware_writes':0}


def apply(card,package,backup):
    card,package,backup=map(lambda p:Path(p).resolve(),[card,package,backup])
    result=plan(card,package)
    if backup.exists() or backup.is_relative_to(card) or card.is_relative_to(backup):raise ValueError('Use fresh local backup outside card')
    protected={g['path'] for g in result['guards']}
    saves=safe_path(card,'Saves')
    if saves.exists():protected.update(p.relative_to(card).as_posix() for p in saves.rglob('*') if p.is_file())
    ancestor=backup.parent
    while not ancestor.exists():ancestor=ancestor.parent
    needed=sum(safe_path(card,rel).stat().st_size for rel in protected)
    needed+=sum(allowed(card,x['path']).stat().st_size for x in result['changes'] if x['previous_sha256'])
    if shutil.disk_usage(ancestor).free<needed+1024*1024:raise ValueError('Not enough local backup space')
    if shutil.disk_usage(card).free<sum(x['bytes'] for x in result['changes'])+1024*1024:raise ValueError('Not enough card staging space')
    backup.mkdir(parents=True);snapshot=[]
    for rel in sorted(protected):
        source=safe_path(card,rel);target=safe_path(backup/'protected',rel)
        digest=lib.sha(source);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        if lib.sha(target)!=digest:raise ValueError('Protected backup mismatch')
        snapshot.append({'path':rel,'sha256':digest})
    for item in result['changes']:
        if item['previous_sha256']:
            target=allowed(backup/'previous',item['path']);target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(allowed(card,item['path']),target)
            if lib.sha(target)!=item['previous_sha256']:raise ValueError('Platform backup mismatch')
    result.update(created_utc=datetime.now(timezone.utc).isoformat(),protected=snapshot,status='backup_verified_install_pending')
    record=backup/'install-receipt.json';record.write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    # Recheck all hashes before first card write; journal each atomic replacement.
    for item in result['changes']:
        p=allowed(card,item['path'])
        if (lib.sha(p) if p.is_file() else None)!=item['previous_sha256']:raise ValueError('Platform changed during backup')
    for item in snapshot:
        if lib.sha(safe_path(card,item['path']))!=item['sha256']:raise ValueError('Protected file changed during backup')
    with (backup/'journal.jsonl').open('x',encoding='utf8') as journal:
        for item in result['changes']:
            if identity(card)!=result['identity']:raise ValueError('Card identity changed')
            target=allowed(card,item['path'])
            if (lib.sha(target) if target.is_file() else None)!=item['previous_sha256']:raise ValueError('Platform changed before replacement')
            journal.write(json.dumps({'path':item['path'],'sha256':item['sha256']})+'\n');journal.flush();os.fsync(journal.fileno())
            publish(allowed(package/'files',item['path']),target,item['sha256'])
    for item in snapshot:
        if lib.sha(safe_path(card,item['path']))!=item['sha256']:raise ValueError('Protected file changed')
    for item in result['changes']:
        if lib.sha(allowed(card,item['path']))!=item['sha256']:raise ValueError('Platform readback mismatch')
    if identity(card)!=result['identity']:raise ValueError('Card identity changed')
    result['status']='installed_sha256_verified';record.write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    return result


def rollback(card,backup,execute=False):
    card,backup=Path(card).resolve(),Path(backup).resolve()
    result=json.loads((backup/'install-receipt.json').read_text(encoding='utf8'))
    if identity(card)!=result['identity']:raise ValueError('Rollback card identity differs')
    pending=[]
    for item in result['changes']:
        target=allowed(card,item['path']);current=lib.sha(target) if target.is_file() else None
        if current==item['previous_sha256']:continue
        if current!=item['sha256']:raise ValueError('Changed platform file; refusing rollback')
        if item['previous_sha256'] and lib.sha(allowed(backup/'previous',item['path']))!=item['previous_sha256']:raise ValueError('Rollback backup mismatch')
        pending.append(item)
    if execute:
        for item in pending:
            if identity(card)!=result['identity']:raise ValueError('Card identity changed')
            target=allowed(card,item['path'])
            if lib.sha(target)!=item['sha256']:raise ValueError('Platform changed during rollback')
            if item['previous_sha256']:publish(allowed(backup/'previous',item['path']),target,item['previous_sha256'])
            else:target.unlink()
    return {'files':len(pending),'applied':execute,'save_writes':0,'firmware_writes':0}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['stage','plan','apply','rollback'])
    for name in ['source','out','card','package','backup']:parser.add_argument('--'+name)
    parser.add_argument('--execute',action='store_true',help='Apply a verified rollback')
    args=parser.parse_args()
    required={'stage':['source','out'],'plan':['card','package'],'apply':['card','package','backup'],'rollback':['card','backup']}[args.action]
    if any(getattr(args,n) is None for n in required):parser.error('Required: '+', '.join('--'+n for n in required))
    try:
        if args.action=='stage':result=stage(args.source,args.out)
        elif args.action=='plan':result=plan(args.card,args.package)
        elif args.action=='apply':result=apply(args.card,args.package,args.backup)
        else:result=rollback(args.card,args.backup,args.execute)
        print(json.dumps({k:v for k,v in result.items() if k not in ['protected','guards','changes','identity']},indent=2))
    except (ValueError,OSError,KeyError) as error:parser.exit(2,str(error)+'\n')
