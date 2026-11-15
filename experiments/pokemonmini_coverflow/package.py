#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Package a complete native Mini build only after source and four-corner checks."""
import argparse,csv,hashlib,importlib.util,json,re,shutil,struct,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('pm_package_prepare',Path(__file__).with_name('prepare.py'))
adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
ROOT=adapter.ROOT
COMMIT='81cfccb7c5620f7acb4a992df2ed355e922d0afd'
REPO='https://github.com/agg23/openfpga-pokemonmini'
sys.path.insert(0,str(ROOT/'tools'))
from apf_metadata import check_core,check_candidate_bitstream
from platform_frontend import encode
import build_library as art
from PIL import Image,ImageDraw

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write(path,data):
    Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8')

def normalized_qsf(raw):
    lines=[line for line in raw.decode().splitlines()
        if not line.startswith('set_global_assignment -name LAST_QUARTUS_VERSION ')]
    # Quartus drops the inherited AUTO assignment after our later STANDARD
    # assignment overrides it. Accept only that precise, already-overridden row.
    auto='set_global_assignment -name FITTER_EFFORT "AUTO FIT"'
    standard='set_global_assignment -name FITTER_EFFORT "STANDARD FIT"'
    if lines.count(auto)==1 and lines.count(standard)==1 and lines.index(auto)<lines.index(standard):
        lines.remove(auto)
    return '\n'.join(lines)

def normalized_build_id(raw):
    text=raw.decode()
    for address in ('0E0','0E1','0E2'):
        text,n=re.subn(r'(?m)^(\s*'+address+r' : )[0-9a-fA-F]{8}(;)$',r'\g<1>00000000\2',text)
        if n!=1:raise ValueError('Unexpected generated build-ID layout')
    return text

