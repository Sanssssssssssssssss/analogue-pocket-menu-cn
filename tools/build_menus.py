#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build native CoverFlow libraries from your ROM filenames, without writing the card."""
import argparse
import json
from pathlib import Path

import build_library
import delivery
from sega_formats import legacy_gamegear
import additional_menus

SYSTEMS={'GB-GBC':(('gb','gbc'),{'.gb','.gbc'}), 'GBA':(('gba',),{'.gba'}),
         'NES':(('nes',),{'.nes'}), 'GG':(('gg',),{'.gg','.sms'}),
         'SMS':(('sms',),{'.sms'}), 'SG1000':(('sg1000',),{'.sg','.sg1','.bin'}),
         'PCE':(('pce',),{'.pce','.sgx'}), 'MD':(('genesis',),{'.md','.gen','.bin'}),
         'SFC':(('snes',),{'.sfc','.smc','.bin'}), 'CPS2':(('jtcps2',),{'.json'})}
SYSTEMS.update({name: ((row['platform'],),row['extensions']) for name,row in additional_menus.PROFILES.items()})


def discover(card):
    found={}
    for system,(platforms,suffixes) in SYSTEMS.items():
        if system in additional_menus.INSTANCE_SYSTEMS:
            if not any(delivery.safe_path(card, f'Assets/{platform}/common').is_dir() for platform in platforms):
                continue
            paths = list(additional_menus.available_instances(card, system))
            if paths:
                found[system] = paths
            continue
        if system == 'CPS2':
            with delivery.imports():
                cps = delivery.module('experiments/console_coverflow/cps2.py')
            paths = list(cps.available_instances(card))
            if paths:
                found[system] = paths
            continue
        paths=[]
        for platform in platforms:
            base=delivery.safe_path(card,f'Assets/{platform}/common')
            for path in sorted(base.rglob('*')):
                if path.is_file() and path.suffix.lower() in suffixes:
                    if system in additional_menus.PROFILES and path.name.lower() in additional_menus.FIRMWARE:
                        continue
                    rel=path.relative_to(card).as_posix();delivery.safe_path(card,rel)
                    if system=='GG' and path.suffix.lower()=='.sms' and not legacy_gamegear(path.read_bytes()):continue
                    paths.append(rel)
        if paths:found[system]=paths
    return found


