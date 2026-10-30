#!/bin/sh
set -eu
project=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
src="$project/experiments/multi_system"
out="$project/.work/multi-system/rtl"
test -d "$out"
cd "$out"
iverilog -g2012 -s tb_launch_guard -o guard.sim "$src/launch_guard.sv" "$src/tb_launch_guard.sv"
vvp guard.sim > guard.log
iverilog -g2012 -s tb_menu -o menu.sim "$src/menu_shell.sv" "$src/tb_menu.sv"
vvp menu.sim > menu.log
cat guard.log menu.log
