# 原生换核 A/B 探针

2026-11-01。这是独立诊断源码，**不是统一游戏前端**。A/B 单独启动、加载器读写诊断和同一加载器内的固定 A→B 换核已获实机确认。按键交互、返回 A 及游戏运行后的重入仍待后续验证。

目标是把三个问题分别验证：加载器还在运行时能否收到按键；宿主能否显示该阶段的视频；第二次 `CORE` 是否确实配置了另一个 FPGA 程序。启动时选中编号、真正重配置、游戏运行后重新唤起加载器，是三个不同结论。

## 新核对的边界

- [官方启动流程](https://www.analogue.co/developer/docs/openfpga/core-boot-process)在 Setup 阶段描述无音视频，加载完成后才发 Reset Exit。因此仅让 FPGA 自己产生光栅，不能证明 Pocket 屏幕已显示菜单。
- [CORE / HOST 指令](https://www.analogue.co/developer/docs/openfpga/chip32-vm/special)明确描述已加载程序可能跳过 `CORE`；本试验已确认同一加载流程内从 ID 0 切到 ID 1。`HOST 0x4001` 释放复位，`0x4002` 继续启动；运行中主动唤起加载器仍须单独验证。
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
| `90` / `A0` / `A4` | 新版 P / M / D 的只读别名；写入不改变结果 |

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

随后 Route3 黑屏，按 B 后短暂出现 Chip32 相关错误并返回；没有记录到完整错误，B 也可能取消了宿主加载流程。Route1 可启动，ID 正确、计时正常，但 M/D 全零。[现场记录与旧字节码复核](evidence/route1-route3-device-report.json)保留这些限制。

## 地址截断修正与最小测试

实际汇编后的旧 `ld r0,#base+0x20` 只加载 `0x20`，没有保留 `0x60000000`；阶段、按键、时钟和 D 的地址同样被截断。对已安装 Route1 的原字节码复测，也得到 M/D 全零、没有发起第二次 CORE。源码已改用完整 32 位地址常量。该错误足以解释无效读写，但不能单独解释 Route3 的全部宿主错误。

`probe_isolation.py` 在真实 Chip32 指令解释器外提供明确标记的 FPGA/宿主模型：覆盖三种旧加载阶段各六条路径、四个新最小加载器，以及复现截断错误的负向检查，共 23 项。它执行真实汇编字节码，**CORE、HOST、PMP 的回应仍是模型**，不证明 Pocket 会允许重配置。见[离线收据](evidence/isolation-validation.json)。独立 RTL 检查也验证向诊断只读别名写零不会擦除结果；没有证据表明系统菜单曾实际擦除旧结果。

新硬件 A/B 分别使用 691 / 684 ALM、均为 2 M10K、0 DSP；各 44 条时序摘要无负 slack、TNS 均为零，最小 slack 为 0.134 / 0.124 ns。APF 协议 I/O 仍使用明确例外，不能称为完整外部板级时序签核。[编译收据](evidence/isolation-builds.json)与历史编译分开保存。

四个新增入口均没有按键轮询、CALL/RET 或提前 HOST；文件操作只加载 16 字节合成种子，没有游戏或非易失写入。

| 测试顺序 | 入口 | 预期诊断 |
|---|---|---|
| 1 | Route4 | 直接启动 A；ID=`0x504C4100`，M/D=0 是正常值 |
| 2 | Route5 | 读回 A；ID 和 D=`0x504C4100`，M=`0xB1` |
| 3 | Route7 | 直接启动 B；ID=`0x504C4201`，M/D=0 是正常值 |
| 4 | Route6 | A→B；只有 ID 和 D=`0x504C4201` 才支持真切换，M=`0xB2` 单独不算通过 |

```sh
python experiments/native_routing/prepare_isolation.py --archive /path/to/core-template.zip --out .work/native-routing/isolation
# 编译 isolation/A/src/fpga 与 isolation/B/src/fpga。
# 先构建上述 Chip32 simulator 的 library，使用同一 Rust 工具链链接模型驱动：
rustc --edition=2021 experiments/native_routing/vm_contract.rs --extern chip32_sim=/path/to/libchip32_sim-HASH.rlib -L dependency=/path/to/deps -o .work/native-routing/vm-contract
python experiments/native_routing/probe_isolation.py --prepared .work/native-routing/isolation --bass /path/to/bass --model .work/native-routing/vm-contract --library /path/to/libchip32_sim-HASH.rlib --out .work/native-routing/isolation-check
python experiments/native_routing/stage_trial.py --isolation --build .work/native-routing/isolation --validation .work/native-routing/isolation-check/receipt.json --out .work/native-routing/isolation-package
```

输出 43 个文件约 6.54 MB。已重新识别卡并备份当前状态，仅新增 Route4～7 的 40 个文件、6,368,966 字节；3 个共用文件哈希一致，保留 Route0～3。安装后校验新增文件及受保护的 4,115 个原文件均一致，详见[安装记录](evidence/isolation-install-report.json)。

Route4 已获实机确认：蓝屏立即出现、ID=`0x504C4100`、R=`1`，见[现场记录](evidence/route4-device-report.json)。这验证最小加载器入口能够正常启动 A 并释放运行复位。

随后 [Route5 通过](evidence/route5-device-report.json)：用户确认蓝屏，ID/D 均符合预期 `0x504C4100`，M 符合 `0xB1`。这验证 VM 的 PMPR 身份读取、PMPW 结果写入和 Core Settings 只读别名回读。

[Route7 通过](evidence/route7-device-report.json)：橙屏、ID=`0x504C4201`、R=`1`，确认 B 能单独启动。[Route6 通过](evidence/route6-device-report.json)：用户确认橙屏、ID/D=`0x504C4201`、M=`0xB2`，确认同一加载器固定 A→B 的第二次 CORE 真正配置了 B。以上均为启动完成后的画面，尚未证明等待按键期间能显示菜单，也未认证游戏运行后重新进入加载器。

## 修正后的按键测试

新版 `loader.asm` 使用完整地址，并在每次 CORE 后加载已验证的 16 字节合成槽。输入仍设约 5 秒计时与 131,072 轮上限，错误消息增加换行以便完整显示。A/B 均触发同一条 A→B→A 身份检查；当前按键用于确认输入通路，尚未分派游戏。

`stage_trial.py --interaction` 只生成新的 Route8～10：初始化前、释放复位后、完整初始化后等待按键。沿用已实机通过的同一 A/B 硬件，核对编译源码与文件哈希，**没有重新编译或更换硬件逻辑**。见[复用编译收据](evidence/interaction-builds.json)和[本轮 23 项模型检查](evidence/interaction-validation.json)。

```sh
# 用当前源码按前文重新准备和检查；硬件完全一致时也可核验后复用已有 A/B 编译输出。
python experiments/native_routing/stage_trial.py --interaction --build .work/native-routing/interaction --validation .work/native-routing/interaction-check/receipt.json --out .work/native-routing/interaction-package
```

输出 33 个文件约 4.95 MB。已备份安装，新增 30 个核心文件、4,777,669 字节；3 个共用文件保持一致，安装后 4,169 个原文件校验通过，见[安装记录](evidence/interaction-install-report.json)。先测 Route8 不按键时能否正常退出，再测试等待期间的按键、画面与 A→B→A 结果。M=`0xE2` 表示没有选到新按键，M=`0xA0` 表示身份检查通过；不能把正常退出直接当作成功。本目录不提供游戏、BIOS、存档或二进制核心下载。

[Route8 不按键实机通过](evidence/route8-device-report.json)：几秒后蓝屏，ID=`0x504C4100`、M=`0xE2`、D=`0`。这确认修正后的初始化前轮询能够正常走完无输入分支，未计量精确等待时长。下一项 Route10 在完整初始化后等待输入：先松开 Run，再在前两秒短按 A，记录按键前是否已有蓝屏和最终 ID/M/D。

随后 [Route10](evidence/route10-device-report.json) 与 [Route9](evidence/route9-device-report.json) 在用户短按 A 后仍为 M=`0xE2`、D=`0`、A 身份。两轮没有进入按键触发的换核分支；用户没有单独确认按键前的画面时序。当前证据无法区分按键时机、等待窗口和宿主是否在此阶段发送输入，不能把它们记成按键测试通过。

## 计时与运行后重入对照

新增两个离线候选入口，均沿用相同 A/B 硬件，文件操作仍只有只读的 16 字节合成槽。[31 项字节码模型检查](evidence/handoff-validation.json)包含旧回归、实测时长的输出格式、无时钟退出上限，以及模型中保存 R12 后的重入分支；模拟器不产生真实按键或 OS 重入事件。[编译复用收据](evidence/handoff-builds.json)与旧硬件报告分开保存。

| 入口 | 用途 | 读数 |
|---|---|---|
| Route11 | 等待最多约 15 秒或达到轮询上限，累计 VM 期间读到的按键 | M 高字节 D1=捕获选择、D2=计时结束、D3=轮询上限；低 16 位为按键按位或；D 为实际经过的 FPGA 毫秒数 |
| Route12 | 先结束 VM、正常运行 A，再从系统 UI 重载槽来重新调用 VM | 初始 M=C1、D=A；运行时按 B 后 C=2；重入成功切 B 后 M=C2、ID/D=B |

[官方 data.json](https://www.analogue.co/developer/docs/openfpga/core-definition-files/data-json)说明 Chip32 下参数位 7 会软重启并保留 FPGA 和 VM 寄存器状态，之后由 VM 处理选中的槽。Route12 使用 `parameters=0x89`：可重载、只读、软重启，未设置 FPGA 完整重载位。VM 在重入时先读取 FPGA 锁存的选择，再执行 CORE。M=E6 表示未读到选择，M=E7 表示目标身份不符。

Route12 的对照步骤：Run 后松开 A，蓝屏时短按 B；在 Core Settings 先确认 C=2，再选择 **Reload test**，重新选中 `probe.dat`。预期橙屏、M=C2、ID/D=`0x504C4201`。这一实验明确由 OS 的文件重载触发；按游戏菜单直接发起重入仍待研究，尚未生成自动统一前端。

```sh
python experiments/native_routing/prepare_handoff.py --reuse .work/native-routing/interaction --out .work/native-routing/handoff
# 重新链接 vm_contract.rs 后，用 probe_handoff.py 代替 probe_isolation.py，参数相同。
python experiments/native_routing/stage_trial.py --handoff --build .work/native-routing/handoff --validation .work/native-routing/handoff-check/receipt.json --out .work/native-routing/handoff-package
```

也可用 `prepare_handoff.py --archive /path/to/core-template.zip` 从固定官方模板准备新工程，再完成硬件编译。候选包为 23 个文件约 3.36 MB，其中 3 个为已存在的共用文件。此包目前仅在电脑准备，安装和实机结果另行记录。

## English

This is a **native FPGA routing diagnostic**, not a unified frontend. Two official-template board projects carry immutable A/B identities; three assembled Chip32 loaders compare input visibility before initialization, after reset release, and after full initialization. The old logging VM must reject the absent FPGA identity instead of claiming a switch. Diagnostic EXIT 0 is not routing success: M=0xA0 is required for the A/B/A identity check.

The local trial removes unused audio clocks and explicitly excepts APF protocol I/O. Internal timing passes; this is not external board-I/O signoff. Physical reports accept A/B startup, VM PMP reporting and fixed A-to-B switching in Route6. Route8 completed its bounded no-input path. Route9 and Route10 still reported M=0xE2/D=0 after A taps, so input-driven switching was not entered; timing and host input delivery remain unresolved. New local Route11 measures elapsed time and observed keys. Route12 is an explicit OS-reload control using a read-only 16-byte slot and parameters 0x89, preserving FPGA state before VM re-entry. Thirty-one model checks pass, including preserved-register branch models; no actual OS event is simulated. Physical re-entry, direct automatic triggering, A-to-B-to-A return and game/save handoff remain unverified. Historical reports and existing game entries are preserved.
