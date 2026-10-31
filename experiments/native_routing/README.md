# 原生换核 A/B 探针

2026-11-01。这是独立的离线诊断源码，**不是统一游戏前端，也不是可直接复制上卡的安装包**。设备卡没有接入；现有 GB/GBC、GBA 与保存进度没有迁移。

目标是把三个问题分别验证：加载器还在运行时能否收到按键；宿主能否显示该阶段的视频；第二次 `CORE` 是否确实配置了另一个 FPGA 程序。启动时选中编号、真正重配置、游戏运行后重新唤起加载器，是三个不同结论。

## 新核对的边界

- [官方启动流程](https://www.analogue.co/developer/docs/openfpga/core-boot-process)在 Setup 阶段描述无音视频，加载完成后才发 Reset Exit。因此仅让 FPGA 自己产生光栅，不能证明 Pocket 屏幕已显示菜单。
- [CORE / HOST 指令](https://www.analogue.co/developer/docs/openfpga/chip32-vm/special)明确描述已加载程序可能跳过 `CORE`；不同 ID 的具体运行阶段行为仍须宿主实测。`HOST 0x4001` 释放复位，`0x4002` 继续启动；两者都不是文档已承诺的“启动另一个已安装核心”入口。
- 现有 [Chip32 模拟器](https://github.com/agg23/openfpga-chip32-sim/blob/c358d70263383a133fcd303b19c3e559caf33c8b/src/cpu.rs)的 CORE 只写 `active_bitstream`，HOST 只记日志，PMPR 不提供 FPGA 读数。不能把其成功日志当成重配置证明。本机版本另有 reload-slot 测试扩展，仍不是 Pocket 宿主。
- 本轮也检查了官方 [2.6.0](https://www.analogue.co/support/pocket/firmware/2.6.0)及 [2.7](https://www.analogue.co/support/pocket/firmware/2.7)发布说明：包含 Recent、退出返回 openFPGA、列表缓存及数量改进，未找到新增运行时自绘菜单换核 API 的声明。没有下载或升级固件。

## 探针行为

`prepare_probe.py`只接受 SHA-256 固定的[官方模板 ZIP](https://github.com/open-fpga/core-template/tree/da3a021b1eaf742604d86d8dc9b33a6666263e6a)，在本仓库 `.work` 的新目录生成 A、B 两套完整板级工程。沿用原板级引脚与存储关闭状态，额外把所有 Target 文件操作请求固定为零。

| 程序 | 编译进硬件的只读身份 | 测试光栅颜色 |
|---|---|---|
| A | `0x504C4100` | 蓝色 |
| B | `0x504C4201` | 橙色 |

两份程序的诊断逻辑和光栅有意不受 APF 的运行复位约束；这只使 FPGA 在加载阶段有能力产生输出，宿主是否呈现它仍待验证。诊断寄存器基址为 `0x60000000`：

| 偏移 | 内容 |
|---|---|
| `00` | 固定身份，只读，PMPW 无法改写 |
| `04` | APF 运行复位是否释放 |
| `08` | FPGA 自有时钟计时，毫秒 |
| `0C` | 同步后的 APF 按键值 |
| `10` | 写入阶段号，清除上次选择 |
| `14` | 新按下 A=1 / B=2；进入阶段时按住的键无效 |

三个独立加载器分别在等待按键前：不提前发 HOST、发 `0x4001`、发 `0x4002`。每个最多轮询 4096 次；次数不代表固定秒数。选到 A 或 B 后均执行固定的 A→B→A 身份检查；此处按键只确认输入通路，尚不分派真实游戏。

无法读出首个身份时输出 `NO_FPGA`；无新按键时输出 `NO_INPUT`；换程序后身份不匹配时输出 `NO_SWITCH`。任一失败均退出。只有三次实际身份读数匹配才输出 `IDENTITY_A_B_A`；即使该项未来通过，也仍需单独确认画面、按键、游戏运行后重入与存档交接。

## 离线复现

需要 Python 3.11+、Icarus Verilog；汇编另需 [BASS](https://github.com/ARM9/bass/tree/828ad2c11bddac45c7daeba9293a5265f2994bd5)及 [Chip32 指令定义](https://github.com/open-fpga/bass-chip32/tree/9e4a919d1ff39b217b75e090e996148654d3f9d7)。原始 ZIP 保留在输出以外的 `originals`，每次使用新输出目录。

```sh
python experiments/native_routing/prepare_probe.py --archive /path/to/core-template.zip --out .work/native-routing/probe
python experiments/native_routing/probe_offline.py --prepared .work/native-routing/probe --bass /path/to/bass --simulator /path/to/chip32-sim-cli --out .work/native-routing/check
```

第二条命令验证只读身份、APF 运行复位期间计时、按键释放／阶段／选择锁存，汇编三份实际 Chip32 字节码，并要求旧日志模拟器因没有 FPGA 身份而拒绝。**该负向结果用于防止假成功，没有模拟真实换核。**

板级编译可在两份工程各自的 `src/fpga` 执行 `quartus_sh --flow compile ap_core`。输出不构成设备安装许可或验收；不能把模板的默认身份元数据直接复制到现有卡上。

## 当前验证

探针 RTL、三份汇编和缺少 FPGA 的拒绝检查已通过，见[收据](offline-validation.json)。两套完整板级工程也已通过 Quartus 综合、布局布线、ASM 和 STA：A 使用 503 ALM，B 使用 495 ALM，均为 2 M10K、0 DSP、0 虚拟引脚。各 44 条已报告时序摘要无负 slack，**但官方模板仍有 2 个未约束时钟、4 个输入和 22 个输出，因此不属于时序完整验收**。日志和二进制只保存在电脑，公开的[编译收据](evidence/board-builds.json)包含哈希与范围。

掌机屏幕、实际按键到达、A→B→A 重配置及运行中重入均未实测。本目录不提供游戏、BIOS、存档或二进制核心下载。

## English

This is an **offline native FPGA routing probe**, not an installable frontend. Two official-template board projects carry immutable A/B identities; three assembled Chip32 loaders compare input visibility before initialization, after reset release, and after full initialization. The old logging VM must reject the absent FPGA identity instead of claiming a switch.

Both board builds complete with zero virtual pins. Template I/O and audio-clock constraints remain incomplete. Physical video, controller delivery, actual A→B→A reconfiguration and re-entering the loader from a running game are untested. No card, firmware, commercial games or personal saves are involved.
