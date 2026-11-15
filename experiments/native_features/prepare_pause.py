#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Add the native pause/save-return controller and its resident Chinese UI."""
import argparse
import json
import re
import shutil
import struct
import sys

from prepare_consoles import ROOT, HERE, PROFILES, prepare as prepare_cheats, replace

sys.path.insert(0, str(ROOT/'tools'))
import build_library


LABELS = ('', '正在暂停', '暂停', '操作失败', '正在保存', '继续游戏', '保存并返回',
          '重试', '返回游戏', '返回游戏库')


def glyph_rom(path):
    rows = []
    for text in LABELS:
        line = [0]*128
        if text:
            width, columns, clipped, missing = build_library.columns(text, build_library.font())
            if width > 128 or clipped or missing:
                raise ValueError('Pause label does not fit: '+text)
            left = (128-width)//2
            line[left:left+width] = struct.unpack('<512H', columns)[:width]
        rows.extend(line)
    path.write_text(''.join(f'{value:04x}\n' for value in rows), encoding='ascii', newline='\n')


def pause_controller(source, slot, save_address):
    source = replace(source, 'input wire prepare_ready,load_ready,io_idle,',
        '''input wire prepare_ready,load_ready,io_idle,pause_allowed,
    output wire [2:0] pause_scene,''')
    source = replace(source, '    assign fault=state==ERROR;',
        '''    assign fault=state==ERROR;
    assign pause_scene = fault ? (game_bound ? 3'd4 : 3'd6) :
        state==PAUSE_WAIT ? 3'd1 :
        state==PAUSE ? (pause_option ? 3'd3 : 3'd2) :
        menu_pause && game_bound ? 3'd5 : 3'd0;

    task automatic resume_game;
        begin
            menu_pause<=0;
            menu_owned<=0;
            menu_show<=0;
            state<=RUN;
        end
    endtask

    task automatic return_to_library;
        begin
            cf_menu<=1;
            cf_pending<=0;
            cf_level_target<=0;
            cf_title_target<=0;
            game_bound<=0;
            menu_reset<=1;
            menu_pause<=0;
            menu_show<=0;
            timer<=0;
            state<=RECORD_REQ;
        end
    endtask''')
    start, end = source.index('            RUN:'), source.index('            QUIT_RTC_OPENED:')
    source = source[:start]+f'''            RUN:if(combo && !combo_prev && pause_allowed)begin
                    menu_pause<=1;menu_owned<=1;menu_show<=0;pause_option<=0;
                    timer<=0;state<=PAUSE_WAIT;
                end
            PAUSE_WAIT:if(press[5])resume_game();
                else if(io_idle)state<=PAUSE;
                else if(timer>=FRAME_TIMEOUT)fail(8'h50);
            PAUSE:if(press[5] || (press[4] && !pause_option))resume_game();
                else if(press[0]||press[1]||press[2]||press[3])pause_option<=~pause_option;
                else if(press[4])begin state<=QUIT_WAIT;timer<=0;end
            QUIT_WAIT:if(io_idle)begin
                    if(save_bytes==0)return_to_library();
                    else command(2,{slot},0,32'h{save_address:08x},save_bytes,QUIT_SAVE_WRITTEN);
                end else if(timer>=FRAME_TIMEOUT)fail(8'h51);
            QUIT_SAVE_WRITTEN:if(result!=0)fail(8'h53);
                else command(3,{slot},0,0,0,QUIT_SAVE_FLUSHED);
            QUIT_SAVE_FLUSHED:if(result!=0)fail(8'h54);else return_to_library();
'''+source[end:]
    # A timed-out APF transaction may still be reading the RAM. Keep it
    # quiescent until the host completes, even if the user presses A or B.
    source = replace(source, 'ERROR:if(press[5])begin', 'ERROR:if(t_done && press[5])begin')
    start, end = source.index('            ERROR:'), source.index('            HOME_OPEN:')
    error_branch = source[start:end].replace('else if(press[4])', 'else if(t_done && press[4])')
    error_branch = error_branch.replace(
        'if(game_bound)begin menu_owned<=0;menu_pause<=0;state<=RUN;end',
        'if(game_bound)resume_game();')
    return source[:start]+error_branch+source[end:]


