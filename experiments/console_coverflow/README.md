# PCE、MD、SFC 与 CPS2 中文 CoverFlow

四组使用独立原生核心，共用封面动画和中文标题。建库从现有目录读取文件名，别名和封面按路径匹配。缺图时生成文字封面。

| 平台 | 适配范围 | 当前验证 |
|---|---|---|
| PCE | `.pce`、`.sgx` 卡带，2 KiB 普通存档 | 完整编译、布线和 APF 命令仿真通过。待实机。 |
| MD | NTSC 线性卡带镜像，64 KiB 电池存档 | 完整编译、布线和 APF 命令仿真通过。待实机。 |
| SFC | 标准 NTSC LoROM、HiROM、ExHiROM，按卡带类型创建普通存档 | 编译与 104 条时序检查通过，最小余量 +0.086 ns。启动控制器和 WRAM、ARAM 读写仿真通过。待实机。 |
| CPS2 | 原版 Jotego 实例及匹配的 `.rom`，保留 DIP、按键映射和独立 NVRAM | `.3` 编译与 124 条已约束时序检查通过，最小余量 +0.085 ns。真实 SPI 启动、实例配置、EEPROM 读回与保存返回仿真通过。待实机。 |

各入口使用独立普通存档，通过 Pocket 的 Quit 退出。PCE、MD、SFC 增加菜单 scaler，CPS2 复用原版的 384×224 scaler。MD 提供可选 CRT 风格，其他机种沿用原版已有选项。[Analogue 显示模式](https://www.analogue.co/developer/docs/openfpga/core-definition-files/video-json)

CPS2 `.2` 曾修正 APF 完成握手；后续完整 SPI 检查发现参数和 EEPROM 读取滞后一拍、实例配置只在上电复位应用，现已停止安装该版本。`.3` 提前准备参数响应、从原生 EEPROM 提交同步构造读回数据，并在每次绑定游戏时应用其配置。合成数据测试包含原生串行 EEPROM 写入、保存 flush、返回菜单及 Stop 后读回；不代表执行了游戏 CPU。继承时钟与外部存储引脚的时序边界见 [CPS timing scope](../cps1_coverflow/TIMING.md)。

最终 CPS 候选还修正了原生 `jt9346` 的全片擦除初始化：补齐地址归零与写数据全 1。原始模块失败对照及两种 EEPROM 宽度的完整逐字验证范围见 [ERASE_ALL 修复](../cps1_coverflow/EEPROM-ERAL-FIX.md)。这项修复不改变存档格式；含旧逻辑的中间位流不再用于新安装。

## 本地构建

1. 用 `prepare.py pce`、`prepare.py genesis` 或 `snes.py` 准备固定上游源码。PCE 在 `projects` 编译 `pce_pocket`，MD 在 `src/fpga` 编译 `ap_core`，SFC 在 `projects` 编译 `snes_pocket`。
2. 用 `package.py` 核对编译输入、完整时序报告和 APF 定义，再生成本地核心包。
3. 用[文件名建库](../../docs/FILENAME-MENUS.md)和[整批更新](../../docs/BATCH-UPDATE.md)生成菜单及安装计划。预检核对原 ROM、分页链接及存档身份。

SFC 使用空闲 SRAM 存封面，读取卡带头识别布局。LoROM、HiROM、ExHiROM 和 512 字节 copier header 的识别结果已与固定版本 Chip32 加载器的合成用例对照。SA-1、Super FX 和 PAL 等游戏继续用原版核心。

CPS2 的 `cps2_native.py` 生成 JTFRAME Pocket 工程的覆盖文件，[上游源码校验清单](cps2-source-lock.json)记录了提交和子模块。先用同版本 JTFRAME 的 `parse`、`cfgstr`、`msg`、`mmr`、`files syn` 生成 `cores/cps2/pocket` 工程。将生成的 `jtframe_pocket*` 放入 Pocket HDL 目录，按脚本的 `COVERFLOW_INPUTS` 列表加入覆盖源码，`font_cn.hex` 放在 Quartus 工程目录，编译 `jtcps2`。编译本次使用 Quartus 22.1std.2 和 seed 7。打包时 `--archive` 指向含 `jtcores` 源码和 `jtbin/pocket/raw` 元数据的本地目录。元数据使用 jtbin 提交 `7274a04840ba43ad529496b63bda9a18c491df68`。

## English

The four native previews use a shared CoverFlow menu. Build libraries from your own files with [the filename tool](../../docs/FILENAME-MENUS.md), then use [batch preflight and backup](../../docs/BATCH-UPDATE.md). PCE supports HuCard and SuperGrafx, MD supports linear NTSC cartridges, and SFC supports standard NTSC cartridges. CPS2 uses original Jotego instances and their ROMs, with the native button map and DIP values. The hardware reports cover fitting and timing. Actual game play and ordinary-save writeback await device acceptance.

源码与协议见 [PCE](https://github.com/agg23/openfpga-pcengine)、[MD](https://github.com/opengateware/openFPGA-Genesis)、[SFC](https://github.com/agg23/openfpga-SNES)、[JTFRAME](https://github.com/jotego/jtcores) 和 [Analogue 实例格式](https://www.analogue.co/developer/docs/openfpga/core-definition-files/instance-json)。
