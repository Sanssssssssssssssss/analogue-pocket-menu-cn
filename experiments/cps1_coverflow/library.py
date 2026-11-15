#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build native CPS1/CPS1.5 menus from existing Pocket instances."""
import argparse,hashlib,importlib.util,json,re,shutil,struct
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
native=load('cps_family_instances',HERE/'instances.py')
shared=load('cps_family_art',ROOT/'experiments/nes_coverflow/library.py')
LABELS={'jtcps1':'卡普空 CPS1','jtcps15':'卡普空 CPS1.5'}
KNOWN_TITLES=json.loads((HERE/'title-aliases.json').read_text(encoding='utf8'))

def title_for(stem):
    # Menu aliases describe the instance filename; they do not claim that the
    # underlying ROM is translated or a particular regional revision.
    base=re.sub(r' \(.*$', '',stem)
    return KNOWN_TITLES.get(base,stem)

def path_bytes(value,platform,namespace):
    if not value.startswith('/') or len(value.encode('utf8'))>=256:raise ValueError('Invalid APF path length')
    if any(p=='..' for p in PurePosixPath(value).parts) or any(c in value for c in ('\\',':','\0')):raise ValueError('Unsafe APF path')
    if not any(value.startswith('/'+p+'/') for p in (f'Assets/{platform}/common',f'Assets/{namespace}/common',f'Saves/{namespace}/common')):raise ValueError('Foreign APF namespace')
    return value.encode('utf8').ljust(256,b'\0')

def pack(entries,covers,platform,namespace,warnings):
    if not 1<=len(entries)<=128 or not entries[-1]['folder']:raise ValueError('Menu page needs bounded records and final parent')
    frame_base=64+1024*len(entries);pause_base=frame_base+65536*len(entries)
    header=struct.pack('<4s5I',b'GBAF',2,len(entries),frame_base,pause_base,65536).ljust(64,b'\0')
    rows=[];art=[];hits=0;missing=0
    for e in entries:
        width,title,clipped,unknown=shared.gb.columns(e['title'],shared.gb.font())
        subwidth,subtitle,_,_=shared.gb.columns(LABELS[platform],shared.gb.font())
        if clipped or unknown:warnings.append({'path':e['rom'],'truncated':clipped,'missing_glyphs':unknown})
        row=bytearray(1024)
        struct.pack_into('<4s7I',row,0,b'ENT1',int(e['folder']),e.get('bytes',0),128,
            e.get('core_mode',0),e.get('button_map',0),width,subwidth)
        struct.pack_into('<I',row,800,e.get('dip_switches',0xffffffff))
        for offset,key in ((32,'rom'),(288,'save'),(544,'rtc')):row[offset:offset+256]=path_bytes(e[key],platform,namespace)
        cover=Path(covers)/Path(e.get('cover_key',e['rom']).lstrip('/')).with_suffix('.png') if covers and not e['folder'] else None
        if cover and cover.is_file():
            if not cover.resolve().is_relative_to(Path(covers).resolve()):raise ValueError('Cover leaves root')
            hits+=1
        else:
            cover=None
            if not e['folder']:missing+=1
        pixels=shared.gb.picture(cover,e['folder'],shared.kind(e['title'])) if cover or e['folder'] else shared.gb.title_card(e['title'],platform,strict=False)
        rows.append(bytes(row));art.append((pixels+title+subtitle).ljust(65536,b'\0'))
    pause=[]
    for i in range(2):
        image=shared.old.visual.pause_frame(i);image.paste((0,0,0),(0,140,240,160));pause.append(shared.old.visual.rgb565(image))
    return header+b''.join(rows+art+pause),hits,missing

