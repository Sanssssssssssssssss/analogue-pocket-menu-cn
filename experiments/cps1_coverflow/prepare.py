#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare native CPS1/CPS1.5 against the reviewed CPS2 bridge and renderer."""
import argparse,hashlib,importlib.util,json,re,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
BASE_RECEIPT='c7303fb5f99123902f35ec98620026fa00caa11d26fdc70afdc05256e342c16e'
PROFILES={'jtcps1':('cps1','cp1lab','CPS1'),'jtcps15':('cps15','c15lab','CPS15')}
COMMIT='559df4a276ca312939a95f9bf0056348d5dac6f2'

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
graph=load('cps_family_source_graph',HERE/'source_graph.py');sha=graph.sha
nv_bridge=load('cps_family_nv_bridge',HERE/'nv_bridge.py')
parameter_bridge=load('cps_family_parameter_bridge',HERE/'parameter_bridge.py')
config_bridge=load('cps_family_config_bridge',HERE/'config_bridge.py')

def replace(s,a,b,count=1):
    if s.count(a)!=count:raise ValueError('Native source anchor changed: '+a[:100])
    return s.replace(a,b)

def patch_game(s,platform):
    s=replace(s,f'module {platform}_game(\n',f'module {platform}_game(\n    input wire lab_block_keys,\n    output reg lab_paused=0,\n')
    s=replace(s,'wire        sclk, sdi, sdo, scs;', '''wire        sclk, sdi, sdo, scs;
wire halt_idle,nv_quiet;
reg [2:0] halt_sync=0;
always @(posedge clk)begin
    halt_sync<={halt_sync[1:0],halt_idle};
    lab_paused<=!rst_game && halt_sync[2] && nv_quiet;
end''')
    s=replace(s,'jtcps1_main u_main(\n','jtcps1_main u_main(\n    .halt_idle(halt_idle),\n')
    for name in ('joystick1','joystick2','joystick3','joystick4','coin','cab_1p'):
        pattern=rf'(\.{name}\s*\(\s*)({name}(?:\[1:0\])?)(\s*\),)'
        def binding(m):
            released="10'h3ff" if name.startswith('joystick') else "2'b11" if '[1:0]' in m[2] else "4'hf"
            return m[1]+'lab_block_keys ? '+released+' : '+m[2]+m[3]
        s,n=re.subn(pattern,binding,s)
        if n<1:raise ValueError('Native input binding missing: '+name)
    s,n=re.subn(r'(\.dump_flag\s*\([^\n]+\))\s*\n',r'\1,\n    .nv_quiet(nv_quiet)\n',s)
    if n!=1:raise ValueError('Native EEPROM interface changed')
    return s