def build(card,out,systems=None,titles=None,covers=None,bios=None,skip_invalid=False,cheats=None,*,packages=None,groups=None):
    card,out=Path(card).resolve(),Path(out).resolve()
    delivery.separate(card,out)
    if not card.is_dir() or out.exists():raise ValueError('Existing input and fresh local output required')
    covers=Path(covers).resolve() if covers else None
    cheats=Path(cheats).resolve() if cheats else None
    packages=Path(packages).resolve() if packages else None
    if packages:
        delivery.separate(card,packages)
        delivery.separate(out,packages)
        if not packages.is_dir():raise ValueError('Core package directory missing')
    if cheats:
        delivery.separate(cheats,out)
        if not cheats.is_file():raise ValueError('Cheat identity index missing')
    if covers:
        delivery.separate(covers,out)
        if not covers.is_dir():raise ValueError('Cover directory missing')
    aliases=delivery.read(titles) if titles else {}
    cheat_format = delivery.read(cheats).get('format') if cheats else None
    if cheat_format not in (None, 'SEGA-CHEATS1', 'POCKET-CHEATS1'):
        raise ValueError('Unknown version-bound cheat index format')
    if not isinstance(aliases,dict) or any(not isinstance(v,str) or not v.strip() for v in aliases.values()):raise ValueError('Nonempty title aliases required')
    found=discover(card);selected=list(found) if systems is None else list(dict.fromkeys(systems))
    if not selected or any(s not in SYSTEMS for s in selected):raise ValueError('Select supported systems containing ROMs')
    if any(s not in found for s in selected):raise ValueError('Selected system has no ROM files')
    known={p for s in selected for p in found[s]}
    if set(aliases)-known:raise ValueError('Alias references a missing or unselected ROM')
    display_groups = delivery.read(groups) if groups else {}
    groupable = {p for s in selected if s in delivery.CONSOLE_SAVES for p in found[s]}
    if not isinstance(display_groups, dict) or set(display_groups)-groupable:
        raise ValueError('Display groups require selected PCE, MD, SFC or CPS2 cartridge paths')
    offline=not (card/'Analogue_Pocket.json').is_file()
    if not offline:delivery.identity(card)
    if bios is None:
        bios=next((p for p in (card/'Assets/gbclab/common/gbc_bios.bin',card/'Assets/gbc/common/gbc_bios.bin') if p.is_file()),None)
    out.mkdir(parents=True);result={}
    with delivery.imports():
        for system in selected:
            per_titles={p:aliases[p] for p in found[system] if p in aliases}
            alias_file=None
            if per_titles:
                alias_file=out/'aliases'/f'{system}.json';delivery.write(alias_file,per_titles)
            dest=out/'libraries'/system
            if system=='GB-GBC':
                manifest=build_library.build(card,dest,alias_file,covers,bios,skip_invalid=skip_invalid)
            elif system=='GBA':
                f1=delivery.module('experiments/gba_menu/library.py')
                f2=delivery.module('experiments/gba_coverflow/library.py')
                f1.build(card,out/'intermediate/GBAF1',alias_file,covers,skip_invalid=skip_invalid,page_limit=128)
                manifest=f2.upgrade(out/'intermediate/GBAF1',dest,alias_file,covers=[covers] if covers else None)
            elif system in delivery.CONSOLE_SAVES:
                lib=delivery.module('experiments/console_coverflow/library.py')
                manifest=lib.build(SYSTEMS[system][0][0],card,dest,alias_file,covers,
                                   groups={p:display_groups[p] for p in found[system] if p in display_groups})
            elif system in additional_menus.PROFILES:
                manifest=additional_menus.library(card,dest,system,alias_file,covers)
            else:
                family='nes_coverflow' if system=='NES' else 'sega_coverflow'
                lib=delivery.module(f'experiments/{family}/library.py')
                args={} if system=='NES' else {'platform':SYSTEMS[system][0][0],'cheats':cheats if cheat_format=='SEGA-CHEATS1' else None}
                manifest=lib.build(card,dest,titles=alias_file,covers=covers,offline_source=offline,**args)
            if system in ('GB-GBC','NES','PCE','MD','SFC') and packages:
                receipt_path = packages/system/'build-receipt.json'
                receipt = delivery.read(receipt_path) if receipt_path.is_file() else {}
                if 'PLCH1' in receipt.get('features', []):
                    import core_candidates
                    import native_cheats
                    core_candidates.validate(packages/system, system)
                    platform = 'gb-family' if system == 'GB-GBC' else SYSTEMS[system][0][0]
                    manifest = native_cheats.bind_library(card, dest, platform, cheats if cheat_format=='POCKET-CHEATS1' else None)
            result[system]={'format':manifest['format'],'library':str(dest.relative_to(out)),
                'source_files_discovered':len(found[system]),'manifest':'library-manifest.json',
                'warnings':len(manifest.get('warnings',[])),
                'cheat_matched_versions':len(manifest.get('cheats',[])),
                'excluded':len(manifest.get('excluded',manifest.get('skipped',[])))}
    delivery.write(out/'delivery.json',{'components':[{'id':system,'package':str(packages/system) if packages else 'packages/'+system,
        'library':row['library']} for system,row in result.items()]})
    receipt={'systems':result,'delivery_config':'delivery.json','source_writes':0,'ROM_copies':0,'existing_save_writes':0,'firmware_writes':0,
        'caption_policy':'ROM filename without extension by default; optional per-path aliases override it',
        'scope':'Read-only local library generation; install/refresh requires compatible native core and verified backup',
        'hardware_acceptance':'New native candidates pending; stable public binary remains GB/GBC'}
    delivery.write(out/'menus.json',receipt)
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--card',required=True);parser.add_argument('--out',required=True)
    parser.add_argument('--systems',nargs='+',choices=SYSTEMS)
    for key in ('titles','covers','bios','cheats','packages','groups'):parser.add_argument('--'+key)
    parser.add_argument('--skip-invalid',action='store_true',help='GB/GBC unsupported sizes and GBA invalid headers: record exclusions, never modify ROM bytes')
    args=parser.parse_args()
    try:
        result=build(args.card,args.out,args.systems,args.titles,args.covers,args.bios,args.skip_invalid,args.cheats,packages=args.packages,groups=args.groups)
        print(json.dumps(result,ensure_ascii=True,indent=2))
    except (OSError,ValueError,KeyError,TypeError) as error:parser.exit(2,str(error)+'\n')


if __name__=='__main__':main()
