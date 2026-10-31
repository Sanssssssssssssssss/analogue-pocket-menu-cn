# 按游戏调用对应的原生核心

目标：统一中文游戏库 → 选择游戏 → 按机种加载对应的 FPGA bitstream → 游戏。GB/GBC 使用原 GB/GBC 硬件实现，GBA 使用原 GBA 实现；一次只配置当前机种。这个目标不要求两套游戏电路同时放进 FPGA，不能用两套资源相加超预算来否定它。

2026-10-31 源码核对结果：按 ROM 选择原生程序已有社区实例；运行中的中文图标页主动发起重配置，仍缺已验证接口。本轮没有连接设备卡。

| 环节 | 证据与状态 |
|---|---|
| 一个包声明多个原生程序 | [官方 core.json](https://www.analogue.co/developer/docs/openfpga/core-definition-files/core-json)支持最多 8 个 bitstream |
| 启动时识别 ROM 并选程序 | [SNES loader](https://github.com/agg23/openfpga-SNES/blob/1a08c84ddef760bedd30a376114fc2e97527df19/support/loader.asm)解析 ROM 信息，在主程序、SPC7110/SDD1/BSX 程序、PAL 程序之间选择；[core.json](https://github.com/agg23/openfpga-SNES/blob/1a08c84ddef760bedd30a376114fc2e97527df19/pkg/pocket/Cores/agg23.SNES/core.json)列出三个 ID |
| OS 中重选可重载文件后调用 Chip32 | [官方 VM 初始化说明](https://www.analogue.co/developer/docs/openfpga/chip32-vm/initialization-of-the-chip32-vm)明确支持；这是宿主触发 |
| 自绘菜单按 A 后主动重启加载器 | [官方 Target 命令](https://www.analogue.co/developer/docs/openfpga/host-target-commands)与 [core-template](https://github.com/open-fpga/core-template/blob/da3a021b1eaf742604d86d8dc9b33a6666263e6a/src/fpga/core/core_bridge_cmd.v)中没有找到已验证的通用接口；不能把文件打开／读取当成已完成重配置 |
| 游戏结束后跨核心返回中文首页 | 未实现、未上机验证 |

SNES 的 `set_core` 路径先执行默认 `CORE 0`，特殊芯片或 PAL 分支再执行相应的 `CORE`。这是加载阶段的现成参考，不能由此推断运行阶段也可随时调用 Chip32。当前旧 VM 实验中的 CORE/HOST 仍是日志模型，不能认证 Pocket 宿主实际重配置。

## 下一项可证伪的小实验

2026-11-01：已建立[独立 A/B 探针](../native_routing/README.md)，包含两份板级源码、三种加载阶段、不可由写寄存器伪造的身份与有限按键轮询。RTL 和实际汇编已检查；旧日志 VM 必须因无 FPGA 读数而拒绝，防止把其 CORE 日志当作真机结果。官方启动流程明确将 Setup 与运行阶段分开；宿主是否显示加载阶段光栅仍待实测。

随后已完成独立诊断包：保留只读身份，增加最近按键及 M/D 结果，移除不用的音频时钟，按已有 GBA 的范围显式处理 APF 协议 I/O 例外。两套新版工程完成全流程编译和内部时序检查，备份后新增 `Pocket Lab Test` 四个入口；当前只请求验证 Route0 对照，实际换核仍待验收。详见[试验包与回退边界](../native_routing/README.md#独立实机诊断包)。

Route0 对照已获用户确认：固定身份正确、运行复位释放、B 键读数正确、计时持续增加。[实机记录](../native_routing/evidence/route0-device-report.json)仅认证该普通启动路径。随后 Route3 黑屏并短暂报错，Route1 可启动但 M/D 全零；实际旧字节码存在地址表达式截断，已用完整地址修正。新一轮 23 项指令模型检查和 A/B 板级编译通过，最小 Route4/5/7/6 包已在本地准备；[新记录](../native_routing/evidence/route1-route3-device-report.json)不把这些离线结果当作原生换核验收。

先使用无 ROM、无 BIOS、无存档的独立 A/B 程序，避免把未知重载机制直接接入游戏：

1. 验证加载阶段先配置一个简单选择器时，Chip32 尚未结束，画面、按键和 `PMPR` 桥接读数能否正常工作。
2. 用户在选择器中按键后，VM 读取选择并执行另一个 `CORE`；新程序显示不同的只读指纹和纯色，区分真实重配置与旧程序换颜色。
3. 验证 APF 交接、退出和反复 A→B→A。只有首轮加载成功不代表游戏运行后还能唤起 VM；需要单独验证返回与重新进入的触发。

“VM 在加载阶段持有选择器”是待测假设：系统可能一直遮住画面、不给核心按键，或不在 VM 执行期间服务 Target 文件请求。[文件指令](https://www.analogue.co/developer/docs/openfpga/chip32-vm/file-process)主要操作已声明的数据槽，也没有提供已验证的任意路径菜单启动接口。本轮没有把上述假设标记为可用，也没有生成可安装的统一启动器。

触发链成立后，才统一数据槽、BIOS 加载地址、平台目录、视频模式和普通存档交接。`CORE` 选择的是同一包中声明的程序 ID，不能把其他已安装核心的文件夹名直接当作 ID。现有两套 BIOS 槽与菜单数据格式不同，具体冲突见 [可行性研究](FEASIBILITY.md)。

也核对了芯片级 `ALTREMOTE_UPDATE`：Cyclone V 的[启用条件](https://www.intel.com/programmable/technical-pdfs/683375.pdf)要求相应的 Active Serial／配置存储器模式，而当前工程声明 Passive Serial、由 Pocket 宿主管理配置。通用 FPGA 远程升级示例不能直接当作从 SD 选择 openFPGA 核心的功能；本轮未启用该 IP 或改配置模式。
