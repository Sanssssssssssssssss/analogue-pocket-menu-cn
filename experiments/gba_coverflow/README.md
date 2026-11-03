# GBA CoverFlow 动画

`.7` 候选沿用 GB/GBC 的封面移动、缩放、亮度、倒影及中文文字绘制，使用五张封面的关联缓存。GBA 游戏由原生核心运行。完整编译通过 104 项时序检查，最小余量 +0.076 ns，TNS 为零；本版实机动画与游戏／存档验收仍待完成。此前可用的 `.3` 保留为回退版本。

封面放入 Pocket 的 256 KB SRAM，占用 227,840 字节。八项 RAM 队列接收上传；完成标志在绘制读取期间保持有效，发布标签前确认整张图片已写完。各图层共用最后一步 RGB 混合，保留整数截断与显示优先级。错误和上传超时可返回菜单。ROM、EWRAM、CRAM0、存档及 RTC 的原有源码与 `.3` 一致。

菜单输出 320×288，使用 GBA 视频时钟的 4/5 像素使能。游戏使用原有 240×160 scaler 0；菜单使用新增 scaler 1。游戏画面仍为原比例、无外框，GBA 默认无 LCD 网格。APF Memories／休眠在此实验中仍禁用。

## 已完成的离线检查

- 五个完整 SRAM 图集、113,920 次物理半字写入、并发上传／读取、4,850 次 DWORD 校验、上传完成保持、非法地址和失效恢复通过。
- 18 帧、2,019,600 次像素比较，与 GB/GBC 参考绘制一致；左右各八个连续姿态、合成中文标题及同时上传第五张封面通过。参考副本只含已记录的负裁切坐标修正；冻结的 GB/GBC 输入未修改。
- 真实 APF 命令引擎、上游 loader、实际 Intel FIFO 和校准后的便携 RAM 模型连接完整 UI，在 GBA 标称时钟下完成 149 帧：A 进入 12 项子目录、五张完整封面预读、16 次切换（含环绕和反向）、B 返回和后续按键。共 121 次 APF 操作、569,600 次物理半字写入。
- 独立控制仿真通过三次 ROM 加载、64K／128K 普通存档、RTC、暂停／恢复、保存失败保留现场、非法路径及旧完成信号拒绝；封面错误／超时与 B 返回通过。
- 从冻结上游重新生成 `.3` 基线后，93 个既有输入逐字节一致，其中 45 个为原生 GBA 源码；生成的错误画面 HEX 只有换行格式不同，数值相同。另重新生成并核对了 106 个最终输入，GB/GBC 的 135 个冻结输入一致。

这些是合成主机、文件及 SRAM 引脚模型的检查。游戏 CPU、实卡保存耐久性和本次动画手感仍需实机确认。便携 RAM 先与实际 Intel 模型核对；SRAM 模型按器件时序编写，不能代替板上验收。完整收据见[本版验证](evidence/sram-gba.7.json)。

![RTL 仿真的封面动画慢放，使用自绘图标与合成中文条目](evidence/gba7-preview.gif)

上图每姿态慢放至 100 ms；核心的八帧移动按菜单帧率执行。它是 RTL 仿真画面，不是掌机录像。

## 编译与复现

```sh
python experiments/gba_coverflow/prepare.py --sources .work/multi-system/sources/gba --out .work/gba-coverflow
python experiments/gba_coverflow/probe_control.py --build .work/gba-coverflow --out .work/gba-control --fault-recovery
python experiments/gba_coverflow/probe_boot.py --build .work/gba-coverflow --out .work/gba-boot --intel-model /licensed/altera_mf.v --hierarchy --full-animation --simulator verilator
python experiments/gba_coverflow/probe_sram_raster.py --build .work/gba-coverflow --out .work/gba-raster --intel-model /licensed/altera_mf.v
# 在 .work/gba-coverflow/src/fpga/build 中运行完整 Quartus compile。
python experiments/gba_coverflow/probe_timing.py --build .work/gba-coverflow --quartus-sta /path/to/quartus_sta
python experiments/gba_menu/package.py --build .work/gba-coverflow --sources .work/multi-system/sources/gba --out .work/gba-package --coverflow
```

