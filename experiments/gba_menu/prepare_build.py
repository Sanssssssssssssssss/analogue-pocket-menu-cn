#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare an isolated GBA core tree. BIOS bytes are always supplied at runtime."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

ROOT=Path(__file__).resolve().parents[2]


def replace(text,old,new,count=1):
    if text.count(old)!=count:
        raise ValueError('Upstream integration anchor changed: '+old[:80])
    return text.replace(old,new)


def integrate(out):
    # Upstream paths assume the GUI's working directory. This build runs in
    # src/fpga/build: point the datatable at the generated MIF and let the QSF
    # load core_constraints.sdc once, after the APF clock definitions.
    table=out/'src/fpga/apf/mf_datatable.v'
    s=table.read_text(encoding='utf-8')
    s=replace(s,'altsyncram_component.init_file = "./apf/build_id.mif",',
              'altsyncram_component.init_file = "../apf/build_id.mif",')
    table.write_text(s,encoding='utf-8',newline='\n')
    constraints=out/'src/fpga/apf/apf_constraints.sdc'
    s=replace(constraints.read_text(encoding='utf-8'),'read_sdc "core/core_constraints.sdc"',
              '# core_constraints.sdc is loaded by ap_core.qsf after this file.')
    constraints.write_text(s,encoding='utf-8',newline='\n')
    core=out/'src/fpga/core/core_top.sv'
    text=core.read_text(encoding='utf-8')
    insertion='''
// Pocket Lab native menu: bridge-clock lifecycle, existing game framebuffer.
wire ui_owned,ui_show,ui_reset,ui_pause,ui_new_load,ui_finish,ui_bound,ui_fault;
wire [7:0] ui_fault_code,ui_state;
wire [10:0] ui_selected;
wire ui_frame_request,ui_frame_ack,ui_frame_started,ui_frame_valid,ui_frame_fault,game_frame_ready;
wire ui_visible,ui_visible_bridge;
wire ui_owned_s,ui_reset_s,ui_pause_s,ui_new_load_s;
wire ui_prepare_ready,ui_load_ready,ui_io_idle;
wire ui_prepare_ready_b,ui_load_ready_b,ui_io_idle_b;
wire ui_frame_ack_b,ui_frame_started_b,ui_frame_valid_b,ui_frame_fault_b;
wire [31:0] ui_param_data;
wire ui_flush;
wire osnotify_s;
reg new_load_toggle=0;
always @(posedge clk_74a) if(ui_new_load)new_load_toggle<=~new_load_toggle;
wire new_load_toggle_s;
synch_3 new_load_toggle_sync(new_load_toggle,new_load_toggle_s,clk_sys);
reg new_load_seen=0;
assign ui_new_load_s=new_load_toggle_s!=new_load_seen;
always @(posedge clk_sys)new_load_seen<=new_load_toggle_s;
synch_3 ui_owned_sync(ui_owned,ui_owned_s,clk_sys);
synch_3 ui_reset_sync(ui_reset,ui_reset_s,clk_sys);
synch_3 ui_pause_sync(ui_pause,ui_pause_s,clk_sys);
synch_3 osnotify_sync(osnotify_inmenu,osnotify_s,clk_sys);
synch_3 ui_visible_sync(ui_visible,ui_visible_bridge,clk_74a);
synch_3 ui_ack_sync(ui_frame_ack,ui_frame_ack_b,clk_74a);
synch_3 ui_started_sync(ui_frame_started,ui_frame_started_b,clk_74a);
synch_3 ui_valid_sync(ui_frame_valid,ui_frame_valid_b,clk_74a);
synch_3 ui_fault_sync(ui_frame_fault,ui_frame_fault_b,clk_74a);
synch_3 ui_prepare_sync(ui_prepare_ready,ui_prepare_ready_b,clk_74a);
synch_3 ui_load_sync(ui_load_ready,ui_load_ready_b,clk_74a);
synch_3 ui_idle_sync(ui_io_idle,ui_io_idle_b,clk_74a);
wire [31:0] ui_capacity;
gba_menu menu (
    .clk(clk_74a),.ready(reset_n && pll_core_locked_s),.buttons(cont1_key),
    .bridge_wr(bridge_wr),.bridge_rd(bridge_rd),.bridge_endian_little(bridge_endian_little),
    .bridge_addr(bridge_addr),.bridge_wr_data(bridge_wr_data),.param_rd_data(ui_param_data),
    .t_read(target_dataslot_read),.t_write(target_dataslot_write),.t_open(target_dataslot_openfile),.t_flush(ui_flush),
    .t_slot(target_dataslot_id),.t_offset(target_dataslot_slotoffset),.t_address(target_dataslot_bridgeaddr),.t_length(target_dataslot_length),
    .t_done(target_dataslot_done),.t_error(target_dataslot_err),
    .frame_ack(ui_frame_ack_b),.frame_started(ui_frame_started_b),.frame_valid(ui_frame_valid_b),.frame_fault(ui_frame_fault_b),.visible(ui_visible_bridge),
    .prepare_ready(ui_prepare_ready_b),.load_ready(ui_load_ready_b),.io_idle(ui_io_idle_b),.save_capacity(ui_capacity),
    .frame_request(ui_frame_request),.menu_owned(ui_owned),.menu_show(ui_show),.menu_reset(ui_reset),.menu_pause(ui_pause),
    .new_load(ui_new_load),.finish_load(ui_finish),.game_bound(ui_bound),.fault(ui_fault),.fault_code(ui_fault_code),
    .state(ui_state),.selected(ui_selected));
assign ui_prepare_ready=save_clear_done && !psram_busy;
assign ui_load_ready=loader_drained && rtc_load_complete && save_clear_done;
assign ui_io_idle=bus_state==BUS_IDLE && save_write_state==SAVE_WR_IDLE &&
                  !psram_busy && !ingress_write_busy && !sdram_wr_pending && !ss_loading && !ss_busy;
'''
    text=replace(text,'// ---- Shared APF Write Ingress and Save Unloader ----',insertion+'\n// ---- Shared APF Write Ingress and Save Unloader ----')
    text=replace(text,'.completion_request   ( dataslot_allcomplete ),',
                 '.completion_request   ( ui_finish ),\n    .transaction_start    ( ui_new_load ),')
    # Reset per-game loader state, retaining the BIOS, PLL and running host clock.
    for anchor in ('save_write_state <= SAVE_WR_IDLE;', 'loader_drained <= 1\'b0;',
                   'save_data_received <= 0;', 'clr_state <= CLR_IDLE;',
                   'last_rom_byte_addr <= 0;', 'rtc_save_loaded <= 0;'):
        at=text.index(anchor)
        before=text.rfind('if (~pll_core_locked)',0,at)
        if before<0 or at-before>100:raise ValueError('Unexpected per-game reset anchor')
        text=text[:before]+text[before:].replace('if (~pll_core_locked)','if (~pll_core_locked || ui_new_load_s)',1)
    text=replace(text,'if (loader_drained && !save_data_received && !save_clear_done)',
                 'if (!save_clear_done && (loader_drained || ui_reset_s))')
    text=replace(text,'.reset           ( ~pll_core_locked ),','.reset           ( ~pll_core_locked | ui_new_load_s ),')
    text=replace(text,'.reset_n                ( pll_core_locked ),',
                 '.reset_n                ( pll_core_locked && !ui_new_load_s ),',count=2)
    text=replace(text,'wire reset_gba = ~pll_core_locked | ~dataslot_allcomplete_s | ~reset_n_s | core_reset_s | ~save_mem_ready;',
                 'wire reset_gba = ~pll_core_locked | ~dataslot_allcomplete_s | ~reset_n_s | core_reset_s | ~save_mem_ready | ui_reset_s;')
    text=replace(text,'wire            savestate_supported = 1;','wire            savestate_supported = 0; // per-game APF memory identity is not adapted yet')
    # This experiment exposes ordinary saves only. Remove the inactive APF
    # savestate staging controller too, leaving room for the native menu.
    text,n=re.subn(r'save_state_controller ss_ctrl \(.*?\n\);', '''// Pocket Lab 2026-10-31: APF memories/sleep are disabled for this core.
assign ss_save=0;assign ss_load=0;assign ss_dout=0;assign ss_ack=0;
assign ss_sdram_wr_req=0;assign ss_sdram_wr_addr=0;assign ss_sdram_wr_data=0;
assign ss_sdram_rd_req=0;assign ss_sdram_rd_addr=0;
assign ss_serving_active=0;assign ss_loading=0;assign ss_bridge_rd_data=0;
assign savestate_start_ack=1;assign savestate_start_busy=0;
assign savestate_start_ok=0;assign savestate_start_err=1;
assign savestate_load_ack=1;assign savestate_load_busy=0;
assign savestate_load_ok=0;assign savestate_load_err=1;
''',text,count=1,flags=re.S)
    if n!=1:raise ValueError('Unexpected savestate controller wiring')
    for name in ('target_dataslot_read','target_dataslot_write','target_dataslot_getfile','target_dataslot_openfile'):
        text=replace(text,'reg             '+name+';', 'wire            '+name+';')
    for name in ('target_dataslot_id','target_dataslot_slotoffset','target_dataslot_bridgeaddr','target_dataslot_length'):
        pattern=r'(?m)^reg(\s+\[[^\]]+\]\s+)'+name+r';'
        text,n=re.subn(pattern,r'wire\1'+name+';',text)
        if n!=1:raise ValueError('Expected one target parameter declaration')
    text=replace(text,'wire    [31:0]  target_buffer_param_struct;',
                 "wire    [31:0]  target_buffer_param_struct=32'hF3000000;")
    text=replace(text,'wire    [31:0]  target_buffer_resp_struct;',
                 "wire    [31:0]  target_buffer_resp_struct=0;\nassign target_dataslot_getfile=0;")
    text=replace(text,'.target_dataslot_read       ( target_dataslot_read ),',
                 '.target_dataslot_flush      ( ui_flush ),\n    .target_dataslot_read       ( target_dataslot_read ),')
    text=replace(text,"    32'hF8xxxxxx: begin", "    32'hF3xxxxxx: bridge_rd_data <= ui_param_data;\n    32'hF4xxxxxx: bridge_rd_data <= {3'd0,ui_bound,ui_owned,ui_reset,ui_pause,ui_fault,ui_selected,5'd0,ui_state};\n    32'hF8xxxxxx: begin")
    text=replace(text,"wire [31:0] rtc_size_bytes = rtc_active ? 32'd16 : 32'd0;", "wire [31:0] rtc_size_bytes = ui_bound ? 32'd16 : 32'd0;\nassign ui_capacity=save_size_bytes;")
    text=replace(text,"datatable_addr_r <= datatable_rtc_phase ? 10'd7 : 10'd5;", "datatable_addr_r <= datatable_rtc_phase ? 10'd9 : 10'd7;")
    text=replace(text,'datatable_data_r <= datatable_rtc_phase ? rtc_size_bytes : save_size_bytes;',
                 'datatable_data_r <= ui_bound ? (datatable_rtc_phase ? rtc_size_bytes : save_size_bytes) : 0;')
    pixel_adapter='''wire [15:0] ui_pixel_addr;
wire [17:0] ui_pixel_data;
wire ui_pixel_we;
gba_menu_pixels ui_pixels (
    .clk_bridge(clk_74a),.clk_memory(clk_sys),.bridge_wr(bridge_wr),.bridge_endian_little(bridge_endian_little),
    .bridge_addr(bridge_addr),.bridge_wr_data(bridge_wr_data),.menu_owned(ui_owned_s),.frame_request(ui_frame_request),
    .game_pixel_addr(pixel_out_addr),.game_pixel_we(pixel_out_we),.pixel_addr(ui_pixel_addr),.pixel_data(ui_pixel_data),
    .pixel_we(ui_pixel_we),.frame_ack(ui_frame_ack),.frame_started(ui_frame_started),.frame_valid(ui_frame_valid),.frame_fault(ui_frame_fault),.game_frame_ready(game_frame_ready));
'''
    text=replace(text,'video_adapter video_out (',pixel_adapter+'\nvideo_adapter video_out (')
    text=replace(text,'.pixel_addr ( pixel_out_addr ),','.pixel_addr ( ui_owned_s ? ui_pixel_addr : pixel_out_addr ),')
    text=replace(text,'.pixel_data ( pixel_out_data ),','.pixel_data ( ui_owned_s ? ui_pixel_data : pixel_out_data ),')
    text=replace(text,'.pixel_we   ( pixel_out_we ),', '.pixel_we   ( ui_owned_s ? ui_pixel_we : pixel_out_we ),\n    .menu_show  ( ui_fault || (ui_owned ? ui_show : game_frame_ready) ),\n    .menu_fault ( ui_fault ),\n    .menu_visible ( ui_visible ),')
    text=replace(text,'fast_forward ? 16\'h0 : sound_out_left',"(fast_forward || ui_owned_s || osnotify_s) ? 16'h0 : sound_out_left")
    text=replace(text,'fast_forward ? 16\'h0 : sound_out_right',"(fast_forward || ui_owned_s || osnotify_s) ? 16'h0 : sound_out_right")
    text=replace(text,'.sleep_external      ( ss_loading ),','.sleep_external      ( ss_loading | ui_pause_s | osnotify_s ),')
    core.write_text(text,encoding='utf-8',newline='\n')

    ingress=out/'src/fpga/pocket/apf_write_ingress.sv'
    text=ingress.read_text(encoding='utf-8')
    text=replace(text,'input  wire        completion_request,','input  wire        completion_request,\n    input wire transaction_start,')
    text=replace(text,'if (completion_rise)\n      fence_pending', 'if (transaction_start) begin\n      fence_enqueued<=0;fence_pending<=0;\n    end\n    if (completion_rise)\n      fence_pending')
    ingress.write_text(text,encoding='utf-8',newline='\n')

    cmd=out/'src/fpga/core/core_bridge_cmd.v'
    text=cmd.read_text(encoding='utf-8')
    anchor='input   wire            target_dataslot_read,'
    text=replace(text,anchor,'input wire target_dataslot_flush,\n'+anchor)
    text=replace(text,'reg             target_dataslot_read_1, target_dataslot_read_queue;',
                 'reg target_dataslot_flush_1=0,target_dataslot_flush_queue=0;\n    reg             target_dataslot_read_1, target_dataslot_read_queue;')
    anchor='target_dataslot_read_1 <= target_dataslot_read;'
    text=replace(text,anchor,'target_dataslot_flush_1<=target_dataslot_flush;\n    if(target_dataslot_flush && !target_dataslot_flush_1)target_dataslot_flush_queue<=1;\n    '+anchor)
    anchor='end else if(target_dataslot_getfile_queue) begin'
    text=replace(text,anchor,"end else if(target_dataslot_flush_queue) begin\n            target_dataslot_flush_queue<=0;target_0[15:0]<=16'h0188;target_20<=target_dataslot_id;\n            tstate<=TARG_ST_DATASLOTOP;\n        "+anchor)
    cmd.write_text(text,encoding='utf-8',newline='\n')

    video=out/'src/fpga/core/video_adapter.sv'
    text=video.read_text(encoding='utf-8')
    text=replace(text,'input  wire        reset,','input wire menu_show,menu_fault,\n    output wire menu_visible,\n    input  wire        reset,')
    anchor='    // === Raster Scan Timing Parameters ==='
    overlay='''    reg [2:0] show_sync=0,fault_sync=0;
    reg show_frame=0,fault_frame=0;
    reg [63:0] error_bitmap[0:239];
    initial $readmemh("gba_menu_error.hex",error_bitmap);
    reg [63:0] error_column=0;
    reg [7:0] error_y=0;
    always @(posedge clk_vid) begin
        show_sync<={show_sync[1:0],menu_show};fault_sync<={fault_sync[1:0],menu_fault};
        if(reset)begin show_frame<=0;fault_frame<=0;end
        else if(video_vs)begin show_frame<=show_sync[2];fault_frame<=fault_sync[2];end
        error_column<=error_bitmap[h_count<240 ? h_count : 9'd0];
        error_y<=v_count;
    end
    wire error_pixel=error_y>=48 && error_y<112 && error_column[error_y-48];
    assign menu_visible=show_frame | fault_frame;
'''
    text=replace(text,anchor,overlay+'\n'+anchor)
    text=replace(text,"video_rgb  <= active_d1 ? {r8, g8, b8} : 24'd0;",
                 "video_rgb  <= !active_d1 ? 24'd0 : fault_frame ? (error_pixel ? 24'he8e6dd : 24'd0) : show_frame ? {r8,g8,b8} : 24'd0;")
    video.write_text(text,encoding='utf-8',newline='\n')
    for name in ('gba_menu.sv','gba_menu_pixels.sv'):
        shutil.copy2(Path(__file__).with_name(name),out/'src/fpga/core'/name)
    qsf=out/'src/fpga/build/ap_core.qsf'
    with qsf.open('a') as f:
        f.write('\nset_global_assignment -name SYSTEMVERILOG_FILE ../core/gba_menu.sv\nset_global_assignment -name SYSTEMVERILOG_FILE ../core/gba_menu_pixels.sv\nset_global_assignment -name SYSTEMVERILOG_FILE ../pocket/data_loader.sv\n')
    sys.path.insert(0,str(Path(__file__).parent))
    from library import text as draw_text
    from PIL import Image
    image=Image.new('RGB',(240,64),'black')
    for line,y in (('操作失败',0),('A 重试   B 返回',24)):draw_text(image,line,y)
    words=[sum((image.getpixel((x,y))!=(0,0,0))<<y for y in range(64)) for x in range(240)]
    (out/'src/fpga/build/gba_menu_error.hex').write_text(''.join(f'{v:016x}\n' for v in words))


