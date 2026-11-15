#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare a native WonderSwan CoverFlow candidate from a frozen upstream tree."""
import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
WORK = ROOT/'.work/repair-20261115/ws'
EXPERIMENTS = ROOT/'experiments'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = load('ws_console_prepare', EXPERIMENTS/'console_coverflow/prepare.py')
nes, gba, replace = base.nes, base.gba, base.replace
sys.path.insert(0, str(EXPERIMENTS/'native_features'))
pause = load('ws_pause_prepare', EXPERIMENTS/'native_features/prepare_pause.py')


def write(path, text):
    path.write_text(text, encoding='utf8', newline='\n')


def controller():
    s = nes.controller('wsclab', 524300, 'ws_menu')
    s = replace(s, 'output reg [7:0] state=0,',
        'output reg [31:0] rom_config=0,expected_save=0,\n'
        '    output reg [1:0] bios_select=0,\n    input wire bios_idle,\n    output reg [7:0] state=0,')
    s = replace(s, '2:rom_bytes<=normalized;',
        '2:rom_bytes<=normalized;3:expected_save<=normalized;5:rom_config<=normalized;')
    s = replace(s, 'rom_bytes<192 || rom_bytes>33554432 || rom_bytes[1:0]!=0',
        'rom_bytes<131072 || rom_bytes>16777216 || (rom_bytes & (rom_bytes-1))!=0 || rom_config>1')
    s = replace(s, 'if(save_capacity!=524300)',
        'if(save_capacity!=expected_save || !(save_capacity==12 || save_capacity==2060 || '
        'save_capacity==8204 || save_capacity==32780 || save_capacity==131084 || '
        'save_capacity==262156 || save_capacity==524300))')
    # All native SRAM/EEPROM files include the upstream twelve-byte RTC tail.
    # BIOS slots are 9/10; the ordinary save is slot 11. No separate RTC file.
    a, b = s.index('            RTC_OPEN:'), s.index('            LOAD_FINISH:')
    s = s[:a]+s[b:]
    s = s.replace('command(1,10,', 'command(1,11,').replace('command(0,10,', 'command(0,11,')
    s = s.replace('command(2,10,', 'command(2,11,').replace('command(3,10,', 'command(3,11,')
    s = replace(s, 'LOAD_FINISH:begin finish_load<=1;state<=LOAD_DRAIN;timer<=0;end',
        "LOAD_FINISH:if(prepare_ready)begin finish_load<=1;state<=LOAD_DRAIN;timer<=0;end\n"
        "                else if(timer>=TIMEOUT)fail(8'h47);")
    s = gba.controller(s, exit_paths=2, cellram=True, associative=True, cover_recovery=True)
    s = gba.retry_art(s)
    s = replace(s, '4:cf_title_width<=', '6:cf_title_width<=')
    s = replace(s, '5:cf_subtitle_width<=', '7:cf_subtitle_width<=')
    s = pause.pause_controller(s, 11, 0x20000000)
    a, b = s.index('            QUIT_RTC_OPENED:'), s.index('            ERROR:')
    s = s[:a]+s[b:]
    s = replace(s, '    localparam [31:0] FRAME_SIZE=',
        '    localparam BIOS_BW_START=57,BIOS_BW_DONE=58,BIOS_BW_DRAIN=59,\n'
        '        BIOS_COLOR_START=60,BIOS_COLOR_DONE=61,BIOS_COLOR_DRAIN=62;\n'
        '    reg bios_loaded=0;\n    localparam [31:0] FRAME_SIZE=')
    s = replace(s, 'if(ready && io_idle)state<=HEADER_REQ;',
        'bios_select<=0;\n            if(ready && io_idle)state<=bios_loaded ? HEADER_REQ : BIOS_BW_START;')
    s = replace(s, '            HEADER_REQ:', '''            BIOS_BW_START:begin
                bios_select<=1;command(0,9,0,32'h30000000,4096,BIOS_BW_DONE);
            end
            BIOS_BW_DONE:if(result!=0)fail(8'h80);else begin state<=BIOS_BW_DRAIN;timer<=0;end
            BIOS_BW_DRAIN:if(timer>=SETTLE_CYCLES && bios_idle)state<=BIOS_COLOR_START;
                else if(timer>=TIMEOUT)fail(8'h81);
            BIOS_COLOR_START:begin
                bios_select<=2;command(0,10,0,32'h30000000,8192,BIOS_COLOR_DONE);
            end
            BIOS_COLOR_DONE:if(result!=0)fail(8'h82);else begin state<=BIOS_COLOR_DRAIN;timer<=0;end
            BIOS_COLOR_DRAIN:if(timer>=SETTLE_CYCLES && bios_idle)begin
                bios_select<=0;bios_loaded<=1;state<=HEADER_REQ;
            end else if(timer>=TIMEOUT)fail(8'h83);
            HEADER_REQ:''')
    # A BIOS failure retry must complete the BIOS sequence before opening a menu.
    s = replace(s, 'HOME_OPEN:begin cf_menu<=1;',
        'HOME_OPEN:if(!bios_loaded)state<=BIOS_BW_START;else begin cf_menu<=1;')
    return s


