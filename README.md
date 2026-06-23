# Retroid Super Flash

A custom, branded build of **[SuperFW](https://github.com/davidgfnet/superfw)** — the open-source
firmware for Supercard / SuperChis Game Boy Advance flashcarts — by [Retroid](https://retroid.nl).

> **This is a fork.** All the heavy lifting is [SuperFW](https://github.com/davidgfnet/superfw)
> by **David Guillen Fandos (davidgf)**, licensed under the **GNU GPL v3**. This fork keeps that
> license and attribution; it only adds the features and branding listed below. Huge thanks to
> davidgf (and ChisBread) for the original work.

## What this fork adds

- **Cover-art / title-screen previews** in the ROM browser, the Recent list and the NOR/flash-games
  list. Reads standard EZ-Flash-Omega thumbnail packs directly: drop the pack's `IMGS/` folder onto
  the root of your SD card (`/IMGS/{c0}/{c1}/{CODE}.bmp`, 120×80 16-bit BMP keyed by GBA game code).
  Each pixel is mapped on the fly to a 216-color palette — no conversion step needed.
- **Two themes**: *Red / Dark* and *Red / White* (selectable in the UI settings tab).
- **Flat white tab icons** with a toggle to switch back to the original colored icons.
- **High-color boot/info logo** rendered cover-art style; its background follows the active theme.
- **Info screen** with a small "Custom Game Boy? Visit Retroid.nl" line + QR code.

These additions live in `src/coverart.{c,h}`, `src/res/{logo_hq,qr_retroid,tab_icons}.h`, the theme
table and render hooks in `src/menu.c`, and the `coverart_enable` / `flat_icons` settings.

## Building

Linux (or WSL on Windows). Toolchain: `gcc-arm-none-eabi`, `build-essential`, `cargo` (Rust), `python3`.

```sh
make BOARD=chis COMPRESSION_RATIO=9     # BOARD = sd | lite | chis
```

The output `superfw.gba` is renamed per board (`superfw-<board>.fw`). Notes:

- The bundled `apultra` compressor's Makefile defaults to `clang`; if you don't have it, build with
  `make -C apultra CC=gcc` (or set `CC?=gcc`) before running `make`.
- Source files use LF line endings; on Windows checkouts make sure your tools don't reintroduce CRLF
  in the build scripts (the Python helpers' shebangs require it).

## Cover-art packs

Any EZ-Flash-Omega style GBA thumbnail pack works — copy its `IMGS/` directory to the SD root. The
firmware looks up `/IMGS/<code[0]>/<code[1]>/<CODE>.bmp` using each ROM's 4-character game code.

## License

GNU GPL v3, inherited from SuperFW. See `LICENSE` / the per-file copyright headers, which are
unchanged. Source for this build is published here in accordance with the GPL.
