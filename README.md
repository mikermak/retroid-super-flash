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
- **Cartridge carousel** (chis build): the SD ROM browser becomes a cover-flow of real
  cartridges. Each game is rendered in 3D on a PC beforehand (Blender) with its real label from
  Screenscraper (`tools/library/maak_bibliotheek.py`, output copied to `/LIBRARY/` on the SD);
  the firmware shows the pre-rendered poses (front, half-turned, side) with a per-pose palette
  slot that is swapped at V-blank, plus title, year, publisher and players. Games without a
  library entry get a blank 3D cart (built into the firmware). L/R switch All / GBA / GB / GBC,
  five themes (Red/Dark, Red/White, Wood, Dark, Light); the classic list stays available
  (UI settings, *Browser view*). Inspired by **[slot.](https://github.com/slot-cfw/slot)** and
  its EZ-Flash Omega port [slot. advance](https://github.com/FrankieT19/slot-advance) (both
  GPL-3.0). The GB/GBC cartridge and folder models are our own; the **GBA cartridge model** is
  "Gameboy Advance Cartridge" by **Vxcl** (https://sketchfab.com/vxclhd), licensed
  **CC-BY-4.0**, source
  https://sketchfab.com/3d-models/gameboy-advance-cartridge-38c1e6702e5d4f21af1d0930689b1d10
  (label face re-UV'd, plastic tinted per game; the .glb is not in this repository, see
  `tools/library/CREDITS.md`). Label scans are copyrighted by their owners and are never part
  of this repository or its releases.

These additions live in `src/coverart.{c,h}`, `src/carousel_gfx.{c,h}`, `src/menu_carousel.h`, `tools/library/`,
`src/res/{logo_hq,qr_retroid,tab_icons}.h`, the theme table and render hooks in `src/menu.c`, and the
`coverart_enable` / `flat_icons` / `browser_view` settings. Carousel previews can be rendered on a PC
with `tools/carousel/make_previews.sh`.

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

A ready-made pack is the official EZ-Flash Omega thumbnail set:
**<https://www.ezflash.cn/zip/IMGS.zip>** — extract its `IMGS/` folder to the root of your SD card.

> Note: thumbnail images are game title-screens owned by their respective publishers; they are not
> bundled with this firmware. Download/supply them yourself.

## License

GNU GPL v3, inherited from SuperFW. See `LICENSE` / the per-file copyright headers, which are
unchanged. Source for this build is published here in accordance with the GPL.
