#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Index existing Arduboy HEX files and seed isolated native EEPROM saves."""
import argparse,hashlib,importlib.util,json,struct,sys
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[2]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
hexfile=load('ard_library_hexfile',Path(__file__).with_name('hexfile.py'))
sys.path.insert(0,str(ROOT/'tools'))
import build_library as art
from install import safe_path
from menu_icons import LABELS,kind,folder_label
NAMESPACE='ardlab'
ASSETS=f'Assets/{NAMESPACE}/common'

def path_bytes(value):
    if not value.startswith(('/Assets/','/Saves/ardlab/common/')) or any(x in value for x in ('\\',':','\0')) or '..' in PurePosixPath(value).parts:
        raise ValueError('Unsafe APF asset path')
    raw=value.encode('utf8')
    if len(raw)>=256:raise ValueError('APF UTF-8 path is 256 bytes or longer')
    return raw.ljust(256,b'\0')

def pack(entries,covers=None,warnings=None):
    if not 1<=len(entries)<=128 or not entries[-1]['folder']:raise ValueError('Page must end with parent')
    base=64+len(entries)*1024;end=base+len(entries)*65536
    header=struct.pack('<4s5I',b'GBAF',2,len(entries),base,end,65536).ljust(64,b'\0')
    rows=[];blobs=[];hits=0;missing=[];glyphs=art.font()
    for e in entries:
        width,title,clipped,unknown=art.columns(e['title'],glyphs)
        subwidth,subtitle,_,_=art.columns('Arduboy 掌机',glyphs)
        if warnings is not None and (clipped or unknown):warnings.append({'path':e['rom'],'truncated':clipped,'missing_glyphs':unknown})
        row=bytearray(1024)
        struct.pack_into('<4s7I',row,0,b'ENT1',int(e['folder']),e.get('bytes',0),e.get('program_bytes',0),width,subwidth,0,0)
        row[32:288]=path_bytes(e['rom'])
        if not e['folder']:row[288:544]=path_bytes(e['save'])
        rows.append(row);cover=None
        if covers is not None and not e['folder']:
            possible=(covers/e['rom'].lstrip('/')).with_suffix('.png')
            if not possible.resolve().is_relative_to(covers):raise ValueError('Cover path escapes source')
            if possible.is_file():cover=possible;hits+=1
        if not e['folder'] and cover is None:missing.append(e['rom'])
        picture=art.picture(cover,e['folder'],kind(e['title'])) if cover or e['folder'] else art.title_card(e['title'],'Arduboy',strict=False)
        blobs.append((picture+title+subtitle).ljust(65536,b'\0'))
    return header+b''.join(rows+blobs),hits,missing

