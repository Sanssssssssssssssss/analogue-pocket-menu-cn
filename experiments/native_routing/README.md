# 原生换核 A/B 探针

2026-11-01。这是独立诊断源码，**不是统一游戏前端**。首轮离线研究之后，已生成并校验独立的 `Pocket Lab Test` 试验包；实机结果待用户反馈。现有游戏入口与存档没有迁移。

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
| `1C` | 最近一次非零按键，释放后保留，便于打开系统菜单读取 |
| `20` | 加载器阶段／结果，对应 Core Settings 的 M |
| `24` | 最后一次身份读数或诊断附加值，对应 D |

三个独立加载器分别在等待按键前：不提前发 HOST、发 `0x4001`、发 `0x4002`。当前版本等待 FPGA 自有计时达到约 5 秒，另设最多 131,072 轮的退出上限；宿主自身超时仍可能更早结束执行。选到 A 或 B 后均执行固定的 A→B→A 身份检查；此处按键只确认输入通路，尚不分派真实游戏。

无法读出首个身份时输出 `NO_FPGA` 并失败退出，旧日志 VM 仍必须在这里被拒绝。已确认 FPGA 存在之后，将结果留在寄存器，再结束加载并显示诊断画面；**EXIT 0 只代表诊断画面可继续启动，不能当作换核成功**。M=`0xA0` 才表示三次身份匹配；M=`0xE2` 为无新按键，`0xE3` 为切 B 后身份不符，`0xE4` 为返回 A 后身份不符。即使身份检查未来通过，也仍需确认物理画面、按键、游戏运行后重入与存档交接。

## 离线复现

需要 Python 3.11+、Icarus Verilog；汇编另需 [BASS](https://github.com/ARM9/bass/tree/828ad2c11bddac45c7daeba9293a5265f2994bd5)及 [Chip32 指令定义](https://github.com/open-fpga/bass-chip32/tree/9e4a919d1ff39b217b75e090e996148654d3f9d7)。原始 ZIP 保留在输出以外的 `originals`，每次使用新输出目录。

```sh
python experiments/native_routing/prepare_probe.py --archive /path/to/core-template.zip --out .work/native-routing/probe
python experiments/native_routing/probe_offline.py --prepared .work/native-routing/probe --bass /path/to/bass --simulator /path/to/chip32-sim-cli --out .work/native-routing/check
```

第二条命令验证只读身份、APF 运行复位期间计时、按键释放／阶段／选择锁存，汇编三份实际 Chip32 字节码，并要求旧日志模拟器因没有 FPGA 身份而拒绝。**该负向结果用于防止假成功，没有模拟真实换核。**

板级编译可在两份工程各自的 `src/fpga` 执行 `quartus_sh --flow compile ap_core`。输出不构成设备安装许可或验收；不能把模板的默认身份元数据直接复制到现有卡上。

## 首轮离线验证

首轮两套完整板级工程通过 Quartus 综合、布局布线、ASM 和 STA：A 使用 503 ALM，B 使用 495 ALM，均为 2 M10K、0 DSP、0 虚拟引脚。各 44 条已报告时序摘要无负 slack，但官方模板仍有 2 个未约束时钟、4 个输入和 22 个输出，因此不属于时序完整验收。此历史结果对应提交 `aac1469`，见[原始收据](evidence/board-builds.json)。

## 独立实机诊断包

新版增加最后按键与 M/D 结果寄存器，并去掉试验不需要的音频时钟生成器。`prepare_trial.py` 重新准备工程，使用已有 GBA 的 APF 协议 I/O 例外范围，并保留相关 PLL 输出间的相位关系。内部时序检查通过；协议 I/O 的例外不等于外部板级 setup/hold 签核，详见[新版编译收据](evidence/trial-builds.json)。

`stage_trial.py` 要求完整编译、无负 slack、无未约束时钟、无虚拟引脚，核对当前探针与汇编校验的哈希后，生成新命名空间的四个入口。所有 Target 文件请求固定关闭，没有非易失数据槽；16 字节合成种子只用于给启动槽一个确定身份。包中不包含游戏、BIOS 或进度。

| 入口 | 作用 |
|---|---|
| Route0 | 不使用 Chip32，先确认普通蓝屏、PMP 身份和按键 |
| Route1 | 加载器在继续初始化之前等待按键 |
| Route2 | 提前释放运行复位，再等待按键 |
| Route3 | 提前继续完整初始化，再等待按键 |

```sh
python experiments/native_routing/prepare_trial.py --archive /path/to/core-template.zip --out .work/native-routing/trial
# 编译 trial/A/src/fpga 与 trial/B/src/fpga，并用 probe_offline.py 检查此副本。
python experiments/native_routing/stage_trial.py --build .work/native-routing/trial --validation .work/native-routing/check/receipt.json --out .work/native-routing/package
```

现场安装新增 42 个文件，约 6.54 MB；先做版本备份，再拒绝所有已存在的目标，用白名单限定 `pocketlab.Route0`～`Route3`、`routetest` 平台和合成种子，发布后校验新增文件与备份范围内的 4,067 个原文件。没有固件、游戏 ROM、原核心或存档覆盖。安装记录和回退清单留在电脑的私有备份目录；公开仓库不保存卡内清单。

先完全关机插卡，进入 **openFPGA → Pocket Lab Test → Change Core → Route0 → Run**。蓝屏后按一次 B，打开 Analogue 菜单的 Core Settings，读取 **ID、R、K**；期望 ID=`0x504C4100`、R=`1`、K=`0x20`。Route0 通过后，才解释另外三项结果；失败时不能直接推断换核接口不可用。

Route0 已获用户实机确认：ID=`0x504C4100`、R=`0x00000001`、K=`0x00000020`，U 持续增加。该结果验证普通启动、身份读回、运行复位释放、B 键到达和探针计时，详见[实机记录](evidence/route0-device-report.json)。画面颜色没有单独描述；Route0 不执行 Chip32，不能据此确认加载阶段交互或自动换核。

下一步测试 Route3：完全关机重开，选择该入口并 Run；松开 A，在前 5 秒内短按 B 两三次，即使黑屏也先按，约 10 秒后读取 M、D、ID 及画面状态。A→B→A 重配置和运行中重入仍未验收。本目录不提供游戏、BIOS、存档或二进制核心下载。

## English

This is a **native FPGA routing diagnostic**, not a unified frontend. Two official-template board projects carry immutable A/B identities; three assembled Chip32 loaders compare input visibility before initialization, after reset release, and after full initialization. The old logging VM must reject the absent FPGA identity instead of claiming a switch. Diagnostic EXIT 0 is not routing success: M=0xA0 is required for the A/B/A identity check.

The new local trial removes unused audio clocks and explicitly excepts APF protocol I/O, following the existing GBA project's scope. Internal timing passes; this is not external board-I/O signoff. Four separate trial entries were installed after a verified backup, without overwriting existing files. The user confirmed Route0 identity, run-reset release, retained B input and advancing uptime. This no-loader control does not verify Chip32 interaction, A→B→A reconfiguration or runtime loader re-entry; Route3 is next. The original board reports remain as historical evidence for commit aac1469.
