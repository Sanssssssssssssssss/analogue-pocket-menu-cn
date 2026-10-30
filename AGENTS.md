# Public Pocket menu project

- Never commit ROMs, BIOS, saves, personal card inventories or credentials.
- `core/src/` matches the device-tested 0.1.2 implementation. Changes require RTL regression, full Quartus timing review and clearly scoped hardware acceptance.
- `tools/` only builds local staging directories or performs explicitly requested, backed-up installations. Do not format cards or modify firmware.
- Run `python -m unittest discover -s tests -v` and `python tools/check_repository.py` for packaging changes. Test with synthetic bytes, never personal games/saves.
- Keep the English and Chinese quick starts consistent. Distinguish simulation, compilation and device reports. Do not advertise GBA or cross-core launching as implemented.
- Preserve upstream notices. New project tools are MIT; inherited hardware components keep their own licenses.
