#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare the CoverFlow overlay for the pinned native JTFRAME Pocket project."""

import argparse
import hashlib
import re
import shutil
import sys
from pathlib import Path

from cps2 import prepare_bridge
from prepare import EXPERIMENTS, SEGA, gba, nes, replace

HERE = Path(__file__).resolve().parent
COVERFLOW_INPUTS = (
    'cps2_menu.sv','cps2_target.sv','sega_menu_target.sv','coverflow_geometry.sv',
    'coverflow_psram_view.sv','coverflow_line_fetch16.sv','coverflow_psram.sv',
    'coverflow_psram_cache.sv','coverflow_dpram_ce.v','picker_dpram.v','data_loader.sv',
)
SOURCES = {
    'jtframe_pocket_top.v':'c6731a7a9a0ff3df146624fa1995a9c7656756540b0f11d0dd6b8eaae7758003',
    'jtframe_pocket.v':'6e195c6a4953c0196c23ac30a5c12c8fd3934a212e6fe61096544c3f4b748153',
    'jtframe_pocket_base.sv':'7dedee83505f5003f7eae7341930dbb14cd955b40aab81841b97de0ce5ce1465',
    'jtframe_pocket_cfg.v':'0e4b889a70276b0b3b8512a4353a583fffb2b16e10b51297e02669c15529402b',
    'jtframe_pocket_video.v':'3890f6a715345d3d36e13b9e0169750c02728a9f30ea6e988c24b0dee368db0b',
}


def controller():
    text=nes.controller('cpslab',128,'cps2_menu')
    text=replace(text,'output reg [7:0] state=0,','output reg [31:0] core_mode=0,button_map=0,dip_switches=0,\n    output reg [7:0] state=0,')
    text=replace(text,'2:rom_bytes<=normalized;','2:rom_bytes<=normalized;4:core_mode<=normalized;5:button_map<=normalized;200:dip_switches<=normalized;')
    text=replace(text,'rom_bytes<192 || rom_bytes>33554432','rom_bytes<48 || rom_bytes>67108864')
    text=replace(text,'command(1,0,0,PARAM,0,ROM_OPENED)','command(1,1,0,PARAM,0,ROM_OPENED)')
    text=replace(text,"command(0,0,0,32'h10000000,rom_bytes,ROM_READ)","command(0,1,0,32'd0,rom_bytes,ROM_READ)")
    text=replace(text,'command(1,10,0,PARAM,0,SAVE_OPENED)','command(1,2,0,PARAM,0,SAVE_OPENED)')
    text=replace(text,"command(0,10,0,32'h20000000,save_bytes,SAVE_READ_DONE)","command(0,2,0,32'd0,save_bytes,SAVE_READ_DONE)",2)
    start,end=text.index('            RUN:'),text.index('            PAUSE_WAIT:')
    text=text[:start]+'            RUN:begin end\n'+text[end:]
    text=gba.controller(text,exit_paths=2,cellram=True,cover_recovery=True)
    text=replace(text,'4:cf_title_width<=','6:cf_title_width<=')
    return replace(text,'5:cf_subtitle_width<=','7:cf_subtitle_width<=')


def video(text):
    text=replace(text,'    input             pxl2_cen,','''    input             pxl2_cen,
    input             menu_active,menu_half_pixel,menu_de,menu_hs,menu_vs,
    input      [23:0] menu_rgb,''')
    text=replace(text,'always @(posedge clk) begin\n    pxl_cnt <= pxl2_cen', '''wire pixel_enable=menu_active ? menu_half_pixel : pxl2_cen;
reg menu_hs_hold=0,menu_vs_hold=0;
always @(posedge clk) begin
    menu_hs_hold<=menu_hs_hold || menu_hs;
    menu_vs_hold<=menu_vs_hold || menu_vs;
    pxl_cnt <= pixel_enable''')
    text=replace(text,'if(pxl2_cen) begin','if(pixel_enable) begin')
    return replace(text,'''            pck_hs  <= base_hs & ~hsl;
            pck_vs  <= base_vs & ~vsl;
            pck_de  <= de;
            // configuration info is sent during ~DE
            pck_rgb <= de ? { extend8(br), extend8(bg), extend8(bb) } :''','''            if(menu_active)begin menu_hs_hold<=0;menu_vs_hold<=0;end
            pck_hs  <= menu_active ? menu_hs_hold || menu_hs : base_hs & ~hsl;
            pck_vs  <= menu_active ? menu_vs_hold || menu_vs : base_vs & ~vsl;
            pck_de  <= menu_active ? menu_de : de;
            // Use the existing horizontal 384x224 scaler (slot 0).
            pck_rgb <= menu_active ? (menu_de ? menu_rgb : 24'd0) : de ? { extend8(br), extend8(bg), extend8(bb) } :''')


