#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Preview/add an isolated Sega entry with progress backup and reversible files."""
import argparse,importlib.util,json,os,re,shutil,struct,sys
from datetime import datetime,timezone
from pathlib import Path
from controller import ROOT,PROFILES
spec=importlib.util.spec_from_file_location('sega_install_primitives',ROOT/'tools/install.py')
sys.path.insert(0,str(ROOT/'tools'))
primitives=importlib.util.module_from_spec(spec);spec.loader.exec_module(primitives)
safe_path,identity,publish=primitives.safe_path,primitives.identity,primitives.publish
from build_library import sha
from apf_metadata import check_core
import menu_bindings
SHORT={'gg':'GG','sms':'SMS','sg1000':'SG1000'}


def allowed(root,rel,platform):
    ns=PROFILES[platform][0];core='Cores/pocketlab.'+SHORT[platform]+'/'
    if not (rel.startswith(core) and (rel[len(core):] in [k+'.json' for k in ('core','data','audio','input','interact','variants','video')]+[platform+'.rbf_r'])
        or rel in (f'Platforms/{ns}.json',f'Platforms/_images/{ns}.bin',f'Assets/{ns}/common/menu.bin')
        or re.fullmatch(f'Assets/{ns}/common/libs/[0-9a-f]{{16}}\\.bin',rel)
        or re.fullmatch(f'Assets/{ns}/cheat/[0-9a-f]{{20}}\\.cht',rel)
        or re.fullmatch(f'Saves/{ns}/common/[0-9a-f]{{20}}\\.sav',rel)):
        raise ValueError('Outside isolated native Sega namespace: '+rel)
    return safe_path(root,rel)


def verify_roms(card,refs,platform):
    by_name={}
    for row in refs:
        rel=row['path']
        if not rel.startswith(f'Assets/{platform}/common/') or not re.fullmatch('[0-9a-f]{64}',row['sha256']):raise ValueError('Invalid native ROM identity')
        path=safe_path(card,rel)
        if not 192<=row['bytes']<=4194304 or row['bytes']%4 or path.stat().st_size!=row['bytes'] or sha(path)!=row['sha256']:raise ValueError('ROM changed or outside native limits: '+rel)
        if rel in by_name:raise ValueError('Duplicate source identity')
        by_name[rel]=row
    if not by_name:raise ValueError('Empty source identities')
    return by_name