def prepare(platform,stock,base_package,out):
    core,namespace,_=PROFILES[platform]
    stock,base_package,out=map(lambda p:Path(p).resolve(),(stock,base_package,out))
    if out.exists() or not out.is_relative_to(ROOT/'.work') or out.is_relative_to(stock):raise ValueError('Choose fresh local .work output')
    receipt=base_package/'build-receipt.json'
    if sha(receipt)!=BASE_RECEIPT:raise ValueError('Expected reviewed CPS2 0.4.0-cps2.2 source receipt')
    base=json.loads(receipt.read_text(encoding='utf8'))
    for rel,digest in base['source_inputs'].items():
        if sha(base_package/'sources'/rel)!=digest:raise ValueError('CPS2 source checksum differs: '+rel)
    upstream=graph.copy(stock,core,out)
    copied={}
    for rel,digest in base['source_inputs'].items():
        # Reuse exact tested frame/CPU/EEPROM transport. Each native game's
        # generated source graph and project macros remain platform-specific.
        if rel.startswith('modules/') or rel=='cores/cps1/hdl/jtcps1_sdram.v':
            dest=out/rel
        elif rel.startswith('cores/cps2/pocket/coverflow/'):
            dest=out/'cores'/core/'pocket/coverflow'/Path(rel).name
        elif rel.startswith('cores/cps2/pocket/') and Path(rel).suffix=='.hex':
            dest=out/'cores'/core/'pocket'/Path(rel).name
        else:continue
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(base_package/'sources'/rel,dest);copied[rel]=digest
    project=out/'cores'/core/'pocket'
    view=project/'coverflow'
    controller=view/'cps2_menu.sv'
    text=controller.read_text(encoding='utf8')
    # Namespace bytes are encoded as byte literals in the strict path gate.
    root_path=('/Assets/'+namespace+'/common/menu.bin').encode().ljust(32,b'\0')
    function='    function automatic [31:0] root_word(input [5:0] n);\n        case(n)\n'
    for i in range(8):function+=f"            {i}:root_word=32'h{root_path[i*4:i*4+4].hex()};\n"
    function+='            default:root_word=0;\n        endcase\n    endfunction'
    text,n=re.subn(r'    function automatic \[31:0\] root_word.*?    endfunction',lambda m:function,text,count=1,flags=re.S)
    if n!=1:raise ValueError('Root path table changed')
    for index,(old,new) in enumerate(zip(b'cpslab',namespace.encode())):
        text=replace(text,f"{index+7}:save_prefix=8'h{old:02x};",f"{index+7}:save_prefix=8'h{new:02x};")
    controller.write_text(text,encoding='utf8',newline='\n')
    # Controller namespace replacement is verified by the generated library
    # parse and real APF loading regression before any package is accepted.
    game=out/'cores'/core/'hdl'/f'jt{core}_game.v'
    game.write_text(patch_game(game.read_text(encoding='utf8'),'jt'+core),encoding='utf8',newline='\n')
    main=out/'cores/cps1/hdl/jtcps1_main.v';s=main.read_text(encoding='utf8')
    s=replace(s,'    output             cpu_cen,','    output             cpu_cen, halt_idle,')
    s=replace(s,'fx68k u_cpu(\n','fx68k u_cpu(\n    .oHALT_IDLE(halt_idle),\n')
    s=replace(s,"assign cpu_cen = 1'b0;","assign cpu_cen = 1'b0;\nassign halt_idle=1'b0;")
    main.write_text(s,encoding='utf8',newline='\n')
    nv_bridge.patch(out,core)
    parameter_bridge.patch(out,core)
    config_bridge.patch(out,core)
    qsf=project/f'jt{core}.qsf';s=qsf.read_text(encoding='utf8')
    s+='\n'
    for p in sorted(view.iterdir()):
        if p.suffix not in {'.v','.sv'}:continue
        kind='SYSTEMVERILOG_FILE' if p.suffix=='.sv' else 'VERILOG_FILE'
        s+=f'set_global_assignment -name {kind} coverflow/{p.name}\n'
    qsf.write_text(s,encoding='utf8',newline='\n')
    # JTFRAME's generator writes absolute source paths. Rebase only this
    # generated project to its retained repository layout before freezing.
    for config in (qsf,project/'files.qip'):
        text=config.read_text(encoding='utf8').replace(stock.as_posix()+'/', '../../../')
        if '/var/tmp/' in text:raise ValueError('Generated project retains a host-specific path')
        config.write_text(text,encoding='utf8',newline='\n')
    result={'platform':platform,'namespace':namespace,'source_repo':'https://github.com/jotego/jtcores','source_commit':COMMIT,
        'base_receipt_sha256':BASE_RECEIPT,'upstream_sources':upstream,'reviewed_base_sources':copied,
        'inputs':{p.relative_to(out).as_posix():sha(p) for p in sorted(out.rglob('*')) if p.is_file()}}
    (out/'cps-preparation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    return out

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--platform',choices=PROFILES,required=True)
    for key in ('stock','base-package','out'):p.add_argument('--'+key,required=True,type=Path)
    a=p.parse_args();print(prepare(a.platform,a.stock,a.base_package,a.out))
