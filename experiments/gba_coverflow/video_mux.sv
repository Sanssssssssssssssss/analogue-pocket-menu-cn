wire [23:0] cf_game_rgb;
wire cf_game_de,cf_game_hs,cf_game_vs,cf_game_skip;
reg cf_video_owner=1;
reg [2:0] cf_enable_sync=0;
always @(posedge clk_vid)begin
    cf_enable_sync<={cf_enable_sync[1:0],cf_menu && !ui_fault};
    // Change the video source in vertical blank; the game is still held/reset
    // throughout the menu's fade/drain and its first complete frame is fenced.
    if(cf_video_owner)begin if(cf_vs)cf_video_owner<=cf_enable_sync[2];end
    else if(cf_game_vs)cf_video_owner<=cf_enable_sync[2];
end
// Scaler 0 remains the inherited 240x160, 3:2 game display; scaler 1 is the
// accepted 320x288 CoverFlow. End-line words never overlap the VS feature field.
wire cf_endline=!cf_de && !cf_vs && !cf_hs;
assign video_rgb=cf_video_owner ? (cf_de ? cf_rgb : cf_endline ? 24'h002000:24'd0) : cf_game_rgb;
assign video_de=cf_video_owner ? cf_de:cf_game_de;
assign video_hs=cf_video_owner ? cf_hs:cf_game_hs;
assign video_vs=cf_video_owner ? cf_vs:cf_game_vs;
assign video_skip=cf_video_owner ? cf_skip:cf_game_skip;
