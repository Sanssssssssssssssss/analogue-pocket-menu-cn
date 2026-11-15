# CPS1 / CPS1.5 中文 CoverFlow

为 Jotego 原生 CPS1、CPS1.5 FPGA 引擎添加中文 CoverFlow。各自显示在 `CN Menu` 分组，保留原游戏比例、旋转、原生输入及 Core Settings。当前是离线验证候选，实机游玩验收待完成。

| 平台 | 新核心 | 菜单目录 | 原游戏目录 |
|---|---|---|---|
| CPS1 | `pocketlab.CPS1` | `Assets/cp1lab/common` | `Assets/jtcps1/common` |
| CPS1.5 | `pocketlab.CPS15` | `Assets/c15lab/common` | `Assets/jtcps15/common` |

左右滚动，A 进入或启动，B 返回。游戏中 L+R+Select 打开暂停页，可继续或保存后返回。覆盖图缺失时显示中文标题卡；封面资源读取失败会保留标题和操作。

## 给已有游戏建库

使用合法取得的原生 Pocket `.rom` 和配套 APF 实例 JSON。街机 ROM 还需要实例中的机型模式、按键与 DIP 配置；单独拖入 MAME ZIP 不会自动转换。缺 ROM、非法路径、错误的实例 MD5 会被排除并记录原因。

```sh
python experiments/cps1_coverflow/library.py jtcps1 --source /path/to/card-copy --out .work/cps1-library
python experiments/cps1_coverflow/library.py jtcps15 --source /path/to/card-copy --out .work/cps15-library
```

两个命令均只读源目录。`--titles` 接受 JSON 路径到显示名称的映射；`--covers` 使用与实例路径一致、扩展名为 `.png` 的图片。常见作品有中文显示别名，其余直接显示原文件名。这些名称不表示游戏内容已经汉化。

生成目录含菜单、缺失的初始存档及 `library-manifest.json`，不包含 ROM 副本。共享安装器会核对源文件、备份目标并处理现有进度；不要用文件管理器覆盖已有存档。

## 存档边界

使用原核心的 128 字节 EEPROM，旧存档逐字节复制，游戏身份由 ROM 内容与实例设置共同确定。已有新菜单存档优先保留。多数 CPS1 游戏本来就不使用 EEPROM；这不会增加原游戏没有的即时存档、休眠或任意进度保存能力。

新读回口观察原 EEPROM 的实际写提交，支持 8 位及 16 位原生组织。测试覆盖真实双线 SPI、串行 EEPROM 写入、保存与 flush、Stop 后晚读、打开路径以及后续 Core Settings 修改。测试中的 ROM 是合成数据，未据此宣称真实商业游戏已运行。

## 构建与来源

引擎固定为 [jotego/jtcores](https://github.com/jotego/jtcores/tree/559df4a276ca312939a95f9bf0056348d5dac6f2)，GPL-3.0-or-later。依赖及原文件许可证保留；新增菜单工具为 MIT。`metadata-lock.json` 锁定原 Pocket 定义。`prepare.py` 生成对应原生工程、复制已审查的公共菜单与桥接代码，并记录每个输入的哈希。

候选包的 `sources/` 是可复核的完整 Quartus 输入闭包；在 `cores/cps1/pocket` 或 `cores/cps15/pocket` 中使用 Quartus Lite 22.1 执行 `quartus_sh --flow compile jtcps1` 或 `jtcps15`。`package.py` 要求完整 Fitter、四个角的 STA、源文件一致以及全部 APF JSON 检查通过，才生成安装包。

APF 平台顺序为菜单目录、原平台、`jtpatreon`。CRT 配置槽 18 指向第 3 项，沿用原共享文件；包不覆盖 `jtpatreon`。索引规则见 [官方 data.json 文档](https://www.analogue.co/developer/docs/openfpga/core-definition-files/data-json)。

完整时序报告保留原 DDR 视频输出、I2S 分频及部分外部 I/O 的约束边界。新增 EEPROM 地址使用两级同步，仅第一同步级为 CDC 例外；其后查表和响应路径参与正常 STA。具体时序、资源和验证范围见候选包的 `build-receipt.json`。
