#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Index existing Supervision paths as Chinese title/cover pages; never copy ROMs."""
import argparse,hashlib,importlib.util,json,struct,sys
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
import build_library as art
from install import safe_path
from menu_icons import LABELS,kind,folder_label
NAMESPACE='svclab'
ASSETS=f'Assets/{NAMESPACE}/common'

def path_bytes(value):
    if not value.startswith('/Assets/') or any(x in value for x in ('\\',':','\0')) or '..' in PurePosixPath(value).parts:
        raise ValueError('Unsafe APF asset path')
    raw=value.encode('utf8')
    if len(raw)>=256:raise ValueError('APF UTF-8 path is 256 bytes or longer')
    return raw.ljust(256,b'\0')

def pack(entries,covers=None,warnings=None):
    if not 1<=len(entries)<=128 or not entries[-1]['folder']:raise ValueError('Page must end with parent')
    base=64+len(entries)*1024;end=base+len(entries)*65536
    header=struct.pack('<4s5I',b'GBAF',2,len(entries),base,end,65536).ljust(64,b'\0')
    rows=[];blobs=[];hits=0;missing=[]
    glyphs=art.font()
    for e in entries:
        width,title,clipped,unknown=art.columns(e['title'],glyphs)
        subwidth,subtitle,_,_=art.columns('Supervision 掌机',glyphs)
        if warnings is not None and (clipped or unknown):warnings.append({'path':e['rom'],'truncated':clipped,'missing_glyphs':unknown})
        row=bytearray(1024)
        struct.pack_into('<4s7I',row,0,b'ENT1',int(e['folder']),e.get('bytes',0),0,width,subwidth,0,0)
        row[32:288]=path_bytes(e['rom'])
        rows.append(row)
        cover=None
        if covers is not None and not e['folder']:
            possible=(covers/e['rom'].lstrip('/')).with_suffix('.png')
            if not possible.resolve().is_relative_to(covers):raise ValueError('Cover path escapes source')
            if possible.is_file():cover=possible;hits+=1
        if not e['folder'] and cover is None:missing.append(e['rom'])
        picture=art.picture(cover,e['folder'],kind(e['title'])) if cover or e['folder'] else art.title_card(e['title'],'Supervision',strict=False)
        blobs.append((picture+title+subtitle).ljust(65536,b'\0'))
    return header+b''.join(rows+blobs),hits,missing

def build(source,out,titles=None,covers=None,rom_dir='Assets/supervision/common'):
    source,out=Path(source).resolve(),Path(out).resolve()
    if out.exists() or out.is_relative_to(source) or source.is_relative_to(out):raise ValueError('Fresh separate staging required')
    aliases=json.loads(Path(titles).read_text(encoding='utf-8-sig')) if titles else {}
    if not isinstance(aliases,dict) or any(not isinstance(v,str) or not v.strip() for v in aliases.values()):raise ValueError('Invalid aliases')
    covers=Path(covers).resolve() if covers else None
    if covers is not None and not covers.is_dir():raise ValueError('Cover root is missing')
    directory=safe_path(source,rom_dir)
    if not directory.is_dir():raise ValueError('ROM directory is missing')
    nodes={'':{'name':'Supervision 游戏库','parent':'','children':[],'games':[]}}
    refs=[];excluded=[];warnings=[]
    def ensure(key):
        if key in nodes:return
        parent,_,leaf=key.rpartition('/');ensure(parent)
        nodes[parent]['children'].append(key)
        nodes[key]={'name':folder_label(leaf),'parent':parent,'children':[],'games':[]}
    for p in sorted(directory.rglob('*')):
        if not p.is_file() or p.suffix.lower() not in ('.sv','.bin'):continue
        rel=p.relative_to(source).as_posix()
        try:
            safe_path(source,rel);path_bytes('/'+rel)
            size=p.stat().st_size
            if size<16384 or size>524288 or size&(size-1):raise ValueError('Native engine requires 16–512 KiB power-of-two image')
            digest=hashlib.sha256(p.read_bytes()).hexdigest()
        except ValueError as e:excluded.append({'path':rel,'reason':str(e)});continue
        key=p.relative_to(directory).parent.as_posix();key='' if key=='.' else key;ensure(key)
        refs.append({'path':rel,'bytes':size,'sha256':digest})
        nodes[key]['games'].append({'title':aliases.get(rel,p.stem),'folder':False,'rom':'/'+rel,'bytes':size})
    # Paginate every node, including directory-only nodes, without altering the
    # user's directory tree. Synthetic page identities cannot collide with keys.
    pending=list(nodes)
    for key in pending:
        node=nodes[key];items=[('folder',c) for c in node['children']]+[('game',g) for g in node['games']]
        if len(items)<=127:continue
        node['children']=[];node['games']=[]
        for index in range(0,len(items),127):
            sub=key+'/@menu-page-'+str(index//127+1)
            while sub in nodes:sub+='-'
            part=items[index:index+127]
            nodes[sub]={'name':f'第 {index//127+1} 页','parent':key,
                'children':[v for t,v in part if t=='folder'],'games':[v for t,v in part if t=='game']}
            node['children'].append(sub)
            for t,v in part:
                if t=='folder':nodes[v]['parent']=sub
        if len(node['children'])>127:raise ValueError('More than 16,129 entries in one folder; subdivide it')
    out.mkdir(parents=True);files=[]
    def page(key):return '/'+ASSETS+('/libs/'+hashlib.sha256(key.encode()).hexdigest()[:16]+'.bin' if key else '/menu.bin')
    def folder(key,title):return {'title':title,'folder':True,'rom':page(key)}
    if len({page(k) for k in nodes})!=len(nodes):raise ValueError('Page hash collision')
    hits=0;missing=[]
    for key,node in nodes.items():
        entries=[folder(c,nodes[c]['name']) for c in node['children']]+node['games']
        entries.append(folder(node['parent'],'返回上级' if key else '返回首页' if refs else '暂无游戏'))
        raw,n,miss=pack(entries,covers,warnings);hits+=n;missing.extend(miss)
        rel=page(key)[1:];dest=safe_path(out,rel);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        files.append({'path':rel,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
    result={'format':'GBAF2/supervision','namespace':NAMESPACE,'files':files,'source_refs':refs,
        'excluded':excluded,'warnings':warnings,'pages':len(nodes),'game_refs':len(refs),
        'cover_hits':hits,'fallback_covers':len(missing),'source_writes':0,'rom_copies':0,
        'save_imports':0,'save_support':'Upstream has no persistent save/savestate interface',
        'hardware_acceptance':'pending'}
    (out/'library-manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('source','out'):p.add_argument('--'+key,required=True,type=Path)
    for key in ('titles','covers'):p.add_argument('--'+key,type=Path)
    p.add_argument('--rom-dir',default='Assets/supervision/common');a=p.parse_args()
    r=build(a.source,a.out,a.titles,a.covers,a.rom_dir);print(json.dumps({k:r[k] for k in ('pages','game_refs','cover_hits','fallback_covers','excluded')},ensure_ascii=False))
