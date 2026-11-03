# GBA 共用 CoverFlow 适配

`.6` 实机首屏正常，进入子目录后文字出现、封面未加载、按键无响应，已恢复 [GBA `.3`](../gba_menu/README.md)。`.5` 与 `.6` 均拒绝重新打包／安装；以下通过记录仅为此前离线检查，不能作为继续安装的依据。具体原因尚待复现，见[设备反馈](../../docs/DEVICE-FEEDBACK-2026-11-03.md)。

后续源码已修正一个单独复现的错误处理缺口：`CF_ART_DRAIN` 遇到后台错误立即进入可返回的错误页，未完成上传的排空等待使用较短的画面 watchdog。旧 `.6` 在注入错误的用例中失败，修正后错误／超时、B 返回及原有加载／保存控制回归通过，见[收据](evidence/drain-fault-guard.json)。这不等于已确认实机根因；修正未生成或安装新 bitstream。

`.6` 复用 [GB/GBC CoverFlow 的几何、逐张移动／缩放、倒影及文字绘制](../coverflow_shared/README.md)。GBA 保留原生游戏核心，封面改放原先空闲的 CRAM1；CRAM0、ROM／EWRAM／普通存档和 RTC 通道继续使用原接口。封面存储使用原生内存时钟（上游标称 100.663296 MHz）及原上游 CellRAM 时序状态机，跨时钟上传／失效事件和状态经过同步。

菜单为 320×288，采用原生视频时钟（上游标称 8.388608 MHz）的 4/5 像素使能；GBA 游戏继续使用 240×160、3:2 的 scaler 0。新增的 scaler 1 用于菜单。已有游戏显示设置保留，默认不增加 LCD 网格。APF Memories／休眠在此实验中仍禁用。

## 检查范围

- GBA 实际时钟下，四帧共 448,800 次像素比较与 GB/GBC 参考绘制相符，包含双向姿态及同时上传另一完整封面。参考副本只含已记录的负裁切坐标修正；冻结源码不变。
- 真实 APF 命令引擎、上游 loader、Intel FIFO／RAM 与 CellRAM 引脚模型完成首次进入菜单、两张完整封面和按键触发动画。GBA 游戏保持 reset，VS 为零，菜单自行产生帧节奏。发布缓存标签后多等一个时钟，避免重复读取刚完成的封面。
- 独立控制仿真覆盖 A/B、环绕、三次游戏加载、64K／128K 普通存档、RTC、暂停、保存失败保留现场及非法路径／旧完成信号拒绝。上游 loader 另检查两种字节序、完整 16 位字形列及头部隔离。
- [完整编译和全部 104 条时序检查通过](evidence/cellram-gba.6.json)：17,305 ALM、284 M10K、48 DSP，最小余量 +0.090 ns，所有 TNS 为零，无 Critical Warning。仅 fit 成功或界面仿真成功均不允许生成候选。

上游请求的内存／视频时钟为 100.663296／8.388608 MHz；TimeQuest 量化报告约 100.69／8.39 MHz，完整时序检查使用其实际生成时钟。光栅仿真使用上游标称值及相同的 12:1 比例。

CellRAM 为行为模型，主机和文件为合成数据，普通存档检查不认证真实卡的保存耐久性。首次菜单检查默认验证按键启动实际动画；逐姿态绘制由独立差分用例验证。另一次 `+full_animation` 运行已完成连续八姿态、共十一帧完整光栅，所有输入先核对为相同字节，选择／姿态／光栅／错误断言通过；收据在同一证据文件。`probe_boot.py --full-animation` 可执行这一耗时检查，默认模式只检查动画启动。

## 资源与更新

`library.py` 将已核对的本地 GBAF1 菜单转为 GBAF2，每项保留 64 KiB 封面／中文字形块。每页最多 128 项（含返回），大目录须分页。ROM、SAV、RTC 的路径／身份字段逐字节保留，转换不复制游戏或进度。

