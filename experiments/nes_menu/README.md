# FC / NES 原生中文菜单候选

独立核心 `pocketlab.NES`，使用原生 NES FPGA 实现。上游为 [agg23/openfpga-NES](https://github.com/agg23/openfpga-NES/tree/be5f1303a0df15d012155cb248b6174bb81e64b6)，不修改原 NES 核心或官方系统。

`prepare_build.py` 校验固定 ZIP 的 SHA256，在 `.work` 新目录接入菜单、加载、视频和普通存档接口。`library.py` 从卡的 NES 精选目录生成本地菜单页，仅引用卡上 ROM，跳过备选目录与相同字节的重复文件。中文名称和封面由调用方提供，缺图保留占位。

普通存档放在新的 `/Saves/neslab/common/`，每个游戏预先创建独立的 256 KiB 全零文件；不会导入或覆盖原进度。`L+R+Select` 请求原 NES 暂停接口，然后可以继续或保存返回。Memories／休眠在候选中禁用。首次测试使用无重要进度的游戏，需验证启动、真实保存、退出重进；文件与接口仿真不等同游戏兼容性。

当前候选[完整编译](evidence/build.json)通过：14,219 / 18,480 ALM，55 / 308 M10K，128 条时序记录最小 slack 为 +0.126 ns，TNS 均为零。沿用上游板级约束，外部端口例外仍存在，不是完整板级签核。`package.py` 已重新生成并逐项核对输入，并拒绝缺失或负 slack 的报告。已生成本地核心包，尚无实机验收，当前菜单为静态过渡。

普通存档的 OS 数据表只在游戏完整加载并绑定后宣告可保存的大小；菜单与未完成加载期间为零。上述编译包含该保护。菜单暂存为 RGB332，游戏 RGB 和同步信号直接通过。

```sh
python experiments/nes_menu/prepare_build.py --archive <pinned-nes.zip> --out .work/nes-menu/build
python experiments/nes_menu/library.py --card <card> --out .work/nes-menu/library --titles <local-titles.json> --covers <local-covers>
python experiments/nes_menu/probe_control.py --out .work/nes-menu/control
python experiments/nes_menu/probe_video.py --out .work/nes-menu/video
# 完整 Quartus 编译与时序检查之后：
python experiments/nes_menu/package.py --build .work/nes-menu/build --archive <pinned-nes.zip> --out .work/nes-menu/package
```

新工具为 MIT；生成树中的上游硬件继续遵守各文件及上游仓库许可证。公开仓库不包含游戏、BIOS、用户存档、个人目录或生成的核心文件。

## English

An independent native NES preview based on the pinned agg23 source. It reuses the menu page format, keeps original cores and progress separate, and uses seeded isolated 256 KiB saves. Memories/sleep are disabled. Full fitting and inherited multi-corner timing passed for one candidate; lifecycle and raster simulations use host/ready models. Physical game launch, saves and navigation remain untested. The packager regenerates and checks the compiled source inputs and refuses failing timing. No ROMs, BIOS, user progress or compiled core files are published here.
