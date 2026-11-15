#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare independent PCE and Genesis native CoverFlow builds from pinned sources."""

import argparse
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPERIMENTS = ROOT / 'experiments'
SEGA = EXPERIMENTS / 'sega_coverflow'
PROFILES = {
    'pce': ('pcelab', 2048, 0x400000, 0x20000000, 'ad241bae913499971cbfc00cd99a11c7284284a2db0818b587c6c2438fc6ddc4'),
    'genesis': ('mdclab', 65536, 0x800000, 0x60000000, '597f7d3412304daf3bf073720ae9bf0ab1125552816fca4dd03a323079568453'),
    'snes': ('snescn', 131072, 0x1000200, 0x20000000, '0a1151ccb8d1a53538d6ea121e09d0ae5059cecfb93d9ee68659944982743c94'),
    'jtcps2': ('cpslab', 128, 0x4000000, 0, '1988419686916fce883190cbf3ef93e32f4ed93400add2159f1f35499f95fff6'),
}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


nes = load('console_nes', EXPERIMENTS / 'nes_menu/prepare_build.py')
gba = load('console_gba', EXPERIMENTS / 'gba_coverflow/prepare.py')
replace = nes.replace


def controller(platform):
    namespace, capacity, maximum, save_address, _ = PROFILES[platform]
    text = nes.controller(namespace, capacity, 'console_menu')
    text = replace(text, 'output reg [7:0] state=0,',
                   'output wire [31:0] cart_size,output reg [31:0] cart_mode=0,\n    output reg [7:0] state=0,')
    text = replace(text, '0:entry_magic<=normalized;1:entry_flags<=normalized;2:rom_bytes<=normalized;',
                   '0:entry_magic<=normalized;1:entry_flags<=normalized;2:rom_bytes<=normalized;3:cart_mode<=normalized;')
    text = replace(text, 'assign fault=state==ERROR;', 'assign cart_size=rom_bytes;\n    assign fault=state==ERROR;')
    text = replace(text, 'rom_bytes<192 || rom_bytes>33554432 || rom_bytes[1:0]!=0',
                   f'rom_bytes<512 || rom_bytes>{maximum} || rom_bytes[1:0]!=0 || cart_mode>{int(platform=="pce")}')
    text = replace(text, "command(0,10,0,32'h20000000,save_bytes,SAVE_READ_DONE)",
                   f"command(0,10,0,32'h{save_address:08x},save_bytes,SAVE_READ_DONE)", 2)
    start, end = text.index('            RUN:'), text.index('            PAUSE_WAIT:')
    text = text[:start] + '            RUN:begin end\n' + text[end:]
    text = gba.controller(text, exit_paths=2, cellram=True, cover_recovery=True)
    # Genesis SRAM occupies 0x6. Menu metadata is never sent to that bus.
    text = replace(text, 'bridge_addr[31:28]==6', 'bridge_addr[31:28]==9', 2)
    return replace(text, "<<10),32'h60000000,1024,RECORD_CHECK);", "<<10),32'h90000000,1024,RECORD_CHECK);")


