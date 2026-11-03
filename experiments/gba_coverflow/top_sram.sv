// Pocket Lab five-slot CoverFlow cache, isolated from game/save memory.
wire cf_menu,cf_go,cf_direction,cf_invalidate,cf_commit,cf_generation,cf_want,cf_anim,cf_tick;
wire [10:0] cf_wanted,cf_loaded,cf_count;
wire [2:0] cf_wanted_slot,cf_loaded_slot;
wire [3:0] cf_target,cf_title_target,cf_level,cf_title_level;
wire [8:0] cf_width,cf_subwidth;
wire cf_mem_idle,cf_underrun,cf_fetch_fault,cf_uploaded;
wire cf_source_request,cf_source_done,cf_view_idle,cf_backend_idle,cf_view_fault,cf_art_fault,cf_uploaded_s;
wire [23:0] cf_source_word;
wire [31:0] cf_source_data;
wire cf_enable_s;
synch_3 cf_cache_enable_sync(.i(cf_menu && !ui_bound && !ui_fault),.o(cf_enable_s),.clk(clk_sys),.rise(),.fall());
synch_3 cf_idle_sync(.i(cf_view_idle && cf_backend_idle),.o(cf_mem_idle),.clk(clk_74a),.rise(),.fall());
synch_3 cf_fault_sync(.i(cf_view_fault || cf_art_fault),.o(cf_fetch_fault),.clk(clk_74a),.rise(),.fall());
synch_3 cf_uploaded_sync(.i(cf_uploaded_s),.o(cf_uploaded),.clk(clk_74a),.rise(),.fall());
wire [23:0] cf_rgb;
wire cf_de,cf_hs,cf_vs,cf_skip,cf_mode;
reg [2:0] cf_pixel_div=0;
always @(posedge clk_vid)cf_pixel_div<=cf_pixel_div==4 ? 3'd0:cf_pixel_div+1'b1;
wire cf_pixel_ce=cf_pixel_div!=4;
wire cf_text_we,cf_art_we;
wire [27:0] cf_text_addr,cf_art_addr;
wire [15:0] cf_text_data,cf_art_data;
data_loader #(.ADDRESS_MASK_UPPER_4(4'h7),.OUTPUT_WORD_SIZE(2),.WRITE_MEM_CLOCK_DELAY(4)) cf_text_input(
    .clk_74a(clk_74a),.clk_memory(clk_74a),.bridge_wr(bridge_wr),.bridge_endian_little(bridge_endian_little),
    .bridge_addr(bridge_addr),.bridge_wr_data(bridge_wr_data),.write_en(cf_text_we),.write_addr(cf_text_addr),.write_data(cf_text_data));
data_loader #(.ADDRESS_MASK_UPPER_4(4'h4),.OUTPUT_WORD_SIZE(2),.WRITE_MEM_CLOCK_DELAY(4)) cf_art_input(
    .clk_74a(clk_74a),.clk_memory(clk_sys),.bridge_wr(bridge_wr),.bridge_endian_little(bridge_endian_little),
    .bridge_addr(bridge_addr),.bridge_wr_data(bridge_wr_data),.write_en(cf_art_we),.write_addr(cf_art_addr),.write_data(cf_art_data));
wire cf_art_begin=target_dataslot_read && target_dataslot_bridgeaddr[31:19]==13'h840 && target_dataslot_bridgeaddr[15:0]==0;
reg cf_upload_toggle=0,cf_clear_toggle=0;
reg [2:0] cf_upload_slot=0;
always @(posedge clk_74a)begin
    if(cf_art_begin)begin cf_upload_toggle<=~cf_upload_toggle;cf_upload_slot<=target_dataslot_bridgeaddr[18:16];end
    if(cf_invalidate)cf_clear_toggle<=~cf_clear_toggle;
end
wire cf_upload_sync_s,cf_clear_sync_s;
wire [2:0] cf_upload_slot_s;
synch_3 cf_upload_event(.i(cf_upload_toggle),.o(cf_upload_sync_s),.clk(clk_sys),.rise(),.fall());
synch_3 cf_clear_event(.i(cf_clear_toggle),.o(cf_clear_sync_s),.clk(clk_sys),.rise(),.fall());
synch_3 #(.WIDTH(3)) cf_slot_sync(.i(cf_upload_slot),.o(cf_upload_slot_s),.clk(clk_sys),.rise(),.fall());
reg cf_upload_seen=0,cf_clear_seen=0;
always @(posedge clk_sys)begin cf_upload_seen<=cf_upload_sync_s;cf_clear_seen<=cf_clear_sync_s;end
coverflow_sram_cache cf_images(.clk(clk_sys),.enable(cf_enable_s),
    .invalidate(cf_clear_seen!=cf_clear_sync_s),.begin_upload(cf_upload_seen!=cf_upload_sync_s),.upload_slot(cf_upload_slot_s),
    .write_en(cf_art_we),.write_addr(cf_art_addr),.write_data(cf_art_data),.upload_ready(cf_uploaded_s),.idle(cf_backend_idle),
    .request(cf_source_request),.word_address(cf_source_word),.done(cf_source_done),.data(cf_source_data),.fault(cf_art_fault),
    .sram_a(sram_a),.sram_dq(sram_dq),.sram_oe_n(sram_oe_n),.sram_we_n(sram_we_n),.sram_ub_n(sram_ub_n),.sram_lb_n(sram_lb_n));
coverflow_assoc_view cf_view(.clk_74a(clk_74a),.clk_sys(clk_sys),.clk_vid(clk_vid),.pixel_ce(cf_pixel_ce),
    .enable(cf_menu && !ui_fault),.hold_gb(ui_owned),.menu_active(ui_show && cf_menu),.vs(cf_game_vs),
    .ago(cf_go),.ago_dir(cf_direction),.invalidate(cf_invalidate),.cache_commit(cf_commit),.cache_game(cf_loaded),
    .cache_slot(cf_loaded_slot),.wanted_slot(cf_wanted_slot),.idx(ui_selected),.count(cf_count),
    .level_target(cf_target),.tl_target(cf_title_target),.htw(cf_width),.hsw(cf_subwidth),
    .gen(cf_generation),.text_we(cf_text_we && cf_text_addr[27:11]==17'h02000),
    .text_addr(cf_text_addr[10:1]),.text_data(cf_text_data),.want_art(cf_want),.wanted_game(cf_wanted),
    .frame_tick(cf_tick),.hr_mode(cf_mode),.anim(cf_anim),.tlevel(cf_title_level),.level(cf_level),
    .hr_rgb(cf_rgb),.hr_de(cf_de),.hr_hs(cf_hs),.hr_vs(cf_vs),.hr_skip(cf_skip),
    .mem_req(cf_source_request),.mem_word_addr(cf_source_word),.mem_done(cf_source_done),.mem_data(cf_source_data),
    .mem_idle(cf_view_idle),.underrun(cf_underrun),.fault(cf_view_fault));
