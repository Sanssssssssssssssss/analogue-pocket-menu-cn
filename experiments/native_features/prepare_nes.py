#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Add verified read-replacement transport to the independent native NES menu."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = load('nes_features_base', ROOT/'experiments/nes_coverflow/prepare.py')
replace = base.replace


def controller(source, namespace='neslab', header_word=4, bridge_base=0x90000000, state_base=53):
    # The console carousel already reserves state 53 for its art commit.
    # Keep each caller's new states outside its existing state allocation.
    import re
    occupied={int(n) for n in re.findall(r'^\s*(\d+)\s*:',source,re.M)}
    if any(n in occupied for n in range(state_base,state_base+6)):
        raise ValueError('Native cheat states overlap the existing controller')
    source = replace(source, 'input wire [31:0] save_capacity,', '''input wire [31:0] save_capacity,
    input wire cheat_ready,cheat_fault,cheat_active_ack,
    output reg cheat_loading=0,cheat_armed=0,''')
    source = replace(source, 'reg [31:0] atlas_stride=0;', '''reg [31:0] atlas_stride=0;
    reg [31:0] cheat_bytes=0;
    localparam CHEAT_BEGIN=CHEAT_STATE_BASE,CHEAT_OPENED=CHEAT_STATE_BASE+1,CHEAT_READ=CHEAT_STATE_BASE+2,CHEAT_DRAIN=CHEAT_STATE_BASE+3,CHEAT_FINISH=CHEAT_STATE_BASE+4,CHEAT_ARMED=CHEAT_STATE_BASE+5;'''.replace('CHEAT_STATE_BASE',str(state_base)))
    source = replace(source, '0:entry_magic<=normalized;1:entry_flags<=normalized;2:rom_bytes<=normalized;',
        f'0:entry_magic<=normalized;1:entry_flags<=normalized;2:rom_bytes<=normalized;{header_word}:cheat_bytes<=normalized;')
    source = replace(source, 'cf_invalidate<=0;cf_commit<=0;cf_go<=0;cf_generation<=0;',
        'cf_invalidate<=0;cf_commit<=0;cf_go<=0;cf_generation<=0;cheat_loading<=0;cheat_armed<=0;')
    source = replace(source, 'cf_title_width>500 || cf_subtitle_width>300',
        'cf_title_width>500 || cf_subtitle_width>300 || (cheat_bytes!=0 && (cheat_bytes<64 || cheat_bytes>304 || cheat_bytes[3:0]!=0))')
    prefix = f'/Assets/{namespace}/cheat/'.encode('ascii')
    if len(prefix) != 21:
        raise ValueError('Expected a six-letter native namespace')
    function = '    function automatic [7:0] cheat_prefix(input [4:0] n);\n        case(n)\n'
    for i, value in enumerate(prefix):
        function += f"            {i}:cheat_prefix=8'h{value:02x};\n"
    function += '            default:cheat_prefix=0;\n        endcase\n    endfunction\n'
    source = replace(source, '    function automatic path_byte_ok', function+'    function automatic path_byte_ok')
    source = replace(source, 'path_byte_ok=c==save_prefix(n[4:0]);',
        'path_byte_ok=c==(rtc ? cheat_prefix(n[4:0]):save_prefix(n[4:0]));')
    for index, old, new in ((42,'r','c'),(43,'t','h'),(44,'c','t')):
        source = replace(source, f'{index}:path_byte_ok=c==(rtc ? "{old}"', f'{index}:path_byte_ok=c==(rtc ? "{new}"')
    source = replace(source, 'else begin cf_menu<=0;menu_reset<=1;menu_pause<=0;game_bound<=0;timer<=0;state<=ROM_START;end',
        'else begin cheat_loading<=0;cheat_armed<=0;cf_menu<=0;menu_reset<=1;menu_pause<=0;game_bound<=0;timer<=0;state<=ROM_START;end')
    launch = 'game_bound<=1;menu_reset<=0;menu_owned<=0;menu_pause<=0;menu_show<=0;state<=RUN;'
    source = replace(source, launch, 'if(cheat_bytes==0)begin '+launch+'''end
                    else begin timer<=0;state<=CHEAT_BEGIN;end''')
    stages = '''            CHEAT_BEGIN:if(io_idle)begin
                    path_select<=2;root_path<=0;open_flags<=0;open_size<=0;command(1,12,0,PARAM,0,CHEAT_OPENED);
                end else if(timer>=TIMEOUT)fail(8'h80);
            CHEAT_OPENED:if(result!=0)fail(8'h81);else begin
                    cheat_loading<=1;command(0,12,0,32'h90000000,cheat_bytes,CHEAT_READ);
                end
            CHEAT_READ:if(result!=0)begin cheat_loading<=0;fail(8'h82);end
                else begin timer<=0;state<=CHEAT_DRAIN;end
            CHEAT_DRAIN:if(timer>=SETTLE_CYCLES)begin cheat_loading<=0;timer<=0;state<=CHEAT_FINISH;end
            CHEAT_FINISH:if(cheat_fault)fail(8'h83);
                else if(cheat_ready)begin cheat_armed<=1;timer<=0;state<=CHEAT_ARMED;end
                else if(timer>=TIMEOUT)fail(8'h84);
            CHEAT_ARMED:if(cheat_active_ack)begin '''+launch+'''end
                else if(timer>=TIMEOUT)fail(8'h85);
            RUN:'''
    stages = stages.replace("32'h90000000", f"32'h{bridge_base:08x}")
    source = replace(source, '            RUN:', stages)
    return source


