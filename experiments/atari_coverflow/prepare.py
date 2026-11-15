#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare Atari CoverFlow wrappers while retaining native shared-save slots."""
import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


console = load('atari_console_adapter', ROOT/'experiments/console_coverflow/prepare.py')
replace = console.replace
PROFILES = {
    '2600': ('atclab', '324f71f2dcc0454738bc1dd9142c2597a7416f4f', '0684ec314e6e5178f3efdc5ef6cb89871ee32a44065f029d4c31070a637135f7'),
    '7800': ('avclab', 'bfab2b52e346a17ca6c4c6572f0c6342206a4483', 'f1b8f64758c2d9c70a07b25604c4e02fa2758ed4e12cef9f4f4d960df39dda16'),
}
FILES = ['coverflow_geometry.sv', 'coverflow_psram_view.sv', 'coverflow_line_fetch16.sv',
         'coverflow_psram.sv', 'coverflow_psram_cache.sv', 'coverflow_dpram_ce.v', 'picker_dpram.v']


def controller(platform):
    namespace, _, sha = PROFILES[platform]
    console.PROFILES[platform] = (namespace, 0, 0x400000, 0, sha)
    text = console.controller(platform)
    text = replace(text, 'command(1,0,0,PARAM,0,ROM_OPENED)', 'command(1,256,0,PARAM,0,ROM_OPENED)')
    text = replace(text, "command(0,0,0,32'h10000000,rom_bytes,ROM_READ)", "command(0,256,0,32'h00000000,rom_bytes,ROM_READ)")
    # SaveKey, FA2 and HSC are shared devices, loaded/flushed by native APF
    # nonvolatile slots. Never open or seed per-ROM GBA-shaped save files.
    text = replace(text, "if(save_capacity!=0)fail(8'h34);\n                    else begin save_bytes<=save_capacity;state<=SAVE_OPEN;end",
                   'save_bytes<=0;state<=LOAD_FINISH;')
    return text


