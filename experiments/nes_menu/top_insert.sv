  // Pocket Lab NES menu: one native NES core, independent game/save namespace.
  wire ui_read,ui_write,ui_open,ui_flush,ui_done;
  wire [2:0] ui_error;
  wire [15:0] ui_slot;
  wire [31:0] ui_offset,ui_address,ui_length,ui_param;
  wire ui_owned,ui_show,ui_reset,ui_pause,ui_new,ui_finish,ui_bound,ui_fault;
  wire [7:0] ui_state,ui_fault_code,ui_first_fault;
  wire [10:0] ui_selected;
  wire ui_request,ui_ack,ui_started,ui_valid,ui_pixel_fault,ui_visible;
  wire ui_owned_s,ui_reset_s,ui_pause_s,ui_paused_s,ui_paused;
  wire ui_visible_b,ui_ack_b,ui_started_b,ui_valid_b,ui_pixel_fault_b;
  wire [15:0] ui_pixel_addr,ui_received,ui_words;
  wire [17:0] ui_pixel_data;
  wire ui_pixel_we;
  wire [23:0] ui_video_rgb;
  wire ui_video_de,ui_video_hs,ui_video_vs;
  reg ui_loading=0;
  reg [19:0] ui_settle=0;
  always @(posedge clk_74a) begin
      if(!reset_n)begin ui_loading<=0;ui_settle<=0;end
      else if(ui_new)begin ui_loading<=1;ui_settle<=0;end
      else if(ui_finish)begin ui_loading<=0;ui_settle<=20'd74000;end
      else if(ui_settle!=0)ui_settle<=ui_settle-1'b1;
  end
  synch_3 sync_ui_owned(ui_owned,ui_owned_s,clk_ppu_21_47);
  synch_3 sync_ui_reset(ui_reset,ui_reset_s,clk_ppu_21_47);
  synch_3 sync_ui_pause(ui_pause,ui_pause_s,clk_ppu_21_47);
  synch_3 sync_ui_paused(ui_paused_s,ui_paused,clk_74a);
  synch_3 sync_ui_visible(ui_visible,ui_visible_b,clk_74a);
  synch_3 sync_ui_ack(ui_ack,ui_ack_b,clk_74a);
  synch_3 sync_ui_started(ui_started,ui_started_b,clk_74a);
  synch_3 sync_ui_valid(ui_valid,ui_valid_b,clk_74a);
  synch_3 sync_ui_fault(ui_pixel_fault,ui_pixel_fault_b,clk_74a);
  nes_menu menu (
      .clk(clk_74a),.ready(reset_n && pll_core_locked),.buttons(cont1_key),
      .bridge_wr(bridge_wr),.bridge_rd(bridge_rd),.bridge_endian_little(bridge_endian_little),
      .bridge_addr(bridge_addr),.bridge_wr_data(bridge_wr_data),.param_rd_data(ui_param),
      .t_read(ui_read),.t_write(ui_write),.t_open(ui_open),.t_flush(ui_flush),
      .t_slot(ui_slot),.t_offset(ui_offset),.t_address(ui_address),.t_length(ui_length),
      .t_done(ui_done),.t_error(ui_error),.frame_ack(ui_ack_b),.frame_started(ui_started_b),
      .frame_valid(ui_valid_b),.frame_fault(ui_pixel_fault_b),.visible(ui_visible_b),
      .prepare_ready(1'b1),.load_ready(!ui_loading && ui_settle==0),
      .io_idle(!ui_loading && (!ui_bound || ui_paused)),.save_capacity(32'd262144),
      .frame_request(ui_request),.menu_owned(ui_owned),.menu_show(ui_show),
      .menu_reset(ui_reset),.menu_pause(ui_pause),.new_load(ui_new),.finish_load(ui_finish),
      .game_bound(ui_bound),.fault(ui_fault),.fault_code(ui_fault_code),
      .first_fault_code(ui_first_fault),.state(ui_state),.selected(ui_selected));
  gba_menu_pixels menu_pixels (
      .clk_bridge(clk_74a),.clk_memory(clk_ppu_21_47),
      .bridge_wr(bridge_wr),.bridge_endian_little(bridge_endian_little),
      .bridge_addr(bridge_addr),.bridge_wr_data(bridge_wr_data),.menu_owned(ui_owned_s),
      .frame_request(ui_request),.game_pixel_addr(16'd0),.game_pixel_we(1'b0),
      .pixel_addr(ui_pixel_addr),.pixel_data(ui_pixel_data),.pixel_we(ui_pixel_we),
      .frame_ack(ui_ack),.frame_started(ui_started),.frame_valid(ui_valid),
      .frame_fault(ui_pixel_fault),.game_frame_ready(),.received_pixels(ui_received),.bridge_words(ui_words));
  menu_video menu_raster (
      .clk_memory(clk_ppu_21_47),.clk_video(clk_video_5_37),.reset(!pll_core_locked),
      .pixel_we(ui_pixel_we),.pixel_addr(ui_pixel_addr),.pixel_data(ui_pixel_data),
      .menu_owned(ui_owned),.menu_show(ui_show),.menu_fault(ui_fault),
      .game_rgb(video_rgb_reg),.game_de(video_de_reg),.game_hs(video_hs_reg),.game_vs(video_vs_reg),
      .menu_visible(ui_visible),.rgb(ui_video_rgb),.de(ui_video_de),.hs(ui_video_hs),.vs(ui_video_vs));
