# 原生上电初值告警审阅

Quartus 22.1 对上游 VHDL 声明初值报告 18061 / 18010。实际综合的上电值如下，与同一模块显式异步 reset 值相符。GG 有 23 个位；SMS／SG 模式优化掉 `gg_pdr[6:0]` 后各 16 个。告警保留，不通过关闭告警获得“零 Critical Warning”。

| 寄存器 | 综合上电值及显式 reset |
|---|---|
| `display_on` | 0 |
| `irq_line_en`, `reset_flags`, `mask_column0` | 1 |
| `spr_address[6:0]` | `1111111` |
| `bg_address[3:1]` | `111`，完整 reset 为 `1110` |
| `jang_bank2[0]` | 1，完整 reset 为 `000011` |
| `jang_bank4[0]` | 1，完整 reset 为 `000101` |
| `gg_pdr[6:0]` | `1111111` |

固定源码位置：`rtl/upstream/vdp.vhd` 声明约 150 行、reset 分支 359～385；`system.vhd` 约 1210～1245；`io.vhd` 约 198～210。`gg_core` 的 `reset_active` 包含菜单／系统 reset、ROM 写入、RAM 清除及 PLL 未锁定。首次菜单与 ROM 加载期间保持原生 reset，因此原生机器使用显式 reset 值启动。

`package.py` 检查每条 Critical Warning 的代码、寄存器名、取值和总数；其他编译阶段不得出现 Critical Warning。完整输入复现还约束上述 reset 源码。这里是源码及综合报告审阅，不扩展为所有上电场景、游戏或板级验收。
