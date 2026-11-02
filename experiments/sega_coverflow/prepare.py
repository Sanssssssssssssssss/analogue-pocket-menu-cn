#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare one independent native Sega machine with the shared CoverFlow UI."""
import argparse,hashlib,json,shutil,struct,sys,zipfile
from pathlib import Path,PurePosixPath
from controller import controller,PROFILES,ROOT,replace
HERE=Path(__file__).resolve().parent
ARCHIVE_SHA='903445e97ba4cd5c52d69fb87f1cfb2f23a53da3d7b341955a2152f833f93bed'
COMMIT='8acc19dcc399950afced528c8ce311174e4f83af'


def extract(archive,out):
    archive,out=Path(archive).resolve(),Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'.work'):raise ValueError('Fresh .work output required')
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=ARCHIVE_SHA:raise ValueError('Pinned Sega archive SHA differs')
    links=[]
    with zipfile.ZipFile(archive) as z:
        prefix=z.namelist()[0].split('/')[0]+'/'
        if sum(i.file_size for i in z.infolist())>100*1024**2:raise ValueError('Archive expansion limit')
        for item in z.infolist():
            if not item.filename.startswith(prefix):raise ValueError('Unexpected archive root')
            rel=item.filename[len(prefix):]
            if not rel:continue
            if '..' in PurePosixPath(rel).parts or '\\' in rel or ':' in rel or rel.startswith('/'):raise ValueError('Unsafe archive path')
            if (item.external_attr>>16)&0o170000==0o120000:
                if rel!='projects/rtl' or z.read(item)!=b'../rtl/upstream':raise ValueError('Unexpected archive link')
                links.append(rel);continue
            dest=out/rel
            if item.is_dir():dest.mkdir(parents=True,exist_ok=True)
            else:dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(z.read(item))
    if links!=['projects/rtl']:raise ValueError('Expected source-layout link missing')
    shutil.copytree(out/'rtl/upstream',out/'projects/rtl')
    return out


