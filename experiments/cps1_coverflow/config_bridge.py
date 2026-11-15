# SPDX-License-Identifier: MIT
"""Latch native instance controls when the menu binds a game, not only at power-up."""
from pathlib import Path

def patch(root,core=None):
    path=Path(root)/'modules/jtframe/target/pocket/hdl/jtframe_pocket_cfg.v'
    text=path.read_text(encoding='utf8')
    before='always @(posedge clk_rom) begin\n    if( rst_rom ) begin'
    if text.count(before)!=1:raise ValueError('CPS configuration reset anchor changed')
    text=text.replace(before,'''// rst_rom is the board's PLL/power reset, not the per-game reset.
// Capture the instance at admission and again when its load becomes bound.
// While running, preserve ordinary Core Settings writes.
reg menu_game_l=0;
always @(posedge clk_rom) begin
    menu_game_l<=menu_game;
    if( rst_rom ) begin''')
    before='''        if( wr ) begin
            case (addr[31:24])'''
    if text.count(before)!=1:raise ValueError('CPS configuration write anchor changed')
    text=text.replace(before,'''        if(menu_game && !menu_game_l)begin
            core_mod<={menu_mode[17:16],9'd0,menu_mode[6:0]};
            button_map<=menu_buttons;
            game_vol<=menu_mode[15:8];
`ifndef JTFRAME_FORCED_DIPSW
            dipsw<=menu_dip;
`endif
        end else if( wr ) begin
            case (addr[31:24])''')
    path.write_text(text,encoding='utf8',newline='\n')
