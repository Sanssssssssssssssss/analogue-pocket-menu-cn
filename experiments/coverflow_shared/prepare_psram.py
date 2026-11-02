#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare a separate CoverFlow backend using a pinned upstream CellRAM driver."""
import argparse,hashlib,json,shutil
from pathlib import Path
from prepare_view import prepare,ROOT,HERE

# The driver is supplied by the same pinned native GBA source used by the
# existing integration. Its full Adam Gastineau MIT notice is retained.
PSRAM_SHA='b9aed3cb12ee298a96e78ad7c26d4657eaa3d970465ffcdc4441dce7022e5c58'


def build(out,source,fast_response=False,clock_speed=74.25):
    source=Path(source).resolve()
    raw=(source/'src/fpga/pocket/psram.sv').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PSRAM_SHA:raise ValueError('Pinned CellRAM driver SHA differs')
    out=prepare(out,compact=True)
    s=(out/'coverflow_view.sv').read_text()
    s=s.replace('module coverflow_view #','module coverflow_psram_view #',1)
    s=s.replace('coverflow_line_fetch #','coverflow_line_fetch16 #',1)
    (out/'coverflow_psram_view.sv').write_text(s,encoding='utf8',newline='\n')
    fetch=(HERE/'line_fetch.sv').read_text()
    fetch=fetch.replace('module coverflow_line_fetch #','module coverflow_line_fetch16 #',1)
    needle='cached<=enable && !drop_pending && !invalidate && !new_line && !line_arrived && !fault;'
    if fetch.count(needle)!=1:raise ValueError('DWORD cache anchor changed')
    fetch=fetch.replace(needle,'cached<=0; // One 16-bit physical read per texture sample.')
    (out/'coverflow_line_fetch16.sv').write_text(fetch,encoding='utf8',newline='\n')
    driver=raw.decode().replace('module psram #','module coverflow_psram #',1)
    driver=driver.replace('rtoi','cf_psram_rtoi').replace('CEIL','CF_PSRAM_CEIL').replace('MAX','CF_PSRAM_MAX')
    (out/'coverflow_psram.sv').write_text(driver,encoding='utf8',newline='\n')
    cache=(HERE/'psram_cache.sv').read_text()
    if fast_response:
        # The GBA raster has shorter lines than GG. Remove two registered
        # handoff bubbles while retaining the pinned driver's pin timings.
        def change(old,new):
            nonlocal cache
            if cache.count(old)!=1:raise ValueError('CellRAM response anchor changed: '+old[:80])
            cache=cache.replace(old,new)
        change('output reg done=0,','output wire done,')
        change('output reg [31:0] data=0,','output wire [31:0] data,')
        change('reg busy_seen=0;', '''reg busy_seen=0,failed_response=0;
    assign done=(state==READ_WAIT && ps_available) || failed_response;
    assign data=failed_response ? 32'd0:{ps_output,ps_output};''')
        change('ps_write<=0;ps_read<=0;done<=0;','ps_write<=0;ps_read<=0;failed_response<=0;')
        change('end else if(read_pending && !ps_busy)begin','end else if((read_pending || request) && !ps_busy)begin')
        change('if(fault)begin done<=1;data<=0;read_pending<=0;end',
            'if(fault)begin failed_response<=1;read_pending<=0;end')
        change('else begin ps_address<=read_address;ps_read<=1;state<=READ_WAIT;end',
            'else begin ps_address<=read_pending ? read_address:word_address[21:0];ps_read<=1;state<=READ_WAIT;end')
        change('data<={ps_output,ps_output};done<=1;read_pending<=0;state<=FREE;',
            'read_pending<=0;state<=FREE;')
    if clock_speed!=74.25:
        anchor='.CLOCK_SPEED(74.25)'
        if cache.count(anchor)!=1:raise ValueError('CellRAM clock anchor changed')
        cache=cache.replace(anchor,f'.CLOCK_SPEED({clock_speed})')
    if fast_response or clock_speed!=74.25:
        (out/'coverflow_psram_cache.sv').write_text(cache,encoding='utf8',newline='\n')
    else:shutil.copy2(HERE/'psram_cache.sv',out/'coverflow_psram_cache.sv')
    proof=json.loads((out/'view-source.json').read_text())
    proof.update({'backend':'Dedicated unused CellRAM die, 128 x 64 KiB cover-only slots',
        'driver_sha256':PSRAM_SHA,'driver_scope':f'Pinned upstream timing state machine, identifiers namespaced, CLOCK_SPEED={clock_speed}',
        'transport':'16-bit sample replicated to response DWORD; old DWORD reuse explicitly disabled',
        'fast_response':fast_response,
        'hardware_acceptance':'pending; a peripheral model is not board-level timing signoff'})
    (out/'view-source.json').write_text(json.dumps(proof,indent=2)+'\n')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True);p.add_argument('--gba-source',required=True)
    a=p.parse_args();print(build(a.out,a.gba_source))
