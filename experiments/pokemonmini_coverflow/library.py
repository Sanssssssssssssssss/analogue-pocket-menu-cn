#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build Mini Chinese CoverFlow pages and missing 8 KiB EEPROM seeds."""
import argparse,hashlib,importlib.util,json
from pathlib import Path,PurePosixPath
_spec=importlib.util.spec_from_file_location('pm_prepare_for_library',Path(__file__).with_name('prepare.py'))
_prepare=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_prepare)
console=_prepare.load('pm_console_library',_prepare.ROOT/'experiments/console_coverflow/library.py')

def path_bytes(value,platform='poke_mini',namespace='pmclab'):
    if (platform,namespace)!=('poke_mini','pmclab'):raise ValueError('Unknown Mini profile')
    if not value.startswith('/') or len(value.encode('utf8'))>=256:raise ValueError('Invalid APF path length')
    if '..' in PurePosixPath(value).parts or any(c in value for c in ('\\',':','\0')):raise ValueError('Unsafe APF path')
    if not any(value.startswith('/'+p+'/') for p in ('Assets/pmclab/common','Saves/pmclab/common','Assets/poke_mini/common')):
        raise ValueError('Foreign APF namespace')
    return value.encode('utf8').ljust(256,b'\0')

def cartridge(path,length):
    # Native CPU maps a 21-bit cartridge address. Accept flat .min homebrew and
    # commercial images; do not impose a signature that excludes homebrew.
    if length<8704 or length>2097152 or length%4:raise ValueError('Mini ROM must be a four-byte-aligned 8704..2097152-byte flat image')
    return {'rom_config':0,'rom_offset':0,'save_bytes':8192}

def build(source,out,titles=None,covers=None):
    source,out=Path(source).resolve(),Path(out).resolve()
    console.PROFILES['poke_mini']=('pmclab',8192,2097152,0x20000000,'native-pinned-tree')
    console.LABELS['poke_mini']='宝可梦迷你'
    console.EXTENSIONS['poke_mini']={'.min'}
    console.cart_config=lambda platform,path,length:cartridge(path,length)
    console.shared.old.path_bytes=path_bytes
    result=console.build('poke_mini',source,out,titles,covers)
    # EEPROM erased state. Existing hashed saves are validated and never staged.
    for entry in result['files']:
        if entry['path'].startswith('Saves/'):
            path=out/entry['path'];path.write_bytes(b'\xff'*8192)
            entry['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    result.update(native_save_format='agg23 raw 8192-byte EEPROM',required_bios={},bios_builtin='freebios.hex')
    (out/'library-manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','out'):p.add_argument('--'+n,type=Path,required=True)
    for n in ('titles','covers'):p.add_argument('--'+n,type=Path)
    a=p.parse_args();r=build(a.source,a.out,a.titles,a.covers)
    print(json.dumps({k:r[k] for k in ('pages','game_refs','cover_hits','fallback_covers')}))