def build(source,out,titles=None,covers=None,rom_dir='Assets/arduboy/common'):
    source,out=Path(source).resolve(),Path(out).resolve()
    if out.exists() or out.is_relative_to(source) or source.is_relative_to(out):raise ValueError('Fresh separate staging required')
    aliases=json.loads(Path(titles).read_text(encoding='utf-8-sig')) if titles else {}
    if not isinstance(aliases,dict) or any(not isinstance(v,str) or not v.strip() for v in aliases.values()):raise ValueError('Invalid aliases')
    covers=Path(covers).resolve() if covers else None
    if covers is not None and not covers.is_dir():raise ValueError('Cover root is missing')
    directory=safe_path(source,rom_dir)
    if not directory.is_dir():raise ValueError('ROM directory is missing')
    nodes={'':{'name':'Arduboy 游戏库','parent':'','children':[],'games':[]}}
    refs=[];excluded=[];warnings=[];seeds={};save_hashes={};save_refs={}
    def ensure(key):
        if key in nodes:return
        parent,_,leaf=key.rpartition('/');ensure(parent);nodes[parent]['children'].append(key)
        nodes[key]={'name':folder_label(leaf),'parent':parent,'children':[],'games':[]}
    for p in sorted(directory.rglob('*')):
        if not p.is_file() or p.suffix.lower()!='.hex':continue
        rel=p.relative_to(source).as_posix()
        try:
            safe_path(source,rel);path_bytes('/'+rel)
            if not 12<=p.stat().st_size<=262144:raise ValueError('HEX file must be 12–262144 bytes')
            raw=p.read_bytes();info=hexfile.validate(raw);digest=hashlib.sha256(raw).hexdigest()
            save=f'Saves/{NAMESPACE}/common/{digest[:20]}.sav'
            if save in save_hashes and save_hashes[save]!=digest:raise ValueError('Save hash collision')
            save_hashes[save]=digest;existing=safe_path(source,save)
            if existing.exists():
                saved=existing.read_bytes()
                if len(saved)!=1024:raise ValueError('Existing per-ROM EEPROM must be exactly 1024 bytes')
                save_refs[save]={'path':save,'bytes':1024,'sha256':hashlib.sha256(saved).hexdigest()}
            else:seeds[save]=b'\xff'*1024
        except ValueError as e:excluded.append({'path':rel,'reason':str(e)});continue
        key=p.relative_to(directory).parent.as_posix();key='' if key=='.' else key;ensure(key)
        refs.append({'path':rel,'bytes':len(raw),'sha256':digest,'save_bytes':1024,'program_bytes':info['program_bytes']})
        nodes[key]['games'].append({'title':aliases.get(rel,p.stem),'folder':False,'rom':'/'+rel,
            'bytes':len(raw),'program_bytes':info['program_bytes'],'save':'/'+save})
    for key in list(nodes):
        node=nodes[key];items=[('folder',c) for c in node['children']]+[('game',g) for g in node['games']]
        if len(items)<=127:continue
        node['children']=[];node['games']=[]
        for index in range(0,len(items),127):
            sub=key+'/@menu-page-'+str(index//127+1)
            while sub in nodes:sub+='-'
            part=items[index:index+127]
            nodes[sub]={'name':f'第 {index//127+1} 页','parent':key,'children':[v for t,v in part if t=='folder'],
                'games':[v for t,v in part if t=='game']};node['children'].append(sub)
            for t,v in part:
                if t=='folder':nodes[v]['parent']=sub
        if len(node['children'])>127:raise ValueError('More than 16,129 entries in one folder; subdivide it')
    out.mkdir(parents=True);files=[]
    def emit(rel,raw):
        dest=safe_path(out,rel);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        files.append({'path':rel,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
    def page(key):return '/'+ASSETS+('/libs/'+hashlib.sha256(key.encode()).hexdigest()[:16]+'.bin' if key else '/menu.bin')
    def folder(key,title):return {'title':title,'folder':True,'rom':page(key)}
    if len({page(k) for k in nodes})!=len(nodes):raise ValueError('Page hash collision')
    hits=0;missing=[]
    for key,node in nodes.items():
        entries=[folder(c,nodes[c]['name']) for c in node['children']]+node['games']
        entries.append(folder(node['parent'],'返回上级' if key else '返回首页' if refs else '暂无游戏'))
        raw,n,miss=pack(entries,covers,warnings);hits+=n;missing.extend(miss);emit(page(key)[1:],raw)
    for rel,raw in seeds.items():emit(rel,raw)
    result={'format':'GBAF2/arduboy','namespace':NAMESPACE,'files':files,'source_refs':refs,'save_refs':list(save_refs.values()),
        'excluded':excluded,'warnings':warnings,'pages':len(nodes),'game_refs':len(refs),
        'cover_hits':hits,'fallback_covers':len(missing),'source_writes':0,'rom_copies':0,'save_imports':0,
        'save_seeds':len(seeds),'save_seed_bytes':1024,'save_seed_fill':255,'save_existing':len(save_refs),
        'save_support':'Native 1KiB EEPROM per HEX content hash; original global save untouched. No states or sleep.',
        'hardware_acceptance':'pending'}
    (out/'library-manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('source','out'):p.add_argument('--'+key,required=True,type=Path)
    for key in ('titles','covers'):p.add_argument('--'+key,type=Path)
    p.add_argument('--rom-dir',default='Assets/arduboy/common');a=p.parse_args()
    r=build(a.source,a.out,a.titles,a.covers,a.rom_dir);print(json.dumps({k:r[k] for k in ('pages','game_refs','cover_hits','save_seeds','excluded')},ensure_ascii=False))
