  // Independent native Sega menu. ROM/save SDRAM remains the game core's;
  // CoverFlow uses the previously idle CellRAM0 bank, pause images use BRAM.
  wire ui_read,ui_write,ui_open,ui_flush,ui_done;
  wire [2:0] ui_error;
  wire [15:0] ui_slot;
  wire [31:0] ui_offset,ui_address,ui_length,ui_param;
  wire ui_owned,ui_show,ui_reset,ui_pause,ui_new,ui_finish,ui_bound,ui_fault;
  wire [7:0] ui_state,ui_fault_code,ui_first_fault;
  wire [10:0] ui_selected;
  wire ui_request,ui_ack,ui_started,ui_valid,ui_pixel_fault,ui_visible;
  wire ui_owned_s,ui_reset_s,ui_pause_s,ui_paused_s,ui_paused,ui_rom_idle_s,ui_rom_idle;
  wire ui_visible_b,ui_ack_b,ui_started_b,ui_valid_b,ui_pixel_fault_b;
  wire [15:0] ui_pixel_addr,ui_received,ui_words;
  wire [17:0] ui_pixel_data;
  wire ui_pixel_we;
  wire [23:0] ui_video_rgb;
  wire ui_video_de,ui_video_hs,ui_video_vs;
  reg ui_loading=0;
  reg [19:0] ui_settle=0;
  always @(posedge clk_74a)begin
      if(!reset_n)begin ui_loading<=0;ui_settle<=0;end
      else if(ui_new)begin ui_loading<=1;ui_settle<=0;end
      else if(ui_finish)begin ui_loading<=0;ui_settle<=20'd74000;end
      else if(ui_settle!=0)ui_settle<=ui_settle-1'b1;
  end
  synch_3 s_ui_owned(ui_owned,ui_owned_s,clk_sys);
  synch_3 s_ui_reset(ui_reset,ui_reset_s,clk_sys);
  synch_3 s_ui_pause(ui_pause,ui_pause_s,clk_sys);
  synch_3 s_ui_paused(ui_paused_s,ui_paused,clk_74a);
  synch_3 s_ui_romidle(ui_rom_idle_s,ui_rom_idle,clk_74a);
  synch_3 s_ui_visible(ui_visible,ui_visible_b,clk_74a);
  synch_3 s_ui_ack(ui_ack,ui_ack_b,clk_74a);
  synch_3 s_ui_started(ui_started,ui_started_b,clk_74a);
  synch_3 s_ui_valid(ui_valid,ui_valid_b,clk_74a);
  synch_3 s_ui_fault(ui_pixel_fault,ui_pixel_fault_b,clk_74a);
  wire ui_cheat_loading,ui_cheat_armed,ui_cheat_armed_s,ui_manual_cheat_s;
  wire ui_payload_ready_s=!cheat_overrun && (cheat_count!=0 || poke_code_total!=0);
  wire ui_payload_ready;
  synch_3 s_ui_payload(ui_payload_ready_s,ui_payload_ready,clk_74a);
  synch_3 s_ui_cheat_arm(ui_cheat_armed,ui_cheat_armed_s,clk_sys);
  reg ui_manual_cheat=0;
  always @(posedge clk_74a)
      if(!reset_n || ui_new)ui_manual_cheat<=0;
      else if(dataslot_requestwrite && dataslot_requestwrite_id==3)ui_manual_cheat<=1;
  synch_3 s_ui_manual(ui_manual_cheat,ui_manual_cheat_s,clk_sys);

  wire cf_menu,cf_go,cf_direction,cf_invalidate,cf_commit,cf_generation,cf_want,cf_anim,cf_tick;
  wire [10:0] cf_wanted,cf_loaded,cf_count;
  wire [3:0] cf_target,cf_title_target,cf_level,cf_title_level;
  wire [8:0] cf_width,cf_subwidth;
  wire cf_request,cf_view_idle,cf_backend_idle,cf_underrun,cf_view_fault,cf_art_fault,cf_done,cf_uploaded;
  wire cf_fault=cf_view_fault || cf_art_fault;
  wire [23:0] cf_word,cf_rgb;
  wire [31:0] cf_data;
  wire cf_de,cf_hs,cf_vs,cf_skip;
  wire cf_text_we,cf_art_we;
  wire [27:0] cf_text_addr,cf_art_addr;
  wire [15:0] cf_text_data,cf_art_data;
  data_loader #(.ADDRESS_MASK_UPPER_4(4'h7),.OUTPUT_WORD_SIZE(2),.WRITE_MEM_CLOCK_DELAY(4)) cf_text_input(
      .clk_74a(clk_74a),.clk_memory(clk_74a),.bridge_wr(bridge_wr),.bridge_endian_little(bridge_endian_little),
      .bridge_addr(bridge_addr),.bridge_wr_data(bridge_wr_data),.write_en(cf_text_we),.write_addr(cf_text_addr),.write_data(cf_text_data));
  data_loader #(.ADDRESS_MASK_UPPER_4(4'h4),.OUTPUT_WORD_SIZE(2),.WRITE_MEM_CLOCK_DELAY(4)) cf_art_input(
      .clk_74a(clk_74a),.clk_memory(clk_74a),.bridge_wr(bridge_wr),.bridge_endian_little(bridge_endian_little),
      .bridge_addr(bridge_addr),.bridge_wr_data(bridge_wr_data),.write_en(cf_art_we),.write_addr(cf_art_addr),.write_data(cf_art_data));
  wire cf_art_begin=ui_read && ui_address[31:23]==9'h084 && ui_address[15:0]==0;
  coverflow_psram_cache cf_images(.clk(clk_74a),.enable(cf_menu && !ui_bound && !ui_fault),
      .invalidate(cf_invalidate),.begin_upload(cf_art_begin),.upload_slot(ui_address[22:16]),
      .write_en(cf_art_we),.write_addr(cf_art_addr),.write_data(cf_art_data),.upload_ready(cf_uploaded),.idle(cf_backend_idle),
      .request(cf_request),.word_address(cf_word),.done(cf_done),.data(cf_data),.fault(cf_art_fault),
      .cram_a(cram0_a),.cram_dq(cram0_dq),.cram_wait(cram0_wait),.cram_clk(cram0_clk),.cram_adv_n(cram0_adv_n),
      .cram_cre(cram0_cre),.cram_ce0_n(cram0_ce0_n),.cram_ce1_n(cram0_ce1_n),.cram_oe_n(cram0_oe_n),
      .cram_we_n(cram0_we_n),.cram_ub_n(cram0_ub_n),.cram_lb_n(cram0_lb_n));
  coverflow_psram_view cf_view(.clk_74a(clk_74a),.clk_sys(clk_74a),.clk_vid(clk_vid),.pixel_ce(1'b1),
      .enable(cf_menu && !ui_fault),.hold_gb(ui_owned),.menu_active(ui_show && cf_menu),.vs(video_vs_reg),
      .ago(cf_go),.ago_dir(cf_direction),.invalidate(cf_invalidate),.cache_commit(cf_commit),.cache_game(cf_loaded),
      .idx(ui_selected),.count(cf_count),.level_target(cf_target),.tl_target(cf_title_target),
      .htw(cf_width),.hsw(cf_subwidth),.gen(cf_generation),
      .text_we(cf_text_we && cf_text_addr[27:11]==17'h02000),.text_addr(cf_text_addr[10:1]),.text_data(cf_text_data),
      .want_art(cf_want),.wanted_game(cf_wanted),.frame_tick(cf_tick),.anim(cf_anim),.tlevel(cf_title_level),.level(cf_level),
      .hr_rgb(cf_rgb),.hr_de(cf_de),.hr_hs(cf_hs),.hr_vs(cf_vs),.hr_skip(cf_skip),
      .mem_req(cf_request),.mem_word_addr(cf_word),.mem_done(cf_done),.mem_data(cf_data),
      .mem_idle(cf_view_idle),.underrun(cf_underrun),.fault(cf_view_fault));
  reg cf_video_owner=1;
  reg [2:0] cf_enable_sync=0;
  always @(posedge clk_vid)begin
      cf_enable_sync<={cf_enable_sync[1:0],cf_menu && !ui_fault};
      if(cf_video_owner)begin if(cf_vs)cf_video_owner<=cf_enable_sync[2];end
      else if(ui_video_vs)cf_video_owner<=cf_enable_sync[2];
  end
  wire [23:0] cf_output_rgb=cf_de ? cf_rgb:(!cf_vs && !cf_hs) ? 24'h008000:24'd0;
  wire cf_output_de=cf_de,cf_output_hs=cf_hs,cf_output_vs=cf_vs;
  sega_menu menu(
      .clk(clk_74a),.ready(reset_n && pll_core_locked),.buttons(cont1_key),
      .bridge_wr(bridge_wr),.bridge_rd(bridge_rd),.bridge_endian_little(bridge_endian_little),
      .bridge_addr(bridge_addr),.bridge_wr_data(bridge_wr_data),.param_rd_data(ui_param),
      .t_read(ui_read),.t_write(ui_write),.t_open(ui_open),.t_flush(ui_flush),
      .t_slot(ui_slot),.t_offset(ui_offset),.t_address(ui_address),.t_length(ui_length),
      .t_done(ui_done),.t_error(ui_error),.frame_ack(ui_ack_b),.frame_started(ui_started_b),
      .frame_valid(ui_valid_b),.frame_fault(ui_pixel_fault_b),.visible(cf_menu ? cf_level!=0:ui_visible_b),
      .prepare_ready(ui_rom_idle && !rom_overrun_74),.load_ready(!ui_loading && ui_settle==0 && ui_rom_idle),
      .io_idle(!ui_loading && (!ui_bound || ui_paused) && ui_rom_idle),.save_capacity(32'd32768),
      .cf_want_art(cf_want),.cf_wanted_game(cf_wanted),.cf_anim(cf_anim),.cf_frame_tick(cf_tick),
      .cf_mem_idle(cf_view_idle && cf_backend_idle),.cf_fetch_fault(cf_fault),.cf_upload_ready(cf_uploaded),
      .cf_level(cf_level),.cf_title_level(cf_title_level),.cf_menu(cf_menu),.cf_go(cf_go),.cf_direction(cf_direction),
      .cf_invalidate(cf_invalidate),.cf_commit(cf_commit),.cf_generation(cf_generation),.cf_loaded_game(cf_loaded),.cf_count(cf_count),
      .cf_level_target(cf_target),.cf_title_target(cf_title_target),.cf_title_width(cf_width),.cf_subtitle_width(cf_subwidth),
      .cheat_loading(ui_cheat_loading),.cheat_armed(ui_cheat_armed),.cheat_payload_ready(ui_payload_ready),.cheat_parse_fault(cheat_overrun_74),
      .frame_request(ui_request),.menu_owned(ui_owned),.menu_show(ui_show),.menu_reset(ui_reset),.menu_pause(ui_pause),
      .new_load(ui_new),.finish_load(ui_finish),.game_bound(ui_bound),.fault(ui_fault),.fault_code(ui_fault_code),
      .first_fault_code(ui_first_fault),.state(ui_state),.selected(ui_selected));
  sega_menu_target menu_target(.clk(clk_74a),.ready(reset_n && pll_core_locked),
      .read_request(ui_read),.write_request(ui_write),.open_request(ui_open),.flush_request(ui_flush),
      .slot(ui_slot),.offset(ui_offset),.address(ui_address),.length(ui_length),.complete(ui_done),.error(ui_error),
      .raw_request(tcmd_req),.raw_command(tcmd),.p0(tcmd_p0),.p1(tcmd_p1),.p2(tcmd_p2),.p3(tcmd_p3),
      .raw_ack(tcmd_ack),.raw_done(tcmd_done),.raw_result(tcmd_result));
  sega_menu_pixels menu_pixels(.clk_bridge(clk_74a),.clk_memory(clk_sys),
      .bridge_wr(bridge_wr),.bridge_endian_little(bridge_endian_little),.bridge_addr(bridge_addr),.bridge_wr_data(bridge_wr_data),
      .menu_owned(ui_owned_s),.frame_request(ui_request),.game_pixel_addr(16'd0),.game_pixel_we(1'b0),
      .pixel_addr(ui_pixel_addr),.pixel_data(ui_pixel_data),.pixel_we(ui_pixel_we),.frame_ack(ui_ack),.frame_started(ui_started),
      .frame_valid(ui_valid),.frame_fault(ui_pixel_fault),.game_frame_ready(),.received_pixels(ui_received),.bridge_words(ui_words));
  menu_video menu_raster(.clk_memory(clk_sys),.clk_video(clk_vid),.reset(!pll_core_locked),
      .pixel_we(ui_pixel_we),.pixel_addr(ui_pixel_addr),.pixel_data(ui_pixel_data),.menu_owned(ui_owned),.menu_show(ui_show),.menu_fault(ui_fault),
      .game_rgb(video_rgb_reg),.game_de(video_de_reg),.game_hs(video_hs_reg),.game_vs(video_vs_reg),
      .menu_visible(ui_visible),.rgb(ui_video_rgb),.de(ui_video_de),.hs(ui_video_hs),.vs(ui_video_vs));
