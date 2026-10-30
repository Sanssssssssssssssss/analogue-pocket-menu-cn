# Contributing

Please keep changes focused on the documented GB/GBC menu. Discuss hardware-interface changes before expanding scope. Preserve upstream copyright/license notices.

## Local checks

Python 3.11+, `python -m pip install -r requirements.txt`, then:

```sh
python -m unittest discover -s tests -v
python tools/check_repository.py
```

Use synthetic bytes in tests. Never commit ROMs, BIOS, saves, a personal card inventory, access tokens or generated library packs. `.work/`, `.build/` and `dist/` are ignored local directories.

Changes to `core/src/` need RTL regressions, full Quartus compilation/timing review and clearly scoped device testing. Python tests do not establish FPGA compatibility. Changes to the library format must preserve the final parent entry and existing save-path mapping or provide an explicit migration.

## Bug reports

Include the release tag, Pocket firmware, platform, steps, exact error, and whether an original core works. For game-specific reports, provide a title/region/revision and optional hash instead of the ROM. Remove local usernames, paths and private library entries from logs. Do not attach entire `library-manifest.json` or backups.

## Versions

Public preview tags use SemVer prerelease syntax, starting with `v0.1.2-public.1`. The tag, `core.json`, release manifest and release title agree. Published tags and assets are not replaced; corrections get a new tag. The initial public bitstream retains its documented lab-build provenance.
