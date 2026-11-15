#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Connect version-bound native ROM read replacements to PCE, MD and SFC."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'experiments/console_coverflow'))
import prepare as console
from prepare_nes import controller
replace=console.replace

PROFILES={
    'pce':('pcelab','target/pocket','core_top.v','console_menu.sv','clk_sys_42_95',4,21,8,0,0x1fffff),
    'genesis':('mdclab','src/fpga/core','core_top.sv','console_menu.sv','clk_sys',5,24,16,0,0x3fffff),
    'snes':('snescn','target/pocket','core_top.sv','snes_menu.sv','clk_sys_21_48',6,24,8,0,0xffffff),
}


def prepare(platform,archive,gba_source,out):
    if platform=='snes':
        import snes
        out=snes.prepare(archive,out)
    else:
        out=console.prepare(archive,gba_source,out,platform)
    ns,folder,filename,menu,clock,ident,addr_bits,data_bits,low,high=PROFILES[platform]
    dest=out/folder
    path=dest/menu
    path.write_text(controller(path.read_text(encoding='utf8'),ns,201,0xa0000000,60),encoding='utf8',newline='\n')
    top=dest/filename
    text=top.read_text(encoding='utf8')
    module='snes_menu' if platform=='snes' else 'console_menu'
    text=replace(text,f'  {module} menu',f'''  wire ui_cheat_loading,ui_cheat_armed,ui_cheat_ready,ui_cheat_fault;
  wire ui_cheat_reset;
  wire [128:0] ui_cheat_code;
  reg [2:0] ui_cheat_arm_sync=0;
  always @(posedge {clock}) ui_cheat_arm_sync<={{ui_cheat_arm_sync[1:0],ui_cheat_armed}};
  reg [2:0] ui_cheat_active_sync=0;
  always @(posedge clk_74a) ui_cheat_active_sync<={{ui_cheat_active_sync[1:0],ui_cheat_arm_sync[2]}};
  native_cheat_loader #(.PLATFORM(16'd{ident}),.ADDRESS_BITS({addr_bits}),.DATA_BITS({data_bits}),
      .MIN_ADDRESS(32'h{low:08x}),.MAX_ADDRESS(32'h{high:08x}),.BASE(32'ha0000000)) game_cheats(
      .clk(clk_74a),.clk_core({clock}),.reset(!reset_n || ui_new),.receiving(ui_cheat_loading),
      .bridge_wr(bridge_wr),.bridge_endian_little(bridge_endian_little),.bridge_addr(bridge_addr),.bridge_wr_data(bridge_wr_data),
      .ready(ui_cheat_ready),.fault(ui_cheat_fault),.code(ui_cheat_code),.code_reset(ui_cheat_reset));
  {module} menu''')
    text=replace(text,'.save_capacity(','''.cheat_ready(ui_cheat_ready),.cheat_fault(ui_cheat_fault),
      .cheat_loading(ui_cheat_loading),.cheat_armed(ui_cheat_armed),
      .cheat_active_ack(ui_cheat_active_sync[2]),.save_capacity(''')
    if platform=='genesis':
        text=replace(text,'.MCLK(clk_sys),','.MCLK(clk_sys),\n    .GG_RESET(ui_cheat_reset),.GG_EN(~ui_cheat_arm_sync[2]),.GG_CODE(ui_cheat_code),.GG_AVAILABLE(),')
        code=dest/'rtl/system.sv'
        value=code.read_text(encoding='utf8')
        value=replace(value,'.BIG_ENDIAN(1)) codes','.BIG_ENDIAN(1), .MAX_CODES(16)) codes')
        code.write_text(value,encoding='utf8',newline='\n')
    else:
        entry='.core_reset(' if platform=='pce' else '.core_reset('
        text=replace(text,entry,'''.native_cheat_code(ui_cheat_code),.native_cheat_reset(ui_cheat_reset),
      .native_cheat_enable(ui_cheat_arm_sync[2]),'''+entry)
        native=out/('rtl/main.sv' if platform=='pce' else 'rtl/mister_top/SNES.sv')
        value=native.read_text(encoding='utf8')
        value=replace(value,'    input wire core_reset,','''    input wire core_reset,
    input wire [128:0] native_cheat_code,
    input wire native_cheat_reset,native_cheat_enable,''')
        declaration='  reg [128:0] gg_code;' if platform=='pce' else '  reg [128:0] gg_code = 0;'
        value=replace(value,declaration,'  wire [128:0] gg_code=native_cheat_code;')
        value=replace(value,'.GG_EN(status[5]),' if platform=='pce' else '.GG_EN(status[24]),', '.GG_EN(~native_cheat_enable),')
        previous='.GG_RESET((cart_download | code_download) & ioctl_wr & !ioctl_addr),' if platform=='pce' else '.GG_RESET((code_download && ioctl_wr && !ioctl_addr) || cart_download),'
        value=replace(value,previous,'.GG_RESET(native_cheat_reset),')
        native.write_text(value,encoding='utf8',newline='\n')
        if platform=='snes':
            snes_core=out/'rtl/upstream/SNES.vhd'
            value=snes_core.read_text(encoding='utf8')
            value=replace(value,'data_in => CPU_DO,','data_in => CPU_DI,')
            snes_core.write_text(value,encoding='utf8',newline='\n')
        codes=list(out.rglob('cheatcodes.sv'))
        if len(codes)!=1:raise ValueError('Expected one pinned native cheat engine')
        value=codes[0].read_text(encoding='utf8')
        import re
        value,count=re.subn(r'(parameter\s+MAX_CODES\s*=\s*)32',r'\g<1>16',value)
        if count!=1:raise ValueError('Native cheat capacity differs')
        duplicate='if (codes[x][ADDR_S-:ADDR_WIDTH] == code_addr) begin'
        if duplicate in value:
            value=replace(value,duplicate,'if (codes[x][ENA_F_S] && codes[x][ADDR_S-:ADDR_WIDTH] == code_addr) begin')
        codes[0].write_text(value,encoding='utf8',newline='\n')
    top.write_text(text,encoding='utf8',newline='\n')
    loader=(HERE/'cheat_loader.sv').read_text(encoding='utf8')
    if platform=='genesis':
        loader=loader.replace('ramstyle="M10K, no_rw_check"','ramstyle="MLAB, no_rw_check"')
    (dest/'native_cheat_loader.sv').write_text(loader,encoding='utf8',newline='\n')
    qsf=out/('src/fpga/ap_core.qsf' if platform=='genesis' else f'projects/{"pce" if platform=="pce" else "snes"}_pocket.qsf')
    separator = '' if qsf.read_bytes().endswith(b'\n') else '\n'
    with qsf.open('a',encoding='utf8',newline='\n') as stream:
        stream.write(separator)
        stream.write(f'set_global_assignment -name SYSTEMVERILOG_FILE {"core" if platform=="genesis" else "../target/pocket"}/native_cheat_loader.sv\n')
    (out/'native-feature-receipt.json').write_text(json.dumps({'features':['PLCH1'],'platform':platform,
        'max_read_replacements':16,'scope':'Version-bound ROM read replacements','hardware_acceptance':'pending'},indent=2)+'\n')
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('platform',choices=PROFILES)
    for name in ('archive','gba-source','out'):parser.add_argument('--'+name,required=name!='gba-source')
    args=parser.parse_args()
    print(prepare(args.platform,args.archive,args.gba_source,args.out))
