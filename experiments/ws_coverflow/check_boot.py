#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare a real WS APF/controller/FIFO/CoverFlow/SRAM boot simulation."""
import argparse
import json
import importlib.util
import shutil
from pathlib import Path
_spec=importlib.util.spec_from_file_location('ws_prepare_for_boot',Path(__file__).with_name('prepare.py'))
_prepare=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_prepare)
ROOT,HERE,load=_prepare.ROOT,_prepare.HERE,_prepare.load
library=load('ws_library_boot',HERE/'library.py')


def wsl(path):
    path=Path(path).resolve()
    return '/mnt/'+path.drive[0].lower()+path.as_posix()[2:] if path.drive else path.as_posix()


def prepare(candidate,out,intel_model):
    candidate,out=Path(candidate).resolve(),Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'.work/repair-20261115/ws'):
        raise ValueError('Fresh local WS test output required')
    out.mkdir(parents=True)
    source=out/'fixture-input'
    folder=source/'Assets/wonderswan/common/角色扮演'
    folder.mkdir(parents=True)
    for name,size in (('bw.rom',4096),('color.rom',8192)):
        (folder.parent/name).write_bytes(bytes(size))
    for index,ram in enumerate(library.PAYLOAD):
        raw=bytearray(131072)
        raw[-10]=index+1;raw[-9]=1;raw[-5]=ram
        (folder/f'测试游戏{index+1}.wsc').write_bytes(raw)
    result=library.build(source,out/'fixture-library')
    rootpage=out/'fixture-library/Assets/wsclab/common/menu.bin'
    child=next((rootpage.parent/'libs').glob('*.bin'))
    for path,name in [(rootpage,'page.hex'),(child,'child.hex')]:
        (out/name).write_text(''.join(f'{x:02x}\n' for x in path.read_bytes()),encoding='ascii')
    core=candidate/'src/fpga/core'
    top=(core/'core_top.v').read_text(encoding='utf8')
    a,b=top.index('  // The original native'),top.index('  // bridge data slot access')
    insertion=top[a:b]
    preamble='''`timescale 1ns/1ps
module tb_ws_boot;
reg clk_74a=0,clk_mem_110_592=0,clk_vid_3_75=0,clk_sys_36_864=0;
always #6.734006734 clk_74a=~clk_74a;
always #4.521122685 clk_mem_110_592=~clk_mem_110_592;
always #81.380208333 clk_vid_3_75=~clk_vid_3_75;
always #13.563368056 clk_sys_36_864=~clk_sys_36_864;
reg booted=0,bridge_wr=0,bridge_rd=0;
reg [31:0] bridge_addr=0,bridge_wr_data=0,cont1_key=0;
wire bridge_endian_little=0,pll_core_locked=1;
wire [15:0] cont1_key_s=cont1_key[15:0];
wire reset_n;
wire [23:0] video_rgb,video_rgb_reg=0;
wire video_de,video_hs,video_vs,video_skip,video_de_reg=0,video_hs_reg=0,video_vs_reg=0;
wire [11:0] save_size=4;
'''
    extra='''
assign ui_rom_idle=1;assign ui_save_idle=1;assign ui_paused_s=0;
wire bios_wr;wire [12:0] bios_addr;wire [15:0] bios_data;
ws_data_loader #(.ADDRESS_MASK_UPPER_4(4'h3),.ADDRESS_SIZE(13),.OUTPUT_WORD_SIZE(2),
 .WRITE_MEM_CLOCK_DELAY(4),.WRITE_MEM_EN_CYCLE_LENGTH(1)) bios_loader(
 .clk_74a(clk_74a),.clk_memory(clk_sys_36_864),.bridge_wr(bridge_wr),
 .bridge_endian_little(bridge_endian_little),.bridge_addr(bridge_addr),.bridge_wr_data(bridge_wr_data),
 .write_complete(1'b0),.idle(ui_bios_idle),.write_en(bios_wr),.write_addr(bios_addr),.write_data(bios_data));
integer bw_writes=0,color_writes=0;
always @(posedge clk_sys_36_864)if(bios_wr)begin
 if(ui_bios==1)bw_writes=bw_writes+1;
 else if(ui_bios==2)color_writes=color_writes+1;
 else $fatal(1,"BIOS write without selected destination");
end
core_bridge_cmd commands(.clk(clk_74a),.reset_n(reset_n),
 .bridge_endian_little(bridge_endian_little),.bridge_addr(bridge_addr),.bridge_rd(bridge_rd),
 .bridge_wr(bridge_wr),.bridge_wr_data(bridge_wr_data),
 .status_boot_done(booted),.status_setup_done(booted),.status_running(reset_n),
 .dataslot_requestread_ack(1'b1),.dataslot_requestread_ok(1'b1),
 .dataslot_requestwrite_ack(1'b1),.dataslot_requestwrite_ok(1'b1),
 .savestate_supported(1'b0),.savestate_addr(32'd0),.savestate_size(32'd0),.savestate_maxloadsize(32'd0),
 .savestate_start_ack(1'b0),.savestate_start_busy(1'b0),.savestate_start_ok(1'b0),.savestate_start_err(1'b1),
 .savestate_load_ack(1'b0),.savestate_load_busy(1'b0),.savestate_load_ok(1'b0),.savestate_load_err(1'b1),
 .target_dataslot_read(1'b0),.target_dataslot_write(1'b0),.target_dataslot_id(16'd0),
 .target_dataslot_slotoffset(32'd0),.target_dataslot_bridgeaddr(32'd0),.target_dataslot_length(32'd0),
 .target_cmd_req(tcmd_req),.target_cmd(tcmd),.target_cmd_p0(tcmd_p0),.target_cmd_p1(tcmd_p1),
 .target_cmd_p2(tcmd_p2),.target_cmd_p3(tcmd_p3),.target_cmd_ack(tcmd_ack),
 .target_cmd_done(tcmd_done),.target_cmd_result(tcmd_result),
 .datatable_addr(10'd0),.datatable_wren(1'b0),.datatable_data(32'd0));
wire [16:0] sram_a;wire [15:0] sram_dq;
wire sram_oe_n,sram_we_n,sram_ub_n,sram_lb_n;
integer physical_reads,physical_writes;
sim_coverflow_sram physical_memory(.clock(clk_sys),.a(sram_a),.dq(sram_dq),.oe_n(sram_oe_n),.we_n(sram_we_n),
 .ub_n(sram_ub_n),.lb_n(sram_lb_n),.reads(physical_reads),.writes(physical_writes));
'''
    tail=(HERE/'tb_boot_driver.sv.in').read_text(encoding='utf8')
    tail=tail.replace('@CHILD_PATH@','/Assets/wsclab/common/libs/'+child.name)
    (out/'tb.sv').write_text(preamble+insertion+extra+tail,encoding='utf8',newline='\n')
    for name in ('font_cn.hex','native_pause.hex'):shutil.copy2(candidate/'src/fpga'/name,out/name)
    files=[core/name for name in ('ws_menu.sv','ws_target.sv','core_bridge_cmd.v','ws_data_loader.sv','data_loader.sv',
        'coverflow_assoc_view.sv','coverflow_assoc_cache.sv','coverflow_geometry.sv','coverflow_line_fetch.sv',
        'coverflow_sram_cache.sv','native_pause_pixels.sv')]
    files += [candidate/'src/fpga/apf/common.v',HERE/'sim_table.sv',
        ROOT/'experiments/gba_coverflow/sim_sram.sv',ROOT/'experiments/coverflow_shared/sim_ram.sv',
        Path(intel_model).resolve(),out/'tb.sv']
    run='#!/bin/bash\nset -eu\nulimit -c 0\ncd "$(dirname "$0")"\n'
    run+='verilator --binary --timing --top-module tb_ws_boot --build-jobs 2 -Wno-fatal --Mdir obj -o probe '
    run+=' '.join('"'+wsl(p)+'"' for p in files)+' > build.log 2>&1\n'
    run+='./obj/probe +hierarchy +full_animation > simulation.log 2>&1\ncat simulation.log\n'
    (out/'run.sh').write_text(run,encoding='utf8',newline='\n')
    (out/'scope.json').write_text(json.dumps({'clock_hz':{'bridge':74250000,'memory':110592000,'video':6144000,'native':36864000},
        'native_CPU_in_boot_sim':False,'BIOS_native_loader':True,'vendor_FIFO':True,
        'real_APF':True,'full_CoverFlow_SRAM':True,'synthetic_game_refs':result['game_refs']},indent=2)+'\n')
    return out/'run.sh'


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--intel-model',type=Path,required=True)
    args=parser.parse_args()
    print(prepare(args.candidate,args.out,args.intel_model))
