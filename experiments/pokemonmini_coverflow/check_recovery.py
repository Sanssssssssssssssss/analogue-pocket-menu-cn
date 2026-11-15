#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Use actual APF commands to test resident errors and Stop/Run ownership."""
import argparse,importlib.util,json
from pathlib import Path
spec=importlib.util.spec_from_file_location('pm_recovery_boot',Path(__file__).with_name('check_boot.py'))
boot=importlib.util.module_from_spec(spec);spec.loader.exec_module(boot)

def prepare(candidate,out,intel_model):
    run=boot.prepare(candidate,out,intel_model);out=run.parent
    p=out/'tb.sv';s=p.read_text(encoding='utf8')
    s=s.replace('    integer menu_page=0,folder_opens=0;',
        '    integer menu_page=0,folder_opens=0;\n    reg fail_first=1,read_failed=0;\n    integer error_ink=0,fault_frames=0;\n'
        '    always @(posedge clk_vid)begin if(ui_fault_v && video_de && video_rgb==24\'heeeee8)error_ink=error_ink+1; if(ui_fault_v && video_vs)fault_frames=fault_frames+1; end')
    s=s.replace('                for(at=0;at<size;at=at+4)begin',
        '                read_failed=fail_first;fail_first=0;\n                for(at=0;!read_failed && at<size;at=at+4)begin')
    s=s.replace("            write_word(32'hf8001000,32'h6f6b0000);operations=operations+1;",
        "            write_word(32'hf8001000,read_failed ? 32'h6f6b0004:32'h6f6b0000);read_failed=0;operations=operations+1;")
    s=s.replace('if(ui_fault || cf_fetch_fault || cf_underrun)','if(cf_fetch_fault || cf_underrun)')
    a=s.index('    initial begin\n        wait(ui_state==13')
    s=s[:a]+'''    initial begin
        wait(ui_fault);wait(fault_frames==3);
        if(error_ink<100 || !ui_reset || ui_bound || !cf_video_owner)
            $fatal(1,"Resident error missing or game released: ink=%0d code=%h",error_ink,ui_fault_code);
        $display("PASS missing header: resident Chinese error visible without any downloaded art; glyph pixels=%0d",error_ink);
        @(negedge clk_74a);cont1_key=32'h10;repeat(4)@(negedge clk_74a);cont1_key=0;
        wait(ui_state==13 && cf_level!=0 && physical_writes==45568);
        repeat(200)@(negedge clk_74a);
        // Model a running, bound game whose VS stops. The APF Stop/Run path and
        // real menu/video logic are exercised; no native CPU is in this fixture.
        force ui_bound=1;force ui_reset=0;force ui_owned=0;force cf_menu=0;
        wait(!cf_video_owner);
        if(ui_registered_save_bytes!=8192)$fatal(1,"Save size not registered for game");
        host_command(16'h10);
        release ui_bound;release ui_reset;release ui_owned;release cf_menu;
        repeat(30)@(posedge clk_vid);
        if(!cf_video_owner || !ui_reset || ui_registered_save_bytes!=8192)
            $fatal(1,"Stop failed to regain video or preserve save size");
        host_command(16'h11);
        wait(ui_state==13 && cf_level!=0 && physical_writes>=91136);
        if(ui_fault || !cf_video_owner || ui_registered_save_bytes!=8192)$fatal(1,"Second Run failed");
        $display("PASS actual APF Stop/Run: menu reclaims video with native VS=0, root reloads, prior 8192-byte save size remains registered");
        $finish;
    end
    initial begin #(64'd2000000000);$fatal(1,"recovery watchdog state=%d code=%h owner=%b",ui_state,ui_fault_code,cf_video_owner);end
endmodule
'''
    p.write_text(s,encoding='utf8',newline='\n')
    scope=json.loads((out/'scope.json').read_text());scope.update(resident_error_without_art=True,APF_Stop_Run=True,running_game_signals_forced_for_ownership=True)
    (out/'scope.json').write_text(json.dumps(scope,indent=2)+'\n',encoding='utf8')
    return run

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('candidate','out','intel-model'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();print(prepare(a.candidate,a.out,a.intel_model))
