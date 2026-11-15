// SPDX-License-Identifier: MIT
// The menu boot harness exercises raw APF requests. Slot-table host indexing
// and native memory sizing are covered separately by metadata/lifecycle checks.
module mf_datatable(input [9:0] address_a,address_b,input clock_a,clock_b,
 input [31:0] data_a,data_b,input wren_a,wren_b,output [31:0] q_a,q_b);
 assign q_a=0;assign q_b=0;
endmodule