def prepare(source, gba_source, out):
    source, gba_source, out = (Path(p).resolve() for p in (source,gba_source,out))
    hdl=source/'modules/jtframe/target/pocket/hdl'
    stock={}
    for filename,digest in SOURCES.items():
        raw=(hdl/filename).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest:
            raise ValueError('Unexpected pinned JTFRAME input: '+filename)
        stock[filename]=raw.decode().replace('\r\n','\n')
    sys.path.insert(0,str(EXPERIMENTS/'coverflow_shared'))
    from prepare_psram import build
    out=build(out,gba_source,clock_speed=96.0)
    def write(name,text):
        (out/name).write_text(text,encoding='utf8',newline='\n')
    bridge=prepare_bridge(hdl/'jtframe_pocket_cmd.v',out/'bridge')
    for name in ('jtframe_pocket_cmd.v','cps2_target.sv'):
        shutil.copy2(bridge/name,out/name)
    shutil.copy2(SEGA/'target_adapter.sv',out/'sega_menu_target.sv')
    loader=list((gba_source/'src/fpga').rglob('data_loader.sv'))
    if len(loader)!=1:
        raise ValueError('Expected the native APF data loader')
    shutil.copy2(loader[0],out/'data_loader.sv')
    write('cps2_menu.sv',controller())

    top=stock['jtframe_pocket_top.v']
    pins=top[top.index('    output    [21:16] cram1_a,'):top.index('    output            cram1_lb_n,')+len('    output            cram1_lb_n,\n')]
    port_names=re.findall(r'\b(cram1_\w+),',pins)
    if len(port_names)!=12:
        raise ValueError('Unexpected CPS2 CellRAM1 pin list')
    bind=''.join(f'    .{name}({name}),\n' for name in port_names)
    top,count=re.subn(r'^assign cram1_\w+\s*=.*?;\n','',top,flags=re.M)
    if count!=11:
        raise ValueError('CPS2 CellRAM1 is no longer idle')
    bind+='    .menu_clk(clk24),\n'
    write('jtframe_pocket_top.v',replace(top,'u_frame(\n','u_frame(\n'+bind))
    frame=stock['jtframe_pocket.v']
    frame=replace(frame,'    input               clk_pico,','    input               clk_pico, menu_clk,\n'+pins.rstrip())
    write('jtframe_pocket.v',replace(frame,') u_base(\n',') u_base(\n'+bind.replace('menu_clk(clk24)','menu_clk(menu_clk)')))

    base=stock['jtframe_pocket_base.sv']
    base=replace(base,'    input           clk48,','    input           clk48, menu_clk,\n'+pins.rstrip())
    base=replace(base,'rst_req <= rst_aux;','rst_req <= rst_aux | ui_reset;')
    base=replace(base,'reg rstn_74a;\n\nalways @(negedge clk_74a ) begin\n    rstn_74a <= ~rst;\nend',
        'wire rstn_74a;\njtframe_sync menu_pad_reset(.clk_in(clk_rom),.clk_out(clk_74a),.raw(rst_req_n),.sync(rstn_74a));')
    base=replace(base,'.rst_rom    ( rst         ),','.rst_rom    ( transport_reset ),')
    base=replace(base,'.rst_rom            ( rst        ),','.rst_rom            ( transport_reset ),')
    base=replace(base,'.down_index    ( ioctl_index    ),','''    .down_index    ( host_index ),
    .menu_game_bound(ui_bound),.menu_open_parameter(ui_param),.target_cmd_req(tcmd_req),.target_cmd(tcmd),
    .target_cmd_p0(tcmd_p0),.target_cmd_p1(tcmd_p1),.target_cmd_p2(tcmd_p2),.target_cmd_p3(tcmd_p3),
    .target_cmd_ack(tcmd_ack),.target_cmd_done(tcmd_done),.target_cmd_result(tcmd_result),''')
    base=replace(base,'.rst_rom    ( rst       ),','''    .rst_rom    ( rst       ),
    .menu_game(ui_loading || ui_bound),.menu_mode(ui_mode),.menu_buttons(ui_buttons[23:0]),.menu_dip(ui_dip),''')
    base=replace(base,'    // scaler modes\n    .rotate','''    .menu_active(cf_video_owner),.menu_half_pixel(cf_half_pixel_ce),.menu_rgb(cf_pixel_bus[26:3]),
    .menu_de(cf_pixel_bus[2]),.menu_hs(cf_pixel_bus[1]),.menu_vs(cf_pixel_bus[0]),
    // scaler modes
    .rotate''')
    base=replace(base,'.snd_left   ( snd_left      ),',".snd_left(ui_bound ? snd_left : 16'd0),")
    base=replace(base,'.snd_right  ( snd_right     ),',".snd_right(ui_bound ? snd_right : 16'd0),")
    sega=(SEGA/'top_insert.sv').read_text(encoding='utf8')
    art=sega[sega.index('  wire cf_menu,'):sega.index('  reg cf_video_owner=1;')]
    art=art.replace('(clk_74a)','(clk_rom)').replace('cram0_','cram1_')
    art=replace(art,'coverflow_psram_view cf_view','coverflow_psram_view #(.HT(9\'d438),.VT(9\'d250)) cf_view')
    art=replace(art,".clk_vid(clk_vid),.pixel_ce(1'b1)",'.clk_vid(menu_clk),.pixel_ce(cf_pixel_ce)')
    art=replace(art,'.vs(video_vs_reg)','.vs(logo_vs)')
    insertion=replace((HERE/'cps2_insert.sv').read_text(encoding='utf8'),'// SHARED_RENDERER',art)
    write('jtframe_pocket_base.sv',replace(base,'endmodule',insertion+'\nendmodule'))

    cfg=replace(stock['jtframe_pocket_cfg.v'],'    input             rst_rom, clk_rom, clk_74a,','''    input             rst_rom, clk_rom, clk_74a,
    input             menu_game,
    input [31:0]      menu_mode,menu_dip,
    input [23:0]      menu_buttons,''')
    cfg=replace(cfg,"        core_mod <= 0;\n        button_map <= 24'h543210;",'''        core_mod <= menu_game ? {menu_mode[17:16],9'd0,menu_mode[6:0]} : 18'd0;
        button_map <= menu_game ? menu_buttons : 24'h543210;
        if(menu_game) game_vol <= menu_mode[15:8];''')
    write('jtframe_pocket_cfg.v',replace(cfg,"        dipsw    <= ~32'h0;","        dipsw    <= menu_game ? menu_dip : ~32'h0;"))
    write('jtframe_pocket_video.v',video(stock['jtframe_pocket_video.v']))

    # Native 384x224 raster uses the same easing/scale table and a shorter layout.
    path='coverflow_psram_view.sv'
    text=(out/path).read_text(encoding='utf8').replace('HR_W = 320, HR_H = 288','HR_W = 384, HR_H = 224')
    text=text.replace("vx[vk] <= cx[vk]","vx[vk] <= cx[vk]+11'sd32").replace("12'sd96","12'sd86")
    text=text.replace('HT1Y = 200, HT2Y = 222, HDY = 256','HT1Y = 181, HT2Y = 200, HDY = 220')
    text=text.replace("9'd160","9'd192").replace("9'd96 : 9'd192","9'd128 : 9'd192")
    text=text.replace("htw_s > 9'd300","htw_s > 9'd364").replace('x < 310','x < 374')
    write(path,text)
    path='coverflow_line_fetch16.sv'
    text=(out/path).read_text(encoding='utf8').replace("12'sd320","12'sd384").replace("12'sd96","12'sd86")
    write(path,text)
    # Eight 96 MHz cycles leave over 13 ns for board and FPGA pin delays.
    path='coverflow_psram_cache.sv'
    text=(out/path).read_text(encoding='utf8')
    write(path,replace(text,'.CLOCK_SPEED(96.0)','.CLOCK_SPEED(96.0),.MIN_WRITE_TIME_FROM_ADV(80),.CF_PSRAM_MAX_ACCESS_TIME_FROM_ADV(80)'))
    return out


if __name__ == '__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    for arg in ('source','gba-source','out'):
        cli.add_argument('--'+arg,type=Path,required=True)
    args=cli.parse_args()
    print(prepare(args.source,args.gba_source,args.out))
