# 单机反馈与打包修正

2026-11-03，使用者在自己的 Pocket 上确认：FC/NES 与 GG 的菜单、CoverFlow 动画及基本启动正常。FC 仍有较多缺图和未翻译名称。GBA 已恢复 `.3`，菜单与游戏可进入，当前待改的是动画。这是使用者报告，未逐款验证全库、保存耐久性或多台设备兼容性。

此前 GBA `.5` 出现“操作失败”，首次诊断码未取得，不能断言原因。工具现拒绝安装或重新打包该设备失败版本。历史编译通过记录仅作离线证据，不能作为继续发布该版本的依据。

NES/GG 首次出现 variants / core setup 错误。已确认打包器遗漏官方必需的 `variants.json`，修复只补原上游空列表定义。打包、首装和更新检查现要求完整的七份 APF JSON，连同正确的包装键、`APF_VER_1` 和 variants 数组。测试覆盖缺文件、清单漏项和设备失败候选拒绝，拒绝发生在发布写卡计划之前。

[官方定义文件清单](https://www.analogue.co/developer/docs/openfpga/core-definition-files)要求 `variants.json`，没有变体时仍需提供定义。

## English

One user reports working NES/GG menus, CoverFlow animation and basic game launch after the missing upstream variants definitions were restored. NES captions/artwork remain incomplete. GBA is back on the previously accepted `.3`, with menu and game launch working; animation remains the requested change. This does not certify every game, save durability or other devices.

GBA `.5` failed on hardware with an unavailable initial diagnostic code; its cause is unconfirmed and the candidate bitstream is now blocked from packaging/installation. Offline fit/timing results are retained as historical evidence. Tools require all seven mandatory APF definitions and reject omitted manifest entries before generating an installation plan. Firmware was not modified.
