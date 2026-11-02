#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Plan/apply a backed-up F1->F2 update of an existing GBA menu entry.

Only the owned bitstream/version, appended menu scaler and menu packs change.
Original game/save identities, game display modes and settings are preserved.
An explicit display-profile option also updates available style metadata.
"""
import argparse,importlib.util,json,os,shutil,struct,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('gba_install',ROOT/'experiments/gba_menu/install.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
sha,safe_path,identity,publish=base.sha,base.safe_path,base.identity,base.publish
from display_styles import configure as configure_display
CORE='Cores/pocketlab.GBA/'
KNOWN_SOURCE={'73226a39e7fd25429ef939d0fd2668902b28674823c9ec65e1a0f0da13771af8'}
MENU_MODE={'width':320,'height':288,'aspect_w':10,'aspect_h':9,'rotation':0,'mirror':0}

def allowed(root,rel):
    if rel not in (CORE+'gba.rbf_r',CORE+'core.json',CORE+'video.json') and not (rel.startswith('Assets/gbalab/common/') and rel.endswith('.bin')):
        raise ValueError('Outside CoverFlow update scope: '+rel)
    return base.allowed(root,rel)

def records(path):
    with path.open('rb') as f:
        header=f.read(64)
        if len(header)!=64:raise ValueError('Truncated menu')
        magic,version,count,art,pause,stride=struct.unpack_from('<4s5I',header)
        if magic!=b'GBAF' or version not in (1,2) or not 1<=count<=2047 or art!=64+count*1024:raise ValueError('Invalid source menu')
        if version==1 and (stride or pause!=art+count*76800):raise ValueError('Invalid F1 layout')
        if version==2 and (stride!=65536 or pause!=art+count*65536):raise ValueError('Invalid F2 layout')
        if version==2 and count>128:raise ValueError('GBA CoverFlow exceeds 128 texture slots')
        if path.stat().st_size!=pause+153600:raise ValueError('Incomplete menu pack')
        rows=[f.read(1024) for _ in range(count)]
        if any(len(row)!=1024 or row[:4]!=b'ENT1' for row in rows):raise ValueError('Invalid launch records')
    return version,[row[:16]+row[24:] for row in rows]

def stage(card,package,library,out,display_profile=False):
    card,package,library,out=map(lambda p:Path(p).resolve(),(card,package,library,out))
    if out.exists() or any(out.is_relative_to(p) or p.is_relative_to(out) for p in (card,package,library)):raise ValueError('Fresh separate staging required')
    ident=identity(card)
    build=json.loads((package/'build-receipt.json').read_text())
    lib=json.loads((library/'library-manifest.json').read_text(encoding='utf8'))
    if build.get('core')!='pocketlab.GBA' or build.get('menu_format')!='GBAF2' or lib.get('format')!='GBAF2' or build['minimum_reported_slack_ns']<0:raise ValueError('Matching timing-checked GBAF2 build/library required')
    by_name={item['path']:item for item in build['files']}
    binary=CORE+'gba.rbf_r';item=by_name[binary]
    if sha(allowed(package/'core',binary))!=item['sha256']:raise ValueError('Candidate binary changed')
    current=allowed(card,binary)
    if sha(current) not in KNOWN_SOURCE | {item['sha256']}:raise ValueError('Current core is not the retained accepted source or this candidate')
    base.check_core(current.parent)
    slots=json.loads(safe_path(card,CORE+'data.json').read_text())['data']['data_slots']
    if [s['id'] for s in slots]!=[100,4,1,10,11]:raise ValueError('Installed APF slot layout differs')
    for row in lib['roms']:
        if not row['path'].startswith('Assets/gba/common/'):raise ValueError('ROM outside GBA library')
        p=safe_path(card,row['path'])
        if p.stat().st_size!=row['bytes'] or sha(p)!=row['sha256']:raise ValueError('ROM changed since library preparation: '+row['path'])
    pages=[]
    for item_page in lib['files']:
        rel=item_page['path'];new=allowed(library,rel);old=allowed(card,rel)
        if new.stat().st_size!=item_page['bytes'] or sha(new)!=item_page['sha256']:raise ValueError('Staged menu changed')
        old_version,old_records=records(old);new_version,new_records=records(new)
        if new_version!=2 or old_records!=new_records:raise ValueError('Launch/save/RTC identity changed: '+rel)
        pages.append((rel,new,item_page))
    metadata=json.loads(allowed(card,CORE+'core.json').read_text())
    metadata['core']['metadata'].update(version=build['version'],date_release='2026-11-02')
    video=json.loads(allowed(card,CORE+'video.json').read_text())
    modes=video['video']['scaler_modes']
    if len(modes) not in (1,2) or (modes[0]['width'],modes[0]['height'],modes[0]['aspect_w'],modes[0]['aspect_h'])!=(240,160,3,2):raise ValueError('Game scaler settings differ')
    if len(modes)==2 and modes[1]!=MENU_MODE:raise ValueError('Existing scaler slot 1 is occupied')
    if len(modes)==1:modes.append(MENU_MODE.copy())
    if display_profile:video=configure_display(video,'gba')
    out.mkdir(parents=True);changes=[]
    for rel,p,record in [(binary,allowed(package/'core',binary),item),*pages]:
        dest=allowed(out,rel);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    for rel,value in [(CORE+'core.json',metadata),(CORE+'video.json',video)]:
        p=allowed(out,rel);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,indent=2)+'\n')
    for p in sorted(x for x in out.rglob('*') if x.is_file()):
        rel=p.relative_to(out).as_posix();previous=sha(allowed(card,rel));digest=sha(p)
        if previous!=digest:changes.append({'path':rel,'sha256':digest,'bytes':p.stat().st_size,'previous_sha256':previous})
    changes.sort(key=lambda c:(c['path']==binary,c['path']==CORE+'core.json',c['path']))
    result={'identity':ident,'changes':changes,'core_version':build['version'],'status':'staged_only','roms_verified':len(lib['roms']),'roms':lib['roms'],
        'pages_checked':len(pages),'game_scaler_modes_preserved':True,'game_display_modes_preserved':not display_profile,
        'display_profile_updated':display_profile,'OS_display_choice_writes':0,'save_writes':0,'rom_writes':0,'firmware_writes':0,'hardware_playtest':'pending'}
    (out/'update-plan.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

def apply(card,staging,backup):
    card,staging,backup=map(lambda p:Path(p).resolve(),(card,staging,backup))
    if backup.exists() or any(backup.is_relative_to(p) or p.is_relative_to(backup) for p in (card,staging)):raise ValueError('Fresh separate backup required')
    result=json.loads((staging/'update-plan.json').read_text())
    if identity(card)!=result['identity']:raise ValueError('Different card')
    for row in result['roms']:
        if not row['path'].startswith('Assets/gba/common/'):raise ValueError('ROM outside GBA library')
        path=safe_path(card,row['path'])
        if path.stat().st_size!=row['bytes'] or sha(path)!=row['sha256']:raise ValueError('ROM changed after staging')
    for c in result['changes']:
        if sha(allowed(card,c['path']))!=c['previous_sha256'] or sha(allowed(staging,c['path']))!=c['sha256']:raise ValueError('Card/staging changed after plan')
    if shutil.disk_usage(card).free<sum(c['bytes'] for c in result['changes'])+32*1024**2:raise ValueError('Insufficient card space')
    progress=[p for name in ('Saves/gbalab','Saves/gba') for p in (card/name).rglob('*') if p.is_file()]
    needed=sum(allowed(card,c['path']).stat().st_size for c in result['changes'])+sum(p.stat().st_size for p in progress)+1024**2
    ancestor=backup.parent
    while not ancestor.exists():ancestor=ancestor.parent
    if shutil.disk_usage(ancestor).free<needed:raise ValueError('Insufficient backup space')
    backup.mkdir(parents=True)
    # Versioned local backup of the changed assets and GBA progress only.
    protected=[]
    for folder in ('Saves/gbalab','Saves/gba'):
        for p in sorted((card/folder).rglob('*')):
            if not p.is_file():continue
            rel=p.relative_to(card).as_posix();safe_path(card,rel)
            target=safe_path(backup/'progress',rel);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
            if sha(target)!=sha(p):raise ValueError('Progress backup mismatch')
            protected.append({'path':rel,'sha256':sha(p)})
    for c in result['changes']:
        target=allowed(backup/'previous',c['path']);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(allowed(card,c['path']),target)
        if sha(target)!=c['previous_sha256']:raise ValueError('Previous file backup mismatch')
    result.update(status='backup_verified_update_pending',protected=protected,created_utc=datetime.now(timezone.utc).isoformat())
    receipt=backup/'update-receipt.json';receipt.write_text(json.dumps(result,indent=2)+'\n')
    with (backup/'journal.jsonl').open('x') as journal:
        for c in result['changes']:
            if identity(card)!=result['identity'] or sha(allowed(card,c['path']))!=c['previous_sha256']:raise ValueError('Card changed during update')
            journal.write(json.dumps(c)+'\n');journal.flush();os.fsync(journal.fileno())
            publish(allowed(staging,c['path']),allowed(card,c['path']),c['sha256'])
    for p in protected:
        if sha(safe_path(card,p['path']))!=p['sha256']:raise ValueError('Progress changed during update')
    result['status']='installed_sha256_verified_progress_unchanged';receipt.write_text(json.dumps(result,indent=2)+'\n');return result

def rollback(card,backup,execute=False):
    card,backup=Path(card).resolve(),Path(backup).resolve();result=json.loads((backup/'update-receipt.json').read_text());changes=[]
    if identity(card)!=result['identity']:raise ValueError('Different card')
    for c in result['changes']:
        actual=sha(allowed(card,c['path']))
        if actual==c['previous_sha256']:continue
        if actual!=c['sha256'] or sha(allowed(backup/'previous',c['path']))!=c['previous_sha256']:raise ValueError('Changed file; refusing rollback')
        changes.append(c)
    if execute:
        for c in changes:
            if identity(card)!=result['identity'] or sha(allowed(card,c['path']))!=c['sha256']:raise ValueError('Card changed during rollback')
            publish(allowed(backup/'previous',c['path']),allowed(card,c['path']),c['previous_sha256'])
    return {'rollback_files':len(changes),'applied':execute,'save_writes':0,'rom_writes':0,'firmware_writes':0}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--card',required=True);p.add_argument('--staging');p.add_argument('--package');p.add_argument('--library');p.add_argument('--backup');p.add_argument('--apply',action='store_true');p.add_argument('--rollback',action='store_true')
    p.add_argument('--display-profile',action='store_true',help='Also declare the supported optional display styles; does not select an OS filter')
    a=p.parse_args()
    if a.rollback:
        if not a.backup:p.error('--rollback needs --backup')
        r=rollback(a.card,a.backup,a.apply)
    elif a.apply:
        if not a.backup or not a.staging:p.error('--apply needs --staging and --backup')
        r=apply(a.card,a.staging,a.backup)
    else:
        if not a.package or not a.library or not a.staging:p.error('Planning needs --package, --library and --staging')
        r=stage(a.card,a.package,a.library,a.staging,a.display_profile)
    print(json.dumps({k:v for k,v in r.items() if k not in ('changes','identity','protected','roms')},indent=2))
