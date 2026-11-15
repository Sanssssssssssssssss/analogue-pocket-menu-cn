#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Reconnect native GBA Memories with cartridge identity checking."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

from prepare_nes import ROOT, HERE, load, replace


gba = load('gba_state_base', ROOT/'experiments/gba_coverflow/prepare.py')


def state_menu(source):
    source = replace(source, 'input wire prepare_ready,load_ready,io_idle,',
        'input wire prepare_ready,load_ready,io_idle,allow_pause,\n    output reg [79:0] state_game_id=0,')
    source = replace(source, 'else begin validate_rtc<=0;validate_index<=0;row_read_addr<=72;state<=VALIDATE_WAIT;end',
        'else begin state_game_id<=0;validate_rtc<=0;validate_index<=0;row_read_addr<=72;state<=VALIDATE_WAIT;end')
    source = replace(source, 'VALIDATE_BYTE:if(!path_byte_ok(validate_index,validate_byte,validate_rtc))',
        '''VALIDATE_BYTE:begin
                if(!validate_rtc && validate_index>=21 && validate_index<=40)
                    state_game_id<={state_game_id[75:0],validate_byte[3:0]+(validate_byte[6] ? 4'd9 : 4'd0)};
                if(!path_byte_ok(validate_index,validate_byte,validate_rtc))''')
    source = replace(source, 'else begin validate_index<=validate_index+1\'b1;state<=VALIDATE_ADDR;end\n            FRAME_BLANK:',
        'else begin validate_index<=validate_index+1\'b1;state<=VALIDATE_ADDR;end\n            end\n            FRAME_BLANK:')
    return replace(source, 'RUN:if(combo && !combo_prev)', 'RUN:if(combo && !combo_prev && allow_pause)')


