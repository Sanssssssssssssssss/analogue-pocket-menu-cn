// SPDX-License-Identifier: MIT
module pm_art_pll(input wire refclk,rst,output wire outclk_0,locked);
altera_pll #(
 .fractional_vco_multiplier("false"),.reference_clock_frequency("74.25 MHz"),
 .operation_mode("normal"),.number_of_clocks(1),
 .output_clock_frequency0("96.0 MHz"),.phase_shift0("0 ps"),.duty_cycle0(50),
 .pll_type("General"),.pll_subtype("General")
) pll(.rst(rst),.outclk(outclk_0),.locked(locked),.fboutclk(),.fbclk(1'b0),.refclk(refclk));
endmodule
