# Changelog

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
