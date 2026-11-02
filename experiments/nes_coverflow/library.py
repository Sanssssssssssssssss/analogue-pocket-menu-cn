#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage the whole NES directory as Chinese CoverFlow pages, read-only at source."""
import argparse,hashlib,importlib.util,json,re,shutil,struct,sys
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from install import identity,safe_path
import build_library as gb
from menu_icons import LABELS,kind
sys.path.insert(0,str(ROOT/'experiments/multi_system'))
from launch_plan import inspect_rom


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


old=load('nes_f1_library',ROOT/'experiments/nes_menu/library.py')
ASSETS=old.ASSETS;SAVES=old.SAVES


def folder(path,title):
    return {'title':title,'folder':True,'rom':path,'save':f'/{SAVES}/'+('0'*20)+'.sav',
        'rtc':f'/{SAVES}/'+('0'*20)+'.rtc'}


def pack(entries,covers=None):
    if not 1<=len(entries)<=2047 or not entries[-1]['folder']:raise ValueError('Page requires final parent')
    base=64+len(entries)*1024;pause=base+len(entries)*65536
    header=struct.pack('<4s5I',b'GBAF',2,len(entries),base,pause,65536).ljust(64,b'\0')
    rows=[];blobs=[];matched=0;missing=[]
    for entry in entries:
        width,title,clipped,unknown=gb.columns(entry['title'],gb.font())
        subwidth,subtitle,_,subunknown=gb.columns('任天堂 红白机',gb.font())
        if unknown or subunknown:raise ValueError('Missing title glyphs: '+''.join(unknown+subunknown))
        row=bytearray(1024)
        struct.pack_into('<4s7I',row,0,b'ENT1',int(entry['folder']),entry.get('bytes',0),262144,
            entry.get('rom_offset',0),entry.get('rom_config',0),width,subwidth)
        for offset,key in [(32,'rom'),(288,'save'),(544,'rtc')]:row[offset:offset+256]=old.path_bytes(entry[key])
        cover=Path(covers)/Path(entry['rom'].lstrip('/')).with_suffix('.png') if covers and not entry['folder'] else None
        if cover and cover.is_file():
            if not cover.resolve().is_relative_to(Path(covers).resolve()):raise ValueError('Cover escapes root')
            matched+=1
        else:
            cover=None
            if not entry['folder']:missing.append(entry['rom'])
        art=gb.picture(cover,entry['folder'],kind(entry['title'])) if cover or entry['folder'] else gb.title_card(entry['title'],'nes')
        rows.append(bytes(row));blobs.append((art+title+subtitle).ljust(65536,b'\0'))
    pause_frames=[]
    for i in range(2):
        image=old.visual.pause_frame(i);image.paste((0,0,0),(0,140,240,160))
        pause_frames.append(old.visual.rgb565(image))
    return header+b''.join(rows+blobs+pause_frames),matched,missing


def mapping(path):
    value=json.loads(Path(path).read_text(encoding='utf-8-sig')) if path else {}
    if not isinstance(value,dict) or any(not isinstance(v,str) or not v.strip() for v in value.values()):raise ValueError('Nonempty caption mapping required')
    return value


