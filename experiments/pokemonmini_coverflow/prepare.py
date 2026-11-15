#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate native Pokemon Mini + Chinese CoverFlow from pinned GPL upstream."""
import argparse,hashlib,importlib.util,json,re,shutil,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
WORK=ROOT/'.work/repair-20261115/pokemonmini'
CONTINUE_WORK=ROOT/'.work/continue-20261116/pokemini'
EXPERIMENTS=ROOT/'experiments'

def private_output(path):
    return any(Path(path).resolve().is_relative_to(root) for root in (WORK,CONTINUE_WORK))
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
ws=load('pm_ws_shared_prepare',EXPERIMENTS/'ws_coverflow/prepare.py')
base,nes,gba,pause,replace=ws.base,ws.nes,ws.gba,ws.pause,ws.replace
def write(path,text):path.write_text(text,encoding='utf8',newline='\n')

def controller():
    s=nes.controller('pmclab',8192,'pm_menu')
    s=replace(s,'rom_bytes<192 || rom_bytes>33554432 || rom_bytes[1:0]!=0',
        'rom_bytes<8704 || rom_bytes>2097152 || rom_bytes[1:0]!=0')
    a,b=s.index('            RTC_OPEN:'),s.index('            LOAD_FINISH:');s=s[:a]+s[b:]
    for op in range(4):s=s.replace(f'command({op},10,',f'command({op},1,')
    s=replace(s,'LOAD_FINISH:begin finish_load<=1;state<=LOAD_DRAIN;timer<=0;end',
        "LOAD_FINISH:if(prepare_ready)begin finish_load<=1;state<=LOAD_DRAIN;timer<=0;end\n"
        "                else if(timer>=TIMEOUT)fail(8'h47);")
    s=gba.controller(s,exit_paths=2,cellram=True,associative=True,cover_recovery=True)
    s=gba.retry_art(s)
    # Shared library stores native configuration/reserved at words 4/5.
    s=replace(s,'4:cf_title_width<=','6:cf_title_width<=')
    s=replace(s,'5:cf_subtitle_width<=','7:cf_subtitle_width<=')
    s=pause.pause_controller(s,1,0x20000000)
    a,b=s.index('            QUIT_RTC_OPENED:'),s.index('            ERROR:');return s[:a]+s[b:]

