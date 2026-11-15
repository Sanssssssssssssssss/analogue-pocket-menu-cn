  // CoverFlow art uses separate on-chip RAM. No bridge target in this range
  // reaches the removed Memories controller or native NES ROM/save memory.
  wire cf_menu,cf_go,cf_direction,cf_invalidate,cf_commit,cf_generation,cf_want,cf_anim,cf_tick;
  wire [10:0] cf_wanted,cf_loaded,cf_count;
  wire [2:0] cf_wanted_slot,cf_loaded_slot;
  wire [3:0] cf_target,cf_title_target,cf_level,cf_title_level;
  wire [8:0] cf_width,cf_subwidth;
  wire cf_request,cf_idle,cf_underrun,cf_view_fault,cf_art_fault,cf_done,cf_art_begin,cf_uploaded;
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
  nes_coverflow_art_ram cf_images(.clk(clk_74a),.enable(cf_menu && !ui_bound && !ui_fault),
      .invalidate(cf_invalidate),.begin_upload(cf_art_begin),.upload_slot(cf_loaded_slot),
      .write_en(cf_art_we),.write_addr(cf_art_addr),.write_data(cf_art_data),.upload_ready(cf_uploaded),
      .request(cf_request),.word_address(cf_word),.done(cf_done),.data(cf_data),.fault(cf_art_fault));
  coverflow_assoc_view cf_view(.clk_74a(clk_74a),.clk_sys(clk_74a),.clk_vid(clk_video_5_37),.pixel_ce(1'b1),
      .enable(cf_menu && !ui_fault),.hold_gb(ui_owned),.menu_active(ui_show && cf_menu),.vs(video_vs_reg),
      .ago(cf_go),.ago_dir(cf_direction),.invalidate(cf_invalidate),.cache_commit(cf_commit),.cache_game(cf_loaded),
      .cache_slot(cf_loaded_slot),.wanted_slot(cf_wanted_slot),.idx(ui_selected),.count(cf_count),
      .level_target(cf_target),.tl_target(cf_title_target),.htw(cf_width),.hsw(cf_subwidth),.gen(cf_generation),
      .text_we(cf_text_we && cf_text_addr[27:11]==17'h02000),.text_addr(cf_text_addr[10:1]),.text_data(cf_text_data),
      .want_art(cf_want),.wanted_game(cf_wanted),.frame_tick(cf_tick),.anim(cf_anim),.tlevel(cf_title_level),.level(cf_level),
      .hr_rgb(cf_rgb),.hr_de(cf_de),.hr_hs(cf_hs),.hr_vs(cf_vs),.hr_skip(cf_skip),
      .mem_req(cf_request),.mem_word_addr(cf_word),.mem_done(cf_done),.mem_data(cf_data),
      .mem_idle(cf_idle),.underrun(cf_underrun),.fault(cf_view_fault));
  reg cf_video_owner=1;
  reg [2:0] cf_enable_sync=0;
  always @(posedge clk_video_5_37)begin
      cf_enable_sync<={cf_enable_sync[1:0],cf_menu && !ui_fault};
      if(cf_video_owner)begin if(cf_vs)cf_video_owner<=cf_enable_sync[2];end
      else if(ui_video_vs)cf_video_owner<=cf_enable_sync[2];
  end
  // The native game's existing scaler modes 0..3 are untouched. Mode 4 is
  // the independent 320x288 menu. No scaler word is emitted during VS/HS.
  wire [23:0] cf_output_rgb=cf_de ? cf_rgb:(!cf_vs && !cf_hs) ? 24'h008000:24'd0;
  wire cf_output_de=cf_de,cf_output_hs=cf_hs,cf_output_vs=cf_vs;
