#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Isolated menu-only resource probe; never an installable Pocket bitstream."""
import argparse
from pathlib import Path
import shutil

p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args()
out=Path(a.out)
if out.exists():raise ValueError('Use a fresh build folder')
out.mkdir(parents=True)
shutil.copy2(Path(__file__).with_name('menu_shell.sv'),out/'menu_shell.sv')
(out/'menu_probe.qpf').write_text('QUARTUS_VERSION = "22.1"\nPROJECT_REVISION = "menu_probe"\n')
(out/'menu_probe.qsf').write_text('''set_global_assignment -name FAMILY "Cyclone V"
set_global_assignment -name DEVICE 5CEBA4F23C8
set_global_assignment -name TOP_LEVEL_ENTITY menu_shell
set_global_assignment -name SYSTEMVERILOG_FILE menu_shell.sv
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
set_global_assignment -name SDC_FILE menu_probe.sdc
set_global_assignment -name NUM_PARALLEL_PROCESSORS 2
set_location_assignment PIN_V15 -to clk
set_instance_assignment -name IO_STANDARD "3.3-V LVCMOS" -to clk
''')
ports = ['reset','buttons[*]','page_request','page[*]','page_write','page_address[*]',
         'page_word[*]','page_commit','page_ready','launch_request','launch_platform[*]',
         'launch_entry[*]','launch_failed','rgb[*]','de','hs','vs','selected[*]']
with (out/'menu_probe.qsf').open('a') as f:
    for port in ports: f.write(f'set_instance_assignment -name VIRTUAL_PIN ON -to {port}\n')
(out/'menu_probe.sdc').write_text('''create_clock -name menu_clk -period 10.000 [get_ports clk]
derive_clock_uncertainty
set_input_delay -clock menu_clk -max 0.0 [remove_from_collection [all_inputs] [get_ports clk]]
set_input_delay -clock menu_clk -min 0.0 [remove_from_collection [all_inputs] [get_ports clk]]
set_output_delay -clock menu_clk -max 0.0 [all_outputs]
set_output_delay -clock menu_clk -min 0.0 [all_outputs]
''')
