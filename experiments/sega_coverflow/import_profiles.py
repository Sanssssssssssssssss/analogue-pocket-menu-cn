#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Convert a previously verified practical-code bundle into identity candidates."""
import argparse,hashlib,json,re
from pathlib import Path,PurePosixPath
COMMIT='da577d2865c2b1b834b2d5f2fd1368fc5110a01c'
LABELS={'lives':'无限生命','health':'生命辅助','money':'金钱辅助','ammo':'弹药辅助'}


def decode(code):
    codes=[]
    for token in re.split(r'\s*\+\s*',code.strip().upper()):
        if re.fullmatch(r'[0-9A-F]{4}-[0-9A-F]{4}',token):
            raw=token.replace('-','')
            if raw[:2]!='00' or not 0xc000<=int(raw[2:6],16)<=0xdfff:raise ValueError('Unsupported PAR work-RAM operation')
            codes.append({'type':'par','address':int(raw[2:6],16),'value':int(raw[6:],16)})
        elif re.fullmatch(r'[0-9A-F]{3}-[0-9A-F]{3}(?:-[0-9A-F]{3})?',token):
            raw=token.replace('-','');address=((int(raw[5],16)^15)<<12)|int(raw[2:5],16)
            if address>=0xc000:raise ValueError('Game Genie outside cartridge space')
            codes.append({'type':'game_genie','code':token})
        else:raise ValueError('Unsupported native token')
    if not codes or len(codes)>16:raise ValueError('Code capacity')
    return codes


def convert(bundle,out,platform):
    bundle,out=Path(bundle).resolve(),Path(out).resolve()
    if out.exists() or out.is_relative_to(bundle):raise ValueError('Fresh output outside original bundle required')
    manifests=json.loads((bundle/'bundle-manifest.json').read_text(encoding='utf8'));manifest={row['path']:row for row in manifests}
    def read(rel):
        if '..' in PurePosixPath(rel).parts or '\\' in rel or rel.startswith('/') or ':' in rel:raise ValueError('Unsafe bundled path')
        raw=(bundle/rel).read_bytes();row=manifest[rel]
        if len(raw)!=row['size'] or hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('Verified bundle entry changed: '+rel)
        return raw
    rows=json.loads(read('library-index.json'))['platforms'][platform];profiles=[];skipped=[]
    for digest,row in rows.items():
        if not row.get('profile'):continue
        if not re.fullmatch('[0-9a-f]{40}',digest) or not re.fullmatch('[0-9a-f]{8}',row['crc32']):raise ValueError('Invalid exact DAT identity')
        raw=read(row['profile']).decode('ascii');effects=[];sources=[]
        try:
            for index,selected in enumerate(row['cheats']):
                expected=f'cheat{index}_code = "'+selected['code']+'"'
                if expected not in raw or f'cheat{index}_enable = true' not in raw:raise ValueError('Selected code differs from verified profile')
                category=selected['category'];effects.append({'title':LABELS[category],'codes':decode(selected['code'])})
                rel=selected['source'].replace('\\','/');prefix='originals/cheat-db/'
                if not rel.startswith(prefix) or '..' in PurePosixPath(rel).parts:raise ValueError('Foreign code source')
                sources.append(rel[len(prefix):])
            if not 1<=len(effects)<=2:raise ValueError('Practical category limit')
        except ValueError as error:
            skipped.append({'sha1':digest,'reason':str(error)});continue
        profiles.append({'sha1':digest,'crc32':row['crc32'],'bytes':row['size'],'effects':effects,
            'source':{'url':'https://github.com/libretro/libretro-database/tree/'+COMMIT+'/cht',
                'commit':COMMIT,'license':'CC-BY-SA-4.0','files':sources}})
    result={'format':'SEGA-CHEATS1','platform':platform,'scope':'Known-ROM identity candidates; actual ROM bytes are still required before automatic application',
        'bundle_index_sha256':hashlib.sha256(read('library-index.json')).hexdigest(),'profiles':profiles,'skipped':skipped}
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8');return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('bundle','out'):p.add_argument('--'+name,required=True)
    p.add_argument('--platform',choices=['gg','sms'],required=True);a=p.parse_args();r=convert(a.bundle,a.out,a.platform)
    print(json.dumps({'platform':a.platform,'candidate_profiles':len(r['profiles']),'skipped':len(r['skipped']),'actual_ROM_matches':'not measured'}))