def native_loader(source):
    s = replace(source, 'module data_loader #(', 'module ws_data_loader #(')
    s = replace(s, 'output reg write_en = 0,', 'output wire idle,\n    output reg write_en = 0,')
    s = replace(s, '  initial begin\n    // Verify parameters', '''  // Report drain in the bridge domain. The quiet fence covers FIFO pointer
  // propagation; the destination state prevents dropping the final request.
  reg [2:0] memory_idle_sync=0;
  reg [5:0] bridge_quiet=0;
  always @(posedge clk_74a)begin
    memory_idle_sync<={memory_idle_sync[1:0],mem_empty && read_state==0 && !write_en && !read_req};
    if((bridge_wr && bridge_addr[31:28]==ADDRESS_MASK_UPPER_4) || write_state!=0 || write_req)
      bridge_quiet<=0;
    else if(bridge_quiet!=63)bridge_quiet<=bridge_quiet+1'b1;
  end
  assign idle=memory_idle_sync[2] && bridge_quiet==63 && write_state==0 && !write_req;

  initial begin
    // Verify parameters''')
    return s

def native_unloader(s):
    # Native halfwords arrive slower than the APF bridge clock. Wait for each
    # response FIFO word; the inherited unconditional second read underflows.
    s=replace(s,'      apf_data_count  <= 0;','')
    s=replace(s,'          data_send_state <= 0;','          data_send_state <= 0;apf_data_count<=0;')
    s=replace(s,'          data_read_req <= 1;\n          data_send_state <= READ_DATA_DELAY;',
        '          data_read_req <= 0;\n          data_send_state <= 0;')
    return s


