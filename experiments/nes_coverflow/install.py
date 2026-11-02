#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Plan/add the new NES entry with targeted progress backup and reversible files."""
import argparse,json,os,re,shutil,struct,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from install import safe_path,identity,publish
from build_library import sha
from apf_metadata import check_core
CORE='Cores/pocketlab.NES/'
ASSETS='Assets/neslab/common/'
SAVES='Saves/neslab/common/'


def allowed(root,rel):
    if not (re.fullmatch(r'Cores/pocketlab\.NES/(?:core|data|audio|input|interact|video)\.json',rel)
        or rel==CORE+'nes.rbf_r' or rel in ('Platforms/neslab.json','Platforms/_images/neslab.bin',ASSETS+'menu.bin')
        or re.fullmatch(ASSETS+r'libs/[0-9a-f]{16}\.bin',rel) or re.fullmatch(SAVES+r'[0-9a-f]{20}\.sav',rel)):
        raise ValueError('Outside isolated NES namespace: '+rel)
    return safe_path(root,rel)


def verify_roms(card,refs):
    by_name={}
    for row in refs:
        rel=row['path']
        if not rel.startswith('Assets/nes/common/') or not re.fullmatch('[0-9a-f]{64}',row['sha256']):raise ValueError('Invalid NES ROM identity')
        path=safe_path(card,rel)
        if path.stat().st_size!=row['bytes'] or sha(path)!=row['sha256']:raise ValueError('ROM changed: '+rel)
        if rel in by_name:raise ValueError('Duplicate source identity')
        by_name[rel]=row
    if not by_name:raise ValueError('Empty source identities')
    return by_name


def plan(card,package,library):
    card,package,library=map(lambda p:Path(p).resolve(),(card,package,library))
    if any(p.is_relative_to(card) or card.is_relative_to(p) for p in (package,library)):raise ValueError('Staging must be outside card')
    ident=identity(card);build=json.loads((package/'build-receipt.json').read_text())
    lib=json.loads((library/'library-manifest.json').read_text(encoding='utf8'))
    if build.get('core')!='pocketlab.NES' or build.get('menu_format')!='GBAF2/NES' or lib.get('format')!='GBAF2/NES' or build['minimum_slack_ns']<0 or build['timing_records']<40:raise ValueError('Matching timing-checked NES CoverFlow components required')
    refs=verify_roms(card,lib['source_refs']);changes=[];seen=set()
    for root,manifest in [(package/'core',build),(library,lib)]:
        for item in manifest['files']:
            rel=item['path'];path=allowed(root,rel);target=allowed(card,rel)
            if rel.casefold() in seen:raise ValueError('Overlapping staged files')
            seen.add(rel.casefold())
            if target.exists():raise ValueError('First-install tool refuses existing file: '+rel)
            if path.stat().st_size!=item['bytes'] or sha(path)!=item['sha256']:raise ValueError('Staged file changed')
            changes.append({**item,'source':str(root)})
    if not {CORE.lower()+'core.json',(ASSETS+'menu.bin').lower()}.issubset(seen):raise ValueError('Incomplete entry')
    meta=check_core(package/'core'/CORE)
    if meta['metadata']['platform_ids']!=['neslab','nes'] or meta['framework']['sleep_supported']:raise ValueError('Unexpected platform/sleep profile')
    slots=json.loads((package/'core'/CORE/'data.json').read_text())['data']['data_slots']
    if [s['id'] for s in slots]!=[100,0,10,11]:raise ValueError('APF datatable order differs')
    pages={c['path'] for c in changes if c['path'].startswith(ASSETS)}
    for rel in pages:
        raw=allowed(library,rel).read_bytes()
        if len(raw)<64:raise ValueError('Truncated menu')
        magic,version,count,base,pause,stride=struct.unpack_from('<4s5I',raw)
        if magic!=b'GBAF' or version!=2 or not 1<=count<=2047 or base!=64+count*1024 or pause!=base+count*65536 or stride!=65536 or len(raw)!=pause+153600:raise ValueError('Menu layout differs')
        for i in range(count):
            row=raw[64+i*1024:64+(i+1)*1024]
            if row[:4]!=b'ENT1' or int.from_bytes(row[4:8],'little') not in (0,1):raise ValueError('Invalid menu record')
            values=[row[o:o+256].split(b'\0',1)[0].decode('utf8') for o in (32,288,544)]
            if any(not value.startswith('/') for value in values):raise ValueError('Absolute APF paths required')
            if row[4]:
                if values[0].lstrip('/') not in pages:raise ValueError('Broken category link')
            else:
                source=refs.get(values[0].lstrip('/'))
                if source is None or int.from_bytes(row[8:12],'little')!=source['bytes']:raise ValueError('Menu ROM identity missing')
                tag=source['sha256'][:20]
                if values[1:]!=['/'+SAVES+tag+'.sav','/'+SAVES+tag+'.rtc']:raise ValueError('Foreign progress identity')
                save=values[1].lstrip('/')
                path=allowed(library,save) if save.casefold() in seen else allowed(card,save)
                if not path.is_file() or path.stat().st_size!=262144:raise ValueError('Seeded progress missing')
        if not raw[64+(count-1)*1024+4]:raise ValueError('Missing parent entry')
    changes.sort(key=lambda c:(c['path']==CORE+'core.json',c['path']=='Platforms/neslab.json',c['path']))
    return {'identity':ident,'changes':changes,'source_refs':lib['source_refs'],'core_version':build['version'],
        'status':'plan_only','source_writes':0,'firmware_writes':0,'original_save_writes':0,'hardware_acceptance':'pending'}