def build(card,out,titles=None,covers=None,folders=None,offline_source=False):
    card,out=Path(card).resolve(),Path(out).resolve()
    if out.exists() or out.is_relative_to(card) or card.is_relative_to(out):raise ValueError('Fresh local staging outside source required')
    ident={'root':str(card),'scope':'read-only offline ROM archive; final card identity/hash verification required'} if offline_source else identity(card)
    titles,folders=mapping(titles),mapping(folders)
    covers=Path(covers).resolve() if covers else None
    if covers and not covers.is_dir():raise ValueError('Missing cover root')
    base=safe_path(card,'Assets/nes/common')
    if not base.is_dir():raise ValueError('NES directory missing')
    nodes={'':{'children':set(),'games':[],'parent':'','title':'红白机游戏库'}}
    def ensure(key):
        if key in nodes:return
        parent=key.rsplit('/',1)[0] if '/' in key else '';ensure(parent)
        leaf=key.rsplit('/',1)[-1]
        label=folders.get('nes/'+key,LABELS.get(leaf,leaf))
        if leaf=='0.FAVORITES':label='经典精选'
        if re.match(r'^9[09][._ -]',leaf):label='备选版本' if not 'Hack' in leaf else '同人改版'
        nodes[key]={'children':set(),'games':[],'parent':parent,'title':label};nodes[parent]['children'].add(key)
    refs=[];excluded=[];ids={};group_hashes={};warnings=[]
    for path in sorted(base.rglob('*')):
        if not path.is_file() or path.suffix.lower()!='.nes':continue
        rel=path.relative_to(card).as_posix();safe_path(card,rel)
        if path.stat().st_size>16777216:
            excluded.append({'path':rel,'reason':'ROM exceeds native experiment size limit'});continue
        raw=path.read_bytes()
        try:info=inspect_rom('nes',raw);old.path_bytes('/'+rel)
        except ValueError as e:excluded.append({'path':rel,'reason':str(e)});continue
        digest=hashlib.sha256(raw).hexdigest();tag=digest[:20]
        if tag in ids and ids[tag]!=digest:raise ValueError('Save identity prefix collision')
        ids[tag]=digest
        key=path.relative_to(base).parent.as_posix();key='' if key=='.' else key;ensure(key)
        # A single canonical save belongs to identical bytes across categories.
        # Duplicate bytes in one directory have one visible entry.
        refs.append({'path':rel,'bytes':len(raw),'sha256':digest,'mapper':info['mapper']})
        if digest in group_hashes.setdefault(key,set()):continue
        group_hashes[key].add(digest)
        title=titles.get(rel,path.stem)
        if rel not in titles:warnings.append({'path':rel,'reason':'filename caption; Chinese name not verified'})
        nodes[key]['games'].append({'title':title,'folder':False,'rom':'/'+rel,'bytes':len(raw),
            'save':f'/{SAVES}/{tag}.sav','rtc':f'/{SAVES}/{tag}.rtc'})
    if not refs:raise ValueError('No structurally supported NES files')
    # Bound long lists while keeping the final parent item and existing genres.
    for key,node in list(nodes.items()):
        if len(node['games'])<=512:continue
        games=node['games'];node['games']=[]
        for i in range(0,len(games),512):
            child=key+'/@page'+str(i//512+1)
            if child in nodes:raise ValueError('Reserved pagination key collision')
            nodes[child]={'children':set(),'games':games[i:i+512],'parent':key,'title':'第 '+str(i//512+1)+' 页'}
            node['children'].add(child)
    def page(key):return f'/{ASSETS}/menu.bin' if key=='' else f'/{ASSETS}/libs/{hashlib.sha256(key.encode()).hexdigest()[:16]}.bin'
    if len({page(k) for k in nodes})!=len(nodes):raise ValueError('Page identity collision')
    estimate=sum(64+(len(v['children'])+len(v['games'])+1)*66560+153600 for v in nodes.values())+len(ids)*262144
    ancestor=out.parent
    while not ancestor.exists():ancestor=ancestor.parent
    if shutil.disk_usage(ancestor).free<estimate+16*1024**2:raise ValueError('Insufficient local staging capacity')
    out.mkdir(parents=True);files=[];matched=0;missing=[]
    def write(rel,raw):
        dest=safe_path(out,rel);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        files.append({'path':rel,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
    for key,node in nodes.items():
        entries=[folder(page(child),nodes[child]['title']) for child in sorted(node['children'])]+node['games']
        entries.append(folder(page(node['parent']),'返回上级' if key else '返回首页'))
        raw,m,miss=pack(entries,covers);write(page(key).lstrip('/'),raw);matched+=m;missing+=miss
    for tag in ids:
        rel=f'{SAVES}/{tag}.sav';existing=safe_path(card,rel)
        if existing.is_file():
            if existing.stat().st_size!=262144:raise ValueError('Unexpected existing isolated save length')
        else:write(rel,bytes(262144))
    receipt={'format':'GBAF2/NES','identity':ident,'files':files,'source_refs':refs,
        'unique_games':len(ids),'pages':len(nodes),'excluded':excluded,'warnings':warnings,
        'covers':{'matched_entry_references':matched,'missing_entry_references':len(missing),'missing':missing},
        'rom_copies':0,'source_writes':0,'save_imports':0,
        'save_policy':'Seed only missing isolated 256 KiB saves; existing progress is never staged or replaced',
        'hardware_acceptance':'pending; native mapper compatibility is not certified by container inspection'}
    (out/'library-manifest.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--card',required=True);p.add_argument('--out',required=True)
    for name in ['titles','covers','folders']:p.add_argument('--'+name)
    p.add_argument('--offline-source',action='store_true',help='Read an existing PC ROM backup; installer still rechecks the actual card')
    a=p.parse_args();r=build(a.card,a.out,a.titles,a.covers,a.folders,a.offline_source)
    print(json.dumps({k:r[k] for k in ['format','unique_games','pages','rom_copies','source_writes']},ensure_ascii=False))
