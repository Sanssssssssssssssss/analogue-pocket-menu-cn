// SPDX-License-Identifier: MIT
// CPS2's game reset is independent of the SPI/menu transport.
wire ui_read,ui_write,ui_open,ui_flush,ui_done,ui_reset,ui_new,ui_finish,ui_bound,ui_fault,ui_show;
wire ui_owned,ui_pause,ui_frame_request;
wire [2:0] ui_error;
wire [15:0] ui_slot;
wire [31:0] ui_offset,ui_address,ui_length,ui_param,ui_mode,ui_buttons,ui_dip;
wire [7:0] ui_state,ui_fault_code,ui_first_fault;
wire [10:0] ui_selected;
wire tcmd_req,tcmd_ack,tcmd_done;
wire [15:0] tcmd,tcmd_result;
wire [31:0] tcmd_p0,tcmd_p1,tcmd_p2,tcmd_p3;
wire [31:0] bridge_addr={sys_addr,2'b00};
wire [31:0] bridge_wr_data=sys_dout;
wire bridge_wr=sys_wr,bridge_rd=sys_rd,bridge_endian_little=1'b0;
wire transport_reset=!rst_req_n;
reg ui_loading=0;
reg [19:0] ui_settle=0;
always @(posedge clk_rom) begin
    if(transport_reset || ui_fault)begin ui_loading<=0;ui_settle<=0;end
    else if(ui_new)begin ui_loading<=1;ui_settle<=0;end
    else if(ui_finish)begin ui_loading<=0;ui_settle<=20'd96000;end
    else if(ui_settle!=0)ui_settle<=ui_settle-1'b1;
end

wire [7:0] host_index;
assign ioctl_index=ui_loading ? (ui_address==0 && (ui_slot==1 || ui_slot==2) ? ui_slot[7:0] : 8'hff)
                              : (ui_bound || host_index==IDX_CRT ? host_index : 8'hff);

reg [1:0] cf_div=0;
always @(posedge menu_clk) cf_div<=cf_div+1'b1;
wire cf_pixel_ce=cf_div==0;

// CoverFlow transport and renderer are inserted here from the common backend.
// SHARED_RENDERER

// RGB and DE hold for four menu clocks. Sync pulses hold for one menu clock.
// The toggle and pixel bus cross together to the 96 MHz serializer.
wire [26:0] cf_pixel_bus;
wire cf_half;
reg cf_half_d=0;
always @(posedge clk_sys) cf_half_d<=cf_half;
wire cf_half_pixel_ce=cf_half!=cf_half_d;
jtframe_sync #(.W(28)) menu_pixels(
    .clk_in(menu_clk),.clk_out(clk_sys),
    .raw({cf_div[1],cf_rgb,cf_de,cf_hs,cf_vs}),.sync({cf_half,cf_pixel_bus}));

reg cf_video_owner=1;
reg [2:0] cf_game_ready=0;
reg cf_game_vs=0;
always @(posedge clk_sys) begin
    cf_game_ready<={cf_game_ready[1:0],ui_bound};
    cf_game_vs<=logo_vs;
    if(logo_vs && !cf_game_vs) cf_video_owner<=!cf_game_ready[2];
    else if(cf_pixel_bus[0] && !cf_game_ready[2]) cf_video_owner<=1;
end

cps2_menu #(.TIMEOUT(34'd16000000000),.SETTLE_CYCLES(20'd96000)) menu(
    .clk(clk_rom),.ready(rst_req_n),.buttons({16'b0,cont1_key}),
    .bridge_wr(bridge_wr),.bridge_rd(bridge_rd),.bridge_endian_little(bridge_endian_little),
    .bridge_addr(bridge_addr),.bridge_wr_data(bridge_wr_data),.param_rd_data(ui_param),
    .t_read(ui_read),.t_write(ui_write),.t_open(ui_open),.t_flush(ui_flush),
    .t_slot(ui_slot),.t_offset(ui_offset),.t_address(ui_address),.t_length(ui_length),
    .t_done(ui_done),.t_error(ui_error),.frame_ack(1'b0),.frame_started(1'b0),
    .frame_valid(1'b0),.frame_fault(1'b0),.visible(cf_menu && cf_level!=0),
    .prepare_ready(1'b1),.load_ready(!ui_loading && ui_settle==0),.io_idle(!ui_loading),.save_capacity(32'd128),
    .cf_want_art(cf_want),.cf_wanted_game(cf_wanted),.cf_anim(cf_anim),.cf_frame_tick(cf_tick),
    .cf_mem_idle(cf_view_idle && cf_backend_idle),.cf_fetch_fault(cf_fault),.cf_upload_ready(cf_uploaded),
    .cf_level(cf_level),.cf_title_level(cf_title_level),.cf_menu(cf_menu),.cf_go(cf_go),.cf_direction(cf_direction),
    .cf_invalidate(cf_invalidate),.cf_commit(cf_commit),.cf_generation(cf_generation),.cf_loaded_game(cf_loaded),
    .cf_count(cf_count),.cf_level_target(cf_target),.cf_title_target(cf_title_target),
    .cf_title_width(cf_width),.cf_subtitle_width(cf_subwidth),
    .frame_request(ui_frame_request),.menu_owned(ui_owned),.menu_show(ui_show),.menu_reset(ui_reset),.menu_pause(ui_pause),
    .new_load(ui_new),.finish_load(ui_finish),.game_bound(ui_bound),.fault(ui_fault),
    .fault_code(ui_fault_code),.first_fault_code(ui_first_fault),.state(ui_state),.selected(ui_selected),
    .core_mode(ui_mode),.button_map(ui_buttons),.dip_switches(ui_dip));

sega_menu_target menu_target(.clk(clk_rom),.ready(rst_req_n),.read_request(ui_read),.write_request(ui_write),
    .open_request(ui_open),.flush_request(ui_flush),.slot(ui_slot),.offset(ui_offset),.address(ui_address),.length(ui_length),
    .complete(ui_done),.error(ui_error),.raw_request(tcmd_req),.raw_command(tcmd),.p0(tcmd_p0),.p1(tcmd_p1),.p2(tcmd_p2),.p3(tcmd_p3),
    .raw_ack(tcmd_ack),.raw_done(tcmd_done),.raw_result(tcmd_result));