def top(source):
    s=source
    for signal in ('a','dq','oe_n','we_n','ub_n','lb_n'):
        s,n=re.subn(r'^  assign sram_'+signal+r'\s*=.*?;\n','',s,flags=re.M)
        if n!=1:raise ValueError('Native SRAM is no longer unused')
    s=replace(s,"      32'hF8xxxxxx: begin","      32'hF3xxxxxx: begin bridge_rd_data<=ui_param;end\n      32'hF8xxxxxx: begin")
    s=replace(s,'  reg ioctl_download = 0;\n  reg save_download = 0;',
        '  wire ioctl_download=ui_loading;\n  wire save_download=ui_loading;')
    a=s.index('  always @(posedge clk_74a) begin\n    if (dataslot_requestwrite)')
    b=s.index('  always @(posedge clk_74a or negedge pll_core_locked)',a);s=s[:a]+s[b:]
    s=replace(s,"datatable_data <= 32'h2000;","datatable_data <= ui_registered_save_bytes;")
    s=replace(s,'datatable_addr <= 1 * 2 + 1;','datatable_addr <= 2 * 2 + 1;')
    s=s.replace('  data_loader #(','  pm_data_loader #(')
    s=replace(s,'  ) rom_data_loader (','  ) rom_data_loader (\n      .idle(ui_rom_idle),')
    s=replace(s,'  ) save_data_loader (','  ) save_data_loader (\n      .idle(ui_save_idle),')
    # ROM SRAM controller takes seven 40 MHz clocks; eight per byte permits
    # continuous APF input and retains five clocks of write assertion.
    s=replace(s,'.WRITE_MEM_CLOCK_DELAY(12),','.WRITE_MEM_CLOCK_DELAY(8),',2)
    a=s.index('  ) save_data_loader (');b=s.index('  wire sd_rd;',a)
    before=s[:a];section=s[a:b];after=s[b:]
    before=before[:before.rindex('  pm_data_loader #(')]+before[before.rindex('  pm_data_loader #('):].replace(
        '.WRITE_MEM_CLOCK_DELAY(8)','.WRITE_MEM_CLOCK_DELAY(6)').replace('.WRITE_MEM_EN_CYCLE_LENGTH(5)','.WRITE_MEM_EN_CYCLE_LENGTH(2)')
    section=replace(section,'.clk_memory(clk_mem_40)','.clk_memory(clk_sys_32)');s=before+section+after
    a=s.index('  data_unloader #(');b=s.index('  wire [12:0] sd_buff_addr',a)
    section=s[a:b].replace('.READ_MEM_CLOCK_DELAY(12)','.READ_MEM_CLOCK_DELAY(2)').replace('.clk_memory(clk_mem_40)','.clk_memory(clk_sys_32)')
    s=s[:a]+section+s[b:]
    a=s.index('  pokemonmini pokemonmini (');b=s.index('  ////////////////////////////////////////////////////////////////////////////////////////',a)
    section=s[a:b].replace('.reset_n(reset_n),','.reset_n(reset_n && !ui_reset_s),\n      .menu_pause(ui_pause_s),.menu_paused(ui_paused_s),')
    section,n=re.subn(r'(\.(?:button_\w+|trigger_\w+|dpad_\w+)\()(cont1_key_s\[\d+\])\)',r'\1\2 && !ui_input_block)',section)
    if n!=9:raise ValueError('Native input map changed')
    s=s[:a]+section+s[b:]
    s=replace(s,'      .datatable_addr(datatable_addr),','''      .target_cmd_req(tcmd_req),.target_cmd(tcmd),
      .target_cmd_p0(tcmd_p0),.target_cmd_p1(tcmd_p1),.target_cmd_p2(tcmd_p2),.target_cmd_p3(tcmd_p3),
      .target_cmd_ack(tcmd_ack),.target_cmd_done(tcmd_done),.target_cmd_result(tcmd_result),
      .datatable_addr(datatable_addr),''')
    for port in ('rgb','de','vs','hs'):s=replace(s,f'  assign video_{port} = video_{port}_reg;','')
    s=replace(s,'  assign video_skip = 0;','')
    s=replace(s,'  wire clk_mem_40;','''  wire clk_menu_96,menu_pll_locked;
  pm_art_pll menu_pll(.refclk(clk_74a),.rst(!pll_core_locked),.outclk_0(clk_menu_96),.locked(menu_pll_locked));
  wire clk_mem_40;''')
    insertion=(HERE/'top_insert.sv').read_text()
    cf=(EXPERIMENTS/'gba_coverflow/top_sram.sv').read_text()
    a,b=cf.index('reg [2:0] cf_pixel_div=0;'),cf.index('wire cf_text_we')
    cf=cf[:a]+"wire cf_pixel_ce=1'b1;\n"+cf[b:]
    cf=cf.replace('target_dataslot_read','ui_read').replace('target_dataslot_bridgeaddr','ui_address')
    cf=replace(cf,'.enable(cf_menu && !ui_fault),.hold_gb(ui_owned),',
        '.pause_scene(ui_pause_scene),.enable(cf_menu && !ui_fault),.hold_gb(ui_owned),')
    video=(EXPERIMENTS/'gba_coverflow/video_mux.sv').read_text();video=video[video.index('reg cf_video_owner=1;'):]
    video=video.replace('cf_menu && !ui_fault','cf_menu || ui_fault || ui_pause')
    cf=replace(cf,'.enable(cf_menu && !ui_fault),','.enable(cf_menu || !ui_bound || ui_fault),')
    video=replace(video,'if(cf_video_owner)begin if(cf_vs)',
        'if(ui_reset_v)cf_video_owner<=1;\n    else if(cf_video_owner)begin if(cf_vs)')
    video=replace(video,'cf_de ? cf_rgb :','cf_de ? (ui_fault_v ? pm_error_rgb:cf_rgb) :')
    return replace(s,'  // bridge data slot access',insertion+'\n'+cf+'\n'+video+'\n  // bridge data slot access')