def prepare(archive,gba_source,out,platform):
    out=extract(archive,out);namespace,slot,address,mode=PROFILES[platform]
    dest=out/'target/pocket';top=dest/'core_top.v';s=top.read_text(encoding='utf8')
    s=replace(s,"  assign cram0_a                 = 'h0;",'  // Dedicated CoverFlow CellRAM pins are driven by the UI backend.')
    for signal,value in [('dq',"{16{1'bZ}}"),('clk','0'),('adv_n','1'),('cre','0'),('ce0_n','1'),('ce1_n','1'),('oe_n','1'),('we_n','1'),('ub_n','1'),('lb_n','1')]:
        import re
        pattern=r'  assign cram0_'+signal+r'\s*= '+re.escape(value)+r';'
        s,n=re.subn(pattern,'',s);assert n==1,signal
    # Runtime cartridge boot is deliberately outside these ROM-menu entries.
    s=replace(s,'wire cart_powered_s = cart_play_s && cart_report_s[16] && cart_report_s[7:0] == GG_ADAPTER_ID;',
        'wire cart_powered_s = 1\'b0; // Independent ROM-menu entry; original cartridge core is retained.')
    s=replace(s,'  wire savestate_supported = 1;','  wire savestate_supported = 0;')
    for old,new in [('wire tcmd_req = 0;','wire tcmd_req;'),('wire [15:0] tcmd = 0;','wire [15:0] tcmd;')]:s=replace(s,old,new)
    for i in range(4):s=replace(s,f'wire [31:0] tcmd_p{i} = 0;',f'wire [31:0] tcmd_p{i};')
    s=replace(s,'      32\'hF0xxxxxx: begin',"      32'hF3xxxxxx: begin bridge_rd_data<=ui_param;end\n      32'hF0xxxxxx: begin")
    anchor='  // =========================================================================='+'\n  // ROM in\n'
    s=replace(s,anchor,(HERE/'top_insert.sv').read_text(encoding='utf8')+'\n'+anchor)
    s=replace(s,'wire cart_download_74 = gg_download_74 | sms_download_74 | sg_download_74;',
        'wire cart_download_74 = ui_loading;')
    s=replace(s,"reg [1:0] sys_mode_74 = 2'd0;",f"wire [1:0] sys_mode_74 = 2'd{mode};")
    a=s.index('  always @(posedge clk_74a) begin\n    if (dataslot_requestwrite) begin\n      case (dataslot_requestwrite_id)')
    b=s.index('  wire save_download_74',a)
    s=s[:a]+s[b:]
    s=replace(s,"wire save_download_74 = any_download && dataslot_requestwrite_id == 16'd2;",
        'wire save_download_74 = ui_loading;')
    s=replace(s,"wire cheat_download_74 = any_download && dataslot_requestwrite_id == 16'd3;",
        "wire cheat_download_74 = ui_cheat_loading || (any_download && dataslot_requestwrite_id == 16'd3);")
    s=replace(s,'datatable_addr <= 1 * 2 + 1;','datatable_addr <= 2 * 2 + 1;')
    s=replace(s,"datatable_data <= 32'h8000;","datatable_data <= ui_bound ? 32'h8000:32'd0;")
    s=replace(s,'wire core_reset = ~reset_n_s | reset_delay_s | cart_hold;',
        'wire core_reset = ~reset_n_s | reset_delay_s | cart_hold | ui_reset_s;')
    s=replace(s,'  reg cheats_en = 0;','  reg cheats_en = 1; // Effective only after a validated automatic or explicit manual payload.')
    s=replace(s,'.cheats_en      (cheats_en_s),',
        '.cheats_en      (cheats_en_s && (ui_cheat_armed_s || ui_manual_cheat_s) && !cheat_overrun),')
    s=replace(s,'      .cart_download(cart_download_s | cb_busy),',
        '      .cart_download(cart_download_s | cb_busy),\n      .menu_pause(ui_pause_s),.menu_paused(ui_paused_s),.load_idle(ui_rom_idle_s),')
    # The retained SS buffer must never consume the 0x42000000 art stream.
    a=s.index('  savestate_apf ss (');b=s.index('  gg_core gg (',a)
    block=s[a:b]
    block=replace(block,'.bridge_wr           (bridge_wr),',".bridge_wr           (bridge_wr && bridge_addr[27:23]!=5'h04),")
    s=s[:a]+block+s[b:]
    for port in ('rgb','de','hs','vs'):
        import re
        pattern=r'assign video_'+port+r'\s*= video_'+port+'_reg;'
        s,n=re.subn(pattern,f'assign video_{port}=cf_video_owner ? cf_output_{port}:ui_video_{port};',s);assert n==1,port
    for side in ('l','r'):s=replace(s,f'.in_{side} (audio_{side}),',f'.in_{side} (ui_owned_s ? 16\'sd0:audio_{side}),')
    top.write_text(s,encoding='utf8',newline='\n')
    bridge=dest/'core_bridge_cmd.v';s=bridge.read_text(encoding='utf8')
    s=replace(s,'initial begin\n    reset_n <= 0;', '''initial begin
    // Match Cyclone V's default startup levels explicitly in RTL simulation.
    hstate<=ST_IDLE;tstate<=TARG_ST_IDLE;host_cmd_start<=0;
    status_setup_done_1<=0;target_0<=0;host_0<=0;
    reset_n <= 0;''')
    s=replace(s,'end else if(target_cmd_req) begin','end else if(target_cmd_req && reset_n) begin')
    a=s.index('    // target > host command executer');b=s.index('\nend\n',a)
    s=s[:b]+'''
    // Stop during file IO cannot leave an old target operation owning the
    // bridge on the next Run. Initial setup's Ready handshake still works in
    // reset; only a running-to-stopped transition cancels an admitted IO.
    if(reset_n && hstate==ST_PARSE && host_cmd==16'h0010)begin
        tstate<=TARG_ST_IDLE;target_0<=0;
        target_cmd_ack<=0;target_cmd_done<=0;target_cmd_result<=0;
    end
'''+s[b:]
    bridge.write_text(s,encoding='utf8',newline='\n')
    core=out/'rtl/gg/gg_core.sv';s=core.read_text(encoding='utf8')
    s=replace(s,'    input  wire        reset,', '    input wire menu_pause,\n    output reg menu_paused=0,\n    output wire load_idle,\n    input  wire        reset,')
    s=replace(s,'wire rom_writing = (wstate != 2\'d0) | ~romq_empty;',
        "wire rom_writing = (wstate != 2'd0) | ~romq_empty;\nassign load_idle=!rom_writing;\nreg [4:0] pause_settle=0;\nalways @(posedge clk_sys)begin\n    if(!menu_pause)begin pause_settle<=0;menu_paused<=0;end\n    else if(pause_settle<16)pause_settle<=pause_settle+1'b1;\n    else menu_paused<=1;\nend\nwire freeze_machine=ss_freeze || menu_pause;")
    s=replace(s,"ss_freeze ? 1'b0 : ce_cpu","freeze_machine ? 1'b0 : ce_cpu")
    s=replace(s,"ss_freeze ? 1'b0 : ce_vdp","freeze_machine ? 1'b0 : ce_vdp")
    s=replace(s,"ss_freeze ? 1'b0 : ce_pix_r","freeze_machine ? 1'b0 : ce_pix_r")
    s=replace(s,"ss_freeze ? 1'b0 : ce_sp","freeze_machine ? 1'b0 : ce_sp")
    core.write_text(s,encoding='utf8',newline='\n')
    (dest/'sega_menu.sv').write_text(controller(platform),encoding='utf8',newline='\n')
    pixels=(ROOT/'experiments/gba_menu/gba_menu_pixels.sv').read_text()
    pixels=replace(pixels,'module gba_menu_pixels (','module sega_menu_pixels (')
    pixels=replace(pixels,'bridge_addr[31:28]==5','bridge_addr[31:28]==8')
    (dest/'sega_menu_pixels.sv').write_text(pixels,encoding='utf8',newline='\n')
    pause=(ROOT/'experiments/nes_menu/menu_video.sv').read_text(encoding='utf8')
    # Native Sega scaler 0 is 160x144. The pause/error raster is 256x240,
    # so it needs its own slot 5 rather than inheriting the game's slot 0.
    pause=replace(pause,"rgb<=!inside_q ? 24'd0 : fault ?",
        "rgb<=!de_q ? ((!hs_q && !vs_q) ? 24'h00A000:24'd0) : !inside_q ? 24'd0 : fault ?")
    (dest/'menu_video.sv').write_text(pause,encoding='utf8',newline='\n')
    shutil.copy2(HERE/'target_adapter.sv',dest/'sega_menu_target.sv')
    sys.path.insert(0,str(ROOT/'experiments/coverflow_shared'))
    from prepare_psram import build
    shared=build(ROOT/'.work/coverflow-delivery'/('sega-'+out.name),gba_source)
    files=['coverflow_geometry.sv','coverflow_psram_view.sv','coverflow_line_fetch16.sv','coverflow_psram.sv','coverflow_psram_cache.sv','coverflow_dpram_ce.v','picker_dpram.v']
    for name in files:shutil.copy2(shared/name,dest/name)
    shutil.copy2(shared/'font_cn.hex',out/'projects/font_cn.hex')
    with (dest/'core.qip').open('a',encoding='utf8',newline='\n') as f:
        for name in files+['sega_menu.sv','sega_menu_pixels.sv','menu_video.sv','sega_menu_target.sv']:
            f.write('set_global_assignment -name '+('SYSTEMVERILOG_FILE' if name.endswith('.sv') else 'VERILOG_FILE')+' [file join $::quartus(qip_path) "'+name+'"]\n')
    # Match the actual Quartus 22.1 build inputs: remove the upstream's
    # redundant/default 25.1 settings, retain all pin/clock/SDC constraints.
    # The packager checks all four 0/85 C slow/fast timing corners explicitly.
    qsf=out/'projects/gg_pocket.qsf';settings=qsf.read_text(encoding='utf8')
    for line in ('NUM_PARALLEL_PROCESSORS 6','TIMING_ANALYZER_MULTICORNER_ANALYSIS ON',
        'MIN_CORE_JUNCTION_TEMP 0','MAX_CORE_JUNCTION_TEMP 85',
        'POWER_PRESET_COOLING_SOLUTION "23 MM HEAT SINK WITH 200 LFPM AIRFLOW"',
        'POWER_BOARD_THERMAL_MODEL "NONE (CONSERVATIVE)"','ENABLE_SIGNALTAP OFF'):
        settings=replace(settings,'set_global_assignment -name '+line+'\n','')
    qsf.write_text(settings+'\nset_global_assignment -name NUM_PARALLEL_PROCESSORS 4\n',encoding='utf8',newline='\n')
    sys.path.insert(0,str(ROOT/'tools'));import build_library as gb
    columns=[0]*240
    for line,y in [('操作失败',0),('A 重试　B 返回',32)]:
        width,raw,_,unknown=gb.columns(line,gb.font());assert not unknown
        for i,v in enumerate(struct.unpack('<512H',raw)[:width]):columns[(240-width)//2+i]|=v<<y
    (out/'projects/gba_menu_error.hex').write_text(''.join(f'{v:016x}\n' for v in columns),encoding='utf8',newline='\n')
    (out/'menu-preparation.json').write_text(json.dumps({'platform':platform,'namespace':namespace,'rom_slot':slot,'rom_address':hex(address),
        'source_commit':COMMIT,'archive_sha256':ARCHIVE_SHA,'display':'Shared accepted CoverFlow; dedicated unused CellRAM, native 5.369 MHz video clock',
        'scope':'Offline native core candidate; full compilation/timing/device checks required','memories_sleep':False,'cartridge_play':False},indent=2)+'\n',encoding='utf8',newline='\n')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',required=True);p.add_argument('--gba-source',required=True)
    p.add_argument('--platform',choices=PROFILES,required=True);p.add_argument('--out',required=True);a=p.parse_args()
    print(prepare(a.archive,a.gba_source,a.out,a.platform))
