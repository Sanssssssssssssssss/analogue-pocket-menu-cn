# SFC / SNES 原生菜单原型

当前是离线原型，尚不能交付上机。最新完整编译虽完成布局布线，但 96 条时序记录中有 4 条为负值，最小 slack **−2.823 ns**，因此不生成可安装包。另有上游 `CEGen` 上电值告警及未匹配的约束项，需要继续检查。

之后补充了普通存档绑定保护：菜单或未完成的加载不向 OS 宣告可保存的 RAM。此修正已在新副本生成，尚未重新完成硬件编译；不能把前述报告当作新输入的编译证据。

原型基于 [agg23/openfpga-SNES](https://github.com/agg23/openfpga-SNES/tree/1a08c84ddef760bedd30a376114fc2e97527df19)，单独接入标准 NTSC 核心。只接受上游加载器判定的芯片类型 0、1、2；PAL 以及 Super FX、SA-1、DSP、SPC7110、SDD1 等协处理器游戏继续留在原入口，不能用同一主核心强行启动。

`library.py headers` 只提取候选头字段、文件大小和哈希；`decide` 用原上游 Chip32 字节码处理同大小的稀疏头部样本，保存核心／映射／RAM／PAL／512 字节文件头判定。VM 的 FPGA 和 host 操作是桩，不证明游戏运行。`build` 再核对源文件哈希、过滤不支持的条目并生成本地菜单。它只引用卡上 ROM；需要调用方核对中文名称和封面。

候选保存路径为独立的 `/Saves/snescn/common/`，按上游 RAM 大小创建新的全零测试进度；已有同路径文件不覆盖，大小不符就停止。不导入原存档。当前只保留原 OS Quit 保存流程，尚未实现游戏内中文暂停／保存返回；普通存档及启动也未实机验证。

```sh
python experiments/snes_menu/prepare_build.py --archive <pinned-snes.zip> --out .work/snes-menu/build
python experiments/snes_menu/library.py headers --card <card> --out <local-headers.json>
python experiments/snes_menu/library.py decide --headers <local-headers.json> --loader <pinned-loader.bin> --simulator <chip32-sim-cli> --out <local-decisions.json>
python experiments/snes_menu/library.py build --card <card> --decisions <local-decisions.json> --out .work/snes-menu/library --titles <local-titles.json>
```

新工具为 MIT；生成树保留上游组件许可证。私人头部字段、目录、ROM、进度和生成核心不进入公开仓库。

## English

Offline standard-NTSC SNES prototype only. Fitting completed, but timing failed (minimum slack −2.823 ns); no installable package is provided. Actual upstream Chip32 bytecode is exercised against sparse header fixtures to preserve its mapping, RAM, copier-header and PAL decisions. This is metadata evidence, not game execution. PAL and co-processor cartridges are excluded from this prototype. New test progress is isolated; the OS Quit/save path and game launch are not accepted on hardware. Chinese runtime pause/save-return is not implemented.
