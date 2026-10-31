#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare two isolated, no-game FPGA probes from a pinned official template."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import zipfile

SHA='db13b8bb131481ebd6609189da1b18921f342481c7f81fd2dd7302781816cdf7'
COMMIT='da3a021b1eaf742604d86d8dc9b33a6666263e6a'
HERE=Path(__file__).resolve().parent

def replace(text,old,new):
    if text.count(old)!=1: raise ValueError('Template anchor changed: '+old[:70])
    return text.replace(old,new)

def prepare(archive,out):
    out=Path(out).resolve();raw=Path(archive).read_bytes()
    if out.exists() or not out.is_relative_to(HERE.parents[1]/'.work'):
        raise ValueError('Use a fresh output directory in this checkout/.work')
    if hashlib.sha256(raw).hexdigest()!=SHA: raise ValueError('Template archive hash mismatch')
    out.mkdir(parents=True);template=out/'template';template.mkdir()
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            parts=PurePosixPath(member.filename).parts
            if '..' in parts or '\\' in member.filename or ':' in member.filename or member.filename.startswith('/'):
                raise ValueError('Unsafe archive path')
            if not member.is_dir():
                target=template.joinpath(*parts[1:]);target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(z.read(member))
    for name,fingerprint,color in [('A','504C4100',('40','100','160')),('B','504C4201',('160','80','40'))]:
        build=out/name;shutil.copytree(template,build)
        top=build/'src/fpga/core/core_top.v';text=top.read_text(encoding='utf8')
        anchor="    32'h10xxxxxx: begin"
        text=replace(text,anchor,"    32'h600000xx: begin bridge_rd_data <= probe_data; end\n"+anchor)
        insert=f'''
wire [31:0] probe_data;
route_probe #(.ID(32'h{fingerprint})) routing_probe (
    .clk(clk_74a),.power_reset(!pll_core_locked_s),.run_reset_n(reset_n),
    .buttons(cont1_key[15:0]),.address(bridge_addr[7:0]),
    .write(bridge_wr && bridge_addr[31:8]==24'h600000),
    .write_data(bridge_wr_data),.read_data(probe_data));
'''
        text=replace(text,'endmodule',insert+'\nendmodule')
        # The probe raster intentionally runs before APF releases the game reset.
        text=replace(text,'posedge clk_core_12288 or negedge reset_n','posedge clk_core_12288 or negedge pll_core_locked')
        text=replace(text,'if(~reset_n) begin','if(~pll_core_locked) begin')
        for field,value in zip(['[23:16]','[15:8] ','[7:0]  '],color):
            text=replace(text,f"vidout_rgb{field} <= 8'd60;",f"vidout_rgb{field} <= 8'd{value};")
        # Never issue Target file operations; all storage interfaces stay disabled.
        for field in ['read','write','getfile','openfile']:
            text=replace(text,f'reg             target_dataslot_{field};',f'wire            target_dataslot_{field} = 0;')
        top.write_text(text,encoding='utf8',newline='\n')
        shutil.copy2(HERE/'route_probe.sv',build/'src/fpga/core/route_probe.sv')
        qsf=build/'src/fpga/ap_core.qsf'
        with qsf.open('a',encoding='utf8') as f:
            f.write('\nset_global_assignment -name SYSTEMVERILOG_FILE core/route_probe.sv\nset_global_assignment -name NUM_PARALLEL_PROCESSORS 4\n')
    for name,command in [('pre-init',0),('reset-exit',0x4001),('full-init',0x4002)]:
        folder=out/'loaders'/name;folder.mkdir(parents=True)
        text=replace((HERE/'loader.asm').read_text(encoding='utf8'),'constant early_host = 0',f'constant early_host = {command}')
        (folder/'loader.asm').write_text(text,encoding='utf8',newline='\n')
    (out/'preparation.json').write_text(json.dumps({'upstream_commit':COMMIT,'archive_sha256':SHA,
        'scope':'Offline preparation only. No board compilation, installation or hardware acceptance implied.',
        'device_access':False,'target_file_operations_enabled':False,'fingerprints':{'A':'504C4100','B':'504C4201'}},indent=2)+'\n')
    return out

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ['archive','out']:p.add_argument('--'+flag,required=True)
    a=p.parse_args();print(prepare(a.archive,a.out))