时序验收要求完整 fit、全部多角时序余量非负且 TNS 为零。另逐条检查四个器件角下的 37 个输出及 16 个输入端点，数据路径不得超过模型的 4.25 ns 预算，公共时钟插入延迟另计。打包器要求匹配 RBF、SDC、QSF、模型和检查脚本哈希的收据，缺失或超预算即拒绝打包。

初始 4 ns 模型拒绝了本版一条 4.053 ns 的地址输出路径；实测输入路径最大 2.870 ns。模型随后按 4.25 ns 双向预算、9.930 ns 保守周期和 25 ns 字节输出关闭延迟重新验证。依据 [AS6C2016-55 数据表](https://www.alliancememory.com/wp-content/uploads/AllianceMemory_2M_LPSRAM_AS6C201620May202021_v1.1_May2021.pdf)，读访问保留 `7 × 9.930 − 4.25 − 55 − 4.25 = 6.01 ns` 板级／偏斜余量。原生 CPU 时钟及所有可执行时序约束未改变。

编译树保留原样；交付副本只修正 SDC 注释中的预算说明。收据记录前后哈希，并核对每条可执行 SDC 行及 RBF 相同。打包器再次验证这些注释变更。

`tb_sram_cache.sv` 可与 `sim_sram.sv` 和生成的 `coverflow_sram_cache.sv` 直接用 Icarus 运行。`probe_boot.py` 保留旧 CellRAM 构建的复现能力；默认生成器现在只生成 `.7` SRAM 方案。

## 此前失败版本

`.5` 和 `.6` 已被实机反馈否决并禁止安装。`.6` 在进入子目录后封面未加载、按键无响应；此前离线仿真未复现这个硬件故障，不能声称根因已确认。独立发现的排空错误处理缺口已修复，见[错误注入收据](evidence/drain-fault-guard.json)；此前编译数据保留在[历史记录](evidence/cellram-gba.6.json)。卡的旧菜单与最新进度通过有版本的局部备份保护。

## English

Candidate `.7` reuses the accepted GB/GBC CoverFlow geometry and compositor with five associative SRAM cover slots (227,840 bytes), an eight-entry RAM upload queue and one shared final RGB blender. The GBA CPU remains native. Full compilation passes 104 timing records with +0.076 ns minimum slack and zero TNS. Hardware animation and game/save acceptance remain pending; `.3` is the previously accepted fallback.

Offline checks pass all 113,920 SRAM writes, 4,850 DWORD samples and 18 complete raster frames / 2,019,600 golden pixel comparisons. The APF/loader/vendor-FIFO wiring runs 149 frames through a 12-entry child, 16 moves including wrap/reversal, B return and subsequent input. Portable RAM is crosschecked against Intel first. The datasheet SRAM model uses 4.25 ns I/O delays, a conservative 9.930 ns period and worst-case byte-output disable. Separate lifecycle/error tests pass. Against `.3`, 93 inherited files (45 native GBA files) are byte-exact; generated error HEX differs only in line endings. All 106 final inputs and 135 frozen GB/GBC inputs are checked.

Packaging requires full fit, all timing/TNS checks and four-corner SRAM routes within the 4.25 ns modeled budget. Measured maxima are 4.053 ns out / 2.870 ns in; the original 4 ns estimate correctly blocked packaging before the model was rerun at its revised bound. The conservative read margin is 6.01 ns. Native clock requirements and executable constraints are unchanged. Only budget comments were updated in a delivery copy, with both SDC versions and the identical RBF bound in the receipt. Hardware behavior remains pending.

Both `.5` and `.6` are device-rejected and blocked. Prior simulation passes did not reproduce `.6`'s physical child-page freeze; its root cause remains unconfirmed. Historical receipts are retained. No ROMs, BIOS, personal progress, private catalogs or licensed simulation models are included.