`update.py` 提供当前卡与核心／菜单格式预检、逐 ROM 核对、局部备份、文件回读及回退。回退保留后来玩的进度，已有游戏视频设置沿用。实际卡更新须重新识别设备，不能复用历史盘符和哈希作为当前认证。

```sh
python experiments/gba_coverflow/prepare.py --sources .work/multi-system/sources/gba --out .work/gba-menu/coverflow-build
python experiments/coverflow_shared/probe_psram_raster.py --gba --gba-source .work/multi-system/sources/gba --out .work/gba-raster
python experiments/gba_coverflow/probe_boot.py --build .work/gba-menu/coverflow-build --out .work/gba-boot --intel-model /licensed/altera_mf.v
python experiments/gba_coverflow/probe_control.py --build .work/gba-menu/coverflow-build --out .work/gba-control
python experiments/gba_coverflow/probe_control.py --build .work/gba-menu/coverflow-build --out .work/gba-fault-control --fault-recovery
python experiments/gba_coverflow/probe_boot.py --build .work/gba-menu/coverflow-build --out .work/gba-hierarchy --intel-model /licensed/altera_mf.v --hierarchy
```

原生 GBA 来源和许可见[原实验](../gba_menu/README.md)。Intel 模型由本机合法 Quartus 安装提供，不随仓库分发。私人标题／封面库、BIOS、ROM、存档不入仓库。没有公共合并 GBA 二进制发行。

## English

Candidate `.6` shows its landing page on hardware but freezes after opening a child page: captions appear, artwork stays unloaded and input is unresponsive. The previously accepted `.3` has been restored. Both `.5` and `.6` are blocked from repackaging/installation. The results below are historical offline checks, not device acceptance; the root cause remains unconfirmed.

The source now fixes a separately reproduced error-handling defect: an upload-drain backend error reports promptly, and an incomplete drain uses the shorter frame watchdog. The old `.6` controller fails fault injection; the corrected controller passes error/timeout, B-return and inherited launch/save regressions. [Evidence](evidence/drain-fault-guard.json) does not establish the original physical cause. No corrected bitstream has been built or installed. `--hierarchy` adds a 12-entry child page, its 11-cover prefetch set, B-return/root reload and subsequent input to the full-wiring boot probe.

The same GB/GBC CoverFlow geometry/compositor now uses otherwise idle CRAM1 at the native memory clock (nominally 100.663296 MHz), retaining the upstream CellRAM pin timing state machine. Native GBA ROM, EWRAM, save/RTC and CRAM0 interfaces remain independent. Menu output is 320×288 at 4/5 of the native video clock; game scaler 0 stays 240×160 with inherited settings.

The upstream requested clocks are 100.663296/8.388608 MHz; TimeQuest reports approximately 100.69/8.39 MHz after PLL quantization. Timing uses the generated clocks; raster simulation uses the nominal pair with the same 12:1 ratio.

Four complete GBA-clock frames pass 448,800 golden pixel comparisons, including concurrent atlas upload. A production-wiring boot probe joins the actual APF engine, upstream loader, Intel FIFO/RAM and a modeled CellRAM bus while game VS is held at zero, checking complete cover transfers and an actual key starting animation. It also rejects redundant uploads. A separate rerun of the source-checked compiled probe completes all eight sequential key-driven poses and eleven full raster frames, with selection/pose/raster/fault assertions passing. Default boot mode only checks animation startup; `--full-animation` runs the additional slow case. Separate controller checks cover launch/save/RTC/error recovery, and separate geometry/raster checks cover poses. Full compilation and all 104 timing records pass: 17,305 ALMs, 284 M10Ks, 48 DSPs, minimum +0.090 ns, zero TNS and no critical warnings. These models do not establish physical compatibility, gameplay or save durability. ROMs, BIOS, progress, private catalogs and licensed simulation models are excluded.
