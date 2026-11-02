# GG / SMS / SG-1000 CoverFlow

三个独立原生 FPGA 入口，复用已认可的 GB/GBC CoverFlow：黑底、封面独立移动／缩放、八帧缓动、明暗、圆角、倒影、Unicode 标题与底部中文。使用上游本来就实现的三种机器模式，每个入口固定自己的模式；游戏 CPU 和存档 SDRAM 路径继续使用原生实现。

| 离线候选 | ALM | M10K | DSP | 时序记录 | 最小 slack |
|---|---:|---:|---:|---:|---:|
| GG `0.4.0-gg.1` | 13,808 | 222 | 32 | 72 | +0.100 ns |
| SMS `0.4.0-sms.1` | 13,799 | 222 | 32 | 72 | +0.071 ns |
| SG-1000 `0.4.0-sg1000.1` | 13,727 | 222 | 32 | 72 | +0.046 ns |

完整编译、四个 0/85°C slow/fast 时序角全部通过，TNS 均为 0。原生模块有已审阅的上电初值告警：GG 23 个寄存器位，SMS/SG 各 16 个；对应显式 reset 值一致，见[审阅说明](POWERUP-REVIEW.md)。其他 Critical Warning 会使打包拒绝。继承的外部端口例外仍存在；这些结果不等同实体 CellRAM、游戏或存档耐久性验收。

封面独占原先空闲的 CRAM0 die 0，128 个 64 KiB 槽；不分享游戏／存档 RAM。菜单 320×288、原生视频时钟下约 47.85 Hz。显示槽 0～3 保留原生游戏，4 为 CoverFlow，5 为 256×240 暂停／错误页，避免 GG 裁切暂停文字。官方[显示风格](../../docs/DISPLAY-STYLES.zh-CN.md)由元数据声明，未伪造核心内更改 OS 滤镜的命令。

## 加载、进度与金手指

`library.py` 扫描对应机种整个 `Assets/<机种>/common`，保留分类、精选和备选。512 游戏分页，同目录相同内容去重，不同分类的相同 ROM 共用内容哈希进度。中文名与封面不改 ROM 路径。缺图／缺中文名有清单；名称或头部检查不认证游戏语言及兼容性。SC-3000 计算机软件不纳入 SG-1000 入口。

每款游戏使用独立 32 KiB 普通存档，仅对缺失的新路径预建 FF 内容。原进度不覆盖，不猜测导入。L+R+Select 打开中文暂停页，可继续或保存并返回；Memories／休眠和实体卡带启动在这些实验入口关闭。原核心继续保留。

原生金手指引擎支持 PAR 工作 RAM 写入及六／九位 Game Genie。自动配置要求 SHA1、CRC32、大小和可选 SHA256 全部匹配，最多两组实用效果，拒绝互相冲突的 RAM 写入。每条代码单独成组；原生解析器确认有效后才启用。改版／汉化 ROM 身份不符时不套用原版代码。解析失败保留已加载的游戏现场，B 可继续且不启用自动代码。手动 Cheats 总开关可以关闭。实际游戏效果仍需实机验收。

