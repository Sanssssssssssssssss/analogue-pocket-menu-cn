# GB / GBC / GBA 前端聚合实验

2026-10-31。GBA `0.2.0-gba.3` 已获用户确认：正常中文菜单和游戏启动可用；普通存档、RTC 和保存返回仍待实机验收。

当前目标是[按游戏自动调用对应的原生 FPGA 程序](NATIVE-CORE-ROUTING.md)。一次配置一个机种；独立程序的资源相加不限制这条路线。启动时按 ROM 选程序已有 SNES 实例，中文图标页触发运行时重配置仍未打通。

## 已实现的入口映射

向两个原有核心的 `platform_ids` 末尾追加共同关联 `pocketlab`，增加 `Platforms/pocketlab.json`，名称为 **Pocket Lab**。原顺序分别保持：

```text
pocketlab.CoverFlow: [gbclab, gb, gbc, pocketlab]
pocketlab.GBA:       [gbalab, gba, pocketlab]
```

这是同一系统分组的实验，切换仍由 Analogue OS 的 **Change Core** 执行。文件已安装并校验，用户已确认分组和核心选择正确。原核心身份、二进制、数据槽、素材与存档位置保持原值。平台索引不能随意重排：[数据槽参数](https://www.analogue.co/developer/docs/openfpga/core-definition-files/data-json)通过数组索引选择素材平台。[核心定义](https://www.analogue.co/developer/docs/openfpga/core-definition-files/core-json)最多支持 4 个平台关联。

## 中文图标页直接换核心

尚未实现，不能把上述分组称为原生统一启动器。

- [Chip32 初始化说明](https://www.analogue.co/developer/docs/openfpga/chip32-vm/initialization-of-the-chip32-vm)说明它按需运行，不与核心常驻执行；`HOST 0x4002` 交回 APF。
- Chip32 的 `CORE` 可以在加载阶段选择二进制，但现有 [Host/Target 接口](https://www.analogue.co/developer/docs/openfpga/host-target-commands)没有公开通用的“运行中启动另一个已安装核心”命令。仍缺少从 FPGA 图标菜单触发重新加载的已验证链路。
- 旧离线分派实验已跑 7 个字节码用例，CORE/HOST 为日志模型、重新加载由测试宿主显式触发；它没有验证 FPGA 菜单按钮能唤起 Chip32。
- 现有两套硬件也不能直接拼接。GB/GBC 使用 13,753 ALM、299 M10K、56 DSP；GBA 使用 15,940 ALM、277 M10K、27 DSP；芯片总预算 18,480 ALM、308 M10K、66 DSP。粗略相加超预算；可复用的模块尚未合并综合，不能把相加当作重新设计不可行的证明。

下一项优先验证菜单与加载器的交接；先以独立 A/B 程序检验加载阶段持有选择器、读取按键选择并执行 `CORE` 的假设，以及游戏结束后的返回入口。按游戏逐个加载原生程序无需同时容纳两套游戏电路。具体门槛和源码证据见[原生程序路由](NATIVE-CORE-ROUTING.md)。

## 界面与素材

GBA `display_update.py` 可在电脑上更新已有菜单图：替换匹配的封面、补中文显示名并去掉底部 A/B 提示。所有启动／存档记录保持逐字节一致。未传入 `--titles` 时保留原有标题像素；传入时只重绘对应文字区域。

```sh
python experiments/gba_menu/display_update.py --card X:/ --covers /path/to/covers --titles /path/to/titles.json --out .work/gba-display-update
```

该工具只生成电脑副本，不负责安装。`--titles` 是卡内相对路径到显示名称的 JSON，例如 `{"Assets/gba/common/Example.gba":"示例游戏"}`；文件夹使用其 `Assets/gbalab/common/...bin` 路径。名称不改变 ROM 文件名，也不代表游戏内文字已汉化。每页最后的返回入口显示“返回首页”或“返回上级”。

封面可来自 [libretro-thumbnails GBA](https://github.com/libretro-thumbnails/Nintendo_-_Game_Boy_Advance)，用 [libretro-database](https://github.com/libretro/libretro-database) 的游戏代码对应原作封面，中文别名可参考 [rom-name-cn](https://github.com/yingw/rom-name-cn)。代码匹配后仍须查看图片：本次发现上游 `Chou Makaimura R (Japan).png` 实际是另一款游戏的图，已在本地改用同作美版封面。汉化／改版版本身份仍须另行核对；按文件名整理的改版副标题只是显示别名。仓库不分发商业游戏、BIOS、个人存档、私人清单或封面包。

用户已确认更新后的中文名称正确。详细的[单核心与动画可行性研究](FEASIBILITY.md)包含逐模块资源、共享外部存储方向和离线淡入淡出原型。过渡已接入独立 GBA 电脑副本，联合启动、八档整帧像素比对及游戏视频绕过仿真已通过；Quartus 综合、布局、ASM、STA 各阶段已完成，流程包装器失败与约束限制保留在[收据](gba-fade-validation.json)中。实机仍使用原可用版本。