def wrapper(source):
    s = replace(source, 'input wire reset_n,',
        'input wire reset_n,menu_pause,\n    output reg menu_paused=0,')
    s = replace(s, 'paused <= syncpaused;', 'paused <= syncpaused || menu_pause;')
    s = replace(s, '.pause_in(paused),', '.pause_in(paused),.menu_paused(engine_paused),')
    s = replace(s, '  reg paused;', '''  wire engine_paused;
  reg [6:0] pause_quiet=0;
  // Let native CPU/DMA transactions retire before exposing save memory.
  always @(posedge clk_sys_36_864)begin
    if(!menu_pause || !engine_paused || clearing_ram || cart_download || sd_buff_wr || sd_buff_rd)
      pause_quiet<=0;
    else if(pause_quiet!=127)pause_quiet<=pause_quiet+1'b1;
    menu_paused<=menu_pause && engine_paused && pause_quiet==127;
  end
  reg paused;''')
    # The upstream immediate EEPROM ack is in the faster memory domain. Delay
    # it until the slower EEPROM port has actually sampled the stable bundle.
    s = replace(s, '  assign save_ram_write_complete = extra_data_addr ? rtc_write_ack : saveIsSRAM ? save_ram_ack : sd_buff_wr;',
        '''  reg eeprom_write_ack=0;
  always @(posedge clk_sys_36_864)
    eeprom_write_ack<=sd_buff_wr && !extra_data_addr && !saveIsSRAM;
  assign save_ram_write_complete = extra_data_addr ? rtc_write_ack : saveIsSRAM ? save_ram_ack : eeprom_write_ack;''')
    # Header + payload are held stable through the native loader's drain fence.
    # Reset only the per-cartridge RTC receive state on a new ROM load.
    s = replace(s, '    if (bk_record_rtc) begin', '    if (bk_record_rtc && sd_buff_wr) begin')
    needle = '        bk_record_rtc <= 0;\n      end\n    end\n  end\n\n  wire [127:0] time_din_h'
    s = replace(s, needle, '''        bk_record_rtc <= 0;
      end
    end
    if(cart_download)begin
      bk_record_rtc<=0;is_save_rtc_ready<=0;RTC_load<=0;
    end
  end

  wire [127:0] time_din_h''')
    # Loading the save happens while cart_download remains asserted. Only reset
    # RTC state on its rising edge, otherwise incoming RTC words are discarded.
    s = replace(s, '  reg bk_record_rtc = 0;', '  reg rtc_cart_prev=0;\n  always @(posedge clk_sys_36_864)rtc_cart_prev<=cart_download;\n  reg bk_record_rtc = 0;')
    s = replace(s, '    if(cart_download)begin\n      bk_record_rtc', '    if(cart_download && !rtc_cart_prev)begin\n      bk_record_rtc')
    s = replace(s, '  wire [127:0] time_din_h = {32\'d0, time_din, "RT"};', '''  // Snapshot the complete RTC tail before the first word is returned.
  reg [79:0] rtc_snapshot=0;
  always @(posedge clk_sys_36_864)
    if(sd_buff_rd && extra_data_addr && sd_buff_addr[8:0]==0)rtc_snapshot<=time_din;
  wire [127:0] time_din_h = {32'd0, rtc_snapshot, "RT"};''')
    return s