`import_profiles.py` 可复用已有校验清单的实用代码包，生成 `SEGA-CHEATS1` 已知版本候选索引。候选数量不等于用户游戏匹配数量；只有 `library.py` 读取实际 ROM 后才确认匹配。数据库代码继承 [libretro-database](https://github.com/libretro/libretro-database/tree/da577d2865c2b1b834b2d5f2fd1368fc5110a01c/cht) 的 CC-BY-SA-4.0，生成私有库保留来源，公开仓库不附代码库或 ROM。

## 构建和安装

固定上游 [kroy GG cheats](https://github.com/kroy-the-rabbit/openfpga-GG-cheats/tree/8acc19dcc399950afced528c8ce311174e4f83af)，ZIP SHA256 `903445e97ba4cd5c52d69fb87f1cfb2f23a53da3d7b341955a2152f833f93bed`。CellRAM 驱动来自[固定 GBA 源码](../gba_menu/README.md)的 Adam Gastineau MIT 模块，SHA256 `b9aed3cb12ee298a96e78ad7c26d4657eaa3d970465ffcdc4441dce7022e5c58`；完整声明保留。解包仅允许已知 `projects/rtl → ../rtl/upstream` 并物化为树内副本。

```sh
python experiments/sega_coverflow/prepare.py --archive originals/gg.zip --gba-source .work/multi-system/sources/gba --platform gg --out .work/sega-menu/build
# 在独立 projects/ 中完整执行 Quartus --flow compile gg_pocket
python experiments/sega_coverflow/package.py --archive originals/gg.zip --gba-source .work/multi-system/sources/gba --platform gg --build .work/sega-menu/build --out .work/sega-menu/package
python experiments/sega_coverflow/library.py --card X:/ --platform gg --out .work/sega-menu/library --titles local-titles.json --covers local-covers --cheats local-profiles.json
python experiments/sega_coverflow/install.py --card X:/ --platform gg --package .work/sega-menu/package --library .work/sega-menu/library
```

SMS / SG 分别传 `sms` / `sg1000`，须单独编译。库生成器可用 `--offline-source` 读取电脑旧备份；最终安装仍重读当前卡上的全部 ROM。最后一条只预览；指定全新的电脑 `--backup` 并加 `--apply` 才首次新增入口。已有目标文件会被拒绝。安装前备份对应机种及 GBA 普通进度，日志记录每个原子写入；`--rollback --backup <目录>` 预览回退，加 `--apply` 执行，保留已玩出的新进度。

打包重新生成并比对所有编译输入。QSF 仅忽略 `LAST_QUARTUS_VERSION`；准备器显式规范化上游冗余／默认设置，并逐角检查实际时序。上游 PRE_FLOW 自动生成的 MIF 只允许日期、时间、随机标识三词不同，完整 MIF SHA256 和原值进入构建收据。所有 HDL／字体／约束保持逐字节复核。

## 验证范围

- 行为 CellRAM 模型：完整封面、slot 127、3,321 次与突发上传重叠的读取、取消及 pin 时序边界通过；四个完整光栅／448,800 点与明确修正裁切算式的原 CoverFlow 参考一致。行为模型不是厂商或整板验收。
- 实际原生 bridge、同步器与适配器：11 次命令覆盖引导 Ready 优先级、两种字节序、参数、停止重启和迟到完成。
- 三个实际生成控制器与原生金手指解析器：分别覆盖无代码、有效代码、无效代码，三次 ROM 加载、预建进度、暂停／继续、保存失败保留现场、路径和超时拒绝。
- 暂停视频检查覆盖 38,400 像素居中、中文错误字形、显示槽与游戏像素直接绕过。安装及库测试使用合成字节，不附个人内容。

证据在 [evidence](evidence/builds.json)。新模块和工具按 MIT；继承的原生模块保留自己的 GPL／APF／生成 IP 声明。不将上游作者的设备测试当作本候选验收。

## English

Independent native GG, SMS and SG-1000 candidates reuse the accepted CoverFlow compositor and dedicated previously idle CellRAM, retaining native CPU/game/save paths. All three full fits and 72 timing records pass; minimum margins are +0.100 / +0.071 / +0.046 ns. Reviewed inherited power-up warnings remain. Synthetic bus, raster, lifecycle, parser and reversible-install checks do not establish physical memory, game, cheat-effect or save durability acceptance. Whole-platform libraries retain folders, versioned identity-bound progress, Chinese captions and artwork; unknown translations/hacks never inherit cheats by name. No OS firmware is modified. Package input reproduction explicitly records the upstream generated build-ID words. Original entries are retained; new experimental entries disable Memories/sleep and cartridge play.
