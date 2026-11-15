#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate an isolated Supervision native CoverFlow from one pinned git tree."""
import argparse, hashlib, importlib.util, json, re, shutil, struct, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
COMMIT='7c01e71e028de81171f74f835812dfc1e109cefe'
REPO='https://github.com/opengateware/console-supervision'
NAMESPACE='svclab'

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

base=load('sv_console_prepare',ROOT/'experiments/console_coverflow/prepare.py')
replace=base.replace

def controller():
    base.PROFILES['pce']=(NAMESPACE,0,524288,0,'')
    text=base.controller('pce').replace('module console_menu #','module supervision_menu #',1)
    text=replace(text,"localparam [31:0] PARAM=32'hF3000000;","localparam [31:0] PARAM=32'hF4000000;")
    text=replace(text,'input wire [31:0] save_capacity,','input wire cart_fault,\n    input wire [31:0] save_capacity,')
    text=replace(text,'rom_bytes<512 || rom_bytes>524288 || rom_bytes[1:0]!=0 || cart_mode>1',
        'rom_bytes<16384 || rom_bytes>524288 || (rom_bytes & (rom_bytes-1))!=0 || cart_mode!=0')
    text=replace(text,'else begin validate_rtc<=0;validate_index<=0;row_read_addr<=72;state<=VALIDATE_WAIT;end',
        'else paint(frame_base+({21\'d0,selected}*FRAME_SIZE),MENU);')
    text=replace(text,"command(0,0,0,32'h10000000,rom_bytes,ROM_READ)","command(0,0,0,32'h00000000,rom_bytes,ROM_READ)")
    a=text.index('            ROM_SETTLE:');b=text.index('            SAVE_OPEN:',a)
    text=text[:a]+'''            ROM_SETTLE:if(cart_fault)fail(8'h37);
                else if(timer>=SETTLE_CYCLES && prepare_ready)state<=LOAD_FINISH;
                else if(timer>=TIMEOUT)fail(8'h35);
'''+text[b:]
    # This engine has no persistent save interface. Make all inherited save
    # states explicit errors rather than permitting any accidental disk write.
    a=text.index('            SAVE_OPEN:');b=text.index('            LOAD_FINISH:',a)
    text=text[:a]+text[b:]
    a=text.index('            PAUSE_WAIT:');b=text.index('            ERROR:',a)
    text=text[:a]+text[b:]
    text=replace(text,'if(game_bound)begin state<=QUIT_WAIT;timer<=0;end else state<=HOME_OPEN;',
        'if(game_bound)begin menu_owned<=0;menu_pause<=0;state<=RUN;end else state<=HOME_OPEN;')
    return text

