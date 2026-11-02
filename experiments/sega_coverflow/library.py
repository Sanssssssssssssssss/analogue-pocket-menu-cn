#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage native Sega CoverFlow pages and strictly identified practical cheats."""
import argparse,hashlib,importlib.util,json,re,shutil,struct,sys,zlib
from pathlib import Path,PurePosixPath
from controller import ROOT,PROFILES
sys.path.insert(0,str(ROOT/'tools'))
from install import safe_path,identity
import build_library as gb
from sega_formats import legacy_gamegear
from menu_icons import LABELS,kind
spec=importlib.util.spec_from_file_location('sega_pause_images',ROOT/'experiments/gba_menu/library.py')
visual=importlib.util.module_from_spec(spec);spec.loader.exec_module(visual)
LABEL={'gg':'世嘉 掌机','sms':'世嘉 家用机','sg1000':'世嘉 早期主机'}
EXT={'gg':('.gg','.sms'),'sms':('.sms',),'sg1000':('.sg','.sg1','.bin')}


def mapping(path):
    value=json.loads(Path(path).read_text(encoding='utf-8-sig')) if path else {}
    if not isinstance(value,dict) or any(not isinstance(v,str) or not v.strip() for v in value.values()):raise ValueError('Nonempty title mapping required')
    return value


def path_field(value,platform):
    namespace=PROFILES[platform][0]
    if not value.startswith('/') or len(value.encode('utf8'))>=256 or any(c in value for c in ('\\',':','\0')) or '..' in PurePosixPath(value).parts:raise ValueError('Unsafe APF path')
    if not any(value.startswith(p) for p in (f'/Assets/{platform}/common/',f'/Assets/{namespace}/common/',f'/Assets/{namespace}/cheat/',f'/Saves/{namespace}/common/')):raise ValueError('Foreign machine namespace')
    return value.encode('utf8').ljust(256,b'\0')


def profiles(path):
    if not path:return {'sha256':{},'identity':{}}
    value=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if value.get('format')!='SEGA-CHEATS1':raise ValueError('Expected SEGA-CHEATS1 identity/effects index')
    result={'sha256':{},'identity':{}}
    for row in value['profiles']:
        for key,n in ([('sha256',64)] if 'sha256' in row else [])+[('sha1',40),('crc32',8)]:
            if not re.fullmatch('[0-9a-fA-F]{'+str(n)+'}',row[key]):raise ValueError('Invalid cheat identity field '+key)
        source=row['source']
        if not source['url'].startswith('https://') or not re.fullmatch('[0-9a-f]{40}',source['commit']) or not source.get('license'):raise ValueError('Cheat provenance required')
        if type(row['bytes'])!=int or not 192<=row['bytes']<=4194304:raise ValueError('Invalid candidate ROM size')
        key=(row['sha1'].lower(),row['crc32'].lower(),row['bytes'])
        if key in result['identity']:raise ValueError('Ambiguous profiles for one exact ROM')
        result['identity'][key]=row
        if 'sha256' in row:
            digest=row['sha256'].lower()
            if digest in result['sha256']:raise ValueError('Ambiguous SHA256 profile')
            result['sha256'][digest]=row
    return result


def cheat_payload(profile,raw):
    facts={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'sha1':hashlib.sha1(raw).hexdigest(),'crc32':f'{zlib.crc32(raw)&0xffffffff:08x}'}
    if any(str(profile[k]).lower()!=str(v).lower() for k,v in facts.items() if k!='sha256' or k in profile):raise ValueError('Cheat profile does not match every available ROM identity field')
    effects=profile['effects']
    if not 1<=len(effects)<=2:raise ValueError('One or two curated practical effects required')
    lines=[];written={};total=0
    for i,effect in enumerate(effects):
        if not effect.get('title') or not effect['codes']:raise ValueError('Named practical effect with codes required')
        for j,code in enumerate(effect['codes']):
            if code['type']=='par':
                address,value=code['address'],code['value']
                if type(address)!=int or type(value)!=int or not 0xc000<=address<=0xdfff or not 0<=value<=255:raise ValueError('PAR must target native work RAM with an 8-bit value')
                if address in written and written[address]!=value:raise ValueError('Conflicting practical RAM effects')
                written[address]=value
                digits=f'00{address:04X}{value:02X}'
                token=digits[:4]+'-'+digits[4:]
            elif code['type']=='game_genie':
                value=code['code'].upper()
                if not re.fullmatch(r'[0-9A-F]{3}-[0-9A-F]{3}(?:-[0-9A-F]{3})?',value):raise ValueError('Unsupported Game Genie shape')
                digits=value.replace('-','');address=((int(digits[5],16)^15)<<12)|int(digits[2:5],16)
                if address>=0xc000:raise ValueError('Game Genie target is outside cartridge ROM space')
                token=value
            else:raise ValueError('Unsupported native cheat mechanism')
            # One parser group per code avoids ambiguous boundaries between
            # six/nine-digit Game Genie and PAR codes in a combined effect.
            lines += [f'cheat{total}_desc = "Effect {i+1} Code {j+1}"',f'cheat{total}_code = "{token}"',f'cheat{total}_enable = true']
            total+=1
    if total>32:raise ValueError('Native engine code capacity exceeded')
    payload=('cheats = '+str(total)+'\n'+'\n'.join(lines)+'\n').encode('ascii');payload+=b'\n'*((-len(payload))%4)
    if len(payload)>65536:raise ValueError('Cheat file too large')
    return payload


