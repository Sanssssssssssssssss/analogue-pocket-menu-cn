# Arduboy 中文 CoverFlow

原生 AVR 引擎、Intel HEX 加载器和 1 KiB EEPROM 来自固定的 [agg23/openfpga-arduboy 源码](https://github.com/agg23/openfpga-arduboy/tree/82bc07fcb14126d96e9d5489bdf5b30e3694769f)。这个源码版本已有 EEPROM，较早的 0.9.0 发行包没有同等保存能力。新增入口 `pocketlab.Arduboy`，系统分组 `CN Menu`，使用独立的 `ardlab` 资产与保存目录。原游戏画面比例及音量设置保留。

把自己的 `.hex` 放在 `Assets/arduboy/common/`，支持子目录。运行 `python experiments/arduboy_coverflow/library.py --source <卡或本地副本> --out <新暂存目录>` 建库，然后安装核心包和生成的文件。文件名直接作为标题；`--titles <JSON>` 可提供原路径到中文名的映射，`--covers <目录>` 按原 ROM 路径匹配 PNG，没有图片则生成文字封面。新增或移动游戏后重新建库。A 进入、B 返回，游戏中通过 Pocket Quit 保存并退出。

支持普通 Arduboy Intel HEX 数据记录与 EOF、32 KiB 内的程序。建库核对校验和、长度、地址、重复记录、结束标记；FX 外部数据、扩展地址记录及 `.arduboy` 压缩包需先转换为原核心支持的 HEX。无法直接兼容的文件会列在清单中。

每个 HEX 的 SHA256 前 20 位对应独立 1 KiB EEPROM，新的保存文件填充 FF。已有正确长度的保存文件原样保留；原 `arduboy_eeprom.sav` 全局保存不自动分配给多个游戏。需要迁移旧进度时，明确目标游戏后再复制为对应哈希名称。没有即时存档和睡眠功能。

开发：`prepare.py --archive <固定源码 ZIP> --gba-source <固定 CellRAM 驱动源码> --out <新 .work 目录>`；在生成树 `src/fpga/` 完整编译 `ap_core`，再运行 `package.py --build <完整编译树> --prepared-source <生成树> --out <新 .work 目录>`。包装器核对输入、Fitter、四角 STA 和 APF 元数据，输出 `core/`、`sources/` 和收据。引擎 GPL3，AVR 组件保留 GPL2-or-later 声明，菜单新增代码 MIT。

图像占用上游闲置的 CRAM0。实际视频 PLL 约 46.476 MHz，菜单用 1/8 像素使能；上游变量名中的 1.25 MHz 不能作为时钟依据。稀疏 HEX 装入前先清空程序 RAM；EEPROM 使用足够容纳完整保存的跨时钟缓冲，核对 1024 字节全部写入后才启动游戏。实机验收状态由交付收据记录，离线仿真不等同于实际游玩确认。

保存读回使用 EEPROM 真实写入的独立镜像，覆盖游戏写入和恢复旧进度；桥端一拍可读取完整四字节，满足 APF 的固定响应窗口。有效保存长度在 Stop 后继续保留，直到开始载入下一款游戏。原 EEPROM 寄存器与读写规则不变。

音频保留原 I2S 比特顺序、音量和声道行为，改为 74.25MHz 单时钟使能，消除原内部派生音频时钟；两根 AVR 蜂鸣器信号先同步，再计算音量与静音。

原生视频的十位除六运算改为逐输入证明相同的常数乘法，活动画面仍是 800×720；完整两帧对照保持像素与同步一致。菜单复位在 AVR 下降沿锁存，使原生门控定时器在下一上升沿前有半周期的稳定时间。

时序报告覆盖已约束的桥、菜单视频、音频、AVR 与 EEPROM 时钟域。上游软件控制的 OLED SPI 仍有一个未约束时钟，收据列出具体名称；不能将四角 STA 通过解释为原游戏全部路径已完成时序证明。
