# Menu pack v9

All multibyte integers are little-endian. This extends the upstream v7 streaming format with a Unicode title layer and folder flag. A folder contains 1..2047 entries, **including its final parent entry**.

| Offset / section | Meaning |
|---|---|
| 0..15 | `GBCV`, version u16 = 9, entry count u16, center width 128, preview width 80, padding |
| 16..527 | 512-byte index block: `IDX1`, favorites/played counts, 27 alphabet section starts |
| 528.. | Entry table, 128 bytes per entry |
| After table | One 65,536-byte art/title block per entry |
| After art | Three NUL-padded 256-byte paths per entry: ROM/folder pack, normal save, suspend |
| Final 512 bytes | Two NUL-padded paths: debug log and favorites configuration |

Entry fields: ASCII fallback title at bytes 0..39; flags at 40 (bit 0 = GB-only, bit 1 = favorite, bit 7 = folder); ROM length at 44; CRC32 at 48; rendered title width at 52. Chinese text comes from the art/title block, not the ASCII fallback.

Each art block starts with 128×128 and 80×80 RGB565 images (45,568 bytes combined). Offset 45,568 holds 512 little-endian u16 columns of a 16-pixel-high title. At most 500 columns are displayed; remaining columns are zero. The rest of the 64 KiB block is padding.

**B navigation opens entry `count-1`.** Every directory, including root, must end in a folder entry pointing to its parent (root points to itself). This final entry must not be sorted among normal titles. Its alphabet index uses the synthetic sort title `ZZZZZZZZ`.

APF paths must fit in 255 UTF-8 bytes plus NUL, use forward slashes and stay in declared platform trees. The package declares `gbclab`, `gb`, `gbc`; ROMs reference `Assets/gb/common` / `Assets/gbc/common`, and generated packs use `Assets/gbclab/common`.

Normal/suspend save paths are `Saves/gbclab/common/<first20ofROMsha256>.sav/.sus`. Identical ROM content deliberately shares an experimental save even when listed in more than one place. Different ROM revisions are not automatically treated as save-compatible. Logs/favorites use `Saves/gbclab/common/meta/`.

The public generator preserves source subdirectories and rejects folders exceeding the entry limit. It does not yet split oversized folders automatically. Do not use the old upstream v6/v7 Companion to overwrite v9 libraries.
