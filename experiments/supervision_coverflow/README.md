# Supervision 中文 CoverFlow

原生 Supervision 引擎保留，增加与 GB/GBC 相同来源的封面动画和中文位图标题。独立入口是 `pocketlab.Supervision`，系统分组 `CN Menu`，资产命名空间 `svclab`。原游戏画面仍使用上游的 320×160、1:1 比例模式。

上游固定为 [opengateware/console-supervision](https://github.com/opengateware/console-supervision/tree/7c01e71e028de81171f74f835812dfc1e109cefe)。游戏引擎 GPL3、菜单新增代码 MIT，组件保留各自声明。固件和原核心无需替换。上游没有普通存档、即时存档或睡眠接口，本入口保持相同边界。

1. 把自己的 `.sv` / `.bin` 游戏放在 `Assets/supervision/common/`，可以按目录分类。支持原生引擎的 16–512 KiB、2 的幂大小镜像。
2. 执行 `python experiments/supervision_coverflow/library.py --source <卡或本地副本> --out <新暂存目录>`。文件名自动成为标题；可加 `--titles <JSON>` 指定中文别名，`--covers <目录>` 匹配与原 ROM 路径一致的 PNG。没有图片时生成文字封面。建库只读原目录、不复制 ROM、不创建保存文件。
3. 核心包和生成的 `Assets/svclab/` 一起安装。A 进入、B 返回；游戏中用 Pocket 的 Quit 退出。添加或移动游戏后重新建库。

开发：`prepare.py --source <固定 git checkout> --gba-source <固定 GBA 驱动源码> --out <新 .work 目录>` 生成完整 Quartus 工程，在 `projects/` 编译 `supervision_pocket`。`package.py --build <完整编译树> --prepared-source <生成树> --out <新 .work 目录>` 校验全部源文件、Fitter 和四角 STA，再输出核心、来源副本和收据。

独立 CRAM0 保存封面。上游实际视频时钟约 8MHz，菜单每四拍接收三拍，320×288/374×300 光栅约 53.48Hz；游戏 PLL 和游戏逻辑保持原样。新 ROM FIFO 等待 SDRAM 的逐字节 busy 完成再发下一个字节，防止菜单流量落入游戏 ROM。中文失败提示驻留 FPGA，资源无法读取时仍可显示。

2026-11-15：完整编译成功，32% ALM、41/308 M10K，104 条四角时序最小余量 +0.128ns。实机验收仍待完成；协议和外部 RAM 的仿真不等同于实际游玩验证。