def wrapper(s):
    # The original output register had framebuffer selection, blending,
    # multiplication, and /255 in one 32 MHz path. There are only 256 possible
    # intensities: a combinational truth table preserves every RGB value and
    # the existing output register's exact cycle, without a divider or DSP.
    off=re.search(r"OFF_COLOR\[0:2\] = '\{([^}]+)\}",s)
    on=re.search(r"ON_COLOR\[0:2\] = '\{([^}]+)\}",s)
    def channels(match):
        return [int(v,16) for v in re.findall(r"8'h([\da-fA-F]+)",match[1])]
    light,dark=channels(off),channels(on)
    if len(light)!=3 or len(dark)!=3:raise ValueError('Native LCD colors changed')
    palette='  function [23:0] pm_lcd_color(input [7:0] intensity);\n    case(intensity)\n'
    for intensity in range(256):
        rgb=bytes(((255-intensity)*a+intensity*b)//255 for a,b in zip(light,dark))
        palette+=f"      8'd{intensity}:pm_lcd_color=24'h{rgb.hex()};\n"
    palette+="      default:pm_lcd_color=24'hxxxxxx;\n    endcase\n  endfunction\n\n"
    s=replace(s,'  // Contrast level on light and dark pixel',palette+'  // Contrast level on light and dark pixel')
    a=s.index('      pixel_value_red   <= ({8\'h0, 8\'hFF - pixel_intensity}')
    b=s.index('    end else begin',a)
    s=s[:a]+'      {pixel_value_red,pixel_value_green,pixel_value_blue} <= pm_lcd_color(pixel_intensity);\n'+s[b:]
    s=replace(s,'    input wire reset_n,','    input wire reset_n,menu_pause,\n    output reg menu_paused=0,')
    s=replace(s,'  reg [3:0] clk_prescale = 0;','''  reg pause_armed=0;
  reg [6:0] pause_quiet=0;
  // Do not freeze the BIOS RTC initialization address (AB); finish its EEPROM
  // writes before acknowledging pause. CPU/DMA clock enables then stop together.
  always @(posedge clk_sys_32)begin
    if(!menu_pause || !reset_n)begin pause_armed<=0;pause_quiet<=0;menu_paused<=0;end
    else if(!pause_armed)begin
      if(minx_address_out!=24'hAB && eeprom_write_stage==0 && !eeprom_we_rtc)pause_armed<=1;
    end else if(pause_quiet!=127)pause_quiet<=pause_quiet+1'b1;
    else menu_paused<=1;
  end
  reg [3:0] clk_prescale = 0;''')
    s=replace(s,'.clk_ce_4mhz(&minx_clk_prescale),','.clk_ce_4mhz((&minx_clk_prescale) && !pause_armed),')
    # Initialize and reset the BIOS RTC injection sequencer for each new ROM;
    # prevent a paused address from repeatedly triggering it.
    s=replace(s,'  reg [4:0] eeprom_write_stage;','  reg [4:0] eeprom_write_stage=0;')
    s=replace(s,"    if (minx_address_out == 24'hAB) eeprom_write_stage <= 1;",
        "    if (minx_address_out == 24'hAB && !pause_armed && !reset) eeprom_write_stage <= 1;")
    needle='''    end
  end

  /////////////////////////  BRAM SAVE/LOAD'''
    s=replace(s,needle,'''    end
    if(reset)begin eeprom_write_stage<=0;eeprom_we_rtc<=0;validate_rtc<=0;end
  end

  /////////////////////////  BRAM SAVE/LOAD''')
    return s

def unloader(s):
    # Native responses arrive six 32 MHz cycles apart; the original bridge
    # drained four bytes back-to-back and underflowed its response FIFO.
    s=replace(s,'      apf_data_count  <= 0;','')
    s=replace(s,'          data_send_state <= 0;','          data_send_state <= 0;apf_data_count<=0;')
    s=replace(s,'          data_read_req <= 1;\n          data_send_state <= READ_DATA_DELAY;',
        '          data_read_req <= 0;\n          data_send_state <= 0;')
    # Complete each memory request in five native clocks. Address and EEPROM
    # output still get two clocks before sampling; return to idle as the FIFO
    # write is issued so four bytes fit within one 75-bridge-clock APF interval.
    s=replace(s,'  always @(posedge clk_memory) begin','  always @(posedge clk_memory) begin\n    data_write_req<=0;')
    s=replace(s,'        fifo_data_in <= read_data;','        fifo_data_in <= read_data;\n        data_read_state<=0;')
    return s

def prepare(source,out):
    source,out=Path(source).resolve(),Path(out).resolve()
    if out.exists() or not private_output(out):raise ValueError('Fresh private Mini candidate required')
    frozen=json.loads((HERE/'upstream-files.json').read_text())
    actual={p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file()}
    if actual!={f['path'] for f in frozen['files']}:raise ValueError('Upstream inventory changed')
    for f in frozen['files']:
        if hashlib.sha256((source/f['path']).read_bytes()).hexdigest()!=f['sha256']:raise ValueError(f['path'])
    shutil.copytree(source,out);dest=out/'src/fpga/core';project=out/'src/fpga'
    # Real registers break the native 43 ns combinational divider. CPU cadence
    # and microcode stay identical; check_cpu.py verifies each observed edge.
    cpu=dest/'rtl/s1c88.sv'
    cpu_text=replace(cpu.read_text(),'        alu_flags\n    );','        alu_flags,\n        clk\n    );')
    # Quartus rounds this ROM to 1024 words. Opcodes only address 0..767;
    # explicitly size and initialize the unused physical tail below.
    cpu_text=replace(cpu_text,'translation_rom[0:767]','translation_rom[0:1023]')
    write(cpu,cpu_text)
    alu=dest/'rtl/alu.sv';s=alu.read_text()
    s=replace(s,'    output reg [3:0] flags\n','    output reg [3:0] flags,\n    input clk\n')
    s=replace(s,'    reg [16:0] R_temp;', '''    reg [16:0] R_temp;
    wire [15:0] divide_result;
    wire [3:0] divide_flags;
    pm_divide divider(.clk(clk),.dividend(A),.divisor(B[7:0]),.size(size),
                      .result(divide_result),.flags(divide_flags));''')
    a,b=s.index('            ALUOP_DIV:'),s.index('            ALUOP_MUL:')
    s=s[:a]+'''            ALUOP_DIV:
            begin
                R = divide_result;
                flags = divide_flags;
            end

'''+s[b:]
    write(alu,s);shutil.copy2(HERE/'divide.sv',dest/'pm_divide.sv')
    error=(EXPERIMENTS/'supervision_coverflow/error_pixels.sv').read_text().replace('sv_error','pm_error')
    write(dest/'error_pixels.sv',error)
    sys.path.insert(0,str(ROOT/'tools'))
    import build_library
    columns=[0]*320
    for caption,y in [('读写失败',0),('A 重试  B 返回',16)]:
        width,raw,clipped,missing=build_library.columns(caption,build_library.font())
        if clipped or missing:raise ValueError('Resident error text missing glyph')
        for i,n in enumerate(struct.unpack('<512H',raw)[:width]):columns[(320-width)//2+i]|=n<<y
    (project/'pm_error.hex').write_text(''.join(f'{n:08x}\n' for n in columns),encoding='ascii')
    write(dest/'core_top.v',top((dest/'core_top.v').read_text()))
    write(dest/'main.sv',wrapper((dest/'main.sv').read_text()))
    write(dest/'data_unloader.sv',unloader((dest/'data_unloader.sv').read_text()))
    write(dest/'pm_menu.sv',controller())
    write(dest/'pm_data_loader.sv',ws.native_loader((dest/'data_loader.sv').read_text()).replace('ws_data_loader','pm_data_loader'))
    shutil.copy2(EXPERIMENTS/'ws_coverflow/art_data_loader.sv',dest/'data_loader.sv')
    cmd=dest/'core_bridge_cmd.v';s=base.target_bridge(cmd.read_text())
    write(cmd,s);shutil.copy2(EXPERIMENTS/'sega_coverflow/target_adapter.sv',dest/'pm_target.sv')
    # A separate UI PLL leaves the inherited 4.194755 MHz RTC and all native
    # requested frequencies untouched. Adding 96 MHz to the native fractional
    # VCO changes its legal divider set and was rejected by Quartus.
    shutil.copy2(HERE/'art_pll.sv',dest/'art_pll.sv')
    sys.path.insert(0,str(EXPERIMENTS/'coverflow_shared'));from prepare_assoc import build
    shared=build(out/'coverflow-shared')
    files=['coverflow_geometry.sv','coverflow_assoc_view.sv','coverflow_assoc_cache.sv','coverflow_line_fetch.sv','coverflow_dpram_ce.v','picker_dpram.v']
    for name in files:shutil.copy2(shared/name,dest/name)
    view=dest/'coverflow_assoc_view.sv';write(view,pause.pause_view(view.read_text()))
    shutil.copy2(EXPERIMENTS/'gba_coverflow/sram_cache.sv',dest/'coverflow_sram_cache.sv')
    shutil.copy2(shared/'font_cn.hex',project/'font_cn.hex')
    qsf=project/'ap_core.qsf';s=qsf.read_text()
    s=replace(s,'-name VERILOG_FILE core/core_top.v','-name SYSTEMVERILOG_FILE core/core_top.v')
    s=s.replace('-name ENABLE_SIGNALTAP ON','-name ENABLE_SIGNALTAP OFF')
    for name in [*files,'coverflow_sram_cache.sv','pm_menu.sv','pm_target.sv','pm_data_loader.sv','art_pll.sv','pm_divide.sv','error_pixels.sv']:
        kind='SYSTEMVERILOG_FILE' if name.endswith('.sv') else 'VERILOG_FILE';s+=f'\nset_global_assignment -name {kind} core/{name}'
    for pin in ('sram_a[*]','sram_dq[*]','sram_oe_n','sram_we_n','sram_ub_n','sram_lb_n'):
        s+=f'\nset_instance_assignment -name FAST_OUTPUT_REGISTER ON -to {pin}'
    s+='\nset_instance_assignment -name FAST_INPUT_REGISTER ON -to sram_dq[*]\nset_instance_assignment -name FAST_OUTPUT_ENABLE_REGISTER ON -to sram_dq[*]'
    s+='\nset_global_assignment -name OPTIMIZE_HOLD_TIMING ALL_PATHS\nset_global_assignment -name FITTER_EFFORT "STANDARD FIT"\n'
    write(qsf,s);pause.include_renderer(dest,project,'ap_core.qsf','core')
    pixels=dest/'native_pause_pixels.sv'
    write(pixels,replace(pixels.read_text(),'bitmap [0:1279]','bitmap [0:2047]'))
    # Quartus already fills these unused tails with zero. Make that explicit
    # in the files so fresh compilations need no memory-depth warning waiver.
    for path,depth in [(project/'rom/translation_rom.mem',1024),(project/'native_pause.hex',2048)]:
        lines=path.read_text().splitlines()
        if len(lines)>depth:raise ValueError('Unexpected ROM depth: '+str(path))
        write(path,'\n'.join(lines+['0']*(depth-len(lines)))+'\n')
    sdc=dest/'core_constraints.sdc';limits=gba.SRAM_SDC.replace('ic|mp1|mf_pllbase_inst|sys_pll_i|general[0]','ic|menu_pll|pll|general[0]')
    limits=limits.replace('7 * 9.930 - 4.25 - 55 - 4.25 = 6.01','7 * 10.416 - 4.25 - 55 - 4.25 = 9.41')
    native_sdc=sdc.read_text().rstrip()+" \\\n -group { ic|menu_pll|pll|general[0].gpll~PLL_OUTPUT_COUNTER|divclk }\n"
    write(sdc,native_sdc+limits)
    metadata(out)
    files=[{'path':p.relative_to(out).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.rglob('*')) if p.is_file()]
    write(out/'preparation.json',json.dumps({'upstream':frozen['upstream'],'files':files,'menu_video_hz':6399998/(374*300),'native_save_bytes':8192,'accepted_on_device':False},indent=2)+'\n')
    return out

def metadata(out):
    directory=out/'dist/Cores/agg23.PokemonMini';meta=json.loads((directory/'core.json').read_text())
    meta['core']['metadata'].update(author='pocketlab',shortname='PokemonMini',version='0.1.0-pm.1',date_release='2026-11-15',platform_ids=['pmclab','poke_mini'],description='Chinese CoverFlow. L+R+Select pause. Candidate.')
    meta['core']['cores']=[{'name':'default','id':0,'filename':'poke_mini.rbf_r'}]
    write(directory/'core.json',json.dumps(meta,indent=2)+'\n')
    slots=[{'name':'Menu','id':100,'required':True,'deferload':True,'filename':'menu.bin','parameters':'0x8','extensions':['bin'],'address':'0x70000000','size_maximum':'0x10000000'},
        {'name':'Cartridge','id':0,'required':False,'deferload':True,'parameters':'0x8','extensions':['min'],'address':'0x10000000','size_maximum':'0x200000'},
        {'name':'Save','id':1,'required':False,'deferload':True,'parameters':'0x0','nonvolatile':True,'extensions':['sav'],'address':'0x20000000','size_maximum':'0x2000'}]
    write(directory/'data.json',json.dumps({'data':{'magic':'APF_VER_1','data_slots':slots}},indent=2)+'\n')
    video=json.loads((directory/'video.json').read_text());video['video']['scaler_modes'].append({'width':320,'height':288,'aspect_w':10,'aspect_h':9,'rotation':0,'mirror':0})
    write(directory/'video.json',json.dumps(video,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();print(prepare(a.source,a.out))