def plan(card,package,library,platform,offline_source=False,refresh=False):
    card,package,library=map(lambda p:Path(p).resolve(),(card,package,library));ns,slot,address,_=PROFILES[platform]
    core='Cores/pocketlab.'+SHORT[platform]+'/'
    if any(p.is_relative_to(card) or card.is_relative_to(p) for p in (package,library)):raise ValueError('Staging must be outside card')
    ident={'root':str(card),'scope':'read-only offline archive; actual card identity required before writes'} if offline_source else identity(card)
    build=json.loads((package/'build-receipt.json').read_text())
    lib=json.loads((library/'library-manifest.json').read_text(encoding='utf8'))
    if (build.get('core')!='pocketlab.'+SHORT[platform] or any(m.get('platform')!=platform or m.get('namespace')!=ns for m in (build,lib))
        or build.get('menu_format')!='GBAF2/Sega' or lib.get('format')!='GBAF2/Sega' or build['minimum_slack_ns']<0 or build['timing_records']<60):raise ValueError('Matching timing-checked Sega CoverFlow components required')
    refs=verify_roms(card,lib['source_refs'],platform);changes=[];seen=set()
    for root,manifest in [(package/'core',build),(library,lib)]:
        for item in manifest['files']:
            rel=item['path'];path=allowed(root,rel,platform);target=allowed(card,rel,platform)
            if rel.casefold() in seen:raise ValueError('Overlapping staged files')
            seen.add(rel.casefold())
            if target.exists() and not refresh:raise ValueError('First-install tool refuses existing file: '+rel)
            if path.stat().st_size!=item['bytes'] or sha(path)!=item['sha256']:raise ValueError('Staged file changed')
            changes.append({**item,'source':str(root)})
    required={core+k+'.json' for k in ('core','data','audio','input','interact','variants','video')}|{core+platform+'.rbf_r',f'Platforms/{ns}.json',f'Platforms/_images/{ns}.bin',f'Assets/{ns}/common/menu.bin'}
    if not {p.casefold() for p in required}.issubset(seen):raise ValueError('Incomplete entry')
    meta=check_core(package/'core'/core)
    if meta['metadata']['platform_ids']!=[ns,platform] or meta['framework']['sleep_supported'] or meta['framework']['hardware']['cartridge_adapter']!=-1:raise ValueError('Unexpected platform/sleep/cartridge profile')
    slots=json.loads((package/'core'/core/'data.json').read_text())['data']['data_slots']
    if [s['id'] for s in slots]!=[100,slot,2,3] or int(slots[1]['address'],16)!=address or int(slots[2]['size_maximum'],16)!=32768:raise ValueError('Native APF datatable binding differs')
    video=json.loads((package/'core'/core/'video.json').read_text())['video']['scaler_modes']
    if len(video)!=6 or [(m['width'],m['height']) for m in video[4:]]!=[(320,288),(256,240)]:raise ValueError('CoverFlow/pause scaler binding differs')
    pages={c['path'] for c in changes if c['path'].startswith(f'Assets/{ns}/common/')};bindings={}
    for rel in pages:
        raw=allowed(library,rel,platform).read_bytes()
        if len(raw)<64:raise ValueError('Truncated menu')
        magic,version,count,base,pause,stride=struct.unpack_from('<4s5I',raw)
        if magic!=b'GBAF' or version!=2 or not 1<=count<=128 or base!=64+count*1024 or pause!=base+count*65536 or stride!=65536 or len(raw)!=pause+153600:raise ValueError('Menu layout differs or exceeds 128 texture slots')
        for i in range(count):
            row=raw[64+i*1024:64+(i+1)*1024];flags,rom_bytes,save_bytes,cheat_bytes=struct.unpack_from('<4I',row,4)
            if row[:4]!=b'ENT1' or flags not in (0,1) or save_bytes!=32768 or cheat_bytes>65536 or cheat_bytes%4:raise ValueError('Invalid menu record')
            values=[row[o:o+256].split(b'\0',1)[0].decode('utf8') for o in (32,288,544)]
            if any(not v.startswith('/') for v in values):raise ValueError('Absolute APF paths required')
            for value in values:safe_path(card,value[1:])
            if flags:
                if values[0][1:] not in pages or cheat_bytes:raise ValueError('Broken category link')
                continue
            source=refs.get(values[0][1:])
            if source is None or rom_bytes!=source['bytes']:raise ValueError('Menu ROM identity missing')
            tag=source['sha256'][:20]
            if tag in bindings and bindings[tag]!=cheat_bytes:raise ValueError('Conflicting cheat bindings for the same ROM')
            bindings[tag]=cheat_bytes
            if values[1:]!=[f'/Saves/{ns}/common/{tag}.sav',f'/Assets/{ns}/cheat/{tag}.cht']:raise ValueError('Foreign progress/cheat identity')
            save=values[1][1:];path=allowed(library,save,platform) if save.casefold() in seen else allowed(card,save,platform)
            if not path.is_file() or path.stat().st_size!=32768:raise ValueError('Seeded progress missing')
            if cheat_bytes:
                cheat=values[2][1:]
                if cheat.casefold() not in seen or allowed(library,cheat,platform).stat().st_size!=cheat_bytes:raise ValueError('Cheat binding/size differs')
        if not raw[64+(count-1)*1024+4]:raise ValueError('Missing parent entry')
    changes.sort(key=lambda c:(c['path']==core+'core.json',c['path']==f'Platforms/{ns}.json',c['path']))
    result={'identity':ident,'platform':platform,'changes':changes,'source_refs':lib['source_refs'],'core_version':build['version'],
        'status':'offline_validation_only' if offline_source else 'plan_only','source_writes':0,'firmware_writes':0,'original_save_writes':0,'hardware_acceptance':'pending'}
    if refresh:
        guards=menu_bindings.existing(card,SHORT[platform],bindings,refs=lib['source_refs'])
        result.update(primitives.refresh_library_plan(card,package/'core',changes,core))
        result['guards']+=guards
    return result


