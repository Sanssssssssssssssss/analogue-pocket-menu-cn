# FC/NES CoverFlow 离线候选

复用已认可的 GB/GBC CoverFlow：封面独立移动、缩放、明暗、圆角、倒影、Unicode 标题及底部中文。NES 继续由自己的 FPGA 核心运行。当前候选已通过完整编译和 128 条时序检查，最小 slack **+0.056 ns**，所有 TNS 为 0；尚未上机。

`prepare.py` 从固定 SHA 的 NES 上游压缩包生成独立 `.work` 树，继承此前的加载／暂停／普通存档适配。五个关联封面槽使用独立 BRAM，不改游戏 SDRAM 总线。`library.py` 扫描整个 `Assets/nes/common`，保留分类、精选和备选入口，同目录相同内容只显示一次；相同 ROM 在不同分类共用内容哈希对应的进度。ROM 不复制，既有进度不覆盖。

## 验证与边界

- 完整布局布线：16,010 / 18,480 ALM，283 / 308 M10K，40 / 66 DSP。没有 Critical Warning；继承的外部接口时序例外仍存在，不能将片内 STA 当作整板实测。
- 720 次双向／环绕选择、9 种目录数量、5 张完整封面及 56,960 次 DWORD 读回通过。关联映射避免游戏号取模产生的错图。
- 真实绘制与原 GB/GBC 参考比较 4 个完整画面、448,800 个光栅采样。参考副本仅修正[共用绘制说明](../coverflow_shared/README.md)中已复现的原裁切符号问题，135 个冻结输入保持原样。
- 实际控制器仿真通过三次 ROM 启动、预建进度读取、暂停恢复、保存／flush、写失败保留现场、路径及超时拒绝。安装工具的合成卡检查覆盖格式错配、ROM 改变、备份／回退和保留新进度。
- 原生视频时钟下，320×288 菜单约 **47.85 Hz**；保持原八帧姿态，实际播放速度及 Pocket 缩放器表现待整包测试。游戏视频沿用原时钟和显示配置。
- 此实验入口关闭 Memories／休眠，使用独立 256 KiB 普通存档。旧核心入口和进度继续保留；不会自动导入无法核对的存档。NES mapper、PAL、外设、实际声音／保存耐久性尚未逐项验收。

证据见 [编译摘要](evidence/build.json)、[完整时序](evidence/nes.sta.summary)、[加载流程](evidence/control.json)、[光栅比较](evidence/raster.json)。它们均不代表实机游戏验收。

## 电脑构建

先按[原 NES 实验](../nes_menu/README.md)获取固定上游 ZIP。需要 Quartus、Icarus、Verilator、Python 和本仓库依赖。所有输出位于电脑，下面不写卡：

```sh
python experiments/nes_coverflow/prepare.py --archive .work/multi-system/sources/originals/nes.zip --out .work/nes-menu/coverflow-build
# 在隔离构建目录 projects/ 执行 Quartus --flow compile nes_pocket，完整编译通过后：
python experiments/nes_menu/package.py --build .work/nes-menu/coverflow-build --archive .work/multi-system/sources/originals/nes.zip --out .work/nes-menu/coverflow-package --coverflow
python experiments/nes_coverflow/library.py --card X:/ --out .work/nes-menu/coverflow-library --titles local-titles.json --covers local-covers
python experiments/nes_coverflow/install.py --card X:/ --package .work/nes-menu/coverflow-package --library .work/nes-menu/coverflow-library
```

最后一条仅预览。卡身份、逐个 ROM、菜单记录、进度路径及包格式核对通过后，`--backup` 指定全新的电脑备份目录并加 `--apply` 才会新增文件。仅适用于首次新增独立入口；已存在的目标会被拒绝。`--rollback --backup <目录>` 预览回退，加 `--apply` 后移除新增入口文件，保留游戏进度。目录、字体及封面缺项会记录，不能将合法 ROM 头视为兼容性证明。

库生成器和安装器预检均支持 `--offline-source` 读取电脑既有 ROM 备份。安装器的离线模式只核对，不接受 `--apply` 或 `--rollback`；正式写卡仍要核对实际卡身份和 ROM。原备份不需要新增 Pocket 标记文件。

## English

Offline native NES candidate reusing the accepted GB/GBC CoverFlow. Full fit and 128 timing records pass with +0.056 ns minimum slack, using 16,010 ALMs / 283 M10K / 40 DSP. Five fully associative texture slots use independent on-chip RAM; the game SDRAM path is retained. Synthetic cache, packed-RAM, raster, controller and installation/rollback checks pass. The original video clock produces an approximately 47.85 Hz menu; physical scaler, animation, mapper, audio and save acceptance remain pending. Memories/sleep are disabled in this independent experiment. Existing entries/progress are retained; only missing isolated ordinary saves are seeded. The whole NES directory is indexed, without ROM copies. No firmware is modified. New tools retain MIT licensing; inherited NES components keep their own licenses.
