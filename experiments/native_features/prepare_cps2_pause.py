#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Add a pause and a drained EEPROM save to the pinned CPS2 CoverFlow tree."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import shutil

from prepare_pause import ROOT, patch, replace, pause_controller, pause_view, include_renderer
from build_library import sha
from install import safe_path

BASE_MANIFEST = '4c82f1bff888de182b117375c6bef47646c8de58a69ad34feba1db0081429da5'
PROJECT = Path('cores/cps2/pocket')
APF = Path('modules/jtframe/target/pocket/hdl')
INIT_INPUTS = {
    'cores/cps2/pocket/logodata.hex': 'b6044b73d9420085e625a2384ee9c3eb5c4f42a5d0095181998a1cf1d82d570e',
    'cores/cps2/pocket/logomap.hex': '1a68b5e14840356bec1ab437ea53d6cdd856115c3c6d4608d1e04f3d94d2d6e4',
    'cores/cps2/pocket/font0.hex': '0446401d8e7ed1730c2f2b820b8bc484666f8e877470a3ff7de4fa62295948f9',
    'cores/cps2/hdl/pal_lut.hex': '1e767155d49e51b04cf2bcc07e8f7a5eebea4cc86d71421351a4d95c8ee2524a',
}


def prepare(source, out, init_inputs):
    source, out, init_inputs = (Path(path).resolve() for path in (source, out, init_inputs))
    if out.exists() or not out.is_relative_to(ROOT/'.work') or out.is_relative_to(source):
        raise ValueError('Choose a fresh .work directory outside the input')
    manifest = source/'source-manifest.json'
    if sha(manifest) != BASE_MANIFEST:
        raise ValueError('Expected the reviewed CPS2 corresponding source manifest')
    base = source/'projects/CPS2'
    files = json.loads(manifest.read_text(encoding='utf8'))['systems']['CPS2']['files']
    for rel, row in files.items():
        if sha(safe_path(base, rel)) != row['sha256']:
            raise ValueError('CPS2 source checksum differs: '+rel)
    inputs = {rel: safe_path(base, rel) for rel in files}
    for rel, digest in INIT_INPUTS.items():
        path = safe_path(init_inputs, rel)
        if rel in inputs or sha(path) != digest:
            raise ValueError('CPS2 memory initialization differs: '+rel)
        inputs[rel] = path
    for rel, path in inputs.items():
        dest = safe_path(out, rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
    view = out/PROJECT/'coverflow'
    # The pinned source bundle predates the APF busy-status handshake repair.
    # Check its exact old input before replacing it with the reviewed adapter.
    target = view/'cps2_target.sv'
    if sha(target) != 'c2a3bc0854c16c20b315ce00fd36d0f2e55ab3f54f0797787a77f9ead0d95cc4':
        raise ValueError('CPS2 target bridge differs from the pinned pre-repair source')
    shutil.copy2(ROOT/'experiments/console_coverflow/cps2_target.sv', target)
    patch(view/'cps2_menu.sv', lambda s: pause_controller(s, 2, 0))
    patch(view/'coverflow_psram_view.sv', lambda s: replace(pause_view(s), '.x(x),', ".x(x-9'd32),"))

    def base_apf(source):
        source = replace(source, '    input           clk48, menu_clk,',
            '    input           clk48, menu_clk,\n    input wire lab_paused,\n'
            '    output wire lab_pause,lab_block_keys,')
        source = replace(source, '.snd_left(ui_bound ? snd_left',
                         '.snd_left(ui_bound && !ui_owned ? snd_left')
        source = replace(source, '.snd_right(ui_bound ? snd_right',
                         '.snd_right(ui_bound && !ui_owned ? snd_right')
        source = replace(source, 'wire ui_owned,ui_pause,ui_frame_request;', '''wire ui_owned,ui_pause,ui_frame_request;
wire [2:0] ui_pause_scene;
reg [2:0] pause_sync=0;
reg block_keys=1;
always @(posedge clk_sys) pause_sync<={pause_sync[1:0],ui_pause};
always @(posedge clk_rom) begin
    if(ui_owned)block_keys<=1;
    else if(cont1_key==0)block_keys<=0;
end
assign lab_block_keys=block_keys;
assign lab_pause=pause_sync[2] && cf_video_owner;''')
        source = replace(source, 'cf_game_ready[1:0],ui_bound}',
                         'cf_game_ready[1:0],ui_bound && !ui_pause && !ui_fault}')
        source = replace(source, '.enable(cf_menu && !ui_fault),.hold_gb(ui_owned),',
                         '.pause_scene(ui_pause_scene),.enable(cf_menu && !ui_fault),.hold_gb(ui_owned),')
        return replace(source, '.io_idle(!ui_loading),.save_capacity',
            '.io_idle(!ui_loading && (!ui_bound || lab_paused)),\n'
            "    .pause_allowed(1'b1),.pause_scene(ui_pause_scene),.save_capacity")

    patch(out/APF/'jtframe_pocket_base.sv', base_apf)

    def frame(source):
        source = replace(source, '    input               clk_pico, menu_clk,',
            '    input               clk_pico, menu_clk,\n    input wire lab_paused,\n'
            '    output wire lab_block_keys,')
        source = replace(source, ') u_base(\n',
            ') u_base(\n    .lab_pause(lab_pause),.lab_paused(lab_paused),.lab_block_keys(lab_block_keys),\n')
        source = replace(source, 'jtframe_board #(\n', 'wire lab_pause;\njtframe_board #(\n')
        return replace(source, ".capture_pause  ( 1'b0            ),", '.capture_pause  ( lab_pause       ),')

    patch(out/APF/'jtframe_pocket.v', frame)
    patch(out/APF/'jtframe_pocket_top.v', lambda s: replace(
        replace(s, 'wire        dip_pause, dip_flip, dip_test;',
                'wire        dip_pause, dip_flip, dip_test;\nwire lab_paused,lab_block_keys;'),
        'u_frame(\n', 'u_frame(\n    .lab_paused(lab_paused),.lab_block_keys(lab_block_keys),\n'))
    patch(out/'modules/jtframe/hdl/inc/jtframe_game_instance.v', lambda s: replace(s, 'u_game(\n',
        'u_game(\n    .lab_paused(lab_paused),.lab_block_keys(lab_block_keys),\n'))

    def game(source):
        source = replace(source, 'module jtcps2_game(\n',
            'module jtcps2_game(\n    input wire lab_block_keys,\n    output reg lab_paused=0,\n')
        source = replace(source, 'wire        sclk, sdi, sdo, scs;', '''wire        sclk, sdi, sdo, scs;
wire halt_idle, nv_quiet;
reg [2:0] halt_sync=0;
always @(posedge clk) begin
    halt_sync <= {halt_sync[1:0],halt_idle};
    lab_paused <= !rst_game && halt_sync[2] && nv_quiet;
end''')
        source = replace(source, 'jtcps2_main u_main(\n',
            'jtcps2_main u_main(\n    .halt_idle(halt_idle),\n')
        for signal in ('joystick1', 'joystick2', 'joystick3', 'joystick4', 'coin', 'cab_1p'):
            released = "10'h3ff" if signal.startswith('joystick') else "4'hf"
            source, count = re.subn(rf'(\.{signal}\s*\(\s*)({signal})(\s*\),)',
                                    rf"\g<1>lab_block_keys ? {released} : \g<2>\3", source, count=1)
            if count != 1:
                raise ValueError('CPS2 player binding changed: '+signal)
        return replace(source, '.dump_flag      (               ),',
                       '.dump_flag      (               ),\n    .nv_quiet(nv_quiet),')

    patch(out/'cores/cps2/hdl/jtcps2_game.v', game)
    patch(out/'cores/cps2/hdl/jtcps2_main.v', lambda s: replace(
        replace(s, '    output             cpu_cen,', '    output             cpu_cen, halt_idle,'),
        'jtframe_m68k u_cpu(\n', 'jtframe_m68k u_cpu(\n    .halt_idle(halt_idle),\n'))
    patch(out/'modules/jtframe/hdl/cpu/jtframe_m68k.v', lambda s: replace(
        replace(s, '    output  RESETn,', '    output  RESETn, halt_idle,'),
        '.oHALTEDn   (             ),', '.oHALTEDn   (             ),\n    .oHALT_IDLE(halt_idle),'))

    def fx68k(source):
        old = 'output oRESETn, output oHALTEDn,'
        # Only the primary fx68k module is used by this project.
        start = source.index(old)
        source = source[:start]+source[start:].replace(old, old+' output reg oHALT_IDLE=0,', 1)
        source = replace(source, 'busControl busControl(', 'wire lab_bus_idle;\n\tbusControl busControl(.lab_bus_idle(lab_bus_idle), ')
        source = replace(source, 'output busStarting,', 'output busStarting, output lab_bus_idle,')
        source = replace(source, 'assign busStarting = (busPhase == S0);',
            '''assign busStarting = (busPhase == S0);
    // Released pins during S0 do not mean the bus is idle. An accepted
    // transaction can still assert its strobes in the following phase.
    assign lab_bus_idle = busPhase==SIDLE && !canStart && ASn && LDSn && UDSn;''')
        return replace(source, 'assign oHALTEDn = !oHalted;', '''assign oHALTEDn = !oHalted;
    always_ff @(posedge clk)
        oHALT_IDLE <= !pwrUp && !extReset && !HALTn && !Halti && lab_bus_idle && BGACKn;''')

    patch(out/'modules/fx68k/hdl/fx68k.sv', fx68k)
    patch(out/'cores/cps1/hdl/jtcps1_sdram.v', lambda s: replace(
        replace(s, '    output          dump_flag\n', '    output          dump_flag, nv_quiet\n'),
        '.dump_flag  ( dump_flag ),', '.dump_flag  ( dump_flag ),\n    .nv_quiet(nv_quiet),'))

    def eeprom_wrapper(source):
        source = replace(source, '    output          dump_flag   // There was a write',
            '    output          dump_flag, nv_quiet')
        source = replace(source, '    wire [AW-1:0] dx_addr;',
            '    wire chip_quiet;\n    assign nv_quiet=chip_quiet && !dump_we && !dx_we;\n'
            '    wire [AW-1:0] dx_addr;')
        return replace(source, '.dump_flag  ( dump_flag )', '.dump_flag  ( dump_flag ),.nv_quiet(chip_quiet)')

    patch(out/'modules/jteeprom/hdl/jt9346_16b8b.v', eeprom_wrapper)
    patch(out/'modules/jteeprom/hdl/jt9346.v', lambda s: replace(replace(s,
        '    output reg      dump_flag   // There was a write',
        '    output reg      dump_flag,\n    output wire     nv_quiet'),
        'always @(posedge clk) last_sclk <= sclk;',
        'assign nv_quiet=!rst && !mem_we && st!=WRITE_ALL && last_sclk==sclk;\n'
        'always @(posedge clk) last_sclk <= sclk;'))
    include_renderer(view, out/PROJECT, 'jtcps2.qsf', 'coverflow')
    module = ROOT/'experiments/cps1_coverflow/nv_bridge.py'
    spec = importlib.util.spec_from_file_location('cps2_native_nv_bridge', module)
    native_nv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(native_nv)
    native_nv.patch(out, 'cps2')
    module = ROOT/'experiments/cps1_coverflow/parameter_bridge.py'
    spec = importlib.util.spec_from_file_location('cps2_parameter_bridge', module)
    parameters = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parameters)
    parameters.patch(out, 'cps2')
    module = ROOT/'experiments/cps1_coverflow/config_bridge.py'
    spec = importlib.util.spec_from_file_location('cps2_config_bridge', module)
    configuration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(configuration)
    configuration.patch(out, 'cps2')
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--init-inputs', required=True)
    args = parser.parse_args()
    print(prepare(args.source, args.out, args.init_inputs))
