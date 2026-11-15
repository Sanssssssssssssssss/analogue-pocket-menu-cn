# WonderSwan 中文 CoverFlow

原生 WS/WSC 候选；每个机种单独进入。原生 224×144 横屏和竖屏比例保留，菜单使用独立 SRAM、320×288 CoverFlow、54.759 Hz。普通存档含原核心 SRAM/EEPROM 与 RTC；L+R+Select 暂停、保存并返回。实机验收仍待完成。

上游：[`agg23/openfpga-wonderswan`](https://github.com/agg23/openfpga-wonderswan/tree/073213a2e5992cff23b174d17763cb6354ee862b)，GPL-2.0。`upstream-files.json` 固定完整输入清单；生成后的源码保留上游许可。附带的 `art_data_loader.sv` 保留原 MIT 许可。

准备方式：

1. 解压上述固定版本源码，运行 `python experiments/ws_coverflow/prepare.py --source <源码目录> --out .work/repair-20261115/ws/candidate`。
2. 原游戏留在 `Assets/wonderswan/common/`，任意中文子目录和 ROM 文件名均可；提供原有 `bw.rom`（4096 字节）、`color.rom`（8192 字节）。运行 `python experiments/ws_coverflow/library.py --source <只读卡或库目录> --out <新的本地输出目录>`。可加 `--titles <中文名称JSON>`、`--covers <封面根目录>`。
3. 输出库保留分类、生成中文字形与封面缓存；没有封面时显示名称卡片。BIOS 只复制到本地输出，ROM 不复制。原版存档不自动导入；已存在的 `wsclab` 存档必须大小正确且含原生 RTC 尾部，绝不覆盖。

兼容边界：ROM 为 128 KiB～16 MiB、2 的幂大小；不符合原核心 AND 地址掩码的 ROM 会列在 `excluded`。保存 payload 为 0、2、8、32、128、256、512 KiB，统一追加 12 字节原生 RTC。三种 EEPROM 采用上游统一的 2 KiB 文件区。初始 RTC 使用生成时的 UTC 日期和时间。Memories、休眠和金手指未接入此候选。

离线验证：`check_boot.py --candidate <候选> --out <新的测试目录> --intel-model <Quartus altera_mf.v>` 生成真实 APF、Intel FIFO、实际频率视频与 SRAM 仿真；`check_lifecycle.py` 检验普通保存长度、失败保留现场、排空、flush 和 Stop 后的保存尺寸保持。`check_transfer.py` 逐字节核对实际保存 FIFO、原生 SDRAM 控制器（含刷新与 CAS3 内存模型）、EEPROM 端口的大小端下载及上传，包含全部原生容量和完整 RTC 尾部。修复了上游上传器连续读取空 FIFO 的问题。启动仿真使用合成数据，未运行商业游戏或实际 BIOS 的 CPU 指令。

`compile.sh` 使用固定 Quartus Docker 镜像，`probe.sh` 检查四角 SRAM 引脚延迟；`package.py --candidate <候选> --build <编译输出> --out <新的包目录>` 要求完整时序、源码哈希和 APF 元数据一致。只有被继承的、未使用字形地址自动补零警告允许通过。所有脚本仅生成电脑候选，不写卡、不修改系统固件。