def pause_view(source):
    source = replace(source, '    input wire enable,hold_gb,menu_active,vs,',
                     '    input wire enable,hold_gb,menu_active,vs,\n    input wire [2:0] pause_scene,')
    source = replace(source, 'reg [23:0] h_out;', '''wire pause_active;
wire [23:0] pause_rgb;
native_pause_pixels pause_screen (
    .clk(clk_vid),.pixel_ce(pixel_ce),.frame_start(hc==0 && vc==0),
    .x(x),.y(y),.scene(pause_scene),.active(pause_active),.rgb(pause_rgb));
reg [23:0] h_out;''')
    return replace(source, "hr_rgb<=s2_act ? h_out:24'h0;",
                   "hr_rgb<=s2_act ? (pause_active ? pause_rgb : h_out) : 24'h0;")


def patch(path, transform):
    path.write_text(transform(path.read_text(encoding='utf8')), encoding='utf8', newline='\n')


def include_renderer(dest, project, qsf, prefix):
    shutil.copy2(HERE/'pause_pixels.sv', dest/'native_pause_pixels.sv')
    glyph_rom(project/'native_pause.hex')
    with (project/qsf).open('a', encoding='utf8', newline='\n') as stream:
        stream.write(f'set_global_assignment -name SYSTEMVERILOG_FILE {prefix}/native_pause_pixels.sv\n')


def pce_pause(out):
    dest = out/'target/pocket'
    patch(dest/'console_menu.sv', lambda s: pause_controller(s, 10, 0x20000000))
    patch(dest/'coverflow_psram_view.sv', pause_view)

    def top(source):
        source = replace(source, '  wire ui_read,ui_write,ui_open,ui_flush,ui_done;',
            '''  wire [2:0] ui_pause_scene;
  wire ui_read,ui_write,ui_open,ui_flush,ui_done;
  wire pce_paused;
  reg [2:0] pce_pause_sync=0, pce_paused_sync=0, pce_owned_sync=3'b111;
  reg pce_input_block=1;
  always @(posedge clk_74a) pce_paused_sync<={pce_paused_sync[1:0],pce_paused};
  always @(posedge clk_sys_42_95) begin
      pce_pause_sync<={pce_pause_sync[1:0],ui_pause};
      pce_owned_sync<={pce_owned_sync[1:0],ui_owned};
      if(pce_owned_sync[2])pce_input_block<=1;
      else if(cont1_key_s[15:0]==0)pce_input_block<=0;
  end''')
        source = replace(source, '.enable(cf_menu && !ui_fault),.hold_gb(ui_owned),',
                         '.pause_scene(ui_pause_scene),.enable(cf_menu && !ui_fault),.hold_gb(ui_owned),')
        source = replace(source, '.io_idle(!ui_loading),',
            '.io_idle(!ui_loading && (!ui_bound || pce_paused_sync[2])),\n'
            "      .pause_allowed(1'b1),.pause_scene(ui_pause_scene),")
        source = replace(source, 'cf_menu || ui_fault}', 'cf_menu || ui_fault || ui_pause}')
        source = replace(source, '.native_cheat_enable(ui_cheat_arm_sync[2]),.core_reset(',
            '.native_cheat_enable(ui_cheat_arm_sync[2]),\n'
            '      .menu_pause(pce_pause_sync[2] && cf_video_owner),.menu_paused(pce_paused),.core_reset(')
        source, count = re.subn(r'(\.p[1-4]_(?:button|dpad)_\w+\()(cont[1-4]_key_s\[\d+\])\)',
                                r'\1\2 && !pce_input_block)', source)
        if count != 48:
            raise ValueError('PCE input bindings changed')
        return source

    patch(dest/'core_top.v', top)

    def wrapper(source):
        source = replace(source, '    input wire core_reset,',
            '    input wire core_reset,menu_pause,\n    output reg menu_paused=0,')
        source = replace(source, '  wire CPU_PAUSE_EN = 0;', '  wire cpu_halted;')
        source = replace(source, '.CPU_PAUSE_EN(CPU_PAUSE_EN),',
                         '.CPU_PAUSE_EN(menu_pause),.CPU_PAUSED(cpu_halted),')
        return replace(source, '  wire bram_wr;', '''  wire bram_wr;
  // Both BRAM ports must be quiet after the final CPU write is sampled.
  always @(posedge clk_sys_42_95)
      menu_paused <= menu_pause && cpu_halted && !bram_wr && !sd_wr &&
                     bram_init_counter==4'hf && !reset && !cart_download;''')

    patch(out/'rtl/main.sv', wrapper)
    patch(out/'rtl/pce/pce_top.vhd', lambda s: replace(replace(s,
        'CPU_PAUSE_EN: in  std_logic;', 'CPU_PAUSE_EN: in  std_logic;\n\t\tCPU_PAUSED: out std_logic;'),
        'ROM_RDY and not CPU_PAUSE_EN,',
        'ROM_RDY and not CPU_PAUSE_EN,\n\tPAUSE_REQ => CPU_PAUSE_EN,\n\tPAUSED => CPU_PAUSED,'))

    def cpu(source):
        source = replace(source, 'WAIT_N\t: in std_logic;',
            'WAIT_N\t: in std_logic;\n\t\tPAUSE_REQ : in std_logic;\n\t\tPAUSED : out std_logic;')
        source = replace(source, 'begin\n\n\t\n\tprocess(CLK, RST_N)',
            '''begin
    PAUSED <= '1' when PAUSE_REQ = '1' and RST_N = '1' and
        CPU_CE = '0' and CPU_CER = '0' and
        ((CPU_CLK_CNT = 5 and CPU_CS = '1') or
         (CPU_CLK_CNT = 23 and CPU_CS = '0')) else '0';

\tprocess(CLK, RST_N)''')
        return source

    patch(out/'rtl/pce/HUC6280/HUC6280.vhd', cpu)
    include_renderer(dest, out/'projects', 'pce_pocket.qsf', '../target/pocket')
    return out


