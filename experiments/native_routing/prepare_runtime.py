#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare fresh runtime read/open probes; leave all accepted build trees untouched."""
import argparse
from pathlib import Path
import shutil
from prepare_probe import HERE, replace
from prepare_trial import trial


def prepare(archive, out, buffered_open=False):
    out=trial(archive,out)
    for name in ['A','B']:
        fpga=out/name/'src/fpga';p=fpga/'core/core_top.v';text=p.read_text()
        text=replace(text,"32'h600000xx: begin bridge_rd_data <= probe_data; end", """32'h60000030,32'h60000034,32'h600000B0,32'h600000B4,32'h600000B8,
    32'hF300xxxx: begin bridge_rd_data <= runtime_data; end
    32'h60000000,32'h60000004,32'h60000008,32'h6000000C,32'h60000010,
    32'h60000014,32'h6000001C,32'h60000020,32'h60000024,
    32'h60000090,32'h600000A0,32'h600000A4: begin bridge_rd_data <= probe_data; end""")
        for field in ['read','openfile']:
            text=replace(text,f'wire            target_dataslot_{field} = 0;',f'wire            target_dataslot_{field};')
        for field,bits,value in [('id','15:0',"16'd0"),('slotoffset','31:0',"32'd0"),
                                 ('bridgeaddr','31:0',"32'h60000080"),('length','31:0',"32'd16")]:
            text=replace(text,f'reg     [{bits}]  target_dataslot_{field};',
                         f'wire    [{bits}]  target_dataslot_{field} = {value};')
        text=replace(text,'wire    [31:0]  target_buffer_param_struct;',"wire    [31:0]  target_buffer_param_struct = 32'hF3000000;")
        text=replace(text,'wire    [31:0]  target_buffer_resp_struct;',"wire    [31:0]  target_buffer_resp_struct = 0;")
        insert="""
wire [31:0] runtime_data;
runtime_request runtime_probe (
    .clk(clk_74a),.power_reset(!pll_core_locked_s),.run_reset_n(reset_n),
    .in_menu(osnotify_inmenu),.buttons(cont1_key[15:0]),
    .address(bridge_addr),.write(bridge_wr),.write_data(bridge_wr_data),
    .ack(target_dataslot_ack),.done(target_dataslot_done),.error(target_dataslot_err),
    .request_read(target_dataslot_read),.request_open(target_dataslot_openfile),
    .read_data(runtime_data));
"""
        text=replace(text,'endmodule',insert+'\nendmodule')
        if buffered_open:
            text=replace(text,"32'hF300xxxx: begin bridge_rd_data <= runtime_data; end", """32'hF300xxxx: begin bridge_rd_data <= runtime_param_data; end""")
            # Keep status readouts combinational; only the filename struct is buffered.
            text=replace(text,"32'h60000030,32'h60000034,32'h600000B0,32'h600000B4,32'h600000B8,",
                "32'h60000030,32'h60000034,32'h600000B0,32'h600000B4,32'h600000B8: begin bridge_rd_data <= runtime_data; end")
            text=replace(text,'endmodule',"""wire [31:0] runtime_param_data;
runtime_param_buffer parameter_buffer(clk_74a,bridge_rd,bridge_addr,runtime_data,runtime_param_data);
endmodule""")
        p.write_text(text,encoding='utf8',newline='\n')
        shutil.copy2(HERE/'runtime_request.sv',fpga/'core/runtime_request.sv')
        cmd=fpga/'core/core_bridge_cmd.v'
        cmd.write_text(replace(cmd.read_text(),'synch_3 s01(bridge_endian_little, endian_little_s, clk);',
            'synch_3 s01(.i(bridge_endian_little),.o(endian_little_s),.clk(clk));'),newline='\n')
        with (fpga/'ap_core.qsf').open('a') as f:f.write('set_global_assignment -name SYSTEMVERILOG_FILE core/runtime_request.sv\n')
        if buffered_open:
            shutil.copy2(HERE/'runtime_param_buffer.sv',fpga/'core/runtime_param_buffer.sv')
            with (fpga/'ap_core.qsf').open('a') as f:f.write('set_global_assignment -name SYSTEMVERILOG_FILE core/runtime_param_buffer.sv\n')
    template=(HERE/'isolation_loader.asm').read_text()
    for number,mode in ([(15,2)] if buffered_open else [(13,1),(14,2)]):
        folder=out/'runtime'/f'Route{number}';folder.mkdir(parents=True)
        body=(HERE/'reentry_body.asm').read_text().replace('#0x60000014','#0x60000034')
        body+=f'\n    ld r0,#0x60000030\n    ld r1,#{mode}\n    pmpw r0,r1\n'
        (folder/'loader.asm').write_text(template.replace('// BODY',body),encoding='utf8',newline='\n')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['archive','out']:p.add_argument('--'+name,required=True)
    p.add_argument('--buffered-open',action='store_true')
    a=p.parse_args();print(prepare(a.archive,a.out,a.buffered_open))
