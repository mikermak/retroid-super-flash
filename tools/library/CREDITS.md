# Credits (tools/library)

All cartridge models below are licensed **CC-BY-4.0**
(https://creativecommons.org/licenses/by/4.0/). The .glb files are not in this
repository; put them in `firmware/library-db/models/` (or pass `--gba-model`,
`--gb-model`, `--nes-model`). Without a model the tool falls back to its own
simple model for that system.

| System | Model | Author | Source |
|---|---|---|---|
| GBA | "Gameboy Advance Cartridge" | **Vxcl** (https://sketchfab.com/vxclhd) | https://sketchfab.com/3d-models/gameboy-advance-cartridge-38c1e6702e5d4f21af1d0930689b1d10 |
| Game Boy / Game Boy Color | "Gameboy cartridge" | **Val Turcea** (https://sketchfab.com/zwinkers) | https://sketchfab.com/3d-models/gameboy-cartridge-0c4f3c521907447098df0792e6cf9a1b |
| NES | "NES Cartridge" | **Anette Rana** (https://sketchfab.com/pertrosfoliea) | https://sketchfab.com/3d-models/nes-cartridge-ce42ffeab9144a2fabf3238053d84832 |

Changes made by `render_carts.py`: the label face of each model gets new UVs and the
real label of each game (the models' own example labels are not used), the plastic is
tinted per game (grey, black, coloured or gold editions), the GBA screw and PCB are not
rendered, models are rotated/scaled to real cartridge dimensions.

Also tested but not used: "Gameboy Cartridge" by Karolina D
(https://sketchfab.com/KarolinaArts, CC-BY-4.0,
https://sketchfab.com/3d-models/gameboy-cartridge-7c0160c8097a43e0a5e146bf4d7e01a1).

- The folder model is our own (render_carts.py).
- Game data and label scans: Screenscraper.fr (labels are copyrighted by their
  owners; they are only used locally and never committed or released).