def md_pause(out):
    dest = out/'src/fpga/core'
    patch(dest/'console_menu.sv', lambda s: pause_controller(s, 10, 0x60000000))
    patch(dest/'coverflow_psram_view.sv', pause_view)

    def top(source):
        source = replace(source, '  wire ui_read,ui_write,ui_open,ui_flush,ui_done;',
            '''  wire [2:0] ui_pause_scene;
  wire ui_read,ui_write,ui_open,ui_flush,ui_done;
  wire md_paused;
  reg [2:0] md_pause_sync=0, md_paused_sync=0, md_owned_sync=3'b111, md_svp_sync=0;
  reg md_input_block=1;
  always @(posedge clk_74a) begin
      md_paused_sync<={md_paused_sync[1:0],md_paused};
      md_svp_sync<={md_svp_sync[1:0],svp_quirk};
  end
  always @(posedge clk_sys) begin
      md_pause_sync<={md_pause_sync[1:0],ui_pause};
      md_owned_sync<={md_owned_sync[1:0],ui_owned};
      if(md_owned_sync[2])md_input_block<=1;
      else if(cont1_key_s[15:0]==0)md_input_block<=0;
  end''')
        source = replace(source, '.enable(cf_menu && !ui_fault),.hold_gb(ui_owned),',
                         '.pause_scene(ui_pause_scene),.enable(cf_menu && !ui_fault),.hold_gb(ui_owned),')
        source = replace(source, '.io_idle(!ui_loading),',
            '.io_idle(!ui_loading && (!ui_bound || md_paused_sync[2])),\n'
            '      .pause_allowed(!md_svp_sync[2]),.pause_scene(ui_pause_scene),')
        source = replace(source, 'cf_menu || ui_fault}', 'cf_menu || ui_fault || ui_pause}')
        source = replace(source, '.PAUSE_EN(cs_menu_pause_enable ? osnotify_inmenu_s : 0),',
            '.PAUSE_EN(cs_menu_pause_enable ? osnotify_inmenu_s : 0),\n'
            '    .MENU_PAUSE(md_pause_sync[2]),.MENU_PAUSED(md_paused),')
        for index in range(4):
            source = replace(source, f'assign joystick_{index} = {{',
                             f"assign joystick_{index} = md_input_block ? 16'd0 : {{")
        return source

    patch(dest/'core_top.sv', top)

    def system(source):
        source = replace(source, '\tinput         PAUSE_EN,',
            '\tinput         PAUSE_EN, MENU_PAUSE,\n\toutput reg    MENU_PAUSED=0,')
        source = replace(source, 'reg  [3:0] mstate;', '''reg  [3:0] mstate;
reg pause_cpu=0;
wire pause_request=MENU_PAUSE && !SVP_QUIRK;''')
        # Keep the divider phase as well as its output enables. Resuming
        # midway through a 68K phase can skip the bus release edge.
        source = replace(source, "\tend\n\telse begin\n\t\tZ80_CLKENn <= 0;",
            '''\tend else if (pause_cpu) begin
        Z80_CLKENn <= 0;
        Z80_CLKENp <= 0;
        PSG_CLKEN <= 0;
        M68K_CLKENp <= 0;
        M68K_CLKENn <= 0;
        FM_CLKEN <= 0;
    end else begin
\t\tZ80_CLKENn <= 0;''')
        source = replace(source, '/*if (rfs_pend) begin',
            '''// Once requested, finish the current transfer but admit no new one.
                if (pause_request) begin end
                else /*if (rfs_pend) begin''')
        source = replace(source, 'always @(posedge MCLK) begin\n\treg [15:0] data;',
            '''always @(posedge MCLK) begin
    pause_cpu <= !reset && pause_request && mstate==MBUS_IDLE;
    // SRAM port A is gated only after the last accepted MBUS operation.
    // STM95 writes are levels and may stay asserted without another SPI edge.
    MENU_PAUSED <= !reset && pause_request && pause_cpu && !LOADING && !BRAM_WE &&
                   !M68K_CLKENp && !M68K_CLKENn && !Z80_CLKENp && !Z80_CLKENn;
end

always @(posedge MCLK) begin
\treg [15:0] data;''')
        source = replace(source, '.wren_a(sram_wren & ~SVP_QUIRK),',
                         '.wren_a(sram_wren & ~SVP_QUIRK & ~pause_cpu),')
        return replace(source, 'assign BRAM_CHANGE = sram_wren;',
                       'assign BRAM_CHANGE = sram_wren && !pause_cpu;')

    patch(dest/'rtl/system.sv', system)
    include_renderer(dest, out/'src/fpga', 'ap_core.qsf', 'core')
    return out