def build(platform,source,out,titles=None,covers=None):
    source,out=Path(source).resolve(),Path(out).resolve();namespace=native.PROFILES[platform]
    if out.exists() or out.is_relative_to(source) or source.is_relative_to(out):raise ValueError('Choose fresh staging outside source')
    aliases=shared.mapping(titles);covers=Path(covers).resolve() if covers else None
    if covers and not covers.is_dir():raise ValueError('Missing cover root')
    assets=f'Assets/{namespace}/common';saves=f'Saves/{namespace}/common'
    nodes={'':{'name':LABELS[platform],'parent':'','children':[],'games':[]}}
    refs={};instances=[];excluded=[];seeds={};save_refs={};existing_save_refs={};warnings=[]
    def ensure(key):
        if key in nodes:return
        parent,_,name=key.rpartition('/');ensure(parent);nodes[parent]['children'].append(key)
        nodes[key]={'name':'备选版本' if name=='_alternatives' else name,'parent':parent,'children':[],'games':[]}
    for path in native.instance_files(source,platform):
        rel=path.relative_to(source).as_posix()
        try:
            p=native.plan(source,rel,platform);rom=p['rom'];path_bytes('/'+rom['path'],platform,namespace)
        except (OSError,ValueError,KeyError,TypeError) as error:
            excluded.append({'path':rel,'reason':str(error)});continue
        config={k:p[k] for k in ('core_mode','button_map','dip_switches')};tag=native.save_id(rom['sha256'],**config)
        refs[rom['path']]={k:rom[k] for k in ('path','bytes','sha256')};refs[rom['path']]['save_bytes']=128
        instances.append({'path':rel,'bytes':path.stat().st_size,'sha256':p['instance_sha256'],'rom_path':rom['path'],'save_tag':tag,**config})
        key='/'.join(path.relative_to(source).parts[3:-1]);ensure(key)
        nodes[key]['games'].append({'title':aliases.get(rel,title_for(path.stem)),'folder':False,'rom':'/'+rom['path'],'cover_key':'/'+rel,
            'bytes':rom['bytes'],**config,'save':f'/{saves}/{tag}.sav','rtc':f'/{saves}/{tag}.rtc'})
        save_rel=f'{saves}/{tag}.sav';existing=native.fs.safe_path(source,save_rel)
        if existing.exists():
            if not existing.is_file() or existing.stat().st_size!=128:raise ValueError('Existing isolated NVRAM has wrong size: '+save_rel)
            existing_save_refs[save_rel]={'path':save_rel,'bytes':128,'sha256':native.fs.sha(existing)}
            continue
        original=p['nvram']['original_path'];old=native.fs.safe_path(source,original)
        if old.exists():
            if not old.is_file() or old.stat().st_size!=128:raise ValueError('Native NVRAM has wrong size: '+original)
            data=old.read_bytes();save_refs[original]={'path':original,'bytes':128,'sha256':hashlib.sha256(data).hexdigest()}
        else:data=b'\xff'*128
        if save_rel in seeds and seeds[save_rel]!=data:raise ValueError('Native saves conflict for one ROM/settings identity')
        seeds[save_rel]=data
    for key,node in list(nodes.items()):
        if len(node['games'])+len(node['children'])<=127:continue
        games=node['games'];node['games']=[]
        for i in range(0,len(games),127):
            sub=(key+'/' if key else '')+f'@page{i//127+1}'
            if sub in nodes:raise ValueError('Pagination collides with original folder')
            nodes[sub]={'name':f'第 {i//127+1} 页','parent':key,'children':[],'games':games[i:i+127]};node['children'].append(sub)
        if len(node['children'])>127:raise ValueError('Too many folders at one level')
    estimate=sum(64+(len(n['children'])+len(n['games'])+1)*66560+153600 for n in nodes.values())+len(seeds)*128
    ancestor=out.parent
    while not ancestor.exists():ancestor=ancestor.parent
    if shutil.disk_usage(ancestor).free<estimate+1024**2:raise ValueError('Insufficient staging capacity')
    out.mkdir(parents=True);files=[];hits=misses=0
    def write(rel,data):
        path=native.fs.safe_path(out,rel);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        files.append({'path':rel,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    def page(key):return f'/{assets}/libs/{hashlib.sha256(key.encode()).hexdigest()[:16]}.bin' if key else f'/{assets}/menu.bin'
    def folder(key,title):return {'title':title,'folder':True,'rom':page(key),'save':f'/{saves}/'+('0'*20)+'.sav','rtc':f'/{saves}/'+('0'*20)+'.rtc'}
    if len({page(k) for k in nodes})!=len(nodes):raise ValueError('Page identity collision')
    for key,node in nodes.items():
        entries=[folder(child,nodes[child]['name']) for child in sorted(node['children'])]+node['games']+[folder(node['parent'],'返回上级' if key else '返回首页')]
        raw,h,m=pack(entries,covers,platform,namespace,warnings);write(page(key)[1:],raw);hits+=h;misses+=m
    for rel,data in seeds.items():write(rel,data)
    result={'format':'GBAF2/'+platform,'files':files,'source_refs':list(refs.values()),'instances':instances,
        'save_refs':list(save_refs.values())+list(existing_save_refs.values()),'save_imports':len(save_refs),'save_seeds':len(seeds),
        'pages':len(nodes),'game_refs':len(instances),'cover_hits':hits,'fallback_covers':misses,'excluded':excluded,'warnings':warnings,
        'source_writes':0,'rom_copies':0,'hardware_acceptance':'pending'}
    (out/'library-manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8');return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('platform',choices=native.PROFILES)
    for key in ('source','out'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--titles',type=Path);p.add_argument('--covers',type=Path);a=p.parse_args()
    r=build(a.platform,a.source,a.out,a.titles,a.covers);print(json.dumps({k:r[k] for k in ('pages','game_refs','cover_hits','fallback_covers','save_imports')}))
