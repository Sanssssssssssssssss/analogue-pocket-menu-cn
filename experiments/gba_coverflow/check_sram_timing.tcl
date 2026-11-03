# SPDX-License-Identifier: MIT
# Run after a full fit, from src/fpga/build. Data delays exclude clock insertion.
project_open ap_core
create_timing_netlist
read_sdc
set output [open ../../../sram-io.tsv w]
puts $output "corner\tdirection\tfrom\tto\tdata_ns"
set regs [get_registers {*cf_images*}]
set inputs [get_registers {*cf_images*pin_input*}]
set ports [get_ports {sram_a[*] sram_dq[*] sram_oe_n sram_we_n sram_ub_n sram_lb_n}]
if {[get_collection_size $ports] != 37 || [get_collection_size $inputs] != 16} {
    error "Incomplete SRAM I/O endpoints"
}
foreach_in_collection corner [get_available_operating_conditions] {
    set_operating_conditions $corner
    update_timing_netlist
    foreach direction {out in} {
        if {$direction eq "out"} {set from $regs;set to $ports} else {
            set from [get_ports {sram_dq[*]}];set to $inputs
        }
        # Enumerate every register/port pair, including separate OE/data paths.
        # Standard 22.1 has no data-delay sorting flag. Inspect the delay of
        # every pair instead, and reject a potentially truncated collection.
        set paths [get_timing_paths -setup -pairs_only -from $from -to $to -npaths 65536 -nworst 65536]
        if {[get_collection_size $paths] == 0 || [get_collection_size $paths] >= 65536} {
            error "Missing or truncated SRAM data paths"
        }
        foreach_in_collection path $paths {
            set a [get_node_info -name [get_path_info -from $path]]
            set b [get_node_info -name [get_path_info -to $path]]
            puts $output "$corner\t$direction\t$a\t$b\t[get_path_info -data_delay $path]"
        }
    }
}
close $output
project_close
