#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Fix the native CPS EEPROM read port and ERASE_ALL initialization.

The original Pocket byte transport returns its previous 32-bit word at the
physical SPI read deadline. Observe both native EEPROM RAM commit sources and
provide a registered four-byte read using the stable SPI address instead.
Only these CPS targets tie EEPROM clk and dump_clk to the same clk_rom net.
The upstream ERASE_ALL branch retains the previous RAM data and command address;
initialize both before its existing WRITE_ALL sequencer. Pure original-module
serial tests reproduce the defect and cover full 64-word/128-byte erase,
disabled erase, repeated erase, subsequent write/read and ordinary WRITE_ALL.
"""
from pathlib import Path


def replace(text, old, new, count=1):
    if text.count(old) != count:
        raise ValueError('Native EEPROM patch anchor changed: '+old[:110])
    return text.replace(old, new)


PORTS = '''    input wire [4:0] lab_nv_addr,
    output wire [31:0] lab_nv_data,
'''
BINDING = '    .lab_nv_addr(lab_nv_addr),.lab_nv_data(lab_nv_data),\n'


def patch(root, core):
    root = Path(root)
    changed = []

    def edit(rel, fn):
        path = root/rel
        path.write_text(fn(path.read_text(encoding='utf8')), encoding='utf8', newline='\n')
        changed.append(rel)

    def chip(s):
        s = replace(s, '''                                            newdata <= {DW{1'b1}};
                                            st      <= WRITE_ALL;''', '''                                            newdata <= {DW{1'b1}};
                                            // ERAL must initialize the same RAM operands as WRAL.
                                            addr    <= 0;
                                            mem_din <= {DW{1'b1}};
                                            st      <= WRITE_ALL;''')
        s = replace(s, '    input           rst,        // system reset', PORTS+'    input           rst,        // system reset')
        mirror = '''// Pocket: the two native EEPROM RAM ports below share clk on CPS.
// Mirror actual commits, including CPU serial writes/erase-all and host restore.
// In 16-bit mode the original byte dump exposes low byte before high byte.
// Host restore runs with the game reset; the two writers cannot overlap.
reg [7:0] lab_nv_b0[0:31],lab_nv_b1[0:31],lab_nv_b2[0:31],lab_nv_b3[0:31];
reg [31:0] lab_nv_q;
assign lab_nv_data=lab_nv_q;
wire lab_nv_we=mem_we || dump_we;
wire [AW-1:0] lab_nv_wa=dump_we ? dump_addr : addr[0+:AW];
wire [DW-1:0] lab_nv_wd=dump_we ? dump_din : mem_din;
always @(posedge clk)begin
    lab_nv_q<={lab_nv_b0[lab_nv_addr],lab_nv_b1[lab_nv_addr],
               lab_nv_b2[lab_nv_addr],lab_nv_b3[lab_nv_addr]};
    if(lab_nv_we)begin
        if(DW==16)begin
            if(lab_nv_wa[0])begin
                lab_nv_b2[lab_nv_wa[AW-1:1]]<=lab_nv_wd[0+:8];
                lab_nv_b3[lab_nv_wa[AW-1:1]]<=lab_nv_wd[8+:8];
            end else begin
                lab_nv_b0[lab_nv_wa[AW-1:1]]<=lab_nv_wd[0+:8];
                lab_nv_b1[lab_nv_wa[AW-1:1]]<=lab_nv_wd[8+:8];
            end
        end else case(lab_nv_wa[1:0])
            0:lab_nv_b0[lab_nv_wa[AW-1:2]]<=lab_nv_wd[0+:8];
            1:lab_nv_b1[lab_nv_wa[AW-1:2]]<=lab_nv_wd[0+:8];
            2:lab_nv_b2[lab_nv_wa[AW-1:2]]<=lab_nv_wd[0+:8];
            3:lab_nv_b3[lab_nv_wa[AW-1:2]]<=lab_nv_wd[0+:8];
        endcase
    end
end
`ifdef SIMULATION
initial if((1<<AW)*DW!=1024)$fatal(1,"CPS EEPROM mirror requires 128 bytes");
always @(posedge clk)if(mem_we && dump_we)$fatal(1,"CPS EEPROM CPU/host commit collision");
`endif

'''
        return replace(s, 'jt9346_dual_ram #(.DW(DW), .AW(AW)) u_ram(', mirror+'jt9346_dual_ram #(.DW(DW), .AW(AW)) u_ram(')

    edit('modules/jteeprom/hdl/jt9346.v', chip)
    edit('modules/jteeprom/hdl/jt9346_16b8b.v', lambda s: replace(replace(s,
        '    input           rst,        // system reset', PORTS+'    input           rst,        // system reset'),
        '    jt9346 #(.AW(AW),.DW(DW),.CW(CW)) u_jt9346 (\n',
        '    jt9346 #(.AW(AW),.DW(DW),.CW(CW)) u_jt9346 (\n'+BINDING))
    edit('cores/cps1/hdl/jtcps1_sdram.v', lambda s: replace(replace(s,
        '    output  [ 7:0]  ioctl_din,', PORTS+'    output  [ 7:0]  ioctl_din,'),
        'jt9346_16b8b #(.DW(EEPROM_DW),.AW(EEPROM_AW)) u_eeprom(\n',
        'jt9346_16b8b #(.DW(EEPROM_DW),.AW(EEPROM_AW)) u_eeprom(\n'+BINDING))
    edit(f'cores/{core}/hdl/jt{core}_game.v', lambda s: replace(replace(s,
        f'module jt{core}_game(\n', f'module jt{core}_game(\n'+PORTS),
        '    .ioctl_din   ( ioctl_din     ),', BINDING+'    .ioctl_din   ( ioctl_din     ),'))
    edit('modules/jtframe/hdl/inc/jtframe_game_instance.v', lambda s: replace(s,
        'u_game(\n', 'u_game(\n'+BINDING))
    edit('modules/jtframe/target/pocket/hdl/jtframe_pocket_top.v', lambda s: replace(replace(s,
        'wire [ 7:0]   ioctl_dout, ioctl_din;',
        'wire [4:0] lab_nv_addr;\nwire [31:0] lab_nv_data;\nwire [ 7:0]   ioctl_dout, ioctl_din;'),
        '    .ioctl_din      ( ioctl_din      ),', BINDING+'    .ioctl_din      ( ioctl_din      ),'))
    # The frame and base carry address toward the game and data toward the host.
    frame_ports = '    output wire [4:0] lab_nv_addr,\n    input wire [31:0] lab_nv_data,\n'
    edit('modules/jtframe/target/pocket/hdl/jtframe_pocket.v', lambda s: replace(replace(s,
        '    input               clk_74a,', frame_ports+'    input               clk_74a,'),
        '    .ioctl_din      ( ioctl_din     ),', BINDING+'    .ioctl_din      ( ioctl_din     ),'))

    def base(s):
        s = replace(s, '    input           clk_74a,', frame_ports+'    input           clk_74a,')
        s = replace(s, '    .ioctl_din32   ( ioctl_din32    ),',
            '    .ioctl_din32   ( host_index==IDX_NVRAM ? lab_nv_data : ioctl_din32 ),')
        s = replace(s, '.menu_game_bound(ui_bound)', '.menu_game_bound(lab_nv_bound)')
        s = replace(s, 'wire [7:0] host_index;\n', '''wire [7:0] host_index;
// SPI addr belongs to clk_74a and is held through the whole transaction.
// Synchronize it before the one-cycle EEPROM lookup. The native read strobe
// crosses a longer request path, so the complete word is ready before sys_rd.
(* altera_attribute="-name SYNCHRONIZER_IDENTIFICATION FORCED_IF_ASYNCHRONOUS" *) reg [4:0] lab_nv_addr_meta=0,lab_nv_addr_sync=0;
always @(posedge clk_rom)begin
    lab_nv_addr_meta<=sys_addr[6:2];
    lab_nv_addr_sync<=lab_nv_addr_meta;
end
assign lab_nv_addr=lab_nv_addr_sync;
// APF can request a final save after Stop has reset the menu controller.
// Retain the previous valid binding through Stop; retire it on a new game load.
reg lab_nv_bound=0;
always @(posedge clk_rom)begin
    if(ui_new)lab_nv_bound<=0;
    else if(ui_bound)lab_nv_bound<=1;
end
''')
        return replace(s, '(ui_bound || host_index==IDX_CRT ? host_index : 8\'hff)',
            '(ui_bound || (lab_nv_bound && host_index==IDX_NVRAM) || host_index==IDX_CRT ? host_index : 8\'hff)')

    edit('modules/jtframe/target/pocket/hdl/jtframe_pocket_base.sv', base)
    edit('modules/jtframe/target/pocket/syn/pocket.sdc', lambda s:s+'''
# CPS EEPROM address CDC: only the first synchronizer stage is asynchronous.
# The second stage, EEPROM lookup and command response remain timed at clk_rom.
set cps_nv_meta [get_registers -nowarn {*|lab_nv_addr_meta[*]}]
if { [get_collection_size $cps_nv_meta] != 5 } {
    error "Expected five CPS NVRAM address synchronizer input registers"
}
set_false_path -to $cps_nv_meta
''')
    return changed
