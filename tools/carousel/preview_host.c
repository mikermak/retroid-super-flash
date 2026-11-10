/*
 * Host (PC) preview renderer for the cartridge carousel.
 *
 * Compiles the real drawing code (src/carousel_gfx.c + the font renderer) for
 * the PC and writes a 240x160 PPM of a carousel screen, so layouts and themes
 * can be checked without hardware. Used by tools/carousel/make_previews.sh.
 *
 *   preview_host <theme 0..4> <scene> <out.ppm> [label.bmp ...]
 *
 * scene: gba   - GBA filter, three carts with label art
 *        all   - "All" filter: folder, GB, GBC generic labels
 *        slide - mid-animation frame (carts sliding)
 *
 * Copyright (C) 2026 Retroid. GPL-3.0-or-later.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

#include "carousel_gfx.h"
#include "res/tab_icons.h"

void *font_base_addr;
extern const uint32_t font_ascii_embedded[];

#define RGB2GBA(c) ((((c) >> 19) & 0x1F) | ((((c) >> 11) & 0x1F) << 5) | ((((c) >> 3) & 0x1F) << 10))

// Must match themes[] in src/menu.c.
static const struct { uint32_t fg, bg, ft, hi; int wood; const char *name; } themes[] = {
  { 0xcc1f2d, 0x0c0c10, 0xf2f2f2, 0x6651c4, 0, "Red/Dark" },
  { 0xcc1f2d, 0xf4f4f4, 0x1a1a1a, 0xf0b8bc, 0, "Red/White" },
  { 0x4a2c17, 0x7a4e2c, 0xf6e7c8, 0xc98a3c, 1, "Wood" },
  { 0x30303a, 0x111116, 0xececf0, 0x3d6fc4, 0, "Dark" },
  { 0x5b6170, 0xe9e9ee, 0x1b1b22, 0xa9c8f2, 0, "Light" },
};

static uint8_t fb[240 * 160];
static uint32_t pal[256];          // RGB888
static uint8_t labels[8][CG_LABEL_W * CG_LABEL_H];
static uint8_t wood[CG_AREA_H * 240];

static uint32_t c555(uint16_t v) {   // GBA BGR555 -> RGB888
  uint32_t r = v & 31, g = (v >> 5) & 31, b = (v >> 10) & 31;
  return ((r * 255 / 31) << 16) | ((g * 255 / 31) << 8) | (b * 255 / 31);
}

static uint8_t cube_idx(unsigned v) {   // same mapping as coverart.c
  unsigned r = v & 0x1F, g = (v >> 5) & 0x1F, b = (v >> 10) & 0x1F;
  return 20 + (((r * 6) >> 5) * 36 + ((g * 6) >> 5) * 6 + ((b * 6) >> 5));
}

static int load_bmp(const char *fn, uint8_t *dst) {
  FILE *f = fopen(fn, "rb");
  if (!f) return 0;
  uint8_t h[54];
  if (fread(h, 1, 54, f) != 54) { fclose(f); return 0; }
  uint32_t off = h[10] | h[11] << 8 | h[12] << 16 | h[13] << 24;
  int32_t w = h[18] | h[19] << 8 | h[20] << 16 | h[21] << 24;
  int32_t rh = h[22] | h[23] << 8 | h[24] << 16 | h[25] << 24;
  int td = rh < 0, hh = td ? -rh : rh;
  memset(dst, 20, CG_LABEL_W * CG_LABEL_H);
  fseek(f, off, SEEK_SET);
  unsigned rb = (w * 2 + 3) & ~3u;
  uint8_t row[256];
  for (int y = 0; y < hh && y < CG_LABEL_H; y++) {
    if (fread(row, 1, rb, f) != rb) break;
    int dy = td ? y : hh - 1 - y;
    for (int x = 0; x < w && x < CG_LABEL_W; x++)
      dst[dy * CG_LABEL_W + x] = cube_idx(row[x * 2] | row[x * 2 + 1] << 8);
  }
  fclose(f);
  return 1;
}

// Draws a 16x16 OBJ icon (4 tiles, 1D mapping) like the GBA would.
static void icon(int x, int y, const uint8_t *tiles, int semi) {
  for (int ty = 0; ty < 2; ty++)
    for (int tx = 0; tx < 2; tx++)
      for (int py = 0; py < 8; py++)
        for (int px = 0; px < 8; px++) {
          uint8_t v = tiles[(ty * 2 + tx) * 64 + py * 8 + px];
          if (!v) continue;
          int X = x + tx * 8 + px, Y = y + ty * 8 + py;
          fb[Y * 240 + X] = semi ? 250 : 251;   // 250/251 = host-only colors
        }
}

int main(int argc, char **argv) {
  if (argc < 4) {
    fprintf(stderr, "usage: %s theme scene out.ppm [bmp...]\n", argv[0]);
    return 1;
  }
  font_base_addr = (void*)font_ascii_embedded;
  int th = atoi(argv[1]);
  const char *scene = argv[2];
  int nl = 0;
  for (int i = 4; i < argc && nl < 8; i++)
    if (load_bmp(argv[i], labels[nl]))
      nl++;

  // Palette: cube + theme colors.
  static const uint8_t lvl[6] = { 0, 6, 12, 19, 25, 31 };
  for (int r = 0; r < 6; r++)
    for (int g = 0; g < 6; g++)
      for (int b = 0; b < 6; b++)
        pal[20 + r * 36 + g * 6 + b] = c555((lvl[b] << 10) | (lvl[g] << 5) | lvl[r]);
  pal[CG_FG] = c555(RGB2GBA(themes[th].fg));
  pal[CG_BG] = c555(RGB2GBA(themes[th].bg));
  pal[CG_FT] = c555(RGB2GBA(themes[th].ft));
  pal[CG_HI] = c555(RGB2GBA(themes[th].hi));
  pal[251] = 0xffffff;
  { // 50% blend white over FG (semi-transparent tab icons)
    uint32_t f = pal[CG_FG];
    pal[250] = ((((f >> 16) & 255) + 255) / 2) << 16 | ((((f >> 8) & 255) + 255) / 2) << 8 | (((f & 255) + 255) / 2);
  }

  for (unsigned y = 0; y < CG_AREA_H; y++)
    cg_wood_row(&wood[y * 240], y);

  // Tab bar as menu.c draws it (FG fill + icons; browser tab selected).
  memset(fb, CG_FG, 240 * 16);
  const uint8_t *tabs[] = { tab_icon_clock, tab_icon_folder, tab_icon_bolt, tab_icon_sliders,
                            tab_icon_globe, tab_icon_wrench, tab_icon_info };
  for (int i = 0; i < 7; i++)
    icon(i * 16, 0, tabs[i], i != 1);

  static const char *const fnames[] = { "All", "GBA", "GB", "GBC" };
  t_cg_scene s;
  memset(&s, 0, sizeof(s));
  s.bgstyle = themes[th].wood ? CG_BG_WOOD : CG_BG_SOLID;
  s.woodtex = wood;
  s.nfilters = 4;
  s.filter_names = fnames;
  s.header_minx = 7 * 16 + 2;
  s.user = "Mike";
  s.path = "/GBA/";

  if (!strcmp(scene, "all")) {
    s.filter = 0;
    s.ncarts = 3;
    s.carts[0] = (t_cg_cart){ -100, CG_CART_FOLDER, NULL, "Homebrew" };
    s.carts[1] = (t_cg_cart){    0, CG_CART_GB,     NULL, "Tetris DX (World)" };
    s.carts[2] = (t_cg_cart){  100, CG_CART_GBC,    NULL, "Link's Awakening" };
    s.name = "Tetris DX (World)";
    s.counter = "7/31";
    s.path = "/";
  } else if (!strcmp(scene, "slide")) {
    s.filter = 1;
    s.ncarts = 4;
    s.carts[0] = (t_cg_cart){ -145, CG_CART_GBA, nl > 0 ? labels[0] : NULL, "A" };
    s.carts[1] = (t_cg_cart){  -45, CG_CART_GBA, nl > 1 ? labels[1] : NULL, "B" };
    s.carts[2] = (t_cg_cart){   55, CG_CART_GBA, nl > 2 ? labels[2] : NULL, "C" };
    s.carts[3] = (t_cg_cart){  155, CG_CART_GBA, NULL, "Unknown homebrew" };
    s.name = "Pokemon - Emerald Version";
    s.counter = "13/58";
  } else {
    s.filter = 1;
    s.ncarts = 3;
    s.carts[0] = (t_cg_cart){ -100, CG_CART_GBA, nl > 0 ? labels[0] : NULL, "Left" };
    s.carts[1] = (t_cg_cart){    0, CG_CART_GBA, nl > 1 ? labels[1] : NULL, "Pokemon - Emerald Version" };
    s.carts[2] = (t_cg_cart){  100, CG_CART_GBA, nl > 2 ? labels[2] : NULL, "Right" };
    s.name = "Pokemon - Emerald Version";
    s.counter = "12/58";
  }

  cg_render_scene(fb, &s);

  FILE *o = fopen(argv[3], "wb");
  fprintf(o, "P6\n240 160\n255\n");
  for (int i = 0; i < 240 * 160; i++) {
    uint32_t c = pal[fb[i]];
    fputc(c >> 16, o); fputc((c >> 8) & 255, o); fputc(c & 255, o);
  }
  fclose(o);
  return 0;
}
