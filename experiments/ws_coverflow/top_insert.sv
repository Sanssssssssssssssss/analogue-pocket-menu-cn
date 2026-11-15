  // The original native SDRAM bus and display modes remain dedicated to WS.
  wire clk_sys=clk_mem_110_592,clk_vid=clk_vid_3_75;
  wire [23:0] cf_game_rgb=video_rgb_reg;
  wire cf_game_de=video_de_reg,cf_game_hs=video_hs_reg,cf_game_vs=video_vs_reg,cf_game_skip=1'b0;
  wire ui_read,ui_write,ui_open,ui_flush,ui_done;
  wire [2:0] ui_error,ui_pause_scene;
  wire [15:0] ui_slot;
  wire [31:0] ui_offset,ui_address,ui_length,ui_param,ui_config,ui_expected_save,ui_native_save;
  wire [1:0] ui_bios;
  wire ui_owned,ui_show,ui_reset,ui_pause,ui_new,ui_finish,ui_bound,ui_fault,ui_request;
  // APF may upload ordinary progress after Stop has cleared menu game_bound.
  // Keep the last loaded size until an explicit new cartridge load starts.
  reg [31:0] ui_registered_save_bytes=0;
  always @(posedge clk_74a)begin
    if(ui_new)ui_registered_save_bytes<=0;
    else if(ui_bound && !ui_reset)ui_registered_save_bytes<=ui_native_save;
  end
  // End ordinary-save advertisement.
  wire [7:0] ui_state,ui_fault_code,ui_first_fault;
  wire [10:0] ui_selected;
  wire tcmd_req,tcmd_ack,tcmd_done;
  wire [15:0] tcmd,tcmd_result;
  wire [31:0] tcmd_p0,tcmd_p1,tcmd_p2,tcmd_p3;
  wire ui_rom_idle,ui_bios_idle,ui_save_idle;
  wire ui_idle=ui_rom_idle && ui_bios_idle && ui_save_idle;
  wire ui_reset_s,ui_pause_s,ui_owned_s,ui_paused_s,ui_paused;
  synch_3 ui_reset_sync(.i(ui_reset),.o(ui_reset_s),.clk(clk_mem_110_592));
  synch_3 ui_pause_sync(.i(ui_pause),.o(ui_pause_s),.clk(clk_sys_36_864));
  synch_3 ui_owner_sync(.i(ui_owned),.o(ui_owned_s),.clk(clk_sys_36_864));
  synch_3 ui_pause_ack_sync(.i(ui_paused_s),.o(ui_paused),.clk(clk_74a));
  synch_3 #(.WIDTH(32)) ui_capacity_sync(.i({11'd0,save_size,9'd0}+32'd12),.o(ui_native_save),.clk(clk_74a));
  reg ui_input_block=1;
  always @(posedge clk_sys_36_864)begin
    if(ui_owned_s)ui_input_block<=1;
    else if(cont1_key_s==0)ui_input_block<=0;
  end
  reg ui_loading=0;
  reg [19:0] ui_settle=0;
  always @(posedge clk_74a)begin
    if(!reset_n || ui_fault)begin ui_loading<=0;ui_settle<=0;end
    else if(ui_new)begin ui_loading<=1;ui_settle<=0;end
    else if(ui_finish)begin ui_loading<=0;ui_settle<=20'd74000;end
    else if(ui_settle!=0)ui_settle<=ui_settle-1'b1;
  end
  ws_menu menu(
    .clk(clk_74a),.ready(reset_n && pll_core_locked),.buttons({16'd0,cont1_key}),
    .bridge_wr(bridge_wr),.bridge_rd(bridge_rd),.bridge_endian_little(bridge_endian_little),
    .bridge_addr(bridge_addr),.bridge_wr_data(bridge_wr_data),.param_rd_data(ui_param),
    .t_read(ui_read),.t_write(ui_write),.t_open(ui_open),.t_flush(ui_flush),
    .t_slot(ui_slot),.t_offset(ui_offset),.t_address(ui_address),.t_length(ui_length),
    .t_done(ui_done),.t_error(ui_error),.frame_ack(1'b0),.frame_started(1'b0),
    .frame_valid(1'b0),.frame_fault(1'b0),.visible(cf_menu && cf_level!=0),
    .prepare_ready(ui_idle),.load_ready(!ui_loading && ui_settle==0 && ui_idle),
    .io_idle(!ui_loading && ui_idle && (!ui_bound || ui_paused)),.save_capacity(ui_native_save),
    .pause_allowed(1'b1),.pause_scene(ui_pause_scene),
    .rom_config(ui_config),.expected_save(ui_expected_save),.bios_select(ui_bios),.bios_idle(ui_bios_idle),
    .cf_want_art(cf_want),.cf_wanted_game(cf_wanted),.cf_anim(cf_anim),.cf_frame_tick(cf_tick),
    .cf_mem_idle(cf_mem_idle),.cf_fetch_fault(cf_fetch_fault),.cf_upload_ready(cf_uploaded),
    .cf_level(cf_level),.cf_title_level(cf_title_level),.cf_wanted_slot(cf_wanted_slot),.cf_loaded_slot(cf_loaded_slot),
    .cf_menu(cf_menu),.cf_go(cf_go),.cf_direction(cf_direction),.cf_invalidate(cf_invalidate),.cf_commit(cf_commit),
    .cf_generation(cf_generation),.cf_loaded_game(cf_loaded),.cf_count(cf_count),.cf_level_target(cf_target),
    .cf_title_target(cf_title_target),.cf_title_width(cf_width),.cf_subtitle_width(cf_subwidth),
    .frame_request(ui_request),.menu_owned(ui_owned),.menu_show(ui_show),.menu_reset(ui_reset),.menu_pause(ui_pause),
    .new_load(ui_new),.finish_load(ui_finish),.game_bound(ui_bound),.fault(ui_fault),.fault_code(ui_fault_code),
    .first_fault_code(ui_first_fault),.state(ui_state),.selected(ui_selected));
  sega_menu_target menu_target(.clk(clk_74a),.ready(reset_n && pll_core_locked),
    .read_request(ui_read),.write_request(ui_write),.open_request(ui_open),.flush_request(ui_flush),
    .slot(ui_slot),.offset(ui_offset),.address(ui_address),.length(ui_length),.complete(ui_done),.error(ui_error),
    .raw_request(tcmd_req),.raw_command(tcmd),.p0(tcmd_p0),.p1(tcmd_p1),.p2(tcmd_p2),.p3(tcmd_p3),
    .raw_ack(tcmd_ack),.raw_done(tcmd_done),.raw_result(tcmd_result));