def pack(entries,platform,covers=None):
    # CB=7 is a direct 128-texture cache. Larger counts can alias at wrap.
    if not 1<=len(entries)<=128 or not entries[-1]['folder']:raise ValueError('Page requires final parent and at most 128 texture slots')
    count=len(entries);base=64+count*1024;pause=base+count*65536
    rows=[];blobs=[];matched=0;missing=[]
    for entry in entries:
        subtitle=LABEL[platform]+(' · 已配金手指' if entry.get('cheat_bytes') else '')
        width,title,_,unknown=gb.columns(entry['title'],gb.font());subwidth,sub,_,subunknown=gb.columns(subtitle,gb.font())
        if unknown or subunknown or subwidth>300:raise ValueError('Unsupported Unicode caption')
        row=bytearray(1024);struct.pack_into('<4s7I',row,0,b'ENT1',int(entry['folder']),entry.get('bytes',0),32768,entry.get('cheat_bytes',0),0,width,subwidth)
        for offset,key in [(32,'rom'),(288,'save'),(544,'cheat')]:row[offset:offset+256]=path_field(entry[key],platform)
        cover=Path(covers)/Path(entry['rom'].lstrip('/')).with_suffix('.png') if covers and not entry['folder'] else None
        if cover and cover.is_file():
            if not cover.resolve().is_relative_to(Path(covers).resolve()):raise ValueError('Cover escapes root')
            matched+=1
        else:
            cover=None
            if not entry['folder']:missing.append(entry['rom'])
        art=gb.picture(cover,entry['folder'],kind(entry['title'])) if cover or entry['folder'] else gb.title_card(entry['title'],platform)
        rows.append(bytes(row));blobs.append((art+title+sub).ljust(65536,b'\0'))
    pause_frames=[]
    for i in range(2):
        image=visual.pause_frame(i);image.paste((0,0,0),(0,140,240,160));pause_frames.append(visual.rgb565(image))
    raw=struct.pack('<4s5I',b'GBAF',2,count,base,pause,65536).ljust(64,b'\0')+b''.join(rows+blobs+pause_frames)
    return raw,matched,missing