def top(source):
    s = source
    for signal in ('a', 'dq', 'oe_n', 'we_n', 'ub_n', 'lb_n'):
        s, n = re.subn(r'^  assign sram_'+signal+r'\s*=.*?;\n', '', s, flags=re.M)
        if n != 1: raise ValueError('Upstream SRAM is no longer unused')
    a, b = s.index("        32'h0: begin"), s.index("        32'h050: begin")
    s = s[:a]+s[b:]
    a, b = s.index('  // Driven by CHIP32'), s.index('  wire [11:0] save_size;')
    s = s[:a]+'''  wire cart_download=ui_loading;
  wire [1:0] bios_download=ui_bios;
  wire [1:0] ext_cart_download=ui_config[0] ? {cart_download,1'b0} : {1'b0,cart_download};

'''+s[b:]
    s = replace(s, "      32'hF8xxxxxx: begin", "      32'hF3xxxxxx: begin bridge_rd_data<=ui_param;end\n      32'hF8xxxxxx: begin")
    s = replace(s, '  wire savestate_supported = 1;', '  wire savestate_supported = 0;')
    a, b = s.index('  save_state_controller save_state_controller ('), s.index('  wire ioctl_wr;')
    s = s[:a]+'''  // Ordinary native SRAM/EEPROM+RTC saves are supported. Memories disabled.
  assign ss_save=0;assign ss_load=0;assign ss_dout=0;assign ss_ack=0;
  assign save_state_bridge_read_data=0;
  assign savestate_start_ack=0;assign savestate_start_busy=0;assign savestate_start_ok=0;assign savestate_start_err=1;
  assign savestate_load_ack=0;assign savestate_load_busy=0;assign savestate_load_ok=0;assign savestate_load_err=1;

'''+s[b:]
    s = s.replace('  data_loader #(', '  ws_data_loader #(')
    s = replace(s, '.write_complete(rom_write_complete),', '.write_complete(rom_write_complete),.idle(ui_rom_idle),')
    s = replace(s, '  ) bios_data_loader (', '  ) bios_data_loader (\n      .idle(ui_bios_idle),')
    s = replace(s, '.write_complete(save_ram_write_complete),', '.write_complete(save_ram_write_complete),.idle(ui_save_idle),')
    # Nine native clocks exceed a fully paused SDRAM refresh+read cycle and
    # permit both halfwords within one 75-clock bridge transaction interval.
    s = replace(s, '.READ_MEM_CLOCK_DELAY(20)', '.READ_MEM_CLOCK_DELAY(9)')
    s = replace(s, 'datatable_data <= save_size * 512 + (has_rtc ? 6 * 2 : 0);',
        'datatable_data <= ui_registered_save_bytes;')
    s = replace(s, 'datatable_addr <= 2 * 3 + 1;', 'datatable_addr <= 2 * 4 + 1;')
    s = replace(s, '.reset_n(reset_n_s),', '.reset_n(reset_n_s && !ui_reset_s),\n      .menu_pause(ui_pause_s),.menu_paused(ui_paused_s),')
    s, n = re.subn(r'(\.(?:button_\w+|dpad_\w+)\()(cont1_key_s\[\d+\])\)', r'\1\2 && !ui_input_block)', s)
    if n != 12: raise ValueError('Upstream WS input map changed')
    s = replace(s, '      .datatable_addr(datatable_addr),', '''      .target_cmd_req(tcmd_req),.target_cmd(tcmd),
      .target_cmd_p0(tcmd_p0),.target_cmd_p1(tcmd_p1),.target_cmd_p2(tcmd_p2),.target_cmd_p3(tcmd_p3),
      .target_cmd_ack(tcmd_ack),.target_cmd_done(tcmd_done),.target_cmd_result(tcmd_result),
      .datatable_addr(datatable_addr),''')
    for port in ('rgb', 'de', 'vs', 'hs'):
        s = replace(s, f'  assign video_{port} = video_{port}_reg;', '')
    s = replace(s, '  assign video_skip = 0;', '')
    insertion = (HERE/'top_insert.sv').read_text(encoding='utf8')
    cf = (EXPERIMENTS/'gba_coverflow/top_sram.sv').read_text(encoding='utf8')
    a, b = cf.index('reg [2:0] cf_pixel_div=0;'), cf.index('wire cf_text_we')
    # PLL outclk2 is 6.144 MHz, irrespective of the inherited 3_75 signal name.
    # 374x300 raster -> 54.759 Hz without clock enables or skipped pixels.
    cf = cf[:a]+"wire cf_pixel_ce=1'b1;\n"+cf[b:]
    cf = cf.replace('target_dataslot_read', 'ui_read').replace('target_dataslot_bridgeaddr', 'ui_address')
    cf = replace(cf, '.enable(cf_menu && !ui_fault),.hold_gb(ui_owned),',
        '.pause_scene(ui_pause_scene),.enable(cf_menu && !ui_fault),.hold_gb(ui_owned),')
    video = (EXPERIMENTS/'gba_coverflow/video_mux.sv').read_text(encoding='utf8')
    video = video[video.index('reg cf_video_owner=1;'):]
    video = video.replace('cf_menu && !ui_fault', 'cf_menu || ui_fault || ui_pause').replace("24'h002000", "24'h004000")
    return replace(s, '  // bridge data slot access', insertion+'\n'+cf+'\n'+video+'\n  // bridge data slot access')