def stage(build,out,prepared_source,io_evidence=None,sram_review=None):
    build,out,prepared_source=(Path(p).resolve() for p in (build,out,prepared_source))
    if out.exists() or not adapter.private_output(out):raise ValueError('Fresh private Mini package required')
    prepared=json.loads((prepared_source/'preparation.json').read_text())
    if prepared['upstream']!=REPO+'/tree/'+COMMIT:raise ValueError('Unknown native source')
    if (build/'preparation.json').read_bytes()!=(prepared_source/'preparation.json').read_bytes():
        raise ValueError('Build preparation differs')
    sources={}
    for row in prepared['files']:
        rel=row['path'];expected=row['sha256'];candidate=prepared_source/rel;p=build/rel
        if not candidate.is_file() or sha(candidate)!=expected:raise ValueError('Prepared input changed: '+rel)
        if not p.is_file():raise ValueError('Compiled input missing: '+rel)
        if sha(p)!=expected:
            normalize=normalized_qsf if rel=='src/fpga/ap_core.qsf' else normalized_build_id if rel=='src/fpga/apf/build_id.mif' else None
            if normalize is None or normalize(p.read_bytes())!=normalize(candidate.read_bytes()):
                raise ValueError('Compiled input changed: '+rel)
        # Include every original and generated source, ROM initialization,
        # project/QIP/SDC file and license. No runtime assets are bundled.
        if rel.startswith('src/') or rel in ('LICENSE','README.md'):sources[rel]=sha(p)
    for rel in ['src/fpga/apf/build_id.mif','src/fpga/apf/build_id.v']:
        if (build/rel).is_file():sources[rel]=sha(build/rel)
    reports=build/'src/fpga/output_files'
    def report(kind):return (reports/('ap_core.'+kind)).read_text(encoding='latin1')
    fit,sta,flow=report('fit.summary'),report('sta.summary'),report('flow.rpt')
    slack=[float(v) for v in re.findall(r'Slack\s*:\s*(-?[\d.]+)',sta)]
    tns=[float(v) for v in re.findall(r'TNS\s*:\s*(-?[\d.]+)',sta)]
    if 'Fitter Status : Successful' not in fit or not re.search(r'Flow Status\s*[;:]\s*Successful',flow):
        raise ValueError('Complete fitting required')
    if len(slack)<80 or min(slack)<0 or len(tns)!=len(slack) or any(tns):raise ValueError('Timing failed or incomplete')
    for corner in ['Slow 1100mV 85C','Slow 1100mV 0C','Fast 1100mV 85C','Fast 1100mV 0C']:
        if corner not in sta:raise ValueError('Missing timing corner')
    for kind in ['map.rpt','fit.rpt','sta.rpt','asm.rpt']:
        if 'Critical Warning (' in report(kind):raise ValueError('Unreviewed critical warning: '+kind)
    if not re.search(r'Unconstrained Clocks\s*;\s*0\s*;\s*0\s*;',report('sta.rpt')):
        raise ValueError('Unconstrained clock')
    raw=(reports/'ap_core.rbf').read_bytes()
    if not 1024**2<len(raw)<3*1024**2 or len(raw)%4:raise ValueError('Bitstream size')
    if io_evidence is None:raise ValueError('Post-fit SRAM data-path evidence required')
    io_evidence=Path(io_evidence).resolve()
    with io_evidence.open(newline='') as f:io_rows=list(csv.DictReader(f,delimiter='\t'))
    expected_corners={'8_slow_1100mv_85c','8_slow_1100mv_0c','MIN_fast_1100mv_85c','MIN_fast_1100mv_0c'}
    if {r['corner'] for r in io_rows}!=expected_corners:raise ValueError('Incomplete SRAM timing corners')
    output_pins={f'sram_a[{i}]' for i in range(17)}|{f'sram_dq[{i}]' for i in range(16)}|{'sram_oe_n','sram_we_n','sram_ub_n','sram_lb_n'}
    input_pins={f'sram_dq[{i}]' for i in range(16)}
    io_delays={}
    for corner in sorted(expected_corners):
        paths=[r for r in io_rows if r['corner']==corner]
        outgoing=[r for r in paths if r['direction']=='out'];incoming=[r for r in paths if r['direction']=='in']
        if {r['to'] for r in outgoing}!=output_pins or {r['from'] for r in incoming}!=input_pins:
            raise ValueError('Incomplete SRAM pins')
        a=max(float(r['data_ns']) for r in outgoing);b=max(float(r['data_ns']) for r in incoming)
        if min(a,b)<=0 or a+b>8.5:raise ValueError('SRAM access budget exceeded')
        io_delays[corner]={'output_ns':a,'input_ns':b,'sum_ns':round(a+b,3),'raw_data_reserve_ns':round(7*10.416-55-a-b,3)}
    encoded=raw.translate(bytes(int(f'{v:08b}'[::-1],2) for v in range(256)))
    if sram_review is None:raise ValueError('Independent SRAM launch/capture review required')
    sram_review=Path(sram_review).resolve()
    review=json.loads(sram_review.read_text(encoding='utf8'))
    if (review['rbf_sha256']!=hashlib.sha256(encoded).hexdigest()
            or review['compiled_source_records_verified']!=len(sources)
            or review['period_ns']!=10.416 or review['sram_access_max_ns']!=55
            or {r['corner'] for r in review['corners']}!=expected_corners or len(review['corners'])!=4):
        raise ValueError('SRAM review does not match this build/protocol')
    for row in review['corners']:
        values=io_delays[row['corner']]
        if (row['output_paths']!=53 or row['input_paths']!=16
                or row['max_output_data_ns']!=values['output_ns'] or row['max_input_data_ns']!=values['input_ns']):
            raise ValueError('SRAM review paths differ from fitted I/O data')
        adverse=max(0,row['max_launch_insertion_ns']-row['min_capture_insertion_ns'])
        reserve=7*10.416-55-values['sum_ns']-adverse
        if abs(reserve-row['setup_margin_before_board_jitter_ns'])>0.001 or reserve<=0:
            raise ValueError('SRAM read has no margin after clock insertion')
        values.update(adverse_insertion_ns=round(adverse,3),reserve_before_board_jitter_ns=round(reserve,3))
    review_files={p.name:sha(p) for p in sram_review.parent.iterdir()
                  if p.is_file() and (p.suffix=='.rpt' or p.name in ('analysis.json','inputs.json','RESULT.md','RESULT.json','analyze.py','io-paths.tcl'))}
    files=out/'core';target=files/'Cores/pocketlab.PokemonMini';target.mkdir(parents=True)
    original=build/'dist/Cores/agg23.PokemonMini'
    meta=json.loads((original/'core.json').read_text())
    meta['core']['metadata'].update(author='pocketlab',shortname='PokemonMini',platform_ids=['pmclab','poke_mini'],
        description='Chinese CoverFlow for native Pokemon Mini',version='0.1.0-pm.1',date_release='2026-11-16',
        url='https://github.com/Sanssssssssssssssss/analogue-pocket-menu-cn')
    meta['core']['cores']=[{'name':'default','id':0,'filename':'poke_mini.rbf_r'}]
    meta['core']['framework']['sleep_supported']=False
    write(target/'core.json',meta)
    for name in ['audio.json','data.json','input.json','interact.json','variants.json','video.json','icon.bin']:
        shutil.copy2(original/name,target/name)
    video=json.loads((target/'video.json').read_text())['video']['scaler_modes']
    if [(v['width'],v['height']) for v in video]!=[(288,192),(320,288)]:
        raise ValueError('Unexpected native/menu scaler dimensions')
    (target/'poke_mini.rbf_r').write_bytes(encoded)
    (target/'info.txt').write_text('Native Pokemon Mini + Chinese CoverFlow.\nL+R+Select: pause, resume or save and return.\nNative 8192-byte EEPROM. FreeBIOS built in; no states or sleep.\nGPL2 engine; MIT menu. Hardware acceptance pending.\n',encoding='ascii')
    check_core(target);digest=check_candidate_bitstream(target/'poke_mini.rbf_r')
    platform=files/'Platforms';(platform/'_images').mkdir(parents=True)
    write(platform/'pmclab.json',{'platform':{'category':'CN Menu','name':'Pokemon Mini Menu CN','manufacturer':'Pocket Lab','year':2026}})
    image=Image.new('L',(521,165),0);draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((26,12,139,153),radius=19,outline=220,width=3)
    draw.rectangle((42,30,123,89),outline=160,width=3)
    draw.line((43,120,76,120),fill=200,width=5);draw.line((59,104,59,136),fill=200,width=5)
    draw.ellipse((103,112,117,126),fill=210)
    for title,y,scale in [('Pokemon Mini',40,2),('中文游戏菜单',104,2)]:
        width,raw_text,clipped,missing=art.columns(title,art.font())
        if missing or clipped:raise ValueError('Missing banner glyph')
        glyph=Image.new('L',(width,16),0);g=ImageDraw.Draw(glyph)
        for x,column in enumerate(struct.unpack('<512H',raw_text)[:width]):
            for row in range(16):
                if column>>row&1:g.point((x,row),fill=235)
        image.paste(glyph.resize((width*scale,16*scale),Image.Resampling.NEAREST),(164,y))
    (platform/'_images/pmclab.bin').write_bytes(encode(image));image.save(out/'platform.png')
    license_dir=target/'licenses';license_dir.mkdir()
    shutil.copy2(build/'LICENSE',license_dir/'PokemonMini-GPL-2.0.txt')
    for name in ['MIT.txt','UPSTREAM-NOTICE.txt','Unifont-LICENSE.txt','Unifont-OFL-1.1.txt','APF-Notice.txt']:
        shutil.copy2(ROOT/'LICENSES'/name,license_dir/name)
    (license_dir/'SOURCES.txt').write_text(f'Native engine: {REPO}\nCommit: {COMMIT}\nMenu and timing additions: experiments/pokemonmini_coverflow.\nCorresponding build inputs are included in the package sources/ directory.\nUpstream GPL, APF and Intel notices remain in their files.\n',encoding='utf8')
    for rel in sources:
        destination=out/'sources'/rel;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(build/rel,destination)
    receipt={'platform':'poke_mini','core':'pocketlab.PokemonMini','namespace':'pmclab','menu_format':'GBAF2/poke_mini',
        'version':'0.1.0-pm.1','source_repo':REPO,'source_commit':COMMIT,'source_inputs':sources,
        'fit':fit,'timing_records':len(slack),'minimum_slack_ns':min(slack),'bitstream_sha256':digest,
        'timing_scope':'Four-corner STA; original native PLLs and CPU enables; eight-stage exact divider; exact 256-color LCD lookup; no new timing exceptions.',
        'sram_timing':{'paths':len(io_rows),'source_sha256':sha(io_evidence),'corners':io_delays,
            'review_sha256':sha(sram_review),'review_files':review_files,
            'rule':'Seven 10.416ns settling cycles: subtract 55ns SRAM access, same-corner maximum output and input data delays, and adverse launch/capture insertion. The inherited 4.25ns-per-side allocation is checked as the same 8.5ns round-trip data budget. Slow85 raw data reserve is 10.169ns; after 2.420ns adverse insertion, 7.749ns remains before unmeasured board flight/loading and unconfigured clock jitter/uncertainty. This is not physical-device sign-off.'},
        'hardware_acceptance':'pending','save_support':'Native per-ROM raw 8192-byte EEPROM; erased FF seeds only for missing dedicated saves; no states or sleep',
        'original_game_scaler_preserved':True,'BIOS_builtin':'pinned upstream freebios.hex','category':'CN Menu',
        'files':[{'path':p.relative_to(files).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(files.rglob('*')) if p.is_file()]}
    write(out/'build-receipt.json',receipt)
    evidence=out/'evidence';evidence.mkdir();shutil.copy2(io_evidence,evidence/'sram-io.tsv')
    (evidence/'sram-review').mkdir()
    for name in review_files:shutil.copy2(sram_review.parent/name,evidence/'sram-review'/name)
    for kind in ['fit.summary','sta.summary','flow.rpt']:shutil.copy2(reports/('ap_core.'+kind),evidence/('ap_core.'+kind))
    return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['build','out','prepared-source','io-evidence','sram-review']:p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();r=stage(a.build,a.out,a.prepared_source,a.io_evidence,a.sram_review)
    print(json.dumps({key:r[key] for key in ['version','timing_records','minimum_slack_ns','bitstream_sha256']}))