def prepare(archive, out):
    out = base.prepare(archive, out)
    dest = out/'target/pocket'
    menu = dest/'nes_menu.sv'
    menu.write_text(controller(menu.read_text(encoding='utf8')), encoding='utf8', newline='\n')
    top = dest/'core_top.v'
    text = top.read_text(encoding='utf8')
    text = replace(text, '  nes_menu menu (', '''  wire ui_cheat_loading,ui_cheat_armed,ui_cheat_armed_s,ui_cheat_ready,ui_cheat_fault;
  wire [128:0] ui_cheat_code;
  wire ui_cheat_reset;
  reg [2:0] ui_cheat_active_sync=0;
  always @(posedge clk_74a) ui_cheat_active_sync<={ui_cheat_active_sync[1:0],ui_cheat_armed_s};
  synch_3 sync_cheat_arm(ui_cheat_armed,ui_cheat_armed_s,clk_ppu_21_47);
  native_cheat_loader #(.PLATFORM(16'd3)) game_cheats(
      .clk(clk_74a),.clk_core(clk_ppu_21_47),.reset(!reset_n || ui_new),.receiving(ui_cheat_loading),
      .bridge_wr(bridge_wr),.bridge_endian_little(bridge_endian_little),.bridge_addr(bridge_addr),.bridge_wr_data(bridge_wr_data),
      .ready(ui_cheat_ready),.fault(ui_cheat_fault),.code(ui_cheat_code),.code_reset(ui_cheat_reset));
  nes_menu menu (''')
    text = replace(text, '.clk(clk_74a),.ready(reset_n && pll_core_locked),.buttons(cont1_key),',
        '''.clk(clk_74a),.ready(reset_n && pll_core_locked),.buttons(cont1_key),
      .cheat_ready(ui_cheat_ready),.cheat_fault(ui_cheat_fault),.cheat_loading(ui_cheat_loading),.cheat_armed(ui_cheat_armed),
      .cheat_active_ack(ui_cheat_active_sync[2]),''')
    text = replace(text, '.menu_pause(ui_pause_s),.menu_paused(ui_paused_s),',
        '.menu_pause(ui_pause_s),.menu_paused(ui_paused_s),\n      .gg_code(ui_cheat_code),.gg_reset(ui_cheat_reset),.gg_enable(ui_cheat_armed_s),')
    top.write_text(text, encoding='utf8', newline='\n')
    native = out/'rtl/nes_top.sv'
    text = native.read_text(encoding='utf8')
    text = replace(text, 'input wire external_reset,',
        'input wire external_reset,\n    input wire [128:0] gg_code,\n    input wire gg_reset,gg_enable,')
    text = replace(text, '  wire gg_code = 0;\n  wire gg_reset = 0;\n  wire gg_avail = 0;', '  wire gg_avail;')
    text = replace(text, '.gg            (status[20]),', '.gg            (~gg_enable),')
    text = replace(text, '.gg_reset      (gg_reset && loader_clk && !ioctl_addr),', '.gg_reset      (gg_reset),')
    # Start/ROM download already holds the CPU in reset before RAM clear starts.
    # Release it from the CPU clock domain after the last memory write drains.
    text = replace(text,
        '  wire reset_nes = ~init_reset_n || download_reset || loader_fail || hold_reset || external_reset || clearing_ram;',
        '''  reg [1:0] clearing_cpu=2'b11;
  always @(posedge clk_ppu_21_47) clearing_cpu <= {clearing_cpu[0],clearing_ram};
  wire reset_nes = ~init_reset_n || download_reset || loader_fail || hold_reset || external_reset || clearing_cpu[1];''')
    native.write_text(text, encoding='utf8', newline='\n')
    core = out/'rtl/upstream/nes.v'
    text = replace(core.read_text(encoding='utf8'), 'CODES codes (', 'CODES #(.MAX_CODES(16)) codes (')
    core.write_text(text, encoding='utf8', newline='\n')
    shutil.copy2(HERE/'cheat_loader.sv', dest/'native_cheat_loader.sv')
    with (dest/'core.qip').open('a', encoding='utf8', newline='\n') as stream:
        stream.write('set_global_assignment -name SYSTEMVERILOG_FILE [file join $::quartus(qip_path) "native_cheat_loader.sv"]\n')
    (out/'native-feature-receipt.json').write_text(json.dumps({'features':['PLCH1'], 'platform':'nes',
        'max_read_replacements':16,'scope':'ROM read replacements, not arbitrary RAM-write or encrypted codes',
        'hardware_acceptance':'pending'}, indent=2)+'\n', encoding='utf8')
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    print(prepare(args.archive, args.out))
