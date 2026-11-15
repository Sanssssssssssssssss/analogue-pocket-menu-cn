#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build Chinese WS/WSC pages without copying ROMs or changing input saves."""
import argparse
import hashlib
import importlib.util
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
_spec=importlib.util.spec_from_file_location('ws_prepare_for_library',Path(__file__).with_name('prepare.py'))
_prepare=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_prepare)
ROOT,load=_prepare.ROOT,_prepare.load

console=load('ws_console_library',ROOT/'experiments/console_coverflow/library.py')
PAYLOAD={0:0,1:8192,2:32768,3:131072,4:262144,5:524288,0x10:2048,0x20:2048,0x50:2048}


def path_bytes(value,platform='wonderswan',namespace='wsclab'):
    if (platform,namespace)!=('wonderswan','wsclab'):
        raise ValueError('Unknown WS profile')
    if not value.startswith('/') or len(value.encode('utf8'))>=256:
        raise ValueError('Invalid APF path length')
    if '..' in PurePosixPath(value).parts or any(c in value for c in ('\\',':','\0')):
        raise ValueError('Unsafe APF path')
    if not any(value.startswith('/'+p+'/') for p in ('Assets/wsclab/common','Saves/wsclab/common','Assets/wonderswan/common')):
        raise ValueError('Foreign APF namespace')
    return value.encode('utf8').ljust(256,b'\0')


def cartridge(path,length):
    # Native maskAddr uses an AND mask, so a non-power-of-two image requires
    # a separately validated mapping/padding policy and is excluded here.
    if length<131072 or length>16777216 or length & (length-1):
        raise ValueError('Native WS candidate requires a power-of-two ROM from 128 KiB through 16 MiB')
    with path.open('rb') as stream:
        stream.seek(-10,2)
        header=stream.read(10)
    if header[1] not in (0,1) or header[5] not in PAYLOAD:
        raise ValueError('Unsupported WonderSwan color/save header')
    return {'rom_config':int(path.suffix.lower()=='.wsc'), 'rom_offset':0,
            'save_bytes':PAYLOAD[header[5]]+12,'ramtype':header[5]}


def rtc_seed(now):
    def bcd(n):return (n//10)*16+n%10
    # Preserve agg23's packed 42-bit BCD date + 32-bit Unix timestamp + 6 pad bits.
    date=(bcd(now.year%100)<<34)|(bcd(now.month)<<29)|(bcd(now.day)<<23)|(
        ((now.weekday()+1)%7)<<20)|(bcd(now.hour)<<14)|(bcd(now.minute)<<7)|bcd(now.second)
    return b'TR'+((int(now.timestamp())<<42)|date).to_bytes(10,'little')


def build(source,out,titles=None,covers=None):
    source,out=Path(source).resolve(),Path(out).resolve()
    bios=[]
    for name,size in (('bw.rom',4096),('color.rom',8192)):
        candidates=[console.shared.safe_path(source,f'Assets/{platform}/common/{name}')
            for platform in ('wsclab','wonderswan')]
        src=next((p for p in candidates if p.is_file()),None)
        if src is None or src.stat().st_size!=size:
            raise ValueError(f'WS requires an existing {name} of exactly {size} bytes')
        bios.append({'path':src.relative_to(source).as_posix(),'bytes':size,
            'sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'destination':f'Assets/wsclab/common/{name}'})
    console.PROFILES['wonderswan']=('wsclab',12,16777216,0x20000000,'native-pinned-tree')
    console.LABELS['wonderswan']='万代掌机'
    console.EXTENSIONS['wonderswan']={'.ws','.wsc'}
    console.cart_config=lambda platform,path,length:cartridge(path,length)
    console.shared.old.path_bytes=path_bytes
    result=console.build('wonderswan',source,out,titles,covers)
    seeded_at=datetime.now(timezone.utc).replace(microsecond=0)
    # Shared generation stages new seeds only. Existing saves are never staged
    # or overwritten; wrong lengths are rejected before the output is created.
    for entry in result['files']:
        if entry['path'].startswith('Saves/'):
            path=out/entry['path']
            path.write_bytes(bytes(entry['bytes']-12)+rtc_seed(seeded_at))
            entry['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    for ref in result['source_refs']:
        existing=console.shared.safe_path(source,'Saves/wsclab/common/'+ref['sha256'][:20]+'.sav')
        if existing.is_file():
            with existing.open('rb') as stream:
                stream.seek(-12,2)
                if stream.read(2)!=b'TR':raise ValueError('Existing WS save has an invalid native RTC trailer: '+str(existing))
    for entry in bios:
        src=source/entry['path'];target=out/entry['destination']
        shutil.copy2(src,target)
        if hashlib.sha256(target.read_bytes()).hexdigest()!=entry['sha256']:
            raise ValueError('BIOS changed while staging')
        result['files'].append({'path':entry['destination'],'bytes':entry['bytes'],'sha256':entry['sha256']})
    result.update(native_save_format='agg23 payload + 12 byte RTC trailer',
        supported_payload_bytes=sorted(set(PAYLOAD.values())),
        required_bios={'bw.rom':4096,'color.rom':8192},bios_refs=bios,seeded_at_utc=seeded_at.isoformat())
    (out/'library-manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','out'):parser.add_argument('--'+name,type=Path,required=True)
    for name in ('titles','covers'):parser.add_argument('--'+name,type=Path)
    args=parser.parse_args()
    result=build(args.source,args.out,args.titles,args.covers)
    print(json.dumps({key:result[key] for key in ('pages','game_refs','cover_hits','fallback_covers')}))
