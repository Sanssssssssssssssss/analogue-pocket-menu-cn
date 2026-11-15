# Pokémon Mini 中文 CoverFlow 预览

`0.1.0-pm.1` 已通过完整 Quartus 构建、四角时序和离线接口验证，可以作为待实机验收的预览包。上游固定为 [`agg23/openfpga-pokemonmini@81cfccb7`](https://github.com/agg23/openfpga-pokemonmini/tree/81cfccb7c5620f7acb4a992df2ed355e922d0afd)，保留 GPL-2.0 引擎、内置 `freebios.hex`、原生时钟、96×64 游戏的 3:2 比例和 8192 字节 EEPROM。

原 CPU 除法半周期路径的基线为 −26.625 ns。现在使用精确的八级除法流水线，CPU 微码及使能节奏保持原样；LCD 颜色的 `/255` 长路径改为逐值相同的 256 项组合表。没有为这些同步路径增加 false path 或 multicycle。最终 104 项四角时序记录全部非负，最低 +0.042 ns，0 critical warning。拟合使用 8,309 ALM（45%）、46 RAM 块（15%）、30 DSP（45%），完整编译 6 分 34 秒。

离线验证包括：

- 33,423,360 个非零除法输入组合逐位对照原 ALU；实际 CPU 运行 1024 次 DIV、1024 次 MUL，逐拍比较总线、寄存器、暂停和 DMA 行为。
- 256 种 LCD 颜色及 640 万时钟、12 帧视频逐拍等价。
- 真实 APF/FIFO/SRAM 的 117 帧启动、12 次导航、8 个动画姿态、A 进入/B 返回；首次缺图失败仍显示常驻中文错误，Stop/Run 可重新取得画面。
- 原生 ROM SDRAM 32 KiB 写入、完整 8 KiB EEPROM 的大小端下载/上传，以及暂停、恢复、保存、失败和超时闭环。
- 真实包在中文合成目录的准备、安装、刷新、回退；已有和新生成的 EEPROM 均保留。

封面 SRAM 使用 96 MHz 时钟：发读后第 7 拍采样、第 8 拍消费并换地址。按 AS6C2016 的 55 ns 访问时间，分别检查四角全部 37 个输出引脚和 16 个输入位，并扣除实际发收时钟插入差；最小余量 7.749 ns，尚未计入未测的板线、实际负载和未配置的时钟不确定度。读保持、写脉冲及总线换向另有检查。包中保留拟合与独立审查证据；这不是整板物理签核。

`Assets/poke_mini/common/` 下的 `.min` 可放在中文子目录，文件名默认成为标题，也支持别名和封面。需要自备游戏；公开包没有试玩 ROM。缺失的独立存档才生成 8192 字节 `FF` 种子，原生旧档不按长度猜测导入。游戏中 **L+R+Select** 打开暂停页，可恢复或保存后返回；不支持即时存档或睡眠。

构建入口：

```text
prepare.py --source <固定源码> --out .work/continue-20261116/pokemini/<新候选>
compile.sh <候选> <新构建输出>
check_cpu.py / check_video.py / check_boot.py / check_transfer.py / check_recovery.py --help
package.py --build <完整构建树> --prepared-source <候选> --io-evidence <sram-io.tsv> --sram-review <独立analysis.json> --out .work/continue-20261116/pokemini/<新包>
library.py --source <库根目录> --out <新菜单目录>
```

打包器核对最终编译输入、四角 STA、全部 SRAM 引脚与独立发收时钟审查；拒绝缺证据或失败构建。对应源码包括 QPF/QIP、字体、微码及所有综合初始化文件。已拟合源中的 `100.663296MHz` 缓存注释来自早期模板，实际为 96 MHz；SDC 的每侧 4.25 ns 注释在审查中按同一次访问的 8.5 ns 往返数据预算核对，没有更改实际约束。

## English

The preview fixes the native divider and LCD arithmetic paths while retaining CPU cadence, native clocks, pixel values and 8 KiB EEPROM semantics. Full four-corner compilation and synthetic CPU, video, APF, memory, save and installer tests pass. The independent SRAM analysis leaves 7.749 ns before unmeasured board/loading and unconfigured clock uncertainty. Physical gameplay, display and save acceptance remain pending. Supply your own `.min` files; no game ROM is bundled. GPL-2.0 engine notices and corresponding build inputs accompany the package. Missing dedicated saves start erased; existing saves are retained, and old formats are not guessed.