def prepare(source, out, menu=False):
    source,out=Path(source).resolve(),Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'.work/gba-menu'):
        raise ValueError('Use a fresh directory under .work/gba-menu')
    if not (source/'src/fpga/core/core_top.sv').is_file():
        raise ValueError('Expected the frozen mincer-ray GBA source tree')
    lock=json.loads(Path(__file__).with_name('upstream-lock.json').read_text(encoding='utf-8'))
    for rel,digest in lock['files'].items():
        if hashlib.sha256((source/rel).read_bytes()).hexdigest()!=digest:
            raise ValueError('Frozen upstream source differs: '+rel)
    out.parent.mkdir(parents=True,exist_ok=True)
    shutil.copytree(source,out)
    bios=out/'src/fpga/gba/gba_bios.vhd'
    text=bios.read_text(encoding='utf-8')
    text,n=re.subn(r'signal rom\s*:\s*t_rom\s*:=\s*\(.*?\);',
                  "signal rom : t_rom := (others => (others => '0'));",text,count=1,flags=re.S|re.I)
    if n!=1:raise ValueError('Unexpected BIOS source declaration; do not compile embedded bytes')
    bios.write_text(text,encoding='utf-8',newline='\n')
    if menu:integrate(out)
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sources',required=True);p.add_argument('--out',required=True)
    p.add_argument('--integrate',action='store_true')
    a=p.parse_args()
    print(prepare(a.sources,a.out,a.integrate))