def sfc_pause(out):
    dest = out/'target/pocket'
    patch(dest/'snes_menu.sv', lambda s: pause_controller(s, 10, 0x20000000))
    patch(dest/'coverflow_assoc_view.sv', pause_view)

    def top(source):
        source = replace(source, "  assign ui_paused_s=1'b0;",
            '''  wire [2:0] ui_pause_scene;
  wire sfc_menu_owns_video;
  reg sfc_input_block=1;
  always @(posedge clk_sys_21_48) begin
      if(ui_owned_s)sfc_input_block<=1;
      else if(cont1_key_s[15:0]==0)sfc_input_block<=0;
  end''')
        source = replace(source, '.enable(cf_menu && !ui_fault),.hold_gb(ui_owned),',
                         '.pause_scene(ui_pause_scene),.enable(cf_menu && !ui_fault),.hold_gb(ui_owned),')
        source = replace(source, 'cf_menu || ui_fault}', 'cf_menu || ui_fault || ui_pause}')
        source = replace(source, 'reg cf_video_owner=1;',
            '''reg cf_video_owner=1;
synch_3 sync_pause_video(cf_video_owner,sfc_menu_owns_video,clk_sys_21_48);''')
        source = replace(source, '.io_idle(!ui_loading && (!ui_bound || ui_paused)),',
            ".io_idle(!ui_loading && (!ui_bound || ui_paused)),\n      .pause_allowed(1'b1),.pause_scene(ui_pause_scene),")
        source = replace(source, '.native_cheat_enable(ui_cheat_arm_sync[2]),.core_reset(',
            '.native_cheat_enable(ui_cheat_arm_sync[2]),\n'
            '      .menu_pause(ui_pause_s && sfc_menu_owns_video),.menu_paused(ui_paused_s),.core_reset(')
        source, count = re.subn(r'(\.p[1-4]_(?:button|dpad)_\w+\()(cont[1-4]_key_s\[\d+\])\)',
                                r'\1\2 && !sfc_input_block)', source)
        if count != 48:
            raise ValueError('SFC input bindings changed')
        return source

    patch(dest/'core_top.sv', top)

    def wrapper(source):
        source = replace(source, '    input wire core_reset,',
            '    input wire core_reset,menu_pause,\n    output reg menu_paused=0,')
        source = replace(source, ') main (\n      .RESET_N(RESET_N),',
            ') main (\n      .RESET_N(RESET_N),.MENU_PAUSE(menu_pause),.MENU_STOPPED(base_stopped),')
        source = replace(source, '  wire wram_write_request =',
            '''  wire base_stopped;
  wire wram_busy;
  reg [2:0] stop_mem=0, mem_drained_sync=0;
  reg memory_drained=0;
  always @(posedge clk_mem_85_9) begin
      stop_mem <= {stop_mem[1:0],base_stopped};
      memory_drained <= stop_mem[2] && !wram_busy && !wram_write_mem[0] &&
                        !aram_new_request && !aram_busy;
  end
  always @(posedge clk_sys) begin
      mem_drained_sync <= {mem_drained_sync[1:0],memory_drained};
      menu_paused <= menu_pause && base_stopped && mem_drained_sync[2] &&
                     !clearing_ram && !cart_download && !save_download &&
                     !sd_wr && BSRAM_WE_N;
  end
  wire wram_write_request =''')
        return replace(source, ".read_en (clearing_ram ? 1'b0 : ~WRAM_CE_N & ~WRAM_OE_N),",
            ".read_en (!stop_mem[2] && !clearing_ram && ~WRAM_CE_N && ~WRAM_OE_N),\n"
            '      .busy(wram_busy),')

    patch(out/'rtl/mister_top/SNES.sv', wrapper)

    def main(source):
        source = replace(source, '\tinput             RESET_N,',
            '\tinput             RESET_N, MENU_PAUSE,\n\toutput reg        MENU_STOPPED=0,')
        source = replace(source, '.enable(1),', '.enable(!MENU_STOPPED),')
        return replace(source, 'wire  [15:0] SNES_ARAM_ADDR;', '''// Retire the current CPU or DMA bus cycle before holding the native engine.
always @(posedge MCLK) begin
    if(!RESET_N || !MENU_PAUSE) MENU_STOPPED<=0;
    else if(SYSCLKF_CE) MENU_STOPPED<=1;
end

wire  [15:0] SNES_ARAM_ADDR;''')

    patch(out/'rtl/upstream/main.v', main)

    def cpu(source):
        # Preserve phase for the first full bus cycle after resuming.
        source = replace(source, "elsif rising_edge(CLK) then\n\t\t\tDMA_CLK_CNT <= DMA_CLK_CNT + 1;",
            "elsif rising_edge(CLK) then\n\t\t  if ENABLE = '1' then\n\t\t\tDMA_CLK_CNT <= DMA_CLK_CNT + 1;")
        source = replace(source,
            "P65_RST_CNT <= P65_RST_CNT + 1;\n\t\t\tend if;\n\t\tend if;",
            "P65_RST_CNT <= P65_RST_CNT + 1;\n\t\t\tend if;\n\t\t  end if;\n\t\tend if;")
        return replace(source, "if DMA_ACTIVEr = '1' or ENABLE = '0' then",
            "if ENABLE = '0' then\n\t\t\t\tnull;\n\t\t\telsif DMA_ACTIVEr = '1' then")

    patch(out/'rtl/upstream/CPU.vhd', cpu)
    include_renderer(dest, out/'projects', 'snes_pocket.qsf', '../target/pocket')
    return out


def prepare(platform, archive, gba_source, out):
    out = prepare_cheats(platform, archive, gba_source, out)
    {'pce': pce_pause, 'genesis': md_pause, 'snes': sfc_pause}[platform](out)
    path = out/'native-feature-receipt.json'
    receipt = json.loads(path.read_text(encoding='utf8'))
    receipt['pause_save_return'] = True
    path.write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf8')
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('platform', choices=tuple(PROFILES))
    parser.add_argument('--archive', required=True)
    parser.add_argument('--gba-source')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    if args.platform != 'snes' and args.gba_source is None:
        parser.error('--gba-source is required for PCE and Genesis')
    print(prepare(args.platform, args.archive, args.gba_source, args.out))
