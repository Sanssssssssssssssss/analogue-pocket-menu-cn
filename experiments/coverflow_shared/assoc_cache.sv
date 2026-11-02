// SPDX-License-Identifier: MIT
// Five fully associative RGB565 cover slots. Logical game IDs never alias by
// modulo: all currently visible and next-step candidates are protected.
module coverflow_assoc_cache (
    input wire clk,enable,invalidate,keys_valid,
    input wire [10:0] candidates[0:4],
    input wire [10:0] visible[0:3],
    input wire commit,
    input wire [2:0] commit_slot,
    input wire [10:0] commit_game,
    output reg want,
    output reg [10:0] wanted_game,
    output reg [2:0] wanted_slot,
    output reg loaded[0:3],
    output reg [2:0] physical[0:3]
);
    reg [4:0] valid=0;
    reg [10:0] tags[0:4];
    reg [4:0] hits,protected_slots;
    reg missing,available;
    integer i,j;
    always @* begin
        hits=0;protected_slots=0;want=0;wanted_game=0;wanted_slot=0;
        missing=0;available=0;
        for(i=0;i<4;i=i+1)begin
            loaded[i]=0;physical[i]=0;
            for(j=0;j<5;j=j+1)if(valid[j] && tags[j]==visible[i])begin
                loaded[i]=1;physical[i]=j[2:0];protected_slots[j]=1;
            end
        end
        for(i=0;i<5;i=i+1)for(j=0;j<5;j=j+1)
            if(valid[j] && tags[j]==candidates[i])begin hits[i]=1;protected_slots[j]=1;end
        // Reverse loops give priority to the nearest missing candidate and the
        // lowest free slot. Invalid slots are preferred over evictable slots.
        for(i=4;i>=0;i=i-1)if(!hits[i])begin missing=1;wanted_game=candidates[i];end
        for(i=4;i>=0;i=i-1)if(!protected_slots[i])begin available=1;wanted_slot=i[2:0];end
        for(i=4;i>=0;i=i-1)if(!valid[i])begin available=1;wanted_slot=i[2:0];end
        want=enable && !invalidate && !commit && keys_valid && missing && available;
    end
    always @(posedge clk)begin
        if(!enable || invalidate)valid<=0;
        else if(commit && commit_slot<5)begin tags[commit_slot]<=commit_game;valid[commit_slot]<=1;end
    end
endmodule
