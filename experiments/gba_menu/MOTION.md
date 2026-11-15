# GBA 菜单动画候选

**2026-11-02：用户明确不接受整页滑动。本文和 `0.2.0-gba.4` 保留为历史工程证据，停止作为当前交付候选。后续直接复用 GB/GBC CoverFlow 的绘制与缩放逻辑，见[完整交付目标](../../docs/COMPLETE-DELIVERY.md)。**

2026-11-01。用户确认 CN 菜单可进入，现有动画仍需改进。本候选保留黑底和现有页面格式，在下一页上传期间显示旧封面，再进行正反向各 8 帧的缓动过渡。它是整页滑动，尚未实现 GB/GBC 那种封面独立移动、缩放。

![自绘中文页面的实际 RTL 光栅预览](evidence/motion-preview.gif)

[像素检查收据](evidence/motion-pixels.json)：21 张完整菜单画面、806,400 个菜单像素及 38,400 个完整色深游戏像素比对通过，包含正反向过渡、上传期间旧画面保留及重置。

[游戏光栅对照](evidence/motion-game-video.json)另将当前候选与已记录的 `0.2.0-gba.3` 视频适配器直接比对：连续两帧的 280,896 个时钟样本、76,800 个游戏像素，RGB、DE、HS、VS 和 scaler skip 均相同。[首屏检查](evidence/motion-boot.json)在分块实现上验证 APF 命令、五段画面传输及可见首屏；残留所有权和缺尾数据的三个用例曾在[分块前同接口候选](evidence/motion-previous-boot.json)通过，后者不作为新分块源码的直接证据。

`gba_motion_video.sv` 保留原来的 38,400 × 18 位游戏帧缓冲和光栅时序。额外缓存当前布局中的三张封面，共 13,824 个 RGB565 像素，以及 240 × 33 位的单色标题掩码。菜单素材本来就是 RGB565，缓存不再降低封面色深；游戏像素沿用完整 18 位路径。额外资源是否能放入器件、时序是否通过，均以完整 Quartus 报告为准。

首次完整布局布线因缓存被上取整而需要 310 块 M10K，超出器件的 308 块，未生成安装包。当前把封面缓存分为三个 4K 像素区和一个 2K 像素区，降低内存分配浪费；上述像素检查已在分块实现上重新通过，完整编译结果另行记录。

分块候选 `0.2.0-gba.4` 现已通过[完整编译](evidence/motion-build.json)：16,041 / 18,480 ALM，306 / 308 M10K，27 DSP，0 个虚拟引脚。104 条继承时序记录均无负 slack，最小 +0.080 ns，TNS 均为零；0 错误、0 critical warning。重新生成并核对了全部编译输入，BIOS 初值为零，运行时由用户自己的文件提供。板级例外沿用上游，未扩展为外部存储／实体显示签核。已生成本地候选，未安装、未实机验收。

缓存只适用于当前固定布局：左侧 `(2,35,48,48)`、中间 `(72,5,96,96)`、右侧 `(190,35,48,48)`，标题位于 y=108～140，背景为纯黑。改变页面布局、增加彩色标题或背景图时，必须一起更新缓存格式和像素检查。游戏暂停页沿用现有显示路径。

`menu_visible` 是上传／显示完成的协议确认。下一页写入时确认值为 false，旧封面从独立缓存显示；完整上传后开始动画，动画结束再允许下一次导航。缺尾帧继续由现有 FIFO／控制器拒绝。候选需要验证 APF Stop/Run、首次显示、暂停／返回和真实 SD 访问，离线光栅通过不等于实机验收。

```sh
python experiments/gba_menu/prepare_motion.py --sources <pinned-gba-source> --out .work/gba-menu/motion-build
python experiments/gba_menu/probe_motion.py --out .work/gba-menu/motion-pixels
python experiments/gba_menu/probe_motion.py --preview --out .work/gba-menu/motion-preview
python experiments/gba_menu/probe_game_video.py --baseline-adapter <accepted-gba3-video_adapter.sv> --out .work/gba-menu/motion-game-video
python experiments/gba_menu/probe_boot.py --motion --build .work/gba-menu/motion-build --intel-model <altera_mf.v> --out .work/gba-menu/motion-boot
# 在上述独立树完整编译、审阅时序后：
python experiments/gba_menu/package.py --motion --build .work/gba-menu/motion-build --sources <pinned-gba-source> --out .work/gba-menu/motion-package
```

预览使用项目自绘图标、中文字库和真实 RTL 光栅输出，无商业游戏素材。生成的 GIF 展示过渡动作，SD 读取等待和实机帧节奏仍需上机验证。本候选不自动写卡，当前可用核心可继续使用。

## English

This is a local GBA menu slide candidate, not device acceptance. A small cache retains the old covers and monochrome title while the existing framebuffer receives the next page. An eight-frame eased slide follows. It does not implement GB/GBC-style independent cover movement and scaling. Current RGB565 menu colors and all 18 game framebuffer bits are retained. The cache depends on the documented fixed black-background layout; custom backgrounds or colored titles require a different format. Version 0.2.0-gba.4 passed full fitting and 104 inherited timing records (minimum slack +0.080 ns, zero negative TNS), with 16,041 ALMs and 306 M10Ks. Sources were regenerated and checked before local packaging. Hardware navigation, launch, pause and save-return acceptance is still required.