def build(card,out,platform,titles=None,covers=None,folders=None,cheats=None,offline_source=False):
    card,out=Path(card).resolve(),Path(out).resolve()
    if out.exists() or out.is_relative_to(card) or card.is_relative_to(out):raise ValueError('Fresh local staging outside source required')
    ident={'root':str(card),'scope':'read-only offline ROM archive; final card identity/hash verification required'} if offline_source else identity(card)
    namespace=PROFILES[platform][0]
    titles,folders,candidates=mapping(titles),mapping(folders),profiles(cheats)
    covers=Path(covers).resolve() if covers else None
    if covers and not covers.is_dir():raise ValueError('Cover root missing')
    source=safe_path(card,f'Assets/{platform}/common')
    if not source.is_dir():raise ValueError('Native machine asset folder missing')
    nodes={'':{'title':LABEL[platform]+'游戏库','parent':'','children':set(),'games':[]}}
    def ensure(key):
        if key in nodes:return
        parent=key.rsplit('/',1)[0] if '/' in key else '';ensure(parent);leaf=key.rsplit('/',1)[-1]
        title=folders.get(platform+'/'+key,LABELS.get(leaf,'经典精选' if leaf=='0.FAVORITES' else leaf))
        nodes[key]={'title':title,'parent':parent,'children':set(),'games':[]};nodes[parent]['children'].add(key)
    refs=[];excluded=[];warnings=[];ids={};seen={};payloads={};applied=[]
    for path in sorted(source.rglob('*')):
        if not path.is_file() or path.suffix.lower() not in EXT[platform]:continue
        rel=path.relative_to(card).as_posix();safe_path(card,rel)
        if platform=='sg1000' and '(SC-3000)' in path.stem:
            excluded.append({'path':rel,'reason':'SC-3000 computer software; keyboard/platform not implemented by this SG-1000 entry'});continue
        if not 192<=path.stat().st_size<=4194304 or path.stat().st_size%4:
            excluded.append({'path':rel,'reason':'native aligned 192-byte..4-MiB limit'});continue
        path_field('/'+rel,platform);raw=path.read_bytes()
        if platform=='gg' and path.suffix.lower()=='.sms' and not legacy_gamegear(raw):
            excluded.append({'path':rel,'reason':'Legacy .sms file is not identified as a Game Gear image; source bytes preserved'});continue
        digest=hashlib.sha256(raw).hexdigest();tag=digest[:20]
        if tag in ids and ids[tag]!=digest:raise ValueError('Progress identity prefix collision')
        ids[tag]=digest
        key=path.relative_to(source).parent.as_posix();key='' if key=='.' else key;ensure(key)
        refs.append({'path':rel,'bytes':len(raw),'sha256':digest})
        if digest in seen.setdefault(key,set()):continue
        seen[key].add(digest);payload=b''
        profile=candidates['sha256'].get(digest) or candidates['identity'].get((hashlib.sha1(raw).hexdigest(),f'{zlib.crc32(raw)&0xffffffff:08x}',len(raw)))
        if profile:
            payload=cheat_payload(profile,raw);payloads[tag]=payload
            if not any(p['sha256']==digest for p in applied):applied.append({'sha256':digest,'effects':[x['title'] for x in profile['effects']],'source':profile['source']})
        title=titles.get(rel,path.stem)
        if rel not in titles:warnings.append({'path':rel,'reason':'filename caption; Chinese name not verified'})
        nodes[key]['games'].append({'folder':False,'title':title,'rom':'/'+rel,'bytes':len(raw),
            'save':f'/Saves/{namespace}/common/{tag}.sav','cheat':f'/Assets/{namespace}/cheat/{tag}.cht','cheat_bytes':len(payload)})
    if not refs:raise ValueError('No native candidate ROM files')
    for key,node in list(nodes.items()):
        if len(node['games'])+len(node['children'])<=127:continue
        games=node['games'];node['games']=[]
        for i in range(0,len(games),127):
            child=key+'/@page'+str(i//127+1)
            if child in nodes:raise ValueError('Reserved pagination key collision')
            nodes[child]={'title':'第 '+str(i//127+1)+' 页','parent':key,'children':set(),'games':games[i:i+127]};node['children'].add(child)
    if any(len(n['games'])+len(n['children'])>127 for n in nodes.values()):raise ValueError('More than 127 child folders; organize into nested categories')
    def page(key):return f'/Assets/{namespace}/common/menu.bin' if not key else f'/Assets/{namespace}/common/libs/{hashlib.sha256(key.encode()).hexdigest()[:16]}.bin'
    if len({page(k) for k in nodes})!=len(nodes):raise ValueError('Category identity collision')
    estimate=sum(64+(len(n['children'])+len(n['games'])+1)*66560+153600 for n in nodes.values())+len(ids)*32768+sum(map(len,payloads.values()))
    ancestor=out.parent
    while not ancestor.exists():ancestor=ancestor.parent
    if shutil.disk_usage(ancestor).free<estimate+16*1024**2:raise ValueError('Insufficient local capacity')
    out.mkdir(parents=True);files=[];matched=0;missing=[]
    def write(rel,raw):
        dest=safe_path(out,rel);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        files.append({'path':rel,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
    def folder(path,title):return {'folder':True,'title':title,'rom':path,
        'save':f'/Saves/{namespace}/common/'+('0'*20)+'.sav','cheat':f'/Assets/{namespace}/cheat/'+('0'*20)+'.cht'}
    for key,node in nodes.items():
        entries=[folder(page(k),nodes[k]['title']) for k in sorted(node['children'])]+node['games']+[folder(page(node['parent']),'返回上级' if key else '返回首页')]
        raw,m,miss=pack(entries,platform,covers);write(page(key).lstrip('/'),raw);matched+=m;missing+=miss
    for tag in ids:
        rel=f'Saves/{namespace}/common/{tag}.sav';existing=safe_path(card,rel)
        if existing.is_file():
            if existing.stat().st_size!=32768:raise ValueError('Existing isolated progress size differs')
        else:write(rel,b'\xff'*32768)
    for tag,payload in payloads.items():write(f'Assets/{namespace}/cheat/{tag}.cht',payload)
    receipt={'format':'GBAF2/Sega','platform':platform,'namespace':namespace,'identity':ident,'files':files,'source_refs':refs,
        'pages':len(nodes),'unique_games':len(ids),'excluded':excluded,'warnings':warnings,'cheats':applied,
        'covers':{'matched_entry_references':matched,'missing_entry_references':len(missing),'missing':missing},
        'rom_copies':0,'source_writes':0,'original_save_writes':0,
        'save_policy':'Only missing isolated 32 KiB saves are seeded to FF; no guessed import or overwrite',
        'hardware_acceptance':'pending; filename/container/identity checks do not certify games or cheat effects'}
    (out/'library-manifest.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['card','out']:p.add_argument('--'+name,required=True)
    p.add_argument('--platform',choices=PROFILES,required=True)
    for name in ['titles','covers','folders','cheats']:p.add_argument('--'+name)
    p.add_argument('--offline-source',action='store_true',help='Read an existing PC ROM backup; installer still rechecks the actual card')
    a=p.parse_args();r=build(a.card,a.out,a.platform,a.titles,a.covers,a.folders,a.cheats,a.offline_source)
    print(json.dumps({k:r[k] for k in ['format','platform','pages','unique_games','rom_copies','source_writes']},ensure_ascii=False))