def prepare(source, out, area=False):
    source = Path(source).resolve()
    out = gba.prepare(source, out)
    core = out/'src/fpga/core'
    menu = core/'gba_menu.sv'
    menu.write_text(state_menu(menu.read_text(encoding='utf8')), encoding='utf8', newline='\n')

    top = core/'core_top.sv'
    text = top.read_text(encoding='utf8')
    original = (source/'src/fpga/core/core_top.sv').read_text(encoding='utf8')
    instance = re.search(r'save_state_controller ss_ctrl \(.*?\n\);', original, re.S)[0]
    for old, new in (
        ('( bridge_wr )', '( state_payload_wr )'), ('( bridge_rd )', '( state_payload_rd )'),
        ('( bridge_addr )', '( state_payload_addr )'), ('( savestate_load )', '( state_load_request )'),
        ('( savestate_start )', '( state_start_request )'),
        ('( savestate_load_ack )', '( state_load_ack )'), ('( savestate_load_err )', '( state_load_err )'),
        ('( savestate_start_ack )', '( state_start_ack )'), ('( savestate_start_err )', '( state_start_err )'),
    ):
        instance = replace(instance, old, new)
    instance = replace(instance, '.clk_sys              ( clk_sys ),', '''.clk_sys              ( clk_sys ),
    .reset_staging        ( !savestate_supported || state_reset_staging ),
    .discard_capture      ( state_discard ),
    .capture_progress     ( state_capture_progress ),
    .staging_clear        ( state_staging_clear ),
    .transport_active     ( state_transport_active ),''')
    block = '''wire [79:0] ui_state_game_id;
wire state_load_valid,state_payload_wr,state_payload_rd,state_envelope_read;
wire [31:0] state_payload_addr,state_envelope_data;
wire state_reset_staging,state_receiving,state_transport_active;
wire state_staging_clear,state_capture_progress;
wire state_start_ack,state_start_err,state_load_ack,state_load_err;
reg state_start_granted=0,state_start_rejected=0;
wire state_start_request=savestate_start && state_start_granted;
wire state_load_request=savestate_load && state_load_valid;
reg state_capturing=0,state_capture_seen=0,state_discard=0;
reg [28:0] state_capture_timer=0;
wire state_idle=!state_capturing && !state_transport_active && !state_receiving &&
                !state_reset_staging && !state_staging_clear;
always @(posedge clk_74a) begin
    if(!savestate_supported)begin
        state_start_granted<=0;state_start_rejected<=savestate_start;
    end else begin
        if(!savestate_start)begin state_start_granted<=0;state_start_rejected<=0;end
        else if(!state_start_granted && !state_start_rejected)begin
            if(state_idle && !savestate_load)begin
                state_start_granted<=1;state_capturing<=1;state_capture_seen<=0;
                state_capture_timer<=0;state_discard<=0;
            end else state_start_rejected<=1;
        end
    end
    if(state_capturing)begin
        if(state_transport_active)state_capture_seen<=1;
        if(state_capture_seen && !state_transport_active)begin state_capturing<=0;state_discard<=0;end
        else if(!savestate_supported || state_capture_timer>=29'd445500000)state_discard<=1;
        else if(state_capture_progress)state_capture_timer<=0;
        else state_capture_timer<=state_capture_timer+1'b1;
    end
end
assign savestate_start_ack=state_start_ack || state_start_rejected;
assign savestate_start_err=state_start_err || state_discard || state_start_rejected;
assign savestate_load_ack=state_load_ack || (savestate_load && !state_load_valid);
assign savestate_load_err=state_load_err || (savestate_load && !state_load_valid);
gba_state_guard state_identity (
    .clk(clk_74a),.enabled(savestate_supported),.capture_active(state_capturing),
    .restore_active(savestate_load_busy),.staging_clear(state_staging_clear),.game_id(ui_state_game_id),
    .bridge_wr(bridge_wr),.bridge_rd(bridge_rd),.bridge_endian_little(bridge_endian_little),
    .bridge_addr(bridge_addr),.bridge_wr_data(bridge_wr_data),
    .load_request(savestate_load),.load_valid(state_load_valid),
    .payload_wr(state_payload_wr),.payload_rd(state_payload_rd),.payload_addr(state_payload_addr),
    .envelope_data(state_envelope_data),.envelope_read(state_envelope_read),
    .reset_staging(state_reset_staging),.receiving(state_receiving));
'''
    text, count = re.subn(r'// Pocket Lab 2026-10-31: APF memories/sleep are disabled for this core\..*?assign savestate_load_err=1;',
                          lambda _: block+instance, text, count=1, flags=re.S)
    if count != 1:
        raise ValueError('Expected the inactive Memories adapter')
    text = replace(text, 'wire            savestate_supported = 0; // per-game APF memory identity is not adapted yet',
        'wire            savestate_supported = reset_n && ui_bound && !ui_owned;')
    text = replace(text, "32'h60D18;", "32'h60D28;", count=2)
    text = replace(text, 'bridge_rd_data <= ss_bridge_rd_data;',
        'bridge_rd_data <= state_envelope_read ? state_envelope_data : ss_bridge_rd_data;')
    text = replace(text, '.io_idle(ui_io_idle_b),.save_capacity(ui_capacity),',
        '.io_idle(ui_io_idle_b),.save_capacity(ui_capacity),\n'
        '    .allow_pause(state_idle),.state_game_id(ui_state_game_id),')
    text = replace(text, '.sleep_external      ( ss_loading | ui_pause_s | osnotify_s ),',
        '.sleep_external      ( ss_loading | ui_pause_s | (osnotify_s && !capture_active_s) ),')
    text = replace(text, 'gba_top #(\n',
        'wire capture_active_s;\nsynch_3 capture_active_sync(state_capturing,capture_active_s,clk_sys);\ngba_top #(\n')
    # The 0x40 state payload shares the top nibble with covers at 0x42.
    text = replace(text, '''cf_art_input(
    .clk_74a(clk_74a),.clk_memory(clk_sys),.bridge_wr(bridge_wr),''',
        '''cf_art_input(
    .clk_74a(clk_74a),.clk_memory(clk_sys),.bridge_wr(bridge_wr && bridge_addr[31:24]==8'h42),''')
    top.write_text(text, encoding='utf8', newline='\n')

    state = core/'save_state_controller.sv'
    text = state.read_text(encoding='utf8')
    text = replace(text, '    input wire clk_sys,',
        '    input wire clk_sys,\n    input wire reset_staging,discard_capture,\n'
        '    output wire transport_active,staging_clear,capture_progress,')
    text = replace(text, '    if (bridge_rd && ~prev_bridge_rd && bridge_addr[31:28] == 4\'h4) begin',
        '''    if(discard_capture && save_read_state==SAVE_RD_NONE && !fifo_save_rd_empty)begin
        save_read_state<=SAVE_RD_REQ;
        fifo_save_read_req<=1;
    end else if (bridge_rd && ~prev_bridge_rd && bridge_addr[31:28] == 4'h4) begin''')
    text = replace(text, "reg  [20:0] last_unloader_addr = 21'hFFFF;", """reg  [20:0] last_unloader_addr = 21'hFFFF;
reg last_start=0;
assign capture_progress=fifo_save_read_req && !discard_capture;
always @(posedge clk_74a) last_start<=savestate_start;""")
    text = replace(text, '    endcase\nend\n\n// ============================================================\n// Main State Machine',
        """    endcase
    if(savestate_start && !last_start)begin
        last_unloader_addr<=21'hffff;save_read_state<=SAVE_RD_NONE;fifo_save_read_req<=0;
    end
end

// ============================================================
// Main State Machine""")
    text = replace(text, 'assign ss_loading = save_state_loading;',
        '''assign ss_loading = save_state_loading;
wire reset_staging_s;
reg stage_reset_prev=0;
synch_3 stage_reset_sync(reset_staging,reset_staging_s,clk_sys);
always @(posedge clk_sys) stage_reset_prev<=reset_staging_s;
synch_3 transport_sync(state!=S_NONE,transport_active,clk_74a);
synch_3 clear_sync(reset_staging_s || fifo_clr_count!=0 || fifo_settle_count!=0 || fifo_load_clr,
                   staging_clear,clk_74a);''')
    text = replace(text, '&& fifo_settle_count == 0) begin',
        '&& fifo_settle_count == 0 && fifo_clr_count==0 && !fifo_load_clr && !reset_staging_s) begin')
    text = replace(text, '    endcase\nend\n\nendmodule', '''    endcase
    if(reset_staging_s && !stage_reset_prev &&
       (state==S_NONE || (state>=S_STAGE_FIFO_RD && state<S_LOAD_TRIGGER)))begin
        // No part of this incomplete stream has been applied to the game.
        state<=S_NONE;save_state_loading<=0;staging_complete<=0;
        savestate_load_cmd<=0;savestate_load_ack<=0;savestate_load_busy<=0;
        fifo_load_read_req<=0;fifo_load_clr<=1;fifo_clr_count<=4'd15;
    end
end

endmodule''')
    state.write_text(text, encoding='utf8', newline='\n')
    shutil.copy2(HERE/'gba_state_guard.sv', core/'gba_state_guard.sv')
    qsf = out/'src/fpga/build/ap_core.qsf'
    if area:
        value = qsf.read_text(encoding='utf8')
        value = replace(value, 'OPTIMIZATION_MODE "AGGRESSIVE PERFORMANCE"', 'OPTIMIZATION_MODE "AGGRESSIVE AREA"')
        value = replace(value, 'OPTIMIZATION_TECHNIQUE SPEED', 'OPTIMIZATION_TECHNIQUE AREA')
        value = replace(value, 'PHYSICAL_SYNTHESIS_COMBO_LOGIC_FOR_AREA OFF', 'PHYSICAL_SYNTHESIS_COMBO_LOGIC_FOR_AREA ON')
        qsf.write_text(value, encoding='utf8', newline='\n')
    with qsf.open('a', encoding='utf8', newline='\n') as stream:
        stream.write('\nset_global_assignment -name SYSTEMVERILOG_FILE ../core/gba_state_guard.sv\n')
    result = {
        'scope': 'GBA Memories for the currently bound exact game; no firmware sleep flag',
        'state_bytes': 396584, 'state_identity': '80-bit prefix of local ROM SHA-256, ABI 1',
        'hardware_acceptance': 'pending',
        'files': {p.relative_to(out).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in (menu, top, state, core/'gba_state_guard.sv')}
    }
    (out/'native-state-receipt.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf8')
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--area', action='store_true')
    args = parser.parse_args()
    print(prepare(args.source, args.out, args.area))
