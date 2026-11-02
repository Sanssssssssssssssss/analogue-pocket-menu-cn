# GBA 共用 CoverFlow 适配

2026-11-03：`.5` 虽通过以下离线检查，上机仍出现“操作失败”，原因未确认，已拒绝重新打包／安装。使用者已恢复 `.3` 并确认菜单、游戏可进入；GBA 动画仍是当前待修项。后续修正先离线验证，见[设备反馈](../../docs/DEVICE-FEEDBACK-2026-11-03.md)。以下编译和实现描述属于历史 `.5`，不代表它获实机验收。

离线开发中，尚未安装或宣布实机可用。使用 [GBA 已确认能打开菜单和游戏的 `.3` 流程](../gba_menu/README.md)，把整页渲染替换为[原版 GB/GBC CoverFlow](../coverflow_shared/README.md)。旧的 `.4` 整页滑动已被用户否决，仅保留历史证据。

`prepare.py` 在新的 `.work/gba-menu/` 副本中适配，保留普通存档、RTC、保存失败后继续游戏和暂停流程。外部 SDRAM 的 40–48 MiB 用于封面；游戏 ROM 为 0–32 MiB，EWRAM 从 32 MiB 开始。暂停页继续使用原有游戏 framebuffer，封面缓存不会覆盖 ROM、普通存档或暂停现场。APF Memories／休眠在此实验中仍禁用。

菜单输出为 320×288；GBA 游戏保留原有 240×160、3:2 的视频和显示模式。物理视频时钟保持不变，菜单采用 4/5 像素使能。启动／退出时会淡出、等待读取结束，再交还游戏接口。

## 资源和检查

`library.py` 将已校验的本地 GBAF1 菜单转为 GBAF2：每条记录使用 64 KiB 的 128／80 像素 RGB565 封面与两行中文字形。游戏、存档和 RTC 的路径字段逐字节保留。只读取原菜单包和身份清单，不复制或修改 ROM／存档。最终安装仍需核对实际卡和 ROM 版本；不能把历史清单当作当前卡认证。

此后端为 128 个直接材质槽，每页最多 128 条（含返回）。转换器和更新器拒绝更大的页面，避免环绕时两个逻辑条目占同一槽；大目录先在源库分层／分页。几何公式可表示更多条目，不代表此后端能缓存这些条目。NES 的关联缓存使用另一套映射，限制不同。

`probe_control.py` 复用既有 GBA 对抗性控制用例，覆盖图像块／文字请求、A/B 返回、环绕、三次加载、64K／128K 普通存档、RTC、暂停、保存失败时保留进度、非法路径及旧完成信号。`probe_text.py` 使用实际上游 loader 与 Intel FIFO，检查两种桥接字节序、保持的写脉冲、完整 16 位字形列及头部区域隔离。渲染器另与实际 GB/GBC 源码逐像素比较。

当前版本已完成完整编译和全部 104 条时序检查：16,953 ALM、282/308 M10K、48/66 DSP，报告 TNS 均为零，无 Critical Warning。SYS 最差 setup 余量 +0.381 ns；所有类型最小值为 Fast 0°C 的 hold +0.001 ns。时序范围沿用上游约束和例外；这不代替实体内存、游戏、保存返回及休眠边界验收。[编译记录](evidence/build.json)保留了范围与最小余量。

先前几轮虽能放入器件，但未通过时序，不生成候选。当前采用桥接时钟计算、跨时钟请求握手、原 RTL 采样的紧凑姿态表，并移除两行 Unicode 字形不再使用的旧字体路径。底层游戏 CPU 运行逻辑沿用固定的原生核心。

`update.py` 为已有 GBA 入口提供预检、局部备份、原子文件发布和回退。旧／新菜单版本必须配套；当前卡逐个核对 ROM 哈希与游戏／存档／RTC 记录，游戏显示模式沿用卡上的设置，只追加菜单尺寸；显式 `--display-profile` 可一并更新可选风格定义。执行前再次检查 ROM 和目标文件，回退会保留后来玩的进度。合成卡测试通过；真实卡更新尚未执行。

```sh
python experiments/gba_coverflow/prepare.py --sources .work/multi-system/sources/gba --out .work/gba-menu/coverflow-build
python experiments/gba_coverflow/library.py --source <verified-local-F1-library> --out .work/coverflow-library --titles <titles.json> --folders <folders.json> --covers <cover-root>
python experiments/gba_coverflow/probe_control.py --build .work/gba-menu/coverflow-build --out .work/control-check
python experiments/gba_coverflow/probe_text.py --build .work/gba-menu/coverflow-build --out .work/text-check --intel-model /licensed/altera_mf.v
```

原生 GBA 输入及其许可仍按原实验的固定来源处理；没有公共合并二进制发布。私人游戏名映射、封面库、BIOS、ROM 和存档不入仓库。

## English

Offline native GBA adapter, not installed or accepted on hardware. It reuses GB/GBC CoverFlow and the previously device-reported GBA menu/game-launch lifecycle, with F2 atlas assets, Unicode rows, isolated texture memory and ordinary save/RTC handling. Game video settings remain inherited. Full fit and 104 inherited multi-corner timing records passed: 16,953 ALMs, 282 M10Ks, 48 DSPs, zero reported TNS and no critical warnings. Minimum SYS setup is +0.381 ns; the overall minimum is a Fast 0°C hold margin of +0.001 ns. Controller, loader/FIFO, cross-clock transport and differential compositor simulations remain separately scoped evidence. Physical memory, gameplay and save-return acceptance are pending. BIOS, ROMs, progress and private artwork/catalogs are excluded; no public combined GBA binary release is claimed.