def bridge(text):
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
            target_20<=target_cmd_p0;target_24<=target_cmd_p1;target_28<=target_cmd_p2;target_2C<=target_cmd_p3;
            target_0<={16'h636D,target_cmd};target_cmd_ack<=1;tstate<=TARG_ST_WAITRESULT_DSO;
        end
    end
    TARG_ST_READYTORUN:begin target_0<=32'h636D0140;tstate<=TARG_ST_WAITRESULT_RTR;end
    TARG_ST_WAITRESULT_RTR:if(target_0[31:16]==16'h6F6B)tstate<=TARG_ST_IDLE;
    TARG_ST_WAITRESULT_DSO:if(target_0[31:16]==16'h6F6B)begin
        target_cmd_result<=target_0[15:0];target_cmd_done<=1;tstate<=TARG_ST_IDLE;
    end
    default:tstate<=TARG_ST_IDLE;
    endcase
    if(reset_n && hstate==ST_PARSE && host_cmd==16'h0010)begin
        tstate<=TARG_ST_IDLE;target_0<=0;target_cmd_ack<=0;target_cmd_done<=0;
    end''' + text[end:]


def prepare(platform, archive, gba_source, out):
    namespace, commit, archive_sha = PROFILES[platform]
    out = console.nes.extract_source(archive, out, archive_sha)
    dest, project = out/'src/fpga/core', out/'src/fpga/ap_core.qsf'
    top = dest/'core_top.v'
    text = top.read_text(encoding='utf8')
    text, count = re.subn(r'^assign cram1_[a-z0-9_]+\s*=.*?;\s*$', '', text, flags=re.M)
    if count != 11:
        raise ValueError(f'Expected unused CellRAM1, found {count} ties')
    text = replace(text, "    32'hF8xxxxxx: begin", "    32'hF3xxxxxx: begin bridge_rd_data<=ui_param;end\n    32'hF8xxxxxx: begin")
    text, count = re.subn(r'(\s+)(\.datatable_addr\s*\(\s*datatable_addr\s*\),)', r'''\1.target_cmd_req(tcmd_req),.target_cmd(tcmd),
    .target_cmd_p0(tcmd_p0),.target_cmd_p1(tcmd_p1),.target_cmd_p2(tcmd_p2),.target_cmd_p3(tcmd_p3),
    .target_cmd_ack(tcmd_ack),.target_cmd_done(tcmd_done),.target_cmd_result(tcmd_result),\1\2''', text)
    if count != 1:
        raise ValueError('APF adapter binding changed')
    # BIOS, HSC, SaveKey and FA2 retain their exact original address/slot path.
    # A menu ROM read is target-side and does not emit host requestwrite.
    text = replace(text, 'cart_download <= dl_s[2] & cart_s[2];', 'cart_download <= (dl_s[2] & cart_s[2]) | ui_loading_s;')
    text = replace(text, 'core_reset    <= ~rst_s[2] | mrst_s[2];', 'core_reset    <= ~rst_s[2] | mrst_s[2] | ui_reset_s;')
    for signal in ('rgb', 'de', 'hs', 'vs'):
        text, count = re.subn(rf'assign video_{signal}(\s*=)', rf'assign console_game_{signal}\1', text)
        if count != 1:
            raise ValueError('Native video output changed: '+signal)
    text = replace(text, 'assign video_skip = vid_skip;', '')
    for channel in ('l', 'r'):
        text = replace(text, f'.audio_{channel}    ( aud_{channel}_f ),', f".audio_{channel}    ( ui_owned_s ? 16'd0 : aud_{channel}_f ),")
    # NTSC 14.318181 MHz and PAL 14.18758 MHz: 2/5 CE gives 51.045/50.580 Hz.
    # PLL and all native game scaler modes stay untouched.
    controller_text = controller(platform)
    insertion = console.insert(platform, 'clk_sys', 'menu_pixel_ce', 2 if platform == '2600' else 4)
    insertion = insertion.replace('cram0_', 'cram1_')
    insertion = insertion.replace('.ready(reset_n && pll_core_locked)', '.ready(reset_n && pll_core_locked_s)')
    insertion = replace(insertion, 'if(cf_video_owner)begin if(cf_vs)', 'if(ui_reset_s)cf_video_owner<=1;\n      else if(cf_video_owner)begin if(cf_vs)')
    insertion = replace(insertion, '.enable(cf_menu && !ui_fault),', '.enable(cf_menu || !ui_bound || ui_fault),')
    insertion = replace(insertion, 'cf_menu || ui_fault', 'cf_menu || !ui_bound || ui_fault')
    insertion = replace(insertion, 'cf_de ? cf_rgb :', 'cf_de ? (ui_fault ? atari_error_rgb : cf_rgb) :')
    insertion = replace(insertion, 'assign video_skip=cf_video_owner && cf_skip;',
                        'assign video_skip=cf_video_owner ? cf_skip : vid_skip;')
    insertion = '''
  reg [2:0] menu_ce_phase=0;
  always @(posedge clk_sys)menu_ce_phase<=menu_ce_phase==4 ? 3'd0 : menu_ce_phase+1'b1;
  wire menu_pixel_ce=menu_ce_phase==0 || menu_ce_phase==2;
  wire ui_loading_s,ui_reset_s,ui_owned_s;
  synch_3 sync_menu_load(ui_loading,ui_loading_s,clk_sys);
  synch_3 sync_menu_reset(ui_reset,ui_reset_s,clk_sys);
  synch_3 sync_menu_owned(ui_owned,ui_owned_s,clk_sys);
  wire [23:0] atari_error_rgb;
  atari_error_pixels error_pixels(.clk(clk_sys),.de(cf_de),.hs(cf_hs),.vs(cf_vs),.skip(cf_skip),.rgb(atari_error_rgb));
''' + insertion
    text = replace(text, 'endmodule', insertion+'\nendmodule')
    top.write_text(text, encoding='utf8', newline='\n')
    target = dest/'core_bridge_cmd.v'
    target.write_text(bridge(target.read_text(encoding='utf8')), encoding='utf8', newline='\n')
    (dest/'console_menu.sv').write_text(controller_text, encoding='utf8', newline='\n')
    shutil.copy2(ROOT/'experiments/sega_coverflow/target_adapter.sv', dest/'sega_menu_target.sv')
    shutil.copy2(HERE/'error_pixels.sv', dest/'error_pixels.sv')
    sys.path.insert(0, str(ROOT/'experiments/coverflow_shared'))
    from prepare_psram import build
    shared = build(out/'coverflow-generated', gba_source)
    for name in FILES:
        shutil.copy2(shared/name, dest/name)
    if platform == '7800':
        # All eight native scaler slots are in use. Reuse native PAL 320x274
        # mode 4 for the menu: only fourteen empty bottom rows are omitted.
        # Titles, page dots (rows 256..259), covers and animation are retained.
        path = dest/'coverflow_psram_view.sv'
        path.write_text(replace(path.read_text(encoding='utf8'), 'HR_W = 320, HR_H = 288;', 'HR_W = 320, HR_H = 274;'), encoding='utf8', newline='\n')
    shutil.copy2(shared/'font_cn.hex', project.parent/'font_cn.hex')
    sys.path.insert(0, str(ROOT/'tools'))
    import build_library
    columns = [0]*320
    for line, shift in [('菜单加载失败', 0), ('按 A 重试', 16)]:
        width, raw, _, missing = build_library.columns(line, build_library.font())
        if missing or width > 320:
            raise ValueError('Resident error text cannot fit')
        values = struct.unpack('<512H', raw)
        for i in range(width):
            columns[(320-width)//2+i] |= values[i] << shift
    (project.parent/'atari_error.hex').write_text(''.join(f'{value:08x}\n' for value in columns), encoding='ascii', newline='\n')
    qsf = re.sub(r'^set_global_assignment -name (?:NUM_PARALLEL_PROCESSORS|ENABLE_SIGNALTAP).*\n', '', project.read_text(encoding='utf8'), flags=re.M)
    qsf += '\nset_global_assignment -name ENABLE_SIGNALTAP OFF\nset_global_assignment -name NUM_PARALLEL_PROCESSORS 4\n'
    for name in [*FILES, 'console_menu.sv', 'sega_menu_target.sv', 'error_pixels.sv']:
        kind = 'SYSTEMVERILOG_FILE' if name.endswith('.sv') else 'VERILOG_FILE'
        qsf += f'set_global_assignment -name {kind} core/{name}\n'
    project.write_text(qsf, encoding='utf8', newline='\n')
    proof = {'platform': platform, 'namespace': namespace, 'commit': commit, 'archive_sha256': archive_sha,
             'scope': 'Native engine; dedicated CellRAM1 CoverFlow; native shared APF nonvolatile slots',
             'menu_scaler_slot': 2 if platform == '2600' else 4,
             'menu_height': 288 if platform == '2600' else 274, 'hardware_acceptance': 'pending'}
    (out/'menu-preparation.json').write_text(json.dumps(proof, indent=2)+'\n', encoding='utf8')
    return out


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('platform', choices=PROFILES)
    for argument in ('archive', 'gba-source', 'out'):
        cli.add_argument('--'+argument, type=Path, required=True)
    args = cli.parse_args()
    print(prepare(args.platform, args.archive, args.gba_source, args.out))
