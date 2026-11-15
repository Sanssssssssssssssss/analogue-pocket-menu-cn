#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate an isolated GB/GBC candidate from the frozen accepted source."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def add_cheats(out, replace):
    picker = 'core/cover_picker.sv'
    replace(picker, "parameter FAV_SLOT    = 16'd104,", """parameter FAV_SLOT    = 16'd104,
    parameter CHEAT_SLOT  = 16'd105,""")
    replace(picker, '    input  wire        ss_start_ok,', '''    output reg         cheat_receiving=0,cheat_armed=0,
    input  wire        cheat_ready,cheat_fault,cheat_active_ack,
    input  wire        ss_start_ok,''')
    replace(picker, 'localparam [1:0] PK_ROM = 0, PK_SAV = 1, PK_SUS = 2;',
        """localparam [1:0] PK_ROM = 0, PK_SAV = 1, PK_SUS = 2, PK_CHEAT = 3;
localparam [6:0] S_CHEAT_LEN=20,S_CHEAT_OPEN=21,S_CHEAT_VALIDATE=22,S_CHEAT_ARM=25,S_CHEAT_START=26;
localparam [31:0] CHEAT_BRIDGE=32'ha0000000;
reg [15:0] cheat_bytes=0;""")
    replace(picker, 'wire [31:0] pstruct = paths0 + {11\'d0, pslot, 8\'d0};', '''wire [12:0] cheat_pslot={1'b0,count,1'b0}+{2'd0,count}+{2'd0,path_idx}+13'd2;
wire [31:0] pstruct = paths0 + {11'd0, (pk==PK_CHEAT && !plog && !pfav ? cheat_pslot : pslot), 8'd0};''')
    replace(picker, '    S_BOOT: begin\n', '    S_BOOT: begin\n        cheat_armed<=0;cheat_receiving<=0;\n')
    replace(picker, '    S_L1: if (oerr != 0)', '''    S_L1: begin
        cheat_armed<=0;
        if (oerr != 0)''')
    replace(picker, """          else begin ent_raddr <= ebase + 11'd22; state <= S_SIZE_READ; end
    S_SIZE_READ: begin ent_raddr <= ent_raddr + 1'b1; state <= S_SIZE_LO; end""",
        """          else begin ent_raddr <= ebase + 11'd21; state <= S_SIZE_READ; end
    end
    S_SIZE_READ: begin ent_raddr <= ent_raddr + 1'b1; state <= S_CHEAT_LEN; end
    S_CHEAT_LEN: begin
        cheat_bytes <= (pver==16'd9) ? ent_q : 16'd0;
        ent_raddr <= ent_raddr + 1'b1; state <= S_SIZE_LO;
    end""")
    replace(picker, '    S_L6: begin picker_reset <= 1; hold_gb <= 0; tmr <= 0; state <= S_L7; end',
        """    S_L6: if(cheat_bytes>=16'd64 && cheat_bytes<=16'd304 && cheat_bytes[3:0]==0)begin
        pk<=PK_CHEAT;pflags<=0;psize<=0;op_slot<=CHEAT_SLOT;op_ret<=S_CHEAT_OPEN;state<=S_PREAD;
    end else state<=S_CHEAT_START;
    S_CHEAT_OPEN: if(oerr!=0)state<=S_CHEAT_START;
        else begin
            cheat_receiving<=1;
            target_dataslot_id<=CHEAT_SLOT;target_dataslot_slotoffset<=0;
            target_dataslot_bridgeaddr<=CHEAT_BRIDGE;target_dataslot_length<={16'd0,cheat_bytes};
            target_dataslot_read<=1;op_ret<=S_CHEAT_VALIDATE;tmr<=0;state<=S_XFER_W;
        end
    S_CHEAT_VALIDATE: begin
        cheat_receiving<=0;
        tmr<=tmr+1'b1;
        if(xerr!=0 || cheat_fault || tmr==28'd296000)state<=S_CHEAT_START;
        else if(cheat_ready)begin cheat_armed<=1;state<=S_CHEAT_ARM;end
    end
    S_CHEAT_ARM: if(cheat_active_ack)state<=S_CHEAT_START;
    S_CHEAT_START: begin picker_reset<=1;hold_gb<=0;tmr<=0;state<=S_L7;end""")

    top = 'core/core_top.sv'
    replace(top, 'assign cart_do = cart_physical_mode ? cart_tran_bank1 : cart_do_backend;', '''wire cheat_receiving,cheat_armed,cheat_ready,cheat_fault,cheat_clear;
wire [128:0] cheat_code;
wire [7:0] cheat_cart_do;
wire cheat_on,cheat_active_ack;
synch_3 cheat_on_sync(cheat_armed,cheat_on,clk_sys);
synch_3 cheat_ack_sync(cheat_on,cheat_active_ack,clk_74a);
native_cheat_loader #(.PLATFORM(16'd1),.ADDRESS_BITS(15),.MIN_ADDRESS(32'd0),
    .MAX_ADDRESS(32'h7fff),.BASE(32'ha0000000)) game_cheats(
    .clk(clk_74a),.clk_core(clk_sys),.reset(!reset_n || (picker_download && !picker_art_load)),
    .receiving(cheat_receiving),.bridge_wr(bridge_wr),.bridge_endian_little(bridge_endian_little),
    .bridge_addr(bridge_addr),.bridge_wr_data(bridge_wr_data),
    .ready(cheat_ready),.fault(cheat_fault),.code(cheat_code),.code_reset(cheat_clear));
gb_rom_cheats rom_patches(
    .clk(clk_sys),.clear(cheat_clear),.code(cheat_code),.enabled(cheat_on),
    .rom_read(cart_rd && !cart_a15 && !cram_rd),.address(cart_addr),
    .data_in(cart_do_backend),.data_out(cheat_cart_do));
assign cart_do = cart_physical_mode ? cart_tran_bank1 : cheat_cart_do;''')
    replace(top, '  .ss_start_ok                ( savestate_start_ok         ),', '''  .cheat_receiving(cheat_receiving),.cheat_armed(cheat_armed),
  .cheat_ready(cheat_ready),.cheat_fault(cheat_fault),.cheat_active_ack(cheat_active_ack),
  .ss_start_ok                ( savestate_start_ok         ),''')
    loader = (HERE.parent/'native_features/cheat_loader.sv').read_text(encoding='utf8')
    loader = loader.replace("if(normalized!={16'd1,PLATFORM})", "if(normalized!=32'h00010001 && normalized!=32'h00010002)")
    (out/'core/native_cheat_loader.sv').write_text(loader, encoding='utf8', newline='\n')
    shutil.copy2(HERE/'gb_rom_cheats.sv', out/'core/gb_rom_cheats.sv')
    with (out/'ap_core.qsf').open('a', encoding='utf8', newline='\n') as stream:
        stream.write('\nset_global_assignment -name SYSTEMVERILOG_FILE core/native_cheat_loader.sv\n'
                     'set_global_assignment -name SYSTEMVERILOG_FILE core/gb_rom_cheats.sv\n')