def target_bridge(text):
    """Add the raw request/ack interface already used by the Sega adapter."""
    text = replace(text, 'input   wire    [9:0]   datatable_addr,', '''input wire target_cmd_req,
input wire [15:0] target_cmd,
input wire [31:0] target_cmd_p0,target_cmd_p1,target_cmd_p2,target_cmd_p3,
output reg target_cmd_ack=0,target_cmd_done=0,
output reg [15:0] target_cmd_result=0,
input   wire    [9:0]   datatable_addr,''')
    text = replace(text, 'initial begin\n    reset_n <= 0;', '''initial begin
    hstate<=ST_IDLE;tstate<=TARG_ST_IDLE;host_cmd_start<=0;
    status_setup_done_1<=0;target_0<=0;host_0<=0;
    reset_n <= 0;''')
    start = text.index('    case(tstate)')
    end = text.index('    endcase', start) + len('    endcase')
    return text[:start] + '''    target_cmd_ack<=0;target_cmd_done<=0;
    case(tstate)
    TARG_ST_IDLE:begin
        if(status_setup_done_queue)begin
            status_setup_done_queue<=0;tstate<=TARG_ST_READYTORUN;
        end else if(target_cmd_req && reset_n)begin
            target_20<=target_cmd_p0;target_24<=target_cmd_p1;
            target_28<=target_cmd_p2;target_2C<=target_cmd_p3;
            target_0<={16'h636D,target_cmd};target_cmd_ack<=1;
            tstate<=TARG_ST_SLOTREAD;
        end
    end
    TARG_ST_READYTORUN:begin
        target_0<=32'h636D0140;tstate<=TARG_ST_WAITRESULT;
    end
    TARG_ST_WAITRESULT:if(target_0[31:16]==16'h6F6B)tstate<=TARG_ST_IDLE;
    TARG_ST_SLOTREAD:if(target_0[31:16]==16'h6F6B)begin
        target_cmd_result<=target_0[15:0];target_cmd_done<=1;tstate<=TARG_ST_IDLE;
    end
    default:tstate<=TARG_ST_IDLE;
    endcase
    if(reset_n && hstate==ST_PARSE && host_cmd==16'h0010)begin
        tstate<=TARG_ST_IDLE;target_0<=0;target_cmd_ack<=0;target_cmd_done<=0;
    end''' + text[end:]


def insert(platform, video_clock, pixel_ce, mode):
    _, capacity, _, _, _ = PROFILES[platform]
    sega = (SEGA / 'top_insert.sv').read_text(encoding='utf8')
    a, b = sega.index('  wire cf_menu,'), sega.index('  reg cf_video_owner=1;')
    art = sega[a:b].replace('.clk_vid(clk_vid),.pixel_ce(1\'b1)',
                             f'.clk_vid({video_clock}),.pixel_ce({pixel_ce})')
    art = art.replace('.vs(video_vs_reg)', '.vs(console_game_vs)')
    a, b = sega.index('  sega_menu menu('), sega.index('  sega_menu_pixels menu_pixels')
    commands = sega[a:b].replace('sega_menu menu(', 'console_menu menu(')
    commands = re.sub(r'\.frame_ack\(.*?\.visible\(cf_menu \? cf_level!=0:ui_visible_b\),',
                      ".frame_ack(1'b0),.frame_started(1'b0),.frame_valid(1'b0),.frame_fault(1'b0),.visible(cf_menu && cf_level!=0),",
                      commands, flags=re.S)
    commands = replace(commands, '.prepare_ready(ui_rom_idle && !rom_overrun_74),.load_ready(!ui_loading && ui_settle==0 && ui_rom_idle),\n'
                       '      .io_idle(!ui_loading && (!ui_bound || ui_paused) && ui_rom_idle),.save_capacity(32\'d32768),',
                       f".prepare_ready(1'b1),.load_ready(!ui_loading && ui_settle==0),\n"
                       f"      .io_idle(!ui_loading),.save_capacity(32'd{capacity}),")
    commands = re.sub(r'\s*\.cheat_[^;]*?(?=\.frame_request)', '\n      ', commands, flags=re.S)
    commands = replace(commands, '.first_fault_code(ui_first_fault),.state(ui_state),.selected(ui_selected));',
                       '.first_fault_code(ui_first_fault),.state(ui_state),.selected(ui_selected),\n'
                       '      .cart_size(ui_cart_size),.cart_mode(ui_cart_mode));')
    return '''
  wire ui_read,ui_write,ui_open,ui_flush,ui_done;
  wire [2:0] ui_error;
  wire [15:0] ui_slot;
  wire [31:0] ui_offset,ui_address,ui_length,ui_param,ui_cart_size,ui_cart_mode;
  wire ui_owned,ui_show,ui_reset,ui_pause,ui_new,ui_finish,ui_bound,ui_fault,ui_request;
  wire [7:0] ui_state,ui_fault_code,ui_first_fault;
  wire [10:0] ui_selected;
  wire tcmd_req,tcmd_ack,tcmd_done;
  wire [15:0] tcmd,tcmd_result;
  wire [31:0] tcmd_p0,tcmd_p1,tcmd_p2,tcmd_p3;
  reg ui_loading=0;
  reg [19:0] ui_settle=0;
  always @(posedge clk_74a)begin
      if(!reset_n || ui_fault)begin ui_loading<=0;ui_settle<=0;end
      else if(ui_new)begin ui_loading<=1;ui_settle<=0;end
      else if(ui_finish)begin ui_loading<=0;ui_settle<=20'd74000;end
      else if(ui_settle!=0)ui_settle<=ui_settle-1'b1;
  end
  wire console_game_de,console_game_hs,console_game_vs;
  wire [23:0] console_game_rgb;
''' + art + commands + f'''
  reg cf_video_owner=1;
  reg [2:0] cf_video_enable=0;
  always @(posedge {video_clock})begin
      cf_video_enable<={{cf_video_enable[1:0],cf_menu || ui_fault}};
      if(cf_video_owner)begin if(cf_vs)cf_video_owner<=cf_video_enable[2];end
      else if(console_game_vs)cf_video_owner<=cf_video_enable[2];
  end
  assign video_rgb=cf_video_owner ? (cf_de ? cf_rgb : !cf_hs && !cf_vs ? 24'h{mode << 13:06x} : 24'd0) : console_game_rgb;
  assign video_de=cf_video_owner ? cf_de : console_game_de;
  assign video_hs=cf_video_owner ? cf_hs : console_game_hs;
  assign video_vs=cf_video_owner ? cf_vs : console_game_vs;
  assign video_skip=cf_video_owner && cf_skip;
'''


