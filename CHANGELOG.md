# Changelog

## Experiment branch — GBA acceptance and Chinese captions, 2026-10-31

- One Pocket user confirmed Chinese menus and game launch in `0.2.0-gba.3`; ordinary saves, RTC and save-return remain unconfirmed.
- Added a local GBA display updater for explicit Chinese aliases, PNG covers and removal of bottom A/B hints. Every launch/save record is preserved; no RTL or game display setting changes.
- Documented the shared Pocket Lab platform association experiment and its platform-index constraints. OS grouping awaits a device report; native automatic cross-core switching remains unimplemented.
- Stable GB/GBC release and public binary remain unchanged. See [experiment scope](experiments/unified_frontend/README.md).

## Experiment branch — machine icons, 2026-10-31

- Original GB/GBC machine and genre pixel illustrations, using the existing RGB565 cover format.
- Optional v9 restyler: machine home, classic shortcut group, corrected parent links, original game/save identities retained.
- Installer checks the source menu snapshot and publishes new child pages before linking them.
- Exact native RTL screenshots and repeatable page preview. Hardware source and bitstream remain the accepted 0.1.2 baseline; the new layout awaits hardware acceptance.

This is a source-branch update, not a new firmware or multi-system core release.

## v0.1.2-public.1 — 2026-10-31

First public preview of Analogue Pocket CoverFlow Chinese Menu.

- Native Chinese GB/GBC UI and independent Unicode title columns (pack v9).
- A opens folders; B returns through the reserved last entry. Menu video stays active through loading to prevent the verified folder white flash.
- Public library builder reads users' existing GB/GBC trees, optional title aliases and PNG covers. ROM names/content and original saves are retained.
- Installer defaults to planning; apply requires a new local backup, verifies checksums and publishes core metadata last. Rollback retains current saves.
- Bilingual documentation, scoped validation record, license notices, issue templates and CI.

The FPGA bitstream is byte-identical to the accepted `0.1.2-cn-lab` build. Public metadata and distribution tools are new. One-device user confirmation covers menu display, GB/GBC launch and menu-transition flash; it does not certify every game, sound, save or suspend function. Game-launch flash/loading delay remain known issues.

## Private development lineage

- `0.1.2-cn-lab`: continuous menu video during boot/folder loading; accepted by user on hardware.
- `0.1.1-cn-lab`: corrected APF platform path declarations (R4), B navigation and folder layout; game launch confirmed.
- Initial lab: Chinese glyphs, v9 title format, cover library and isolated trial installation.

Private lab tags are historical checkpoints, not public distribution tags. Public tags are immutable and identify the corresponding source, metadata, release archive and checksums. Automatic multi-platform switching remains research, not a release feature.
