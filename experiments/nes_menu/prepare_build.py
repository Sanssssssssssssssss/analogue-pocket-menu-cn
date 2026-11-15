#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare an isolated NES visual-menu core from a SHA-pinned upstream ZIP."""
import argparse,hashlib,importlib.util,json,re,shutil,sys,zipfile
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('gba_prepare',ROOT/'experiments/gba_menu/prepare_build.py')
gba_prepare=importlib.util.module_from_spec(spec);spec.loader.exec_module(gba_prepare)
replace=gba_prepare.replace

ARCHIVE_SHA='8699f04685f156d2887712d7f148623419b94c2739c3e4981ebb795a65ed6c0f'

def controller(namespace='neslab',save_capacity=262144,module='nes_menu'):
    if len(namespace)!=6 or not namespace.isascii() or not namespace.isalpha():raise ValueError('Expected six ASCII namespace letters')
    s=(ROOT/'experiments/gba_menu/gba_menu.sv').read_text(encoding='utf8')
    s=replace(s,'module gba_menu #(',f'module {module} #(')
    s=replace(s,"parameter [19:0] SETTLE_CYCLES=20'd7400,","parameter [19:0] SETTLE_CYCLES=20'd74000,")
    words=('/Assets/'+namespace+'/common/menu.bin\0').encode().ljust(256,b'\0')
    function='    function automatic [31:0] root_word(input [5:0] n);\n        case(n)\n'
    for i in range(8):function+=f"            {i}:root_word=32'h{words[4*i:4*i+4].hex()};\n"
    function+='            default:root_word=0;\n        endcase\n    endfunction'
    s,n=re.subn(r'    function automatic \[31:0\] root_word.*?    endfunction',lambda m:function,s,count=1,flags=re.S);assert n==1
    prefix=('/Saves/'+namespace+'/common/').encode()
    function='    function automatic [7:0] save_prefix(input [4:0] n);\n        case(n)\n'
    for i,b in enumerate(prefix):function+=f"            {i}:save_prefix=8'h{b:02x};\n"
    function+="            default:save_prefix=\"/\";\n        endcase\n    endfunction"
    s,n=re.subn(r'    function automatic \[7:0\] save_prefix.*?    endfunction',lambda m:function,s,count=1,flags=re.S);assert n==1
    s=s.replace('command(1,1,0,PARAM,0,ROM_OPENED)','command(1,0,0,PARAM,0,ROM_OPENED)')
    s=s.replace("command(0,1,0,32'h10000000,rom_bytes,ROM_READ)","command(0,0,0,32'h10000000,rom_bytes,ROM_READ)")
    s=replace(s,'if(save_capacity!=65536 && save_capacity!=131072)',f"if(save_capacity!={save_capacity})")
    # NES previews use fully seeded, isolated save files. Missing files are an error,
    # avoiding reliance on unspecified fresh FAT allocation contents.
    s=replace(s,"else if(result==3)state<=SAVE_CREATE;else fail(8'h40);","else fail(8'h40);")
    s=replace(s,"SAVE_READ_DONE:if(result!=0)fail(8'h42);else state<=RTC_OPEN;",
                 "SAVE_READ_DONE:if(result!=0)fail(8'h42);else state<=LOAD_FINISH;")
    start=s.index('            QUIT_SAVE_FLUSHED:');end=s.index('            QUIT_RTC_OPENED:',start)
    s=s[:start]+'''            QUIT_SAVE_FLUSHED:if(result!=0)fail(8'h54);else begin
                    game_bound<=0;menu_reset<=1;menu_pause<=0;menu_show<=0;timer<=0;state<=RECORD_REQ;
                end
'''+s[end:]
    return s

