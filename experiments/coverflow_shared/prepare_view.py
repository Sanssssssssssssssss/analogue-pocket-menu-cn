#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Reuse the accepted CoverFlow raster/compositor and cache ordering verbatim."""
import argparse,hashlib,json,shutil
from pathlib import Path
from prepare_geometry import geometry,ROOT,SOURCE
HERE=Path(__file__).resolve().parent
def take(s,start,end):
    a=s.index(start);b=s.index(end,a);return s[a:b]
def view(compact=False):
    geom,provenance=geometry(compact);s=SOURCE.read_text(encoding='utf8')
    cache=take(s,'// ---------------------------------------------------------------- cover cache (clk_74a)','// platform line, character j')
    cache=cache.replace('reg  [10:0] cg [0:3];','wire [10:0] cg [0:3];')
    position=take(s,'// position bar thumb:','// ================================================================== video (clk_vid)')
    video=take(s,'// ================================================================== video (clk_vid)','reg [1:0] ovl_s')
    raster=take(s,'// ---------------------------------------------------------------- hi-res menu:','// ---------------------------------------------------------------- SDRAM line fetcher')
    raster=raster.replace('localparam [8:0] HT = 374, VT = 300, HOFF = 40, VOFF = 6;','localparam [8:0] HOFF = 40, VOFF = 6;')
    raster=raster.replace('always @(posedge clk_vid)', 'always @(posedge clk_vid) if(pixel_ce)')
    video=video.replace('always @(posedge clk_vid)', 'always @(posedge clk_vid) if(pixel_ce)')
    raster=raster.replace('picker_dpram #(.WIDTH(16), .ADDR(10)) line_buf (','coverflow_dpram_ce #(.WIDTH(16), .ADDR(10)) line_buf (')
    raster=raster.replace('.rclk(clk_vid), .raddr({y[0], x}), .q(lb_q));','.rclk(clk_vid), .rce(pixel_ce), .raddr({y[0], x}), .q(lb_q));')
    # Both text rows accept Unicode bitmap columns; the accepted title path is unchanged.
    raster=raster.replace('(bitmap_titles && s2_t1)', '(bitmap_titles && (s2_t1 || s2_t2))')
    legacy_alpha="wire [1:0] galpha = (bitmap_titles && (s2_t1 || s2_t2)) ? {2{title_pixel_hr2}} : (s2_gv ? {2{font2_q[s2_col]}} : 2'd0);"
    if raster.count(legacy_alpha)!=1:raise ValueError('Bitmap text alpha anchor changed')
    # Both rows are bitmap columns. Alpha outside those rows is never used by
    # the compositor. Drop the unreachable legacy glyph path and its 8 M10Ks.
    raster=raster.replace(legacy_alpha,'wire [1:0] galpha={2{title_pixel_hr2}};')
    raster=raster.replace('s2_pix <= lb_q;','s2_pix <= line_ready ? lb_q : 16\'h2124;')
    old='''always @(posedge clk_vid) if(pixel_ce) begin
    hr_de <= hde[1]; hr_hs <= hhs[1]; hr_vs <= hvs[1];
    hr_rgb <= s2_act ? h_out : 24'h0;
end'''
    new='''always @(posedge clk_vid) begin
    hr_hs<=0;hr_vs<=0;hr_skip<=hr_de;
    if(pixel_ce)begin
        hr_de<=hde[1];hr_hs<=hhs[1];hr_vs<=hvs[1];hr_skip<=0;
        hr_rgb<=s2_act ? h_out:24'h0;
    end
end'''
    if raster.count(old)!=1:raise ValueError('Raster output anchor changed')
    raster=raster.replace(old,new)
    prefix='''// SPDX-License-Identifier: MIT
// Adapted from the accepted maxsorto/Pocket Lab cover_picker.sv.
module coverflow_view #(parameter CB=7,parameter [8:0] HT=374,VT=300)(
    input wire clk_74a,clk_sys,clk_vid,pixel_ce,
    input wire enable,hold_gb,menu_active,vs,
    input wire ago,ago_dir,invalidate,cache_commit,
    input wire [10:0] cache_game,idx,count,
    input wire [3:0] level_target,tl_target,
    input wire [8:0] htw,hsw,
    input wire gen,text_we,
    input wire [9:0] text_addr,
    input wire [15:0] text_data,
    output wire want_art,
    output wire [10:0] wanted_game,
    output wire frame_tick,hr_mode,anim,
    output wire [3:0] af,tlevel,
    output reg [3:0] level=0,
    output reg hr_de=0,hr_hs=0,hr_vs=0,hr_skip=0,
    output reg [23:0] hr_rgb=0,
    output wire mem_req,
    output wire [23:0] mem_word_addr,
    input wire mem_done,
    input wire [31:0] mem_data,
    output wire mem_idle,underrun,fault
);
localparam DEBUG_SQUARES=0;
wire [10:0] rcount=count,rlo=0;
wire [7:0] title_w=0;
reg [2:0] vs_s=0;reg vs_any=0;
always @(posedge clk_74a)vs_s<={vs_s[1:0],vs_any};
assign frame_tick=vs_s[1] && !vs_s[2];
always @(posedge clk_74a)if(!enable)level<=0;else if(frame_tick)begin
    if(level<level_target)level<=level+1'b1;
    else if(level>level_target)level<=level>=2 ? level-2'd2:4'd0;
end
wire adir;
wire signed [10:0] cx[0:3];wire [7:0] cs[0:3];wire [4:0] cb[0:3];wire cv[0:3];
wire [10:0] neighbors[0:4];
genvar ni;generate for(ni=0;ni<5;ni=ni+1)begin:neighbor_wire assign neighbors[ni]=cgame[ni];end endgenerate
coverflow_geometry geometry(.clk_74a(clk_74a),.enable(enable),.frame_tick(frame_tick),.ago(ago),.ago_dir(ago_dir),
    .tl_target(tl_target),.rcount(rcount),.cgame(neighbors),.anim(anim),.adir(adir),.af(af),.tlevel(tlevel),
    .x(cx),.size(cs),.brightness(cb),.game(cg),.valid(cv));
'''
    driver='''reg [CB:0] clear_left=(1<<CB);
wire clearing=clear_left!=0;
always @(posedge clk_74a)begin
    tag_we<=0;need_clr<=invalidate || clearing || cache_commit;
    if(ago)last_left<=ago_dir;
    if(invalidate)clear_left<=(1<<CB);
    else if(clearing)begin tag_we<=1;tag_wa<=clear_left-1'b1;tag_wd<=0;clear_left<=clear_left-1'b1;end
    else if(cache_commit)begin tag_we<=1;tag_wa<=cache_game[CB-1:0];tag_wd<={1'b1,cache_game};end
end
assign want_art=enable && !clearing && need_ok;
assign wanted_game=need_g;
'''
    text='''wire [9:0] map2_ra;wire [15:0] map2_q;
coverflow_dpram_ce #(.WIDTH(16),.ADDR(10)) text_ram(.wclk(clk_74a),.we(text_we),.waddr(text_addr),.wdata(text_data),
    .rclk(clk_vid),.rce(pixel_ce),.raddr(map2_ra),.q(map2_q));
wire bitmap_titles=1;
wire [11:0] pause_font_addr=0;
wire [9:0] t1x=0;
wire [15:0] glyph;
'''
    debug='''wire [15:0] dbg=0;
wire dbg_art_done=0,dbg_art_err=0;
'''
    fetch='''wire [9:0] ready_even,ready_odd;
reg [9:0] even_meta=0,even_sync=0,odd_meta=0,odd_sync=0;
always @(posedge clk_vid)begin even_meta<=ready_even;even_sync<=even_meta;odd_meta<=ready_odd;odd_sync<=odd_meta;end
reg line_ready=0;
always @(posedge clk_vid)if(pixel_ce && hc==HOFF-4)
    line_ready<=y[0] ? odd_sync=={1'b1,y}:even_sync=={1'b1,y};
reg invalidate_toggle=0;
always @(posedge clk_74a)if(invalidate)invalidate_toggle<=~invalidate_toggle;
reg [2:0] invalidate_sync=0;
always @(posedge clk_sys)invalidate_sync<={invalidate_sync[1:0],invalidate_toggle};
wire invalidate_sys=invalidate_sync[2]!=invalidate_sync[1];
reg [1:0] fetch_enable=0;
always @(posedge clk_sys)fetch_enable<={fetch_enable[0],enable && menu_active && level!=0};
coverflow_line_fetch #(.CB(CB)) fetcher(.clk(clk_sys),.enable(fetch_enable[1]),.invalidate(invalidate_sys),
    .line_toggle(lreq_t),.line_y(lreq_y),.cover_x(vx),.cover_size(vs_),.cover_game(vg),.cover_valid(vv),.cover_loaded(vl),
    .mem_req(mem_req),.mem_word_addr(mem_word_addr),.mem_done(mem_done),.mem_data(mem_data),.mem_idle(mem_idle),
    .line_we(lb_we),.line_addr(lb_wa),.line_data(lb_wd),.ready_even(ready_even),.ready_odd(ready_odd),.underrun(underrun),.fault(fault));
endmodule
'''
    # Fetcher owns these signals; remove the copied declaration initializers.
    raster=raster.replace('reg         lb_we = 0; reg [9:0] lb_wa = 0; reg [15:0] lb_wd = 0;',
        'wire lb_we;wire [9:0] lb_wa;wire [15:0] lb_wd;')
    font=take(s,'module font_hr_rom','// 5x7 font ROM')
    code=(prefix+cache+driver+position+video+text+debug+raster+fetch+font).replace('font_hr_rom','coverflow_font_rom')
    provenance.update({'scope':'Accepted cache candidate ordering, geometry, reflection, rounded cover, title marquee, dots, compositor; ready/response line transport',
        'adaptations':['pixel clock enable and RAM read enable','single physical-clock sync pulses','bitmap columns for both Unicode text rows','completed-line guard','new ready/response texture transport']})
    return geom,code,provenance
