# Pocket 显示风格

候选包默认以最高像素清晰度显示原始画面；游戏使用各原生核心的比例和尺寸，菜单保持黑底。`video.json` 声明可选显示模式，实际选择保存在 Pocket 的系统显示设置中，已有选择不会因声明选项而被强制切换。

| 机种 | 清晰原画 | 可选屏幕风格 |
|---|---|---|
| GB / GBC | None，无网格 | 反射式彩色 LCD、GBC LCD / LCD+、背光彩色 LCD |
| GBA | None，无网格，3:2 | GBA LCD、SP 101、通用反射／背光 LCD；按需选择 |
| GG | None，10:9 | GG / GG+、通用反射／背光 LCD |
| NES / SMS / SG-1000 | None，原生比例 | CRT Trinitron |

中文对照：**None = 原始清晰**，**Reflective Color LCD = 反射式彩色 LCD**，**Backlit Color LCD = 背光彩色 LCD**，**CRT Trinitron = 显像管扫描线**。GBA 希望无网格时选 None。系统显示选项的英文由 Analogue OS 绘制，当前核心不能替换它的字体或标签。

LCD 模式采用整数像素放大，部分非方形像素机种可能无法同时保持指定比例；追求原比例时选 None。CRT 使用高度整数倍并按声明比例计算宽度。灰度 LCD / DMG / GBP 需要核心响应 `00B8` 并输出灰度，本轮候选未实现这条路径，因此不新增这些选项。GB 仍可用通用彩色 LCD 表现网格。

`tools/display_styles.py` 在打包时保留全部原生／菜单显示槽，仅配置可用效果和 `defaults.sharpness=3`。GBA 的 CoverFlow 为槽 1，NES 为槽 4，世嘉为槽 4、暂停页为槽 5；这些槽控制尺寸，不是系统滤镜编号。未添加冒充 OS 滤镜开关的菜单。

已装 GBA 的更新器默认保留显示定义；显式加 `--display-profile` 才把本表可选模式一并纳入备份／回退。GB/GBC 用 `tools/build_release.py --display-profile` 构建独立元数据候选，仍只接受原 `0.1.2` 的固定 bitstream 哈希。稳定发布元数据和实际游戏显示选择保持各自记录。

来源：[Analogue 官方 video.json](https://www.analogue.co/developer/docs/openfpga/core-definition-files/video-json)、[视频总线](https://www.analogue.co/developer/docs/openfpga/bus-communication)。配置和槽位离线检查已完成，具体 LCD／CRT 外观仍需实机验收。

English: candidate metadata declares supported optional native display modes and sharpness while retaining all game/UI scaler slots. It does not command an OS filter or overwrite stored user choices. Use None for clear, grid-free GBA output. Grayscale modes are omitted because the required notification/response and grayscale-video path is not implemented. Physical filter appearance remains unaccepted.
