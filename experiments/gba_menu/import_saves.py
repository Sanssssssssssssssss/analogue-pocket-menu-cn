#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Copy matching ordinary saves into a new local GBA staging directory."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from install import safe_path


def digest(raw):return hashlib.sha256(raw).hexdigest()


def prepare(card,library,out,preferred=()):
    card,out=Path(card).resolve(),Path(out).resolve()
    if out.exists() or out.is_relative_to(card) or card.is_relative_to(out):raise ValueError('Use fresh local save staging')
    manifest=json.loads(Path(library).read_text(encoding='utf-8'))
    candidates={};skipped=[]
    preferred=set(preferred)
    for rel in preferred:
        if not rel.startswith('Saves/gba/common/') or not safe_path(card,rel).is_file():
            raise ValueError('Preferred save must be an existing original GBA save')
    for row in manifest['roms']:
        rel=Path(row['path']).relative_to('Assets/gba/common')
        expected=row['save_bytes']
        if expected not in (65536,131072):raise ValueError('Invalid target save capacity')
        for ext in ('.sav','.srm'):
            original=safe_path(card,'Saves/gba/common/'+rel.with_suffix(ext).as_posix())
            if not original.is_file():continue
            before=original.stat();raw=original.read_bytes()
            if original.stat().st_mtime_ns!=before.st_mtime_ns:raise ValueError('Source progress changed')
            rtc=None
            if len(raw) in (65552,131088):raw,rtc=raw[:-16],raw[-16:]
            if len(raw) not in (512,8192,32768,65536,131072) or len(raw)>expected:
                skipped.append({'path':original.relative_to(card).as_posix(),'reason':'unrecognized size or would truncate'});continue
            body=raw.ljust(expected,b'\xff')
            candidates.setdefault(row['save'],[]).append((original,body,rtc,row['rtc']))
    out.mkdir(parents=True)
    files=[];imports=[]
    for target,options in sorted(candidates.items()):
        chosen=[v for v in options if v[0].relative_to(card).as_posix() in preferred]
        alternatives=[v[0].relative_to(card).as_posix() for v in options]
        if chosen:options=chosen
        # Equal ROMs share a hash identity; disagreeing originals require review.
        if len({digest(v[1]) for v in options})!=1 or len({digest(v[2]) for v in options if v[2]})>1:
            skipped.append({'path':target,'reason':'different existing saves for the same ROM identity'});continue
        original,body,rtc,rtc_target=options[0]
        for rel,data in ((target,body),(rtc_target,rtc)):
            if data is None:continue
            if not rel.startswith('Saves/gbalab/common/'):raise ValueError('Save target outside lab')
            p=safe_path(out,rel);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
            files.append({'path':rel,'sha256':digest(data),'bytes':len(data)})
        imports.append({'source':original.relative_to(card).as_posix(),'source_sha256':digest(original.read_bytes()),
                        'target':target,'bytes':len(body),'rtc_footer_copied':rtc is not None,
                        'explicit_preference':bool(chosen),'alternatives_preserved':alternatives})
    result={'source_writes':0,'original_save_writes':0,'files':files,'imports':imports,'skipped':skipped,
            'scope':'Copies ordinary saves only; emulator formats and gameplay require physical acceptance'}
    (out/'save-manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('card','library','out'):p.add_argument('--'+arg,required=True)
    p.add_argument('--prefer',action='append',default=[],help='Explicit original card-relative save to prefer if equal-ROM progress conflicts')
    a=p.parse_args()
    try:
        r=prepare(a.card,a.library,a.out,a.prefer);print(json.dumps({'ordinary_saves':len(r['imports']),'files':len(r['files']),'skipped':len(r['skipped']),'source_writes':0}))
    except (OSError,ValueError) as e:p.exit(2,str(e)+'\n')