def prepare(out,compact=False):
    out=Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'.work'):raise ValueError('Fresh .work output required')
    out.mkdir(parents=True);geom,code,proof=view(compact)
    (out/'coverflow_geometry.sv').write_text(geom,encoding='utf8',newline='\n')
    (out/'coverflow_view.sv').write_text(code,encoding='utf8',newline='\n')
    ram=(ROOT/'core/src/core/picker_dpram.v').read_text(encoding='utf8')
    ram=ram.replace('module picker_dpram','module coverflow_dpram_ce').replace('input  wire             rclk,','input wire rce, input  wire rclk,')
    ram=ram.replace('.clock_enable_input_b("BYPASS")','.clock_enable_input_b("NORMAL")').replace('.clocken1(1\'b1)', '.clocken1(rce)')
    (out/'coverflow_dpram_ce.v').write_text(ram,encoding='utf8',newline='\n')
    shutil.copy2(ROOT/'core/src/core/picker_dpram.v',out/'picker_dpram.v')
    shutil.copy2(HERE/'line_fetch.sv',out/'coverflow_line_fetch.sv')
    shutil.copy2(ROOT/'core/src/font_cn.hex',out/'font_cn.hex')
    (out/'view-source.json').write_text(json.dumps(proof,indent=2)+'\n')
    return out
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True);p.add_argument('--compact',action='store_true');a=p.parse_args();print(prepare(a.out,a.compact))
