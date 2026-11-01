# 复用 openFPGA 机种列表

2026-11-01。按用户最新方向，当前主线改为复用系统机种列表，由 Analogue OS 加载各自核心，再进入现有中文游戏菜单。界面内自动换核实验保留为研究记录，不继续追加同类实机测试。本轮仅查看官方文档和电脑备份，未访问设备卡。

## 可用方式与边界

```text
openFPGA 原生机种列表
  ├─ GB / GBC → pocketlab.CoverFlow → 已有中文分类、封面和游戏
  └─ GBA      → pocketlab.GBA       → 已有中文分类、封面和游戏
```

这是由系统启动各自核心，沿用现有可用入口，不需要在 FPGA 游戏菜单里请求运行时重配置。选择入口后仍遵循系统的启动操作，不承诺消除 Run 等系统步骤。GB/GBC 先保留共同入口，不能仅改名称就声称已经按 GB、GBC 分别直达不同菜单。

| 层级 | 公开能力 | 本项目结论 |
|---|---|---|
| 平台名称、分类、厂商、年份 | `Platforms/<id>.json` | 可定制显示信息；分类分组还受 OS 的 Group openFPGA 设置影响 |
| 平台标志图 | `Platforms/_images/<id>.bin` | 可提供机种图形；属于平台图像，不能据此承诺改变整个列表布局 |
| 平台与核心关联 | `core.json` 的 `platform_ids` | 现有 GB/GBC、GBA 专属平台已存在，共同 Pocket Lab 分组也已验收 |
| 每台机种里的中文游戏菜单 | 各核心自行实现 | GB/GBC 与 GBA 已有实现；其他核心需要逐个适配，配置文件不会自动把它们变为中文 |
| 系统字体、Run/Settings、列表布局与动画 | 所查 SDK 未提供替换接口 | 不把 openFPGA 当成整套系统 UI 源码；系统菜单全汉化仍是另一个未解决问题 |

官方区分开发者可用的主 FPGA 和 Analogue OS 专用的系统 FPGA。openFPGA 提供核心开发、包装和交互接口，不能由名称推断整个 OS 前端均可直接改源码。[官方架构](https://www.analogue.co/developer/docs/openfpga/overview)

平台字段和标志图的位置有公开定义。[平台元数据](https://www.analogue.co/developer/docs/openfpga/platform-metadata)；类别分组及字母排序见[官方分组说明](https://www.analogue.co/developer/docs/openfpga/changelog/1-1-beta-5)。这些接口没有承诺 OS 的汉字字体覆盖；JSON 能存中文不等于系统能显示中文。把汉字画进标志图也不等于系统文字已汉化。

## 当前配置与电脑候选

已核对最新安装前备份中的元数据：

```text
pocketlab.CoverFlow: [gbclab, gb, gbc, pocketlab]
pocketlab.GBA:       [gbalab, gba, pocketlab]
```

GBA BIOS 槽显式使用平台索引 1（`gba`）；菜单槽使用索引 0（`gbalab`）。GB/GBC 的菜单资源也依赖原平台顺序。因此本轮候选只修改 `Platforms/gbclab.json`、`Platforms/gbalab.json` 的 `name`，分别预览为 `GB / GBC`、`GBA`，不重排平台、不改核心身份或文件路径。平台关联会影响素材与保存目录，不能把它当成纯显示字段随意更换。[核心定义](https://www.analogue.co/developer/docs/openfpga/core-definition-files/core-json)

电脑候选位于本仓库 `.work/system-frontend/metadata-preview-1/`，仅有两个平台 JSON 和私有来源／哈希清单。已检查 JSON、名称长度及除 name 外其他字段保持一致。尚未写卡、没有实际 OS 截图或新一轮启动验收。这是显示名预览，不是完整的新前端包。

候选采用机种标准缩写，保留核心内已有的真实中文游戏显示。图标方案沿用黑底方向，未来按官方平台图格式单独准备；不为未验证的系统字体承诺全中文列表。

## 后续实现顺序

1. 先确定官方机种入口的命名、分组和标志图，再在新识别、备份后的卡上验证显示与原核心启动。
2. 统一现有 GB/GBC、GBA 游戏菜单的视觉与返回行为，保留已验收的加载逻辑；普通存档／RTC／保存返回仍按各核心现有验收范围处理。
3. 其他机种逐个接入，沿用各自原生核心；不把 NES/SNES 等列为已完成的中文菜单。

## English

The current direction reuses the native openFPGA platform list, lets Analogue OS load the selected existing core, then enters that core's Chinese game menu. Platform names/categories/art are documented SD metadata; the SDK does not expose replacement of the global OS layout or font. This is not OS source modification or a full system translation. The offline two-file preview changes only platform display names to GB / GBC and GBA. Core identities, platform ordering, BIOS indices and paths are retained. No card access or new hardware acceptance is claimed; the previous routing experiments remain archived evidence.