def extract_source(archive,out,expected_sha):
    archive,out=Path(archive).resolve(),Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'.work'):raise ValueError('Fresh output under .work required')
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=expected_sha:raise ValueError('Upstream archive SHA mismatch')
    with zipfile.ZipFile(archive) as z:
        if sum(x.file_size for x in z.infolist())>=300*1024**2:raise ValueError('Upstream archive too large')
        prefix=z.namelist()[0].split('/')[0]+'/'
        for item in z.infolist():
            if not item.filename.startswith(prefix):raise ValueError('Unexpected archive root')
            rel=item.filename[len(prefix):]
            if not rel:continue
            if '..' in PurePosixPath(rel).parts or '\\' in rel or ':' in rel or rel.startswith('/'):raise ValueError('Unsafe archive path')
            if (item.external_attr>>16)&0o170000==0o120000:raise ValueError('Archive links refused')
            dst=out/rel
            if item.is_dir():dst.mkdir(parents=True,exist_ok=True)
            else:dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(z.read(item))
    return out

def prepare(archive,out):
    out=extract_source(archive,out,ARCHIVE_SHA)
    core=out/'target/pocket/core_top.v';s=core.read_text(encoding='utf8')
    insertion=(HERE/'top_insert.sv').read_text(encoding='utf8')
    s=replace(s,'  // bridge data slot access',insertion+'\n  // bridge data slot access')
    s=replace(s,'  wire savestate_supported = 1;','  wire savestate_supported = 0;')
    start=s.index('  save_state_controller save_state_controller (')
    end=s.index('\n  );',start)+len('\n  );')
    s=s[:start]+'''  // Preview supports ordinary saves. Memories/sleep remain in the original core.
  assign ss_save=0;assign ss_load=0;assign ss_dout=0;assign ss_ack=0;
  assign save_state_bridge_read_data=0;
  assign savestate_start_ack=0;assign savestate_start_busy=0;assign savestate_start_ok=0;assign savestate_start_err=1;
  assign savestate_load_ack=0;assign savestate_load_busy=0;assign savestate_load_ok=0;assign savestate_load_err=1;
'''+s[end:]
    s=replace(s,'      .datatable_addr(datatable_addr),','''      .target_dataslot_read(ui_read),.target_dataslot_write(ui_write),
      .target_dataslot_flush(ui_flush),.target_dataslot_getfile(1'b0),
      .target_dataslot_openfile(ui_open),.target_dataslot_done(ui_done),.target_dataslot_err(ui_error),
      .target_dataslot_id(ui_slot),.target_dataslot_slotoffset(ui_offset),
      .target_dataslot_bridgeaddr(ui_address),.target_dataslot_length(ui_length),
      .target_buffer_param_struct(32'hF3000000),.target_buffer_resp_struct(32'd0),
      .datatable_addr(datatable_addr),''')
    s=replace(s,"      32'hF8xxxxxx: begin", "      32'hF3xxxxxx: begin bridge_rd_data <= ui_param; end\n      32'hF8xxxxxx: begin")
    s=replace(s,'wire ioctl_download = is_downloading && dataslot_requestwrite_id == 0;','wire ioctl_download = ui_loading;')
    s=replace(s,"      datatable_data <= has_save ? 32'h40_000 : 32'h0;","      datatable_data <= ui_bound ? 32'h40000 : 32'h0;")
    s=replace(s,'datatable_addr <= 1 * 2 + 1;','datatable_addr <= 2 * 2 + 1;')
    s=replace(s,'.external_reset(external_reset_s || prev_region != region_s || pll_reset),',
                 '.external_reset(external_reset_s || prev_region != region_s || pll_reset || ui_reset_s),\n      .menu_pause(ui_pause_s),.menu_paused(ui_paused_s),')
    s=replace(s,'.is_downloading  (is_downloading),','.is_downloading  (ui_loading),')
    for port in ('de','hs','vs','rgb'):s=replace(s,f'assign video_{port} = video_{port}_reg;',f'assign video_{port} = ui_video_{port};')
    core.write_text(s,encoding='utf8',newline='\n')
    nes=out/'rtl/nes_top.sv';s=nes.read_text(encoding='utf8')
    s=replace(s,'input wire external_reset,','input wire external_reset,\n    input wire menu_pause,output wire menu_paused,')
    s=replace(s,'pausecore <= sleep_savestate;','pausecore <= sleep_savestate || menu_pause;')
    s=replace(s,'wire                                                         corepaused;',
        'wire                                                         corepaused;\n  assign menu_paused=corepaused;')
    nes.write_text(s,encoding='utf8',newline='\n')
    cmd=out/'target/pocket/core_bridge_cmd.v';s=cmd.read_text(encoding='utf8')
    s=replace(s,'input   wire            target_dataslot_read,','input wire target_dataslot_flush,\ninput   wire            target_dataslot_read,')
    s=replace(s,'reg             target_dataslot_read_1, target_dataslot_read_queue;',
        'reg target_dataslot_flush_1=0,target_dataslot_flush_queue=0;\n    reg             target_dataslot_read_1, target_dataslot_read_queue;')
    s=replace(s,'target_dataslot_read_1 <= target_dataslot_read;',
        'target_dataslot_flush_1<=target_dataslot_flush;\n    if(target_dataslot_flush && !target_dataslot_flush_1)target_dataslot_flush_queue<=1;\n    target_dataslot_read_1 <= target_dataslot_read;')
    s=replace(s,'end else if(target_dataslot_getfile_queue) begin',
        "end else if(target_dataslot_flush_queue) begin\n            target_dataslot_flush_queue<=0;target_0[15:0]<=16'h0188;target_20<=target_dataslot_id;\n            tstate<=TARG_ST_DATASLOTOP;\n        end else if(target_dataslot_getfile_queue) begin")
    cmd.write_text(s,encoding='utf8',newline='\n')
    dest=out/'target/pocket';(dest/'nes_menu.sv').write_text(controller(),encoding='utf8',newline='\n')
    for file,source in [('gba_menu_pixels.sv',ROOT/'experiments/gba_menu/gba_menu_pixels.sv'),('menu_video.sv',HERE/'menu_video.sv')]:shutil.copy2(source,dest/file)
    with (dest/'core.qip').open('a',encoding='utf8') as f:
        for name in ['nes_menu.sv','gba_menu_pixels.sv','menu_video.sv']:
            f.write(f'\nset_global_assignment -name SYSTEMVERILOG_FILE [file join $::quartus(qip_path) "{name}"]\n')
    # Quartus runs from projects/; preserve the upstream build-ID generator.
    table=out/'platform/pocket/mf_datatable.v';s=table.read_text(encoding='utf8')
    s=replace(s,'altsyncram_component.init_file = "./build_id.mif",','altsyncram_component.init_file = "../platform/pocket/build_id.mif",')
    table.write_text(s,encoding='utf8',newline='\n')
    palette=out/'rtl/upstream/video.sv';s=palette.read_text(encoding='utf8')
    s=replace(s,'"rtl/tao.mif"','"../rtl/upstream/tao.mif"')
    palette.write_text(s,encoding='utf8',newline='\n')
    sys.path.insert(0,str(ROOT/'tools'))
    import build_library
    lines=['操作失败','A 重试　B 返回']
    columns=[0]*240
    for line,y in zip(lines,[0,32]):
        width,raw,_,missing=build_library.columns(line,build_library.font());assert not missing
        import struct
        values=struct.unpack('<512H',raw)
        for i in range(width):columns[(240-width)//2+i]|=values[i]<<y
    (out/'projects/gba_menu_error.hex').write_text(''.join(f'{x:016x}\n' for x in columns))
    (out/'menu-preparation.json').write_text(json.dumps({'upstream_archive_sha256':ARCHIVE_SHA,
        'scope':'NES-only native menu candidate; no firmware/card access; full compilation and device acceptance required'},indent=2)+'\n')
    return out

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    print(prepare(a.archive,a.out))