def prepare(out, cheats=False):
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'.work'):
        raise ValueError('Use a new candidate directory under .work')
    inputs = json.loads((ROOT/'docs/build/source-inputs.json').read_text(encoding='utf8'))['files']
    for row in inputs:
        if hashlib.sha256((ROOT/'core/src'/row['path']).read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('The frozen source differs: '+row['path'])
    shutil.copytree(ROOT/'core/src', out)
    def replace(relative, before, after):
        path = out/relative
        text = path.read_text(encoding='utf8')
        if text.count(before) != 1:
            raise ValueError('Candidate source anchor differs: '+relative)
        path.write_text(text.replace(before, after), encoding='utf8', newline='\n')
    replace('core/cover_picker.sv',
        '''        if ((tmr > 28'd512 && ss_load_ok) || tmr == 28'd148_000_000) begin
            // consume the resume point: truncate the .sus to 0 bytes
            pk <= PK_SUS; pflags <= 32'd2; psize <= 0; op_slot <= SUS_SLOT; op_ret <= S_L11; state <= S_PREAD;
        end''',
        '''        if (tmr > 28'd512 && ss_load_ok) begin
            // Consume a resume point only after the state manager confirms restoration.
            pk <= PK_SUS; pflags <= 32'd2; psize <= 0; op_slot <= SUS_SLOT; op_ret <= S_L11; state <= S_PREAD;
        end else if (tmr == 28'd148_000_000) begin
            // Preserve the file and stop the partial game on a failed/late restore.
            ss_load <= 0; ecode <= "U"; enum_ <= 3'd7; state <= S_LFAIL;
        end''')
    replace('core/core_top.sv', 'if (bw_en & ~picker_hr_mode) begin', 'if (bw_en) begin')
    changes = ['Preserve suspend file on restore timeout',
               'Apply host-requested grayscale to every active scaler including the cover menu']
    if cheats:
        add_cheats(out, replace)
        changes.append('Load bounded exact-ROM read replacements before game reset')
    files = [{'path': p.relative_to(out).as_posix(), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
             for p in sorted(out.rglob('*')) if p.is_file()]
    (out/'candidate-inputs.json').write_text(json.dumps({'base': '0.1.2', 'changes': changes,
        'files': files, 'hardware_acceptance': 'pending'}, indent=2)+'\n', encoding='utf8')
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    parser.add_argument('--cheats', action='store_true')
    args = parser.parse_args()
    print(prepare(args.out, args.cheats))