def prepare(archive, gba_source, out, platform):
    out = nes.extract_source(archive, out, PROFILES[platform][-1])
    pce = platform == 'pce'
    dest = out / ('target/pocket' if pce else 'src/fpga/core')
    project = out / ('projects/pce_pocket.qsf' if pce else 'src/fpga/ap_core.qsf')
    top = dest / ('core_top.v' if pce else 'core_top.sv')
    text = top.read_text(encoding='utf8')
    text, removed = re.subn(r'^\s*assign cram0_[a-z0-9_]+\s*=.*?;\s*$', '', text, flags=re.M)
    if removed != 11:
        raise ValueError(f'Expected 11 idle CRAM assignments, found {removed}')
    text = replace(text, "32'hF8xxxxxx: begin", "32'hF3xxxxxx: begin bridge_rd_data<=ui_param;end\n    32'hF8xxxxxx: begin")
    text = re.sub(r'(\s+)(\.datatable_addr\s*\(\s*datatable_addr\s*\),)', r'''\1.target_cmd_req(tcmd_req),.target_cmd(tcmd),
      .target_cmd_p0(tcmd_p0),.target_cmd_p1(tcmd_p1),.target_cmd_p2(tcmd_p2),.target_cmd_p3(tcmd_p3),
      .target_cmd_ack(tcmd_ack),.target_cmd_done(tcmd_done),.target_cmd_result(tcmd_result),\1\2''', text, count=1)
    text = re.sub(r'\s*assign video_skip\s*=\s*0;', '', text, count=1)
    if pce:
        text = replace(text, '{ioctl_download, save_download, is_sgx},', '{ui_loading, ui_loading, ui_cart_mode[0]},')
        text = replace(text, "datatable_data <= mb128_enable ? 32'h20000 : 32'h800;", "datatable_data <= ui_bound ? 32'h800 : 0;")
        text = replace(text, 'datatable_addr <= 1 * 2 + 1;', 'datatable_addr <= 2 * 2 + 1;')
        text = replace(text, '.core_reset(~reset_n || reset_delay > 0),', '.core_reset(~reset_n || reset_delay > 0 || ui_reset),')
        for port, signal in [('vsync_out','vs'),('hsync_out','hs'),('de','de'),('rgb_out','rgb')]:
            text = replace(text, f'.{port}(video_{signal})', f'.{port}(console_game_{signal})')
        at = text.index('  ) sound_i2s (')
        audio = replace(text[at:], '.audio_l(audio_l),', ".audio_l(ui_owned ? 16'd0 : audio_l),")
        text = text[:at] + replace(audio, '.audio_r(audio_r),', ".audio_r(ui_owned ? 16'd0 : audio_r),")
        pixel = '''  reg [2:0] menu_pixel_div=0;
  always @(posedge clk_sys_42_95) menu_pixel_div<=menu_pixel_div==6 ? 3'd0 : menu_pixel_div+1'b1;
  wire menu_pixel_ce=menu_pixel_div==0;
'''
        insertion = pixel + insert(platform, 'clk_sys_42_95', 'menu_pixel_ce', 6)
    else:
        text = replace(text, "ioctl_download & bridge_addr[31:28] == 4'h1,", 'ui_loading,')
        text = replace(text, 'reg [31:0] rom_file_size = 0;', 'wire [31:0] rom_file_size = ui_cart_size;')
        text = replace(text, '\t\t\tif (datatable_div == 4) begin\n\t\t\t\trom_file_size <= datatable_q;\n\t\t\tend\n', '')
        text = replace(text, "datatable_data <= 32'd65536;", "datatable_data <= ui_bound ? 32'd65536 : 0;")
        text = replace(text, 'datatable_addr <= 1 * 2 + 1;', 'datatable_addr <= 2 * 2 + 1;')
        text = replace(text, 'wire reset = ~reset_n | cart_download | region_set;', 'wire reset = ~reset_n | cart_download | region_set | ui_reset;')
        for signal in ('de','hs','vs','rgb'):
            text = replace(text, f'assign video_{signal} = video_{signal}_reg;', f'assign console_game_{signal} = video_{signal}_reg;')
        text = replace(text, '.audio_l(AUDIO_L),', ".audio_l(ui_owned ? 16'd0 : AUDIO_L),")
        text = replace(text, '.audio_r(AUDIO_R),', ".audio_r(ui_owned ? 16'd0 : AUDIO_R),")
        modes = json.loads((out/'dist/Cores/ericlewis.Genesis/video.json').read_text())['video']['scaler_modes']
        insertion = insert(platform, 'current_pix_clk', "1'b1", len(modes))
    text = replace(text, 'endmodule', insertion + '\nendmodule')
    top.write_text(text, encoding='utf8', newline='\n')
    bridge = dest / 'core_bridge_cmd.v'
    bridge.write_text(target_bridge(bridge.read_text(encoding='utf8')), encoding='utf8', newline='\n')
    (dest/'console_menu.sv').write_text(controller(platform), encoding='utf8', newline='\n')
    shutil.copy2(SEGA/'target_adapter.sv', dest/'sega_menu_target.sv')
    sys.path.insert(0, str(EXPERIMENTS / 'coverflow_shared'))
    from prepare_psram import build
    shared = build(ROOT/'.work/coverflow-delivery'/('console-'+out.name), gba_source)
    files = ['coverflow_geometry.sv','coverflow_psram_view.sv','coverflow_line_fetch16.sv',
             'coverflow_psram.sv','coverflow_psram_cache.sv','coverflow_dpram_ce.v','picker_dpram.v']
    for name in files:
        shutil.copy2(shared/name, dest/name)
    shutil.copy2(shared/'font_cn.hex', project.parent/'font_cn.hex')
    settings = re.sub(r'^set_global_assignment -name (?:ENABLE_SIGNALTAP|USE_SIGNALTAP_FILE|SIGNALTAP_FILE|NUM_PARALLEL_PROCESSORS).*\n',
                      '', project.read_text(encoding='utf8'), flags=re.M)
    with project.open('w', encoding='utf8', newline='\n') as output:
        output.write(settings+'\nset_global_assignment -name ENABLE_SIGNALTAP OFF\nset_global_assignment -name NUM_PARALLEL_PROCESSORS 4\n')
        for name in [*files, 'console_menu.sv', 'sega_menu_target.sv']:
            kind = 'SYSTEMVERILOG_FILE' if name.endswith('.sv') else 'VERILOG_FILE'
            output.write(f'set_global_assignment -name {kind} {"../target/pocket" if pce else "core"}/{name}\n')
    return out


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('platform', choices=('pce','genesis'))
    for arg in ('archive','gba-source','out'):
        cli.add_argument('--'+arg, type=Path, required=True)
    args = cli.parse_args()
    print(prepare(args.archive, args.gba_source, args.out, args.platform))
