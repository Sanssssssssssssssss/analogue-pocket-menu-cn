// Shared CoverFlow reads 40..48 MiB of the 64 MiB SDRAM. GBA ROM occupies
// 0..32 MiB and EWRAM starts at 32 MiB. No UI texture shares game/save memory.
wire cf_menu,cf_go,cf_direction,cf_invalidate,cf_commit,cf_generation,cf_want,cf_anim,cf_tick;
wire [10:0] cf_wanted,cf_loaded,cf_count;
wire [3:0] cf_target,cf_title_target,cf_level,cf_title_level;
wire [8:0] cf_width,cf_subwidth;
wire cf_mem_req,cf_mem_idle,cf_underrun,cf_fetch_fault;
wire [23:0] cf_mem_word;
wire cf_source_request,cf_source_done,cf_view_idle,cf_bridge_idle,cf_view_fault,cf_bridge_fault;
wire [23:0] cf_source_word;
wire [31:0] cf_source_data;
assign cf_mem_idle=cf_view_idle && cf_bridge_idle;
assign cf_fetch_fault=cf_view_fault || cf_bridge_fault;
coverflow_memory_bridge cf_memory_bridge(.source_clock(clk_74a),.memory_clock(clk_sys),
    .source_request(cf_source_request),.source_word_address(cf_source_word),.source_done(cf_source_done),.source_data(cf_source_data),
    .source_idle(cf_bridge_idle),.source_fault(cf_bridge_fault),.memory_request(cf_mem_req),.memory_word_address(cf_mem_word),
    .memory_done(sdram_rd_ready),.memory_data(sdram_rd_data));
wire cf_mem_idle_b,cf_fault_b;
synch_3 cf_idle_sync(cf_mem_idle,cf_mem_idle_b,clk_74a);
synch_3 cf_fault_sync(cf_fetch_fault,cf_fault_b,clk_74a);
wire [23:0] cf_rgb;
wire cf_de,cf_hs,cf_vs,cf_skip,cf_mode;
reg [2:0] cf_pixel_div=0;
always @(posedge clk_vid)cf_pixel_div<=cf_pixel_div==4 ? 3'd0:cf_pixel_div+1'b1;
wire cf_pixel_ce=cf_pixel_div!=4; // 8.388608 MHz * 4/5, exact accepted menu rate.
wire cf_text_we;
wire [27:0] cf_text_addr;
wire [15:0] cf_text_data;
data_loader #(.ADDRESS_MASK_UPPER_4(4'h7),.OUTPUT_WORD_SIZE(2),.WRITE_MEM_CLOCK_DELAY(4)) cf_text_input(
    .clk_74a(clk_74a),.clk_memory(clk_74a),.bridge_wr(bridge_wr),.bridge_endian_little(bridge_endian_little),
    .bridge_addr(bridge_addr),.bridge_wr_data(bridge_wr_data),.write_en(cf_text_we),.write_addr(cf_text_addr),.write_data(cf_text_data));
coverflow_view cf_view(.clk_74a(clk_74a),.clk_sys(clk_74a),.clk_vid(clk_vid),.pixel_ce(cf_pixel_ce),
    .enable(cf_menu && !ui_fault),.hold_gb(ui_owned),.menu_active(ui_show && cf_menu),.vs(cf_game_vs),
    .ago(cf_go),.ago_dir(cf_direction),.invalidate(cf_invalidate),.cache_commit(cf_commit),.cache_game(cf_loaded),
    .idx(ui_selected),.count(cf_count),.level_target(cf_target),.tl_target(cf_title_target),.htw(cf_width),.hsw(cf_subwidth),
    .gen(cf_generation),.text_we(cf_text_we && cf_text_addr[27:11]==17'h02000),
    .text_addr(cf_text_addr[10:1]),.text_data(cf_text_data),.want_art(cf_want),.wanted_game(cf_wanted),
    .frame_tick(cf_tick),.hr_mode(cf_mode),.anim(cf_anim),.tlevel(cf_title_level),.level(cf_level),
    .hr_rgb(cf_rgb),.hr_de(cf_de),.hr_hs(cf_hs),.hr_vs(cf_vs),.hr_skip(cf_skip),
    .mem_req(cf_source_request),.mem_word_addr(cf_source_word),.mem_done(cf_source_done),.mem_data(cf_source_data),
    .mem_idle(cf_view_idle),.underrun(cf_underrun),.fault(cf_view_fault));
