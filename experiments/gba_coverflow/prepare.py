#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Adapt the tested GBA lifecycle to the accepted shared CoverFlow renderer.

All edits land in a new .work tree. The accepted GB/GBC inputs, upstream source,
and earlier GBA candidates are immutable inputs.
"""
import argparse,importlib.util,json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('gba_prepare',ROOT/'experiments/gba_menu/prepare_build.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
replace=base.replace

SRAM_SDC='''
# Dedicated cover SRAM: AS6C2016-55BIN, 55 ns address/byte access,
# 45 ns WE pulse, 25 ns data setup, 20 ns output disable.
# Counter waits supply the external cycle. The packager separately requires
# every fitted I/O DATA path <= 4.25 ns at all corners (excluding clock insertion).
# Eight sys cycles with the input register give seven physical settling cycles:
# 7 * 9.930 - 4.25 - 55 - 4.25 = 6.01 ns remaining for board/skew margin.
# https://www.alliancememory.com/as6c2016/
# Clock endpoints keep these limits scoped to the asynchronous SRAM pins.
# The independent post-fit data-path check covers every SRAM pin.
set cf_sram_clock [get_clocks {ic|mp1|mf_pllbase_inst|sys_pll_i|general[0].gpll~PLL_OUTPUT_COUNTER|divclk}]
set cf_sram_ports [get_ports {sram_a[*] sram_dq[*] sram_oe_n sram_we_n sram_ub_n sram_lb_n}]
if {[get_collection_size $cf_sram_clock] != 1 || [get_collection_size $cf_sram_ports] != 37} {
    error "CoverFlow SRAM clock/pins are missing"
}
set_max_delay 10.000 -from $cf_sram_clock -to $cf_sram_ports
set_min_delay 0.000 -from $cf_sram_clock -to $cf_sram_ports
set_max_delay 10.000 -from [get_ports {sram_dq[*]}] -to $cf_sram_clock
set_min_delay -10.000 -from [get_ports {sram_dq[*]}] -to $cf_sram_clock
'''

def controller(text,exit_paths=1,cellram=False,associative=False,cover_recovery=False):
    if associative and not cellram:raise ValueError('Physical upload fence required for associative GBA cache')
    text=replace(text,'// GBAF1 page reader and GBA launch/save lifecycle, clocked by the APF bridge.',
        '// GBAF2 CoverFlow adapter; inherited GBA launch, ordinary save and RTC lifecycle.')
    text=replace(text,'input wire [31:0] save_capacity,','''input wire [31:0] save_capacity,
    input wire cf_want_art,cf_anim,cf_frame_tick,cf_mem_idle,cf_fetch_fault,
    input wire [10:0] cf_wanted_game,
    input wire [3:0] cf_level,cf_title_level,
    output reg cf_menu=1,cf_go=0,cf_direction=0,cf_invalidate=0,cf_commit=0,cf_generation=0,
    output reg [10:0] cf_loaded_game=0,
    output wire [10:0] cf_count,
    output reg [3:0] cf_level_target=0,cf_title_target=0,
    output reg [8:0] cf_title_width=0,cf_subtitle_width=0,''')
    text=replace(text,'localparam [31:0] FRAME_SIZE=76800;','''localparam CF_TEXT_WAIT=47,CF_TEXT_DONE=48,CF_ART_REQ=49,CF_ART_DONE=50,CF_ART_DRAIN=51,CF_EXIT=52;
    reg [3:0] cf_pending=0;
    reg [5:0] cf_repeat=0;
    reg [1:0] cf_chunk=0;
    reg [10:0] cf_art_game=0;
    reg [7:0] cf_after_exit=ACTIVATE;
    reg [31:0] atlas_stride=0;
    assign cf_count=count[10:0];
    wire [31:0] cf_chunk_offset={16'd0,cf_chunk,14'd0};
    localparam [31:0] FRAME_SIZE=76800;''')
    text=replace(text,'3:frame_base<=normalized;4:pause_base<=normalized;',
        '3:frame_base<=normalized;4:pause_base<=normalized;5:atlas_stride<=normalized;')
    text=replace(text,'0:entry_magic<=normalized;1:entry_flags<=normalized;2:rom_bytes<=normalized;',
        '''0:entry_magic<=normalized;1:entry_flags<=normalized;2:rom_bytes<=normalized;
            4:cf_title_width<=normalized<=500 ? normalized[8:0]:9'h1FF;
            5:cf_subtitle_width<=normalized<=300 ? normalized[8:0]:9'h1FF;''')
    text=replace(text,'begin frame_offset<=offset;after_frame<=next_state;menu_owned<=1;menu_show<=0;timer<=0;state<=FRAME_BLANK;end',
        '''begin
            menu_owned<=1;timer<=0;
            if(next_state==MENU)begin cf_menu<=1;cf_title_target<=0;state<=CF_TEXT_WAIT;end
            else begin frame_offset<=offset;after_frame<=next_state;menu_show<=0;state<=FRAME_BLANK;end
        end''')
    text=replace(text,'t_read<=0;t_open<=0;t_write<=0;t_flush<=0;new_load<=0;finish_load<=0;',
        '''t_read<=0;t_open<=0;t_write<=0;t_flush<=0;new_load<=0;finish_load<=0;
        cf_go<=0;cf_commit<=0;cf_invalidate<=0;
        if(cf_menu && !game_bound)begin
            cf_pending<=cf_pending | {press[5],press[4],press[3]|press[1],press[2]|press[0]};
            if(cf_frame_tick)begin
                if(!(buttons[0]||buttons[1]||buttons[2]||buttons[3]))cf_repeat<=0;
                else if(cf_repeat<18)cf_repeat<=cf_repeat+1'b1;
                else begin
                    cf_repeat<=14;
                    if(buttons[0]||buttons[2])cf_pending[0]<=1;
                    else cf_pending[1]<=1;
                end
            end
        end else begin cf_pending<=0;cf_repeat<=0;end''')
    text=replace(text,'fault_code<=0;first_fault_code<=0;go_back<=0;root_path<=0;command_armed<=0;',
        '''fault_code<=0;first_fault_code<=0;go_back<=0;root_path<=0;command_armed<=0;
            cf_menu<=1;cf_pending<=0;cf_repeat<=0;cf_level_target<=0;cf_title_target<=0;
            cf_invalidate<=0;cf_commit<=0;cf_go<=0;cf_generation<=0;''')
    text=replace(text,'header_version!=1','header_version!=2')
    text=replace(text,"pause_base<frame_base || pause_base>32'h10000000",
        "pause_base!=frame_base+(count<<16) || atlas_stride!=65536")
    text=replace(text,'else begin selected<=0;state<=RECORD_REQ;end',
        'else begin selected<=0;cf_pending<=0;cf_invalidate<=1;cf_menu<=1;cf_level_target<=0;state<=RECORD_REQ;end')
    text=replace(text,"RECORD_REQ:command(0,100,64+({21'd0,selected}<<10),32'h60000000,1024,RECORD_CHECK);",
        "RECORD_REQ:if(cf_title_level==0)command(0,100,64+({21'd0,selected}<<10),32'h60000000,1024,RECORD_CHECK); else cf_title_target<=0;")
    text=replace(text,"entry_magic!=32'h31544E45 || entry_flags>1",
        "entry_magic!=32'h31544E45 || entry_flags>1 || cf_title_width>500 || cf_subtitle_width>300")
    start=text.index('            MENU:begin');end=text.index('            ACTIVATE:begin',start)
    text=text[:start]+'''            MENU:begin
                if(cf_fetch_fault)fail(8'h74);
                else if(!cf_anim && cf_pending[2])begin
                    cf_pending<=0;cf_level_target<=0;cf_title_target<=0;cf_after_exit<=ACTIVATE;timer<=0;state<=CF_EXIT;
                end else if(!cf_anim && cf_pending[3])begin
                    cf_pending<=0;cf_level_target<=0;cf_title_target<=0;cf_after_exit<=RECORD_REQ;timer<=0;state<=CF_EXIT;
                end else if(!cf_anim && (cf_pending[0]||cf_pending[1]))begin
                    cf_direction<=cf_pending[0];cf_go<=1;cf_title_target<=0;
                    selected<=cf_pending[0] ? (selected==0 ? count[10:0]-1'b1:selected-1'b1) : (selected+1>=count ? 11'd0:selected+1'b1);
                    cf_pending[1:0]<=0;timer<=0;state<=RECORD_REQ;
                end else if(cf_want_art && !game_bound && io_idle)begin
                    cf_art_game<=cf_wanted_game;cf_chunk<=0;state<=CF_ART_REQ;
                end
            end
            CF_TEXT_WAIT:if(cf_title_level==0)command(0,100,frame_base+({21'd0,selected}<<16)+45568,32'h71000000,2048,CF_TEXT_DONE);
                else if(timer>=TIMEOUT)fail(8'h75);
            CF_TEXT_DONE:if(result!=0)fail(8'h76);else begin
                    cf_generation<=~cf_generation;cf_title_target<=8;cf_level_target<=8;menu_show<=1;state<=MENU;
                end
            CF_ART_REQ:command(0,100,frame_base+({21'd0,cf_art_game}<<16)+cf_chunk_offset,
                32'h12800000+({25'd0,cf_art_game[6:0]}<<16)+cf_chunk_offset,
                cf_chunk==2 ? 32'd12800:32'd16384,CF_ART_DONE);
            CF_ART_DONE:if(result!=0)fail(8'h70);
                else if(cf_chunk==2)begin timer<=0;state<=CF_ART_DRAIN;end
                else begin cf_chunk<=cf_chunk+1'b1;state<=CF_ART_REQ;end
            CF_ART_DRAIN:if(timer>=SETTLE_CYCLES && io_idle)begin
                    cf_loaded_game<=cf_art_game;cf_commit<=1;state<=MENU;
                end else if(timer>=TIMEOUT)fail(8'h71);
            CF_EXIT:if(cf_level==0 && cf_mem_idle && !visible && io_idle)begin
                    menu_show<=0;
                    if(cf_after_exit==RECORD_REQ)begin selected<=count[10:0]-1'b1;go_back<=1;end
                    state<=cf_after_exit;
                end else if(timer>=TIMEOUT)fail(8'h72);
''' + text[end:]
    text=replace(text,'else begin menu_reset<=1;menu_pause<=0;game_bound<=0;timer<=0;state<=ROM_START;end',
        'else begin cf_menu<=0;menu_reset<=1;menu_pause<=0;game_bound<=0;timer<=0;state<=ROM_START;end')
    text=replace(text,'game_bound<=0;menu_reset<=1;menu_pause<=0;menu_show<=0;timer<=0;state<=RECORD_REQ;',
        'cf_menu<=1;cf_pending<=0;cf_level_target<=0;cf_title_target<=0;game_bound<=0;menu_reset<=1;menu_pause<=0;menu_show<=0;timer<=0;state<=RECORD_REQ;',exit_paths)
    text=replace(text,'HOME_OPEN:begin root_path<=1;',
        'HOME_OPEN:begin cf_menu<=1;cf_level_target<=0;cf_title_target<=0;root_path<=1;')
    # NES/Sega adapt the legacy controller too; keep their accepted output
    # unchanged while the GBA transport gains a physical-upload drain fence.
    if cellram:
        text=replace(text,'input wire cf_want_art,cf_anim,cf_frame_tick,cf_mem_idle,cf_fetch_fault,',
            'input wire cf_want_art,cf_anim,cf_frame_tick,cf_mem_idle,cf_fetch_fault,cf_upload_ready,')
        text=replace(text,"32'h12800000+({25'd0,cf_art_game[6:0]}<<16)+cf_chunk_offset,",
            "32'h42000000+({25'd0,cf_art_game[6:0]}<<16)+cf_chunk_offset,")
        text=replace(text,'CF_ART_DRAIN:if(timer>=SETTLE_CYCLES && io_idle)begin',
            "CF_ART_DRAIN:if(cf_fetch_fault)fail(8'h74);\n                else if(timer>=SETTLE_CYCLES && io_idle && cf_upload_ready)begin")
        # A cover drain must not inherit the much longer full-ROM watchdog.
        text=replace(text,"else if(timer>=TIMEOUT)fail(8'h71);",
            "else if(timer>=(FRAME_TIMEOUT<TIMEOUT ? FRAME_TIMEOUT:TIMEOUT))fail(8'h71);")
        text=replace(text,'cf_loaded_game<=cf_art_game;cf_commit<=1;state<=MENU;',
            'cf_loaded_game<=cf_art_game;cf_commit<=1;state<=53;')
        # Let need_clr invalidate the published cache miss before requesting
        # another atlas. Otherwise the just-committed cover is read twice.
        text=replace(text,'            CF_EXIT:if(cf_level==0',
            '            53:state<=MENU;\n            CF_EXIT:if(cf_level==0')
    if associative:
        text=replace(text,'input wire [10:0] cf_wanted_game,',
            'input wire [10:0] cf_wanted_game,\n    input wire [2:0] cf_wanted_slot,')
        text=replace(text,'output reg [10:0] cf_loaded_game=0,',
            'output reg [10:0] cf_loaded_game=0,\n    output reg [2:0] cf_loaded_slot=0,')
        text=replace(text,'cf_art_game<=cf_wanted_game;cf_chunk<=0;state<=CF_ART_REQ;',
            'cf_art_game<=cf_wanted_game;cf_loaded_slot<=cf_wanted_slot;cf_chunk<=0;state<=CF_ART_REQ;')
        text=replace(text,"32'h42000000+({25'd0,cf_art_game[6:0]}<<16)+cf_chunk_offset,",
            "32'h42000000+({29'd0,cf_loaded_slot}<<16)+cf_chunk_offset,")
    if associative or cover_recovery:
        if not cellram:raise ValueError('Cover recovery requires the upload drain fence')
        text=replace(text,'reg [10:0] cf_art_game=0;',
            'reg [10:0] cf_art_game=0;\n    reg cf_art_unavailable=0;')
        text=replace(text,'    task automatic paint(','''    task automatic skip_cover_art;
        begin
            // An incomplete atlas may have overwritten an old slot. Keep the
            // titles and controls working with placeholders until the next Run.
            cf_art_unavailable<=1;cf_invalidate<=1;state<=MENU;
        end
    endtask
    task automatic paint(''')
        text=replace(text,'cf_invalidate<=0;cf_commit<=0;cf_go<=0;cf_generation<=0;',
            'cf_invalidate<=0;cf_commit<=0;cf_go<=0;cf_generation<=0;cf_art_unavailable<=0;')
        text=replace(text,"if(cf_fetch_fault)fail(8'h74);",'if(!cf_art_unavailable && cf_fetch_fault)skip_cover_art();',2)
        text=replace(text,'else if(cf_want_art && !game_bound && io_idle)',
            'else if(!cf_art_unavailable && cf_want_art && !game_bound && io_idle)')
        text=replace(text,"CF_ART_DONE:if(result!=0)fail(8'h70);",
            'CF_ART_DONE:if(result!=0 || cf_fetch_fault)skip_cover_art();')
        text=replace(text,"else if(timer>=(FRAME_TIMEOUT<TIMEOUT ? FRAME_TIMEOUT:TIMEOUT))fail(8'h71);",
            'else if(timer>=(FRAME_TIMEOUT<TIMEOUT ? FRAME_TIMEOUT:TIMEOUT))skip_cover_art();')
    return text

def retry_art(text):
    """Retry optional art only after transport, cache and raster have drained."""
    text=replace(text,'reg cf_art_unavailable=0;', '''reg cf_art_unavailable=0;
    reg [1:0] cf_art_retries=0,cf_recovery_frames=0;
    localparam CF_RECOVER_FRAME=54,CF_RECOVER_CLEAR=55,CF_RECOVER_DRAIN=56;''')
    text=replace(text,'cf_art_unavailable<=1;cf_invalidate<=1;state<=MENU;', '''cf_art_unavailable<=1;cf_invalidate<=1;timer<=0;cf_recovery_frames<=0;
            if(cf_art_retries<2)begin cf_art_retries<=cf_art_retries+1'b1;state<=CF_RECOVER_FRAME;end
            else state<=MENU;''')
    text=replace(text,'cf_generation<=0;cf_art_unavailable<=0;',
        'cf_generation<=0;cf_art_unavailable<=0;cf_art_retries<=0;cf_recovery_frames<=0;')
    text=replace(text,'else begin selected<=0;cf_pending<=0;cf_invalidate<=1;cf_menu<=1;cf_level_target<=0;state<=RECORD_REQ;end',
        'else begin selected<=0;cf_pending<=0;cf_invalidate<=1;cf_menu<=1;cf_level_target<=0;cf_art_unavailable<=0;cf_art_retries<=0;state<=RECORD_REQ;end')
    return replace(text,'            53:state<=MENU;', '''            53:state<=MENU;
            // Two raster ticks retire every old visible-slot snapshot. No APF
            // command is in flight here: only completed optional reads retry.
            CF_RECOVER_FRAME:begin
                if(cf_frame_tick && cf_recovery_frames<2)cf_recovery_frames<=cf_recovery_frames+1'b1;
                if(cf_recovery_frames==2 && cf_mem_idle && io_idle)state<=CF_RECOVER_CLEAR;
                else if(timer>=FRAME_TIMEOUT)state<=MENU;
            end
            CF_RECOVER_CLEAR:begin cf_invalidate<=1;timer<=0;state<=CF_RECOVER_DRAIN;end
            CF_RECOVER_DRAIN:if(timer>=SETTLE_CYCLES && cf_mem_idle && io_idle && !cf_fetch_fault)begin
                    cf_art_unavailable<=0;state<=MENU;
                end else if(timer>=FRAME_TIMEOUT)state<=MENU;''')


def share_color_blend(text):
    a=text.index('reg [23:0] h_out;');z=text.index('always @(posedge clk_vid) begin\n    hr_hs<=0;',a)
    return text[:a]+'''// Share the three final blend products across mutually exclusive layers.
// Selection priority and the original integer truncation stay unchanged.
reg [23:0] h_foreground;
reg [4:0] h_weight;
wire [23:0] h_out={mix(s2_br,h_foreground[23:16],h_weight),
    mix(s2_bg,h_foreground[15:8],h_weight),mix(s2_bb,h_foreground[7:0],h_weight)};
always @* begin
    h_foreground={s2_br,s2_bg,s2_bb};h_weight=0;
    if(s2_dbg)begin h_foreground=s2_dbv ? 24'h20E040:24'h601010;h_weight=16;end
    else if(s2_c && !s2_cut)begin h_foreground={cr2,cg2,cb2};h_weight=hwc;end
    else if(s2_t1)begin h_foreground={8'd246,8'd246,8'd250};h_weight=twc;end
    else if(s2_t2)begin h_foreground={8'd128,8'd140,8'd168};h_weight=twc;end
    else if(s2_dc)begin h_foreground={8'd232,8'd236,8'd244};h_weight=hlvl;end
    else if(s2_dd)begin h_foreground={8'd74,8'd82,8'd104};h_weight=hlvl;end
end
'''+text[z:]


def retime_cpu(text):
    # The existing multiply state has four clocks (wait=3..0). Keep its
    # architectural timing and put the arithmetic stages in those clocks.
    text=replace(text,'   signal mul_product       : unsigned(63 downto 0);','''   signal mul_signed_mode   : std_logic;
   signal mul_low_low       : unsigned(31 downto 0);
   signal mul_low_high      : signed(33 downto 0);
   signal mul_high_low      : signed(33 downto 0);
   signal mul_high_high     : signed(33 downto 0);
   signal mul_middle        : signed(34 downto 0);
   signal mul_product       : unsigned(63 downto 0);

   function sum_three(a,b,c : signed(34 downto 0)) return signed is
      variable carry : signed(34 downto 0);
   begin
      carry := shift_left((a and b) or (a and c) or (b and c),1);
      return (a xor b xor c) + carry;
   end function;''')
    text=replace(text,'                           mul_stage <= MULCALCMUL;\n                           mul_wait  <= 3;',
                 '                           mul_signed_mode <= execute_mul_long and execute_mul_signed;\n'
                 '                           mul_stage <= MULCALCMUL;\n                           mul_wait  <= 3;')
    text=replace(text,'''                        if (execute_mul_long = '0' or execute_mul_signed = '0') then
                           mul_product <= mul_op1 * mul_op2;
                        else
                           mul_product <= unsigned(signed(mul_op1) * signed(mul_op2));
                        end if;
                        mul_result <= mul_product;''','''                        case mul_wait is
                           when 3 =>
                              mul_low_low <= mul_op1(15 downto 0) * mul_op2(15 downto 0);
                              mul_low_high <= signed('0' & mul_op1(15 downto 0)) *
                                 signed((mul_signed_mode and mul_op2(31)) & mul_op2(31 downto 16));
                              mul_high_low <= signed((mul_signed_mode and mul_op1(31)) & mul_op1(31 downto 16)) *
                                 signed('0' & mul_op2(15 downto 0));
                              mul_high_high <= signed((mul_signed_mode and mul_op1(31)) & mul_op1(31 downto 16)) *
                                 signed((mul_signed_mode and mul_op2(31)) & mul_op2(31 downto 16));
                           when 2 =>
                              mul_middle <= sum_three(signed(resize(mul_low_low(31 downto 16),35)),
                                 resize(mul_low_high,35),resize(mul_high_low,35));
                           when 1 =>
                              mul_product <= (unsigned(mul_high_high(31 downto 0)) +
                                 unsigned(resize(mul_middle(34 downto 16),32))) &
                                 unsigned(mul_middle(15 downto 0)) & mul_low_low(15 downto 0);
                           when 0 => mul_result <= mul_product;
                        end case;''')
    # Select ADD/ADC during the arithmetic stage, before the writeback mux.
    at=text.index('      variable mul_low_sum')
    text=text[:at]+'''      variable add_carry : std_logic;
      variable add_sum : unsigned(33 downto 0);
'''+text[at:]
    start=text.index('                           when alu_add =>',text.index('                     when ALUCALC'))
    end=text.index('                           when alu_sub_withcarry =>',start)
    text=text[:start]+'''                           when alu_add | alu_add_withcarry =>
                              add_carry := '0';
                              if execute_functions_detail=alu_add_withcarry then add_carry := Flag_Carry; end if;
                              add_sum := ('0' & alu_op1 & add_carry) + ('0' & alu_op2 & add_carry);
                              alu_result_add <= add_sum(33 downto 1);
                              alu_result <= add_sum(32 downto 1);

                           when alu_sub =>
                              alu_result <= alu_op1 - alu_op2;

'''+text[end:]
    return replace(text,'''                        if (execute_functions_detail = alu_add or execute_functions_detail = alu_add_withcarry) then
                           calc_result <= alu_result_add(31 downto 0);
                        else
                           calc_result <= alu_result;
                        end if;''','''                        calc_result <= alu_result;''')


def prepare(source,out):
    out=base.prepare(source,out,True)
    cpu=out/'src/fpga/gba/gba_cpu.vhd'
    cpu.write_text(retime_cpu(cpu.read_text(encoding='utf8')),encoding='utf8',newline='\n')
    core=out/'src/fpga/core';top=core/'core_top.sv'
    (core/'gba_menu.sv').write_text(retry_art(controller((core/'gba_menu.sv').read_text(encoding='utf8'),cellram=True,associative=True)),encoding='utf8',newline='\n')
    sys.path.insert(0,str(ROOT/'experiments/coverflow_shared'))
    from prepare_assoc import build as shared_prepare
    shared=shared_prepare(ROOT/'.work/coverflow-delivery'/('assoc-'+out.name))
    files=['coverflow_geometry.sv','coverflow_assoc_view.sv','coverflow_assoc_cache.sv',
        'coverflow_line_fetch.sv','coverflow_dpram_ce.v','picker_dpram.v']
    for name in files:
        shutil.copy2(shared/name,core/name)
    # Keep menu pixel products in DSPs; the pixel arithmetic is unchanged.
    view=core/'coverflow_assoc_view.sv'
    view.write_text(share_color_blend(replace(view.read_text(encoding='utf8'),'module coverflow_assoc_view #',
        '(* multstyle = "dsp" *) module coverflow_assoc_view #')),encoding='utf8',newline='\n')
    shutil.copy2(HERE/'sram_cache.sv',core/'coverflow_sram_cache.sv')
    files.append('coverflow_sram_cache.sv')
    shutil.copy2(shared/'font_cn.hex',out/'src/fpga/build/font_cn.hex')
    s=top.read_text(encoding='utf8')
    s=replace(s,'gba_menu menu (',(HERE/'top_sram.sv').read_text(encoding='utf8')+'\ngba_menu menu (')
    s=replace(s,'.frame_ack(ui_frame_ack_b)', '''.cf_want_art(cf_want),.cf_wanted_game(cf_wanted),.cf_anim(cf_anim),.cf_frame_tick(cf_tick),
    .cf_mem_idle(cf_mem_idle),.cf_fetch_fault(cf_fetch_fault),.cf_upload_ready(cf_uploaded),.cf_level(cf_level),.cf_title_level(cf_title_level),
    .cf_wanted_slot(cf_wanted_slot),.cf_loaded_slot(cf_loaded_slot),
    .cf_menu(cf_menu),.cf_go(cf_go),.cf_direction(cf_direction),.cf_invalidate(cf_invalidate),.cf_commit(cf_commit),
    .cf_generation(cf_generation),.cf_loaded_game(cf_loaded),.cf_count(cf_count),
    .cf_level_target(cf_target),.cf_title_target(cf_title_target),.cf_title_width(cf_width),.cf_subtitle_width(cf_subwidth),
    .frame_ack(ui_frame_ack_b)''')
    s=replace(s,'.visible(ui_visible_bridge)', '.visible(cf_menu ? cf_level!=0 : ui_visible_bridge)')
    # The five-cover cache fits in unused SRAM. Native CRAM0/SDRAM and the
    # original inactive CRAM1 assignments retain their accepted ownership.
    idle_sram="assign sram_a = 'h0;\nassign sram_dq = {16{1'bZ}};\n"+''.join(
        f'assign sram_{name}  = 1;\n' for name in ('oe_n','we_n','ub_n','lb_n'))
    s=replace(s,idle_sram,'// SRAM is owned exclusively by the CoverFlow cache.\n')
    for signal in ['rgb','de','vs','hs','skip']:
        s=replace(s,f'.video_{signal}  ( video_{signal} )' if signal=='rgb' else f'.video_{signal}   ( video_{signal} )' if signal in ['de','vs','hs'] else '.video_skip ( video_skip )',
            f'.video_{signal} ( cf_game_{signal} )')
    s=replace(s,'video_adapter video_out (',(HERE/'video_mux.sv').read_text(encoding='utf8')+'\nvideo_adapter video_out (')
    top.write_text(s,encoding='utf8',newline='\n')
    with (core/'core_constraints.sdc').open('a',encoding='utf8',newline='\n') as f:f.write(SRAM_SDC)
    with (out/'src/fpga/build/ap_core.qsf').open('a') as f:
        for name in files:
            f.write('set_global_assignment -name '+('SYSTEMVERILOG_FILE' if name.endswith('.sv') else 'VERILOG_FILE')+' ../core/'+name+'\n')
        for port in ('sram_a[*]','sram_dq[*]','sram_oe_n','sram_we_n','sram_ub_n','sram_lb_n'):
            f.write('set_instance_assignment -name FAST_OUTPUT_REGISTER ON -to '+port+'\n')
        f.write('set_instance_assignment -name FAST_INPUT_REGISTER ON -to sram_dq[*]\n')
        f.write('set_instance_assignment -name FAST_OUTPUT_ENABLE_REGISTER ON -to sram_dq[*]\n')
    qsf=out/'src/fpga/build/ap_core.qsf'
    qsf.write_text(replace(qsf.read_text(encoding='utf8'),'set_global_assignment -name SEED 4','set_global_assignment -name SEED 5'),encoding='utf8',newline='\n')
    return out

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sources',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    print(prepare(a.sources,a.out))