def prepare(source,out,gba_source):
    base.PROFILES['pce']=(NAMESPACE,0,524288,0,'')
    source,out=Path(source).resolve(),Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'.work') or out.is_relative_to(source):
        raise ValueError('Use a fresh .work output outside source')
    head=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    dirty=subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True)
    if head!=COMMIT or dirty:raise ValueError('Pinned clean upstream checkout required')
    shutil.copytree(source,out,ignore=shutil.ignore_patterns('.git'))
    dest=out/'target/pocket';project=out/'projects'
    top=dest/'core_top.sv';text=top.read_text(encoding='utf8')
    text,count=re.subn(r'^\s*assign cram0_[a-z0-9_]+\s*=.*?;\s*$','',text,flags=re.M)
    if count!=11:raise ValueError('CRAM0 must be fully unused upstream')
    text=replace(text,"32'hF8xxxxxx: begin", "32'hF4xxxxxx: begin bridge_rd_data <= ui_param; end\n            32'hF8xxxxxx: begin")
    text=re.sub(r'(\s+)(\.datatable_addr\s*\(\s*datatable_addr\s*\),)',r'''\1.target_cmd_req(tcmd_req),.target_cmd(tcmd),
            .target_cmd_p0(tcmd_p0),.target_cmd_p1(tcmd_p1),.target_cmd_p2(tcmd_p2),.target_cmd_p3(tcmd_p3),
            .target_cmd_ack(tcmd_ack),.target_cmd_done(tcmd_done),.target_cmd_result(tcmd_result),\1\2''',text,count=1)
    text=replace(text,'wire       RESET = ~(reset_n && core_reset_s);','wire RESET = ~(reset_n && core_reset_s) || ui_reset_s;')
    text=replace(text,'reg  [31:0] reset_timer;','reg [31:0] reset_timer=0;')
    text=replace(text,'reg         temp_reset;','reg temp_reset=0;')
    a=text.index('    wire  [7:0] ioctl_index;');b=text.index('    wire  [7:0] rom_dout;',a)
    text=text[:a]+'''    wire ioctl_wr;
    wire rom_download;
    wire cart_busy;
    wire rom_idle_s,rom_idle;
    wire [31:0] rom_received_s;
    reg [31:0] rom_received_meta=0,rom_received=0;
    wire rom_overrun;
    synch_3 s_rom_load(ui_loading,rom_download,clk_ram);
    synch_3 s_rom_idle(rom_idle_s,rom_idle,clk_74a);
    always @(posedge clk_74a)begin rom_received_meta<=rom_received_s;rom_received<=rom_received_meta;end
    sv_rom_loader sv_rom_input(.clk_bridge(clk_74a),.clk_memory(clk_ram),
        .ready(reset_n && pll_core_locked),.start(ui_new),.active(ui_loading),
        .bridge_wr(bridge_wr),.bridge_endian_little(bridge_endian_little),
        .bridge_addr(bridge_addr),.bridge_wr_data(bridge_wr_data),
        .address(ioctl_addr),.data(ioctl_dout),.write_en(ioctl_wr),.busy(cart_busy),
        .idle(rom_idle_s),.bytes_written(rom_received_s),.overflow(rom_overrun));

'''+text[b:]
    text=replace(text,'    wire        cart_busy;\n','')
    text=replace(text,'    wire        palette_download = (ioctl_index[5:0] == 3) && ioctl_download;\n','')
    text=replace(text,'    assign ioctl_wait = cart_busy & rom_download;\n','')
    text=replace(text,'    always @(posedge clk_sys) begin\n        if (rom_download && ioctl_wr)',
        '    always @(posedge clk_ram) begin\n        if (rom_download && ioctl_wr)')
    text=replace(text,'.ch0_busy   ( cart_busy  )', '''.ch0_busy   ( cart_busy  ),
              .ch1_addr(25'd0),.ch1_rd(1'b0),.ch1_wr(1'b0),.ch1_din(8'd0),
              .ch2_addr(25'd0),.ch2_rd(1'b0),.ch2_wr(1'b0),.ch2_din(8'd0)''')
    # The original video raster and its 1:1 scaler remain intact.
    for port in ('RGB','VS','HS','DE'):
        text,n=re.subn(r'\.o'+port+r'\s*\(\s*video_'+port.lower()+r'\s*\)',f'.o{port} ( console_game_{port.lower()} )',text)
        if n!=1:raise ValueError('Original video output differs: '+port)
    text=replace(text,'.iPRESET   ( ),',".iPRESET   ( 3'd0 ),")
    text=replace(text,'.audio_l    ( supervision_l[15:1] ),',".audio_l    ( ui_owned ? 15'd0 : supervision_l[15:1] ),")
    text=replace(text,'.audio_r    ( supervision_r[15:1] ),',".audio_r    ( ui_owned ? 15'd0 : supervision_r[15:1] ),")
    insertion=base.insert('pce','clk_vid','menu_pixel_ce',1).replace('console_menu menu(','supervision_menu menu(',1)
    insertion=replace(insertion,'.prepare_ready(1\'b1),.load_ready(!ui_loading && ui_settle==0),',
        ".cart_fault(rom_overrun),.prepare_ready(rom_idle && rom_received==ui_cart_size),.load_ready(!ui_loading && ui_settle==0 && rom_idle),")
    insertion=replace(insertion,".io_idle(!ui_loading),.save_capacity(32'd0),",".io_idle(!ui_loading && rom_idle),.save_capacity(32'd0),")
    insertion=replace(insertion,'.enable(cf_menu && !ui_fault),','.enable(cf_menu || !ui_bound || ui_fault),')
    insertion=replace(insertion,'cf_menu || ui_fault','cf_menu || !ui_bound || ui_fault')
    insertion=replace(insertion,'cf_de ? cf_rgb :', 'cf_de ? (ui_fault ? sv_error_rgb:cf_rgb) :')
    insertion+='''
  // Original PLL output1 is 8MHz (upstream comment says 5.1429MHz).
  // Three accepted pixel clocks in four => 6MHz / (374*300) = 53.476Hz.
  reg [1:0] menu_div=0;
  always @(posedge clk_vid)menu_div<=menu_div+1'b1;
  wire menu_pixel_ce=menu_div!=3;
  wire ui_reset_s;
  synch_3 s_ui_reset(ui_reset,ui_reset_s,clk_sys);
  wire [23:0] sv_error_rgb;
  sv_error_pixels error_pixels(.clk(clk_vid),.de(cf_de),.hs(cf_hs),.vs(cf_vs),.skip(cf_skip),.rgb(sv_error_rgb));
'''
    text=text.replace('\nendmodule',insertion+'\nendmodule',1)
    top.write_text(text,encoding='utf8',newline='\n')
    bridge=dest/'core_bridge_cmd.v'
    bridge.write_text(base.target_bridge(bridge.read_text(encoding='utf8')),encoding='utf8',newline='\n')
    (dest/'supervision_menu.sv').write_text(controller(),encoding='utf8',newline='\n')
    target=(ROOT/'experiments/sega_coverflow/target_adapter.sv').read_text(encoding='utf8')
    (dest/'sega_menu_target.sv').write_text(target.replace("32'hF3000000","32'hF4000000"),encoding='utf8',newline='\n')
    for name in ['rom_loader.sv','error_pixels.sv']:shutil.copy2(HERE/name,dest/name)
    sys.path.insert(0,str(ROOT/'experiments/coverflow_shared'))
    from prepare_psram import build
    shared=build(out/'coverflow-generated',gba_source)
    files=['coverflow_geometry.sv','coverflow_psram_view.sv','coverflow_line_fetch16.sv','coverflow_psram.sv',
        'coverflow_psram_cache.sv','coverflow_dpram_ce.v','picker_dpram.v']
    for name in files:shutil.copy2(shared/name,dest/name)
    shutil.copy2(shared/'font_cn.hex',project/'font_cn.hex')
    sys.path.insert(0,str(ROOT/'tools'))
    import build_library
    columns=[0]*320
    for caption,y in [('读取失败',0),('按 A 重试',16)]:
        width,raw,clipped,missing=build_library.columns(caption,build_library.font())
        if clipped or missing:raise ValueError('Resident error text missing glyph')
        for i,n in enumerate(struct.unpack('<512H',raw)[:width]):columns[(320-width)//2+i]|=n<<y
    (project/'sv_error.hex').write_text(''.join(f'{n:08x}\n' for n in columns),encoding='ascii')
    table=out/'platform/pocket/mf_datatable.v'
    table.write_text(table.read_text().replace('"./apf/build_id.mif"','"../platform/pocket/build_id.mif"'),encoding='utf8',newline='\n')
    settings=project/'supervision_pocket.qsf'
    qsf=re.sub(r'^set_global_assignment -name NUM_PARALLEL_PROCESSORS.*$', '',settings.read_text(),flags=re.M)
    qsf+='\nset_global_assignment -name NUM_PARALLEL_PROCESSORS 4\nset_global_assignment -name ENABLE_SIGNALTAP OFF\n'
    for name in files+['supervision_menu.sv','sega_menu_target.sv','rom_loader.sv','error_pixels.sv']:
        kind='SYSTEMVERILOG_FILE' if name.endswith('.sv') else 'VERILOG_FILE'
        qsf+=f'set_global_assignment -name {kind} ../target/pocket/{name}\n'
    settings.write_text(qsf,encoding='utf8',newline='\n')
    manifest={'source_repo':REPO,'source_commit':COMMIT,'namespace':NAMESPACE,
        'video':{'physical_mhz':8,'pixel_enable':'3/4','menu_total':[374,300],'menu_active':[320,288],
            'menu_hz':6000000/374/300,'game_scaler_unchanged':True},
        'save_support':'No persistent save or savestate interface in this upstream; no save slot generated.',
        'inputs':{p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()}}
    (out/'sv-preparation.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
    return out

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['source','out','gba-source']:p.add_argument('--'+key,required=True,type=Path)
    a=p.parse_args();print(prepare(a.source,a.out,a.gba_source))