def prepare(source, art_loader, out):
    source, art_loader, out = Path(source).resolve(), Path(art_loader).resolve(), Path(out).resolve()
    if out.exists() or not out.is_relative_to(WORK):
        raise ValueError('A fresh candidate path under .work/repair-20261115/ws is required')
    frozen = json.loads((HERE/'upstream-files.json').read_text(encoding='utf8'))
    actual={p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file()
        and not {'.git','db','incremental_db','output_files'} & set(p.relative_to(source).parts)}
    if actual!={entry['path'] for entry in frozen['files']}:
        raise ValueError('Upstream source inventory changed')
    if art_loader.read_bytes()!=(HERE/'art_data_loader.sv').read_bytes():
        raise ValueError('The menu art loader differs from the verified bundled loader')
    for item in frozen['files']:
        if hashlib.sha256((source/item['path']).read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Upstream source changed: '+item['path'])
    shutil.copytree(source, out, ignore=shutil.ignore_patterns('.git','db','incremental_db','output_files'))
    dest, project = out/'src/fpga/core', out/'src/fpga'
    write(dest/'core_top.v', top((dest/'core_top.v').read_text(encoding='utf8')))
    write(dest/'ws_menu.sv', controller())
    write(dest/'ws_data_loader.sv', native_loader((dest/'data_loader.sv').read_text(encoding='utf8')))
    write(dest/'data_unloader.sv',native_unloader((dest/'data_unloader.sv').read_text(encoding='utf8')))
    shutil.copy2(art_loader, dest/'data_loader.sv')
    write(dest/'wonderswan.sv', wrapper((dest/'wonderswan.sv').read_text(encoding='utf8')))
    swan = dest/'rtl/swanTop.vhd'
    s = replace(swan.read_text(encoding='utf8'), '      pause_in                   : in  std_logic;',
        '      pause_in                   : in  std_logic;\n      menu_paused                : out std_logic;')
    s = replace(s, '\nbegin\n', '''
begin
   menu_paused <= '1' when pause_in='1' and reset_in='0' and ce='0' and ce_cpu='0' and ce_4x='0'
      and EXTRAM_read='0' and EXTRAM_write='0' and EXTRAM_acc_1='0' and EXTRAM_acc_2='0' else '0';
''')
    write(swan, s)
    cmd = dest/'core_bridge_cmd.v'
    s = base.target_bridge(cmd.read_text(encoding='utf8'))
    s = s.replace('TARG_ST_SLOTREAD', 'TARG_ST_DATASLOTOP').replace('TARG_ST_WAITRESULT;', 'TARG_ST_WAITRESULT_RTR;').replace('TARG_ST_WAITRESULT:', 'TARG_ST_WAITRESULT_RTR:')
    write(cmd, s)
    shutil.copy2(EXPERIMENTS/'sega_coverflow/target_adapter.sv', dest/'ws_target.sv')
    sys.path.insert(0, str(EXPERIMENTS/'coverflow_shared'))
    from prepare_assoc import build
    shared = build(out/'coverflow-shared')
    files = ['coverflow_geometry.sv','coverflow_assoc_view.sv','coverflow_assoc_cache.sv',
             'coverflow_line_fetch.sv','coverflow_dpram_ce.v','picker_dpram.v']
    for name in files: shutil.copy2(shared/name, dest/name)
    view = dest/'coverflow_assoc_view.sv'
    write(view, pause.pause_view(view.read_text(encoding='utf8')))
    s = (EXPERIMENTS/'gba_coverflow/sram_cache.sv').read_text(encoding='utf8')
    s = s.replace('timer<=8;', 'timer<=9;')
    write(dest/'coverflow_sram_cache.sv', s)
    shutil.copy2(shared/'font_cn.hex', project/'font_cn.hex')
    qsf = project/'ap_core.qsf'
    s = replace(qsf.read_text(encoding='utf8'), '-name VERILOG_FILE core/core_top.v', '-name SYSTEMVERILOG_FILE core/core_top.v')
    s = replace(s, '-name ENABLE_SIGNALTAP ON', '-name ENABLE_SIGNALTAP OFF')
    for name in [*files, 'coverflow_sram_cache.sv','ws_menu.sv','ws_target.sv','ws_data_loader.sv']:
        kind = 'SYSTEMVERILOG_FILE' if name.endswith('.sv') else 'VERILOG_FILE'
        s += f'\nset_global_assignment -name {kind} core/{name}'
    for pin in ('sram_a[*]','sram_dq[*]','sram_oe_n','sram_we_n','sram_ub_n','sram_lb_n'):
        s += f'\nset_instance_assignment -name FAST_OUTPUT_REGISTER ON -to {pin}'
    s += '\nset_instance_assignment -name FAST_INPUT_REGISTER ON -to sram_dq[*]'
    s += '\nset_instance_assignment -name FAST_OUTPUT_ENABLE_REGISTER ON -to sram_dq[*]'
    s += '\nset_global_assignment -name OPTIMIZE_HOLD_TIMING ALL_PATHS'
    s += '\nset_global_assignment -name FITTER_EFFORT "STANDARD FIT"'
    write(qsf, s+'\n')
    pause.include_renderer(dest, project, 'ap_core.qsf', 'core')
    # The renderer declares 2048 words; pad unused labels explicitly.
    glyphs=(project/'native_pause.hex').read_text(encoding='ascii').splitlines()
    if len(glyphs)!=1280:raise ValueError('Pause font shape changed')
    write(project/'native_pause.hex','\n'.join(glyphs+['0000']*768)+'\n')
    sdc = dest/'core_constraints.sdc'
    limits = gba.SRAM_SDC.replace('sys_pll_i|general[0]', 'altera_pll_i|general[0]')
    limits = limits.replace('Eight sys cycles with the input register give seven physical settling cycles:',
        'Nine 110.592 MHz sys cycles give eight physical settling cycles:').replace(
        '7 * 9.930 - 4.25 - 55 - 4.25 = 6.01', '8 * 9.042 - 4.25 - 55 - 4.25 = 8.84')
    limits += '''
# The first fit exposed a 15 ps fast-corner hold violation on the inherited
# sprite DMA register -> sprite RAM input path. Require extra data delay;
# no false paths, clock changes or relaxed timing are used.
set ws_sprite_from [get_registers {*igpu*spriteDMAData*}]
set ws_sprite_to [get_registers {*igpu*spriteRAM*}]
if {[get_collection_size $ws_sprite_from] < 16 || [get_collection_size $ws_sprite_to] < 16} {
    error "WS sprite hold endpoints missing"
}
set_min_delay 0.750 -from $ws_sprite_from -to $ws_sprite_to
'''
    write(sdc, sdc.read_text(encoding='utf8')+limits)
    metadata(out)
    files = [{'path':p.relative_to(out).as_posix(), 'bytes':p.stat().st_size,
              'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
             for p in sorted(out.rglob('*')) if p.is_file()]
    write(out/'preparation.json', json.dumps({'upstream':frozen['upstream'],'files':files,
        'menu_video_hz':6144000/(374*300),'native_saves':'upstream payload + 12 RTC bytes',
        'accepted_on_device':False}, indent=2)+'\n')
    return out


def metadata(out):
    directory=out/'dist/Cores/agg23.WonderSwan'
    meta=json.loads((directory/'core.json').read_text())
    meta['core']['metadata'].update(shortname='WS Menu CN',version='0.1.0-ws.1',date_release='2026-11-15',
        description='Native WonderSwan and Color with Chinese CoverFlow; offline candidate')
    meta['core']['framework'].pop('chip32_vm',None)
    meta['core']['framework']['sleep_supported']=False
    meta['core']['cores']=[{'name':'default','id':0,'filename':'wswan.rbf_r'}]
    write(directory/'core.json',json.dumps(meta,indent=2)+'\n')
    slots=[{'name':'Menu','id':100,'required':True,'deferload':True,'filename':'menu.bin','parameters':'0x8','extensions':['bin'],'address':'0x70000000'},
           {'name':'Cartridge','id':0,'required':False,'deferload':True,'parameters':'0x8','extensions':['ws','wsc'],'address':'0x10000000'},
           {'name':'B&W BIOS','id':9,'required':True,'deferload':True,'filename':'bw.rom','parameters':'0x0','extensions':['rom'],'address':'0x30000000'},
           {'name':'Color BIOS','id':10,'required':True,'deferload':True,'filename':'color.rom','parameters':'0x0','extensions':['rom'],'address':'0x30000000'},
           {'name':'Save','id':11,'required':False,'deferload':True,'parameters':'0x0','nonvolatile':True,'extensions':['sav'],'address':'0x20000000'}]
    write(directory/'data.json',json.dumps({'data':{'magic':'APF_VER_1','data_slots':slots}},indent=2)+'\n')
    video=json.loads((directory/'video.json').read_text())
    video['video']['scaler_modes'].append({'width':320,'height':288,'aspect_w':10,'aspect_h':9,'rotation':0,'mirror':0})
    write(directory/'video.json',json.dumps(video,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--art-loader',type=Path,default=HERE/'art_data_loader.sv')
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    print(prepare(args.source,args.art_loader,args.out))