def apply(card,package,library,backup):
    card,backup=Path(card).resolve(),Path(backup).resolve()
    if backup.exists() or any(backup.is_relative_to(Path(p).resolve()) or Path(p).resolve().is_relative_to(backup) for p in (card,package,library)):raise ValueError('Fresh external backup required')
    result=plan(card,package,library)
    if shutil.disk_usage(card).free<sum(c['bytes'] for c in result['changes'])+32*1024**2:raise ValueError('Insufficient card space')
    protected=[p for name in ('Saves/nes','Saves/neslab','Saves/gba','Saves/gbalab') for p in (card/name).rglob('*') if p.is_file()]
    ancestor=backup.parent
    while not ancestor.exists():ancestor=ancestor.parent
    if shutil.disk_usage(ancestor).free<sum(p.stat().st_size for p in protected)+1024**2:raise ValueError('Insufficient backup space')
    backup.mkdir(parents=True);records=[]
    for p in protected:
        rel=p.relative_to(card).as_posix();safe_path(card,rel)
        dest=safe_path(backup/'progress',rel);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
        if sha(dest)!=sha(p):raise ValueError('Progress backup mismatch')
        records.append({'path':rel,'sha256':sha(p),'bytes':p.stat().st_size})
    verify_roms(card,result['source_refs'])
    result.update(status='backup_verified_install_pending',protected=records,created_utc=datetime.now(timezone.utc).isoformat())
    receipt=backup/'install-receipt.json';receipt.write_text(json.dumps(result,indent=2)+'\n')
    with (backup/'journal.jsonl').open('x') as journal:
        for c in result['changes']:
            if identity(card)!=result['identity'] or allowed(card,c['path']).exists():raise ValueError('Card changed during install')
            journal.write(json.dumps(c)+'\n');journal.flush();os.fsync(journal.fileno())
            publish(allowed(Path(c['source']),c['path']),allowed(card,c['path']),c['sha256'])
    for row in records:
        if sha(safe_path(card,row['path']))!=row['sha256']:raise ValueError('Protected progress changed')
    result['status']='installed_sha256_verified_original_progress_unchanged';receipt.write_text(json.dumps(result,indent=2)+'\n')
    return result


def rollback(card,backup,execute=False):
    card,backup=Path(card).resolve(),Path(backup).resolve()
    result=json.loads((backup/'install-receipt.json').read_text())
    if identity(card)!=result['identity']:raise ValueError('Different card')
    changes=[]
    for c in result['changes']:
        if c['path'].startswith('Saves/'):continue
        p=allowed(card,c['path'])
        if not p.exists():continue
        if sha(p)!=c['sha256']:raise ValueError('Changed file; preserve it for review')
        changes.append(c)
    if execute:
        for c in reversed(changes):
            p=allowed(card,c['path'])
            if identity(card)!=result['identity'] or sha(p)!=c['sha256']:raise ValueError('Card changed during rollback')
            p.unlink()
    return {'applied':execute,'entry_files_removed':len(changes),'save_writes':0,'firmware_writes':0}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--card',required=True)
    for name in ['package','library','backup']:p.add_argument('--'+name)
    p.add_argument('--apply',action='store_true');p.add_argument('--rollback',action='store_true');a=p.parse_args()
    if a.rollback:
        if not a.backup:p.error('Rollback needs --backup')
        r=rollback(a.card,a.backup,a.apply)
    else:
        if not a.package or not a.library or (a.apply and not a.backup):p.error('Package/library and, for writes, backup required')
        r=apply(a.card,a.package,a.library,a.backup) if a.apply else plan(a.card,a.package,a.library)
    print(json.dumps({k:v for k,v in r.items() if k not in ('changes','source_refs','protected','identity')},indent=2))
