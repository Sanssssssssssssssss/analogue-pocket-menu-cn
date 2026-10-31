// SPDX-License-Identifier: MIT
// GBAF1 page reader and GBA launch/save lifecycle, clocked by the APF bridge.
module gba_menu #(
    parameter [33:0] TIMEOUT=34'd8910000000,
    parameter [19:0] SETTLE_CYCLES=20'd7400,
    parameter [33:0] FRAME_TIMEOUT=34'd371250000
) (
    input wire clk, ready,
    input wire [31:0] buttons,
    input wire bridge_wr, bridge_rd, bridge_endian_little,
    input wire [31:0] bridge_addr, bridge_wr_data,
    output reg [31:0] param_rd_data=0,
    output reg t_read=0,t_write=0,t_open=0,t_flush=0,
    output reg [15:0] t_slot=0,
    output reg [31:0] t_offset=0,t_address=0,t_length=0,
    input wire t_done,
    input wire [2:0] t_error,
    input wire frame_ack,frame_started,frame_valid,frame_fault,visible,
    input wire prepare_ready,load_ready,io_idle,
    input wire [31:0] save_capacity,
    output reg frame_request=0,
    output reg menu_owned=1,menu_show=0,menu_reset=1,menu_pause=0,
    output reg new_load=0,finish_load=0,game_bound=0,
    output wire fault,
    output reg [7:0] fault_code=0,
    output reg [7:0] first_fault_code=0,
    output reg [7:0] state=0,
    output reg [10:0] selected=0
);
    localparam BOOT=0,HEADER_REQ=1,HEADER_CHECK=2,RECORD_REQ=3,RECORD_CHECK=4,
        VALIDATE_ADDR=5,VALIDATE_WAIT=6,VALIDATE_BYTE=7,
        FRAME_BLANK=8,FRAME_ISSUE=9,FRAME_ARM=10,FRAME_DRAIN=11,FRAME_SHOW=12,MENU=13,
        ACTIVATE=14,FOLDER_OPENED=15,ROM_START=16,ROM_OPENED=17,ROM_READ=18,ROM_SETTLE=19,
        SAVE_OPEN=20,SAVE_OPENED=21,SAVE_CREATE=22,SAVE_CREATED=23,SAVE_READ_DONE=24,
        RTC_OPEN=25,RTC_OPENED=26,RTC_CREATE=27,RTC_CREATED=28,RTC_READ_DONE=29,
        LOAD_FINISH=30,LOAD_DRAIN=31,RUN=32,PAUSE_WAIT=33,PAUSE=34,
        QUIT_WAIT=35,QUIT_SAVE_OPENED=36,QUIT_SAVE_WRITTEN=37,QUIT_SAVE_FLUSHED=38,
        QUIT_RTC_OPENED=39,QUIT_RTC_WRITTEN=40,QUIT_RTC_FLUSHED=41,
        ERROR=42,HOME_OPEN=43,HOME_OPENED=44,CMD_WAIT=45,FRAME_TRANSFERRED=46;
    localparam [31:0] FRAME_SIZE=76800;
    localparam [31:0] PARAM=32'hF3000000;
    (* ramstyle="M10K, no_rw_check" *) reg [31:0] row[0:255];
    reg [31:0] key_prev=0;
    wire [31:0] press=buttons & ~key_prev;
    wire combo=buttons[8] && buttons[9] && buttons[14];
    reg combo_prev=0;
    reg [31:0] header_magic=0,header_version=0,count=0,frame_base=0,pause_base=0;
    reg [31:0] entry_magic=0,entry_flags=0,rom_bytes=0,save_bytes=0;
    reg [1:0] path_select=0;
    reg root_path=0;
    reg [31:0] open_flags=0,open_size=0;
    reg [7:0] row_read_addr=0;
    reg [31:0] row_q=0,param_q=0,root_q=0;
    reg [6:0] param_index=0;
    reg [7:0] return_state=0,after_frame=MENU;
    reg [2:0] result=0;
    reg command_armed=0,go_back=0,pause_option=0,drain_was_low=0;
    reg [33:0] timer=0;
    reg [31:0] frame_offset=0;
    // Fixed 240x160 RGB565 pages: four 16 KiB reads and one 11 KiB tail.
    reg [2:0] frame_chunk=0;
    wire [31:0] frame_sent={15'd0,frame_chunk,14'd0};
    wire [31:0] frame_length=frame_chunk==4 ? 32'd11264 : 32'd16384;
    reg [6:0] validate_index=0;
    reg validate_rtc=0;
    wire [31:0] normalized=bridge_endian_little ? bridge_wr_data :
        {bridge_wr_data[7:0],bridge_wr_data[15:8],bridge_wr_data[23:16],bridge_wr_data[31:24]};
    wire [7:0] path_base=path_select==0 ? 8'd8 : path_select==1 ? 8'd72 : 8'd136;
    wire [7:0] validate_byte=row_q[31-8*validate_index[1:0] -:8];

    function automatic [31:0] root_word(input [5:0] n);
        case(n)
            0:root_word="/Ass";1:root_word="ets/";2:root_word="gbal";3:root_word="ab/c";
            4:root_word="ommo";5:root_word="n/me";6:root_word="nu.b";7:root_word=32'h696e0000;
            default:root_word=0;
        endcase
    endfunction
    function automatic [7:0] save_prefix(input [4:0] n);
        case(n)
            0:save_prefix="/";1:save_prefix="S";2:save_prefix="a";3:save_prefix="v";
            4:save_prefix="e";5:save_prefix="s";6:save_prefix="/";7:save_prefix="g";
            8:save_prefix="b";9:save_prefix="a";10:save_prefix="l";11:save_prefix="a";
            12:save_prefix="b";13:save_prefix="/";14:save_prefix="c";15:save_prefix="o";
            16:save_prefix="m";17:save_prefix="m";18:save_prefix="o";19:save_prefix="n";
            default:save_prefix="/";
        endcase
    endfunction
    function automatic path_byte_ok(input [6:0] n,input [7:0] c,input rtc);
        if(n<21) path_byte_ok=c==save_prefix(n[4:0]);
        else if(n<41) path_byte_ok=(c>="0"&&c<="9")||(c>="a"&&c<="f");
        else case(n)
            41:path_byte_ok=c==".";
            42:path_byte_ok=c==(rtc ? "r" : "s");
            43:path_byte_ok=c==(rtc ? "t" : "a");
            44:path_byte_ok=c==(rtc ? "c" : "v");
            default:path_byte_ok=c==0;
        endcase
    endfunction

    // Raw bridge words preserve string byte order. Scalar metadata uses normalized words.
    always @(posedge clk) begin
        if(bridge_wr && bridge_addr[31:28]==6 && bridge_addr[27:10]==0) begin
            row[bridge_addr[9:2]]<=bridge_endian_little ?
                {bridge_wr_data[7:0],bridge_wr_data[15:8],bridge_wr_data[23:16],bridge_wr_data[31:24]}:bridge_wr_data;
        end
        row_q<=row[row_read_addr];
        param_index<=bridge_addr[8:2];
        // Unconditional synchronous RAM reads let Quartus duplicate the BRAM
        // for two readers. A conditional read here otherwise creates 8192 FFs.
        param_q<=row[path_base+{2'd0,bridge_addr[7:2]}];
        root_q<=root_word(bridge_addr[7:2]);
        if(bridge_rd) param_rd_data<=param_index==64 ? open_flags : param_index==65 ? open_size : root_path ? root_q : param_q;
    end
    always @(posedge clk) if(bridge_wr) begin
        if(bridge_addr[31:28]==7 && bridge_addr[27:6]==0) case(bridge_addr[5:2])
            0:header_magic<=normalized;1:header_version<=normalized;2:count<=normalized;
            3:frame_base<=normalized;4:pause_base<=normalized;
            default:begin end
        endcase
        if(bridge_addr[31:28]==6 && bridge_addr[27:10]==0) case(bridge_addr[9:2])
            0:entry_magic<=normalized;1:entry_flags<=normalized;2:rom_bytes<=normalized;
            default:begin end
        endcase
    end
    task automatic command(input [1:0] operation,input [15:0] slot,
        input [31:0] offset,address,length,input [7:0] next_state);
        begin
            t_slot<=slot;t_offset<=offset;t_address<=address;t_length<=length;
            case(operation) 0:t_read<=1;1:t_open<=1;2:t_write<=1;3:t_flush<=1;endcase
            return_state<=next_state;state<=CMD_WAIT;timer<=0;command_armed<=!t_done;
        end
    endtask
    task automatic fail(input [7:0] code);
        begin
            fault_code<=code;if(first_fault_code==0)first_fault_code<=code;
            state<=ERROR;menu_show<=0;
        end
    endtask
    task automatic paint(input [31:0] offset,input [7:0] next_state);
        begin frame_offset<=offset;after_frame<=next_state;menu_owned<=1;menu_show<=0;timer<=0;state<=FRAME_BLANK;end
    endtask
    assign fault=state==ERROR;

    always @(posedge clk) begin
        key_prev<=buttons;combo_prev<=combo;
        t_read<=0;t_open<=0;t_write<=0;t_flush<=0;new_load<=0;finish_load<=0;
        if(!load_ready)drain_was_low<=1;
        timer<=timer+1'b1;
        // APF Stop/Run must establish ownership even when registers retain game state.
        if(!ready || state==BOOT)begin
            state<=BOOT;timer<=0;selected<=0;frame_request<=0;frame_chunk<=0;
            menu_owned<=1;menu_show<=0;menu_reset<=1;menu_pause<=0;game_bound<=0;
            fault_code<=0;first_fault_code<=0;go_back<=0;root_path<=0;command_armed<=0;
            if(ready && io_idle)state<=HEADER_REQ;
        end else case(state)
            HEADER_REQ:command(0,100,0,32'h70000000,64,HEADER_CHECK);
            HEADER_CHECK:if(result!=0 || header_magic!=32'h46414247 || header_version!=1 ||
                    count<1 || count>2047 || frame_base!=64+(count<<10) ||
                    pause_base<frame_base || pause_base>32'h10000000)fail(8'h10);
                else begin selected<=0;state<=RECORD_REQ;end
            RECORD_REQ:command(0,100,64+({21'd0,selected}<<10),32'h60000000,1024,RECORD_CHECK);
            RECORD_CHECK:if(result!=0 || entry_magic!=32'h31544E45 || entry_flags>1)fail(8'h11);
                else if(entry_flags[0])begin
                    if(go_back)begin go_back<=0;state<=ACTIVATE;end
                    else paint(frame_base+({21'd0,selected}*FRAME_SIZE),MENU);
                end else if(rom_bytes<192 || rom_bytes>33554432 || rom_bytes[1:0]!=0)fail(8'h12);
                else begin validate_rtc<=0;validate_index<=0;row_read_addr<=72;state<=VALIDATE_WAIT;end
            VALIDATE_ADDR:begin row_read_addr<=(validate_rtc ? 8'd136 : 8'd72)+{3'd0,validate_index[6:2]};state<=VALIDATE_WAIT;end
            VALIDATE_WAIT:state<=VALIDATE_BYTE;
            VALIDATE_BYTE:if(!path_byte_ok(validate_index,validate_byte,validate_rtc))fail(8'h13);
                else if(validate_index==45)begin
                    if(!validate_rtc)begin validate_rtc<=1;validate_index<=0;row_read_addr<=136;state<=VALIDATE_WAIT;end
                    else if(go_back)fail(8'h14);
                    else paint(frame_base+({21'd0,selected}*FRAME_SIZE),MENU);
                end else begin validate_index<=validate_index+1'b1;state<=VALIDATE_ADDR;end
            FRAME_BLANK:if(!visible)begin frame_request<=~frame_request;frame_chunk<=0;state<=FRAME_ARM;timer<=0;end
                else if(timer>=FRAME_TIMEOUT)fail(8'h20);
            FRAME_ARM:if(frame_started==frame_request && !frame_valid && !frame_fault)state<=FRAME_ISSUE;
                else if(timer>=FRAME_TIMEOUT)fail(8'h24);
            FRAME_ISSUE:command(0,100,frame_offset+frame_sent,32'h50000000+frame_sent,frame_length,FRAME_TRANSFERRED);
            FRAME_TRANSFERRED:if(result!=0 || frame_fault)fail(8'h21);
                else if(frame_chunk==4)begin state<=FRAME_DRAIN;timer<=0;end
                else begin frame_chunk<=frame_chunk+1'b1;state<=FRAME_ISSUE;end
            FRAME_DRAIN:if(result!=0 || frame_fault)fail(8'h21);
                else if(frame_ack==frame_request && frame_valid)begin menu_show<=1;state<=FRAME_SHOW;timer<=0;end
                else if(timer>=FRAME_TIMEOUT)fail(8'h22);
            FRAME_SHOW:if(visible)begin state<=after_frame;timer<=0;end else if(timer>=FRAME_TIMEOUT)fail(8'h23);
            MENU:begin
                if(press[4])begin menu_show<=0;state<=ACTIVATE;end
                else if(press[5])begin selected<=count[10:0]-1'b1;go_back<=1;menu_show<=0;state<=RECORD_REQ;end
                else if(press[2]||press[0])begin selected<=selected==0 ? count[10:0]-1'b1 : selected-1'b1;state<=RECORD_REQ;menu_show<=0;end
                else if(press[3]||press[1])begin selected<=selected+1>=count ? 11'd0 : selected+1'b1;state<=RECORD_REQ;menu_show<=0;end
            end
            ACTIVATE:begin
                root_path<=0;path_select<=0;open_flags<=0;open_size<=0;
                if(entry_flags[0])command(1,100,0,PARAM,0,FOLDER_OPENED);
                else begin menu_reset<=1;menu_pause<=0;game_bound<=0;timer<=0;state<=ROM_START;end
            end
            FOLDER_OPENED:if(result!=0)fail(8'h30);else state<=HEADER_REQ;
            ROM_START:if(io_idle && !visible)begin
                    new_load<=1;drain_was_low<=0;command(1,1,0,PARAM,0,ROM_OPENED);
                end else if(timer>=TIMEOUT)fail(8'h31);
            ROM_OPENED:if(result!=0)fail(8'h32);else command(0,1,0,32'h10000000,rom_bytes,ROM_READ);
            ROM_READ:if(result!=0)fail(8'h33);else begin state<=ROM_SETTLE;timer<=0;end
            ROM_SETTLE:if(timer>=SETTLE_CYCLES && prepare_ready)begin
                    if(save_capacity!=65536 && save_capacity!=131072)fail(8'h34);
                    else begin save_bytes<=save_capacity;state<=SAVE_OPEN;end
                end else if(timer>=TIMEOUT)fail(8'h35);
            SAVE_OPEN:begin path_select<=1;open_flags<=0;open_size<=0;command(1,10,0,PARAM,0,SAVE_OPENED);end
            SAVE_OPENED:if(result==0)command(0,10,0,32'h20000000,save_bytes,SAVE_READ_DONE);
                else if(result==3)state<=SAVE_CREATE;else fail(8'h40);
            SAVE_CREATE:begin open_flags<=3;open_size<=save_bytes;command(1,10,0,PARAM,0,SAVE_CREATED);end
            SAVE_CREATED:if(result==1)state<=RTC_OPEN;else if(result==0)command(0,10,0,32'h20000000,save_bytes,SAVE_READ_DONE);else fail(8'h41);
            SAVE_READ_DONE:if(result!=0)fail(8'h42);else state<=RTC_OPEN;
            RTC_OPEN:begin path_select<=2;open_flags<=0;open_size<=0;command(1,11,0,PARAM,0,RTC_OPENED);end
            RTC_OPENED:if(result==0)command(0,11,0,32'h21000000,16,RTC_READ_DONE);
                else if(result==3)state<=RTC_CREATE;else fail(8'h43);
            RTC_CREATE:begin open_flags<=3;open_size<=16;command(1,11,0,PARAM,0,RTC_CREATED);end
            RTC_CREATED:if(result==1)state<=LOAD_FINISH;else if(result==0)command(0,11,0,32'h21000000,16,RTC_READ_DONE);else fail(8'h44);
            RTC_READ_DONE:if(result!=0)fail(8'h45);else state<=LOAD_FINISH;
            LOAD_FINISH:begin finish_load<=1;state<=LOAD_DRAIN;timer<=0;end
            LOAD_DRAIN:if(load_ready && drain_was_low)begin
                    game_bound<=1;menu_reset<=0;menu_owned<=0;menu_pause<=0;menu_show<=0;state<=RUN;
                end else if(timer>=TIMEOUT)fail(8'h46);
            RUN:if(combo && !combo_prev)begin menu_pause<=1;menu_owned<=1;menu_show<=0;pause_option<=0;timer<=0;state<=PAUSE_WAIT;end
            PAUSE_WAIT:if(io_idle)paint(pause_base,PAUSE);else if(timer>=TIMEOUT)fail(8'h50);
            PAUSE:if(press[5] || (press[4] && !pause_option))begin
                    menu_pause<=0;menu_owned<=0;menu_show<=0;state<=RUN;
                end else if(press[0]||press[1]||press[2]||press[3])begin
                    pause_option<=~pause_option;paint(pause_base+(pause_option ? 32'd0 : FRAME_SIZE),PAUSE);
                end else if(press[4])begin menu_show<=0;state<=QUIT_WAIT;timer<=0;end
            QUIT_WAIT:if(io_idle)begin
                    path_select<=1;root_path<=0;open_flags<=3;open_size<=save_bytes;
                    command(1,10,0,PARAM,0,QUIT_SAVE_OPENED);
                end else if(timer>=TIMEOUT)fail(8'h51);
            QUIT_SAVE_OPENED:if(result>1)fail(8'h52);else command(2,10,0,32'h20000000,save_bytes,QUIT_SAVE_WRITTEN);
            QUIT_SAVE_WRITTEN:if(result!=0)fail(8'h53);else command(3,10,0,0,0,QUIT_SAVE_FLUSHED);
            QUIT_SAVE_FLUSHED:if(result!=0)fail(8'h54);else begin
                    path_select<=2;open_flags<=3;open_size<=16;command(1,11,0,PARAM,0,QUIT_RTC_OPENED);
                end
            QUIT_RTC_OPENED:if(result>1)fail(8'h55);else command(2,11,0,32'h21000000,16,QUIT_RTC_WRITTEN);
            QUIT_RTC_WRITTEN:if(result!=0)fail(8'h56);else command(3,11,0,0,0,QUIT_RTC_FLUSHED);
            QUIT_RTC_FLUSHED:if(result!=0)fail(8'h57);else begin
                    game_bound<=0;menu_reset<=1;menu_pause<=0;menu_show<=0;timer<=0;state<=RECORD_REQ;
                end
            ERROR:if(press[5])begin
                    if(game_bound)begin menu_owned<=0;menu_pause<=0;state<=RUN;end
                    else state<=HOME_OPEN;
                end else if(press[4])begin
                    if(game_bound)begin state<=QUIT_WAIT;timer<=0;end else state<=HOME_OPEN;
                end
            HOME_OPEN:begin root_path<=1;open_flags<=0;open_size<=0;go_back<=0;command(1,100,0,PARAM,0,HOME_OPENED);end
            HOME_OPENED:if(result!=0)fail(8'h60);else state<=HEADER_REQ;
            CMD_WAIT:begin
                if(!t_done)command_armed<=1;
                if(command_armed && t_done)begin result<=t_error;state<=return_state;timer<=0;end
                else if(timer>=TIMEOUT)fail(8'hFE);
            end
            default:fail(8'hFF);
        endcase
    end
endmodule