def apply(card,package,library,backup,platform):
    card,backup=Path(card).resolve(),Path(backup).resolve()
    if backup.exists() or any(backup.is_relative_to(Path(p).resolve()) or Path(p).resolve().is_relative_to(backup) for p in (card,package,library)):raise ValueError('Fresh external backup required')
    result=plan(card,package,library,platform)
    if shutil.disk_usage(card).free<sum(c['bytes'] for c in result['changes'])+32*1024**2:raise ValueError('Insufficient card space')
    roots=('Saves/gba','Saves/gbalab','Saves/'+platform,'Saves/'+PROFILES[platform][0])
    protected=[p for name in roots for p in (card/name).rglob('*') if p.is_file()]
    ancestor=backup.parent
    while not ancestor.exists():ancestor=ancestor.parent
    if shutil.disk_usage(ancestor).free<sum(p.stat().st_size for p in protected)+1024**2:raise ValueError('Insufficient backup space')
    backup.mkdir(parents=True);records=[]
    for p in protected:
        rel=p.relative_to(card).as_posix();safe_path(card,rel);dest=safe_path(backup/'progress',rel);dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(p,dest);digest=sha(p)
        if sha(dest)!=digest:raise ValueError('Progress backup verification failed')
        records.append({'path':rel,'bytes':p.stat().st_size,'sha256':digest})
    result.update(protected=records,created_utc=datetime.now(timezone.utc).isoformat(),status='backed_up_before_writes')
    receipt=backup/'install-receipt.json';receipt.write_text(json.dumps(result,indent=2)+'\n')
    verify_roms(card,result['source_refs'],platform)
    with (backup/'journal.jsonl').open('a',encoding='utf8') as journal:
        for c in result['changes']:
            if identity(card)!=result['identity']:raise ValueError('Card changed during installation')
            target=allowed(card,c['path'],platform)
            if target.exists():raise ValueError('Destination appeared; preserve it')
            journal.write(json.dumps(c)+'\n');journal.flush();os.fsync(journal.fileno())
            publish(allowed(Path(c['source']),c['path'],platform),target,c['sha256'])
    for row in records:
        if sha(safe_path(card,row['path']))!=row['sha256']:raise ValueError('Protected progress changed')
    result['status']='installed_sha256_verified_original_progress_unchanged';receipt.write_text(json.dumps(result,indent=2)+'\n');return result


def rollback(card,backup,execute=False):
    card,backup=Path(card).resolve(),Path(backup).resolve();result=json.loads((backup/'install-receipt.json').read_text());platform=result['platform']
    if identity(card)!=result['identity']:raise ValueError('Different card')
    changes=[]
    for c in result['changes']:
        if c['path'].startswith('Saves/'):continue
        p=allowed(card,c['path'],platform)
        if not p.exists():continue
        if sha(p)!=c['sha256']:raise ValueError('Changed file; preserve it for review')
        changes.append(c)
    if execute:
        for c in reversed(changes):
            p=allowed(card,c['path'],platform)
            if identity(card)!=result['identity'] or sha(p)!=c['sha256']:raise ValueError('Card changed during rollback')
            p.unlink()
    return {'applied':execute,'entry_files_removed':len(changes),'save_writes':0,'firmware_writes':0}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--card',required=True);p.add_argument('--platform',choices=PROFILES)
    for name in ('package','library','backup'):p.add_argument('--'+name)
    p.add_argument('--apply',action='store_true');p.add_argument('--rollback',action='store_true')
    p.add_argument('--offline-source',action='store_true',help='Read-only preflight against a PC ROM archive; never permits writes')
    a=p.parse_args()
    if a.offline_source and (a.apply or a.rollback):p.error('Offline archive validation cannot apply or roll back')
    if a.rollback:
        if not a.backup:p.error('Rollback needs --backup')
        r=rollback(a.card,a.backup,a.apply)
    else:
        if not a.platform or not a.package or not a.library or (a.apply and not a.backup):p.error('Platform/package/library and, for writes, backup required')
        r=apply(a.card,a.package,a.library,a.backup,a.platform) if a.apply else plan(a.card,a.package,a.library,a.platform,a.offline_source)
    print(json.dumps({k:v for k,v in r.items() if k not in ('changes','source_refs','protected','identity')},indent=2))
