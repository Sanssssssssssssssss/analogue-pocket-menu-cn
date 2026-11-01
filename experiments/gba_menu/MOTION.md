# GBA 菜单动画候选

2026-11-01。用户确认 CN 菜单可进入，现有动画仍需改进。本候选保留黑底和现有页面格式，在下一页上传期间显示旧封面，再进行正反向各 8 帧的缓动过渡。它是整页滑动，尚未实现 GB/GBC 那种封面独立移动、缩放。

![自绘中文页面的实际 RTL 光栅预览](evidence/motion-preview.gif)

[像素检查收据](evidence/motion-pixels.json)：21 张完整菜单画面、806,400 个菜单像素及 38,400 个完整色深游戏像素比对通过，包含正反向过渡、上传期间旧画面保留及重置。

`gba_motion_video.sv` 保留原来的 38,400 × 18 位游戏帧缓冲和光栅时序。额外缓存当前布局中的三张封面，共 13,824 个 RGB565 像素，以及 240 × 33 位的单色标题掩码。菜单素材本来就是 RGB565，缓存不再降低封面色深；游戏像素沿用完整 18 位路径。额外资源是否能放入器件、时序是否通过，均以完整 Quartus 报告为准。

首次完整布局布线因缓存被上取整而需要 310 块 M10K，超出器件的 308 块，未生成安装包。当前把封面缓存分为三个 4K 像素区和一个 2K 像素区，降低内存分配浪费；上述像素检查已在分块实现上重新通过，完整编译结果另行记录。

缓存只适用于当前固定布局：左侧 `(2,35,48,48)`、中间 `(72,5,96,96)`、右侧 `(190,35,48,48)`，标题位于 y=108～140，背景为纯黑。改变页面布局、增加彩色标题或背景图时，必须一起更新缓存格式和像素检查。游戏暂停页沿用现有显示路径。

`menu_visible` 是上传／显示完成的协议确认。下一页写入时确认值为 false，旧封面从独立缓存显示；完整上传后开始动画，动画结束再允许下一次导航。缺尾帧继续由现有 FIFO／控制器拒绝。候选需要验证 APF Stop/Run、首次显示、暂停／返回和真实 SD 访问，离线光栅通过不等于实机验收。

```sh
python experiments/gba_menu/prepare_motion.py --sources <pinned-gba-source> --out .work/gba-menu/motion-build
python experiments/gba_menu/probe_motion.py --out .work/gba-menu/motion-pixels
python experiments/gba_menu/probe_motion.py --preview --out .work/gba-menu/motion-preview
python experiments/gba_menu/probe_boot.py --motion --build .work/gba-menu/motion-build --intel-model <altera_mf.v> --out .work/gba-menu/motion-boot
# 在上述独立树完整编译、审阅时序后：
python experiments/gba_menu/package.py --motion --build .work/gba-menu/motion-build --sources <pinned-gba-source> --out .work/gba-menu/motion-package
```

预览使用项目自绘图标、中文字库和真实 RTL 光栅输出，无商业游戏素材。生成的 GIF 展示过渡动作，SD 读取等待和实机帧节奏仍需上机验证。本候选不自动写卡，当前可用核心可继续使用。

## English

This is an offline GBA menu slide candidate, not device acceptance. A small cache retains the old covers and monochrome title while the existing framebuffer receives the next page. An eight-frame eased slide follows. It does not implement GB/GBC-style independent cover movement and scaling. Current RGB565 menu colors and all 18 game framebuffer bits are retained. The cache depends on the documented fixed black-background layout; custom backgrounds or colored titles require a different format. Complete synthesis, fitting, timing, APF lifecycle checks and hardware testing are required before installation.
