# 更新已有菜单的显示名和封面

`tools/update_display.py` 在电脑上更新已有 v9 菜单，保留机种、分类、ROM／存档／休眠路径、CRC、收藏标记及日志路径。游戏页按新标题重建字母索引；目录页顺序保留。生成和安装分开执行，安装沿用版本备份及回读校验。

映射是 UTF-8 JSON，键为含前导 `/` 的卡内游戏路径。每个涉及更新的游戏页须包含所有游戏的 `title`，包括不变的标题，避免排序时丢失原中文名。可指定本地图片及 SHA256；`fallback: true` 为没有封面的条目生成标注“文字封面”的卡片。

```json
{
  "/Assets/gbc/common/Example.gbc": {
    "title": "测试冒险",
    "fallback": true
  }
}
```

```sh
python tools/update_display.py --card X:/ --out .work/display-update --mapping display-map.json
python tools/install.py --card X:/ --package dist/core --library .work/display-update
```

第二条仅预览。确认目标卡和计划后，补上 `--apply --backup <新的电脑备份目录>`。使用与卡上相同的核心包可以只更新显示素材。原有游戏文件名和游戏内语言不变。未找到可靠对照的名称保留原文；文字封面不代表原版包装图。

可参考 [yingw/rom-name-cn](https://github.com/yingw/rom-name-cn) 的中文对照和 [libretro-thumbnails](https://github.com/libretro-thumbnails) 的包装图。处理私人库时，保留来源、修订和文件校验记录；不要把个人游戏清单、BIOS 或存档提交本仓库。中文显示名不能证明 ROM 是汉化版。

English: `update_display.py` stages title/cover changes over an existing v9 library. Supply every game's display title on an updated game page so sorting and the letter index stay consistent. ROM/save/suspend paths, CRCs, favorite identities, parent links and log paths remain intact. Optional local covers require their SHA256; missing art can use clearly labeled text cards. Stage first, then use the existing backed-up installer. A translated display name does not translate the game itself.
