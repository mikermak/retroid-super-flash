/*
 * Host (PC) preview renderer for the cartridge carousel v2.
 *
 * Compiles the real drawing code (src/carousel_gfx.c + the font renderer) for
 * the PC and writes a 240x160 PPM of one carousel frame.
 *
 *   preview_host <theme 0..4> <slide> <filter 0..3> <out.ppm> <item-2> .. <item+2>
 *
 * item = "-" (nothing), "file.crt", or "blank:file.crt:Title" (blank cart, "_" = space).
 * slide = animation offset in 1/256 cart units (0 = at rest).
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

// Must match themes[] in src/menu.c (fg, bg, ft, hi).
static const uint32_t menu_themes[5][4] = {
  { 0xcc1f2d, 0x0c0c10, 0xf2f2f2, 0x6651c4 },   // Red/Dark
  { 0xcc1f2d, 0xf4f4f4, 0x1a1a1a, 0xf0b8bc },   // Red/White
  { 0x4a2c17, 0x7a4e2c, 0xf6e7c8, 0xc98a3c },   // Wood
  { 0x30303a, 0x111116, 0xececf0, 0x3d6fc4 },   // Dark
  { 0x5b6170, 0xe9e9ee, 0x1b1b22, 0xa9c8f2 },   // Light
};

static uint8_t fb[240 * 160];
static uint16_t pal[256];
static uint8_t bg[CG_AREA_H * 240];

static uint32_t c555(uint16_t v) {
  uint32_t r = v & 31, g = (v >> 5) & 31, b = (v >> 10) & 31;
  return (((r << 3) | (r >> 2)) << 16) | (((g << 3) | (g >> 2)) << 8) | ((b << 3) | (b >> 2));
}

static void *load(const char *fn) {
  FILE *f = fopen(fn, "rb");
  if (!f) { fprintf(stderr, "cannot open %s\n", fn); exit(1); }
  fseek(f, 0, SEEK_END);
  long n = ftell(f);
  fseek(f, 0, SEEK_SET);
  void *p = malloc(n);
  if (fread(p, 1, n, f) != (size_t)n) exit(1);
  fclose(f);
  return p;
}

static void icon(int x, int y, const uint8_t *tiles, int semi) {
  for (int ty = 0; ty < 2; ty++)
    for (int tx = 0; tx < 2; tx++)
      for (int py = 0; py < 8; py++)
        for (int px = 0; px < 8; px++) {
          if (!tiles[(ty * 2 + tx) * 64 + py * 8 + px]) continue;
          fb[(y + ty * 8 + py) * 240 + x + tx * 8 + px] = semi ? 250 : 251;
        }
}

int main(int argc, char **argv) {
  if (argc < 10) {
    fprintf(stderr, "usage: %s theme slide filter out.ppm item*5\n", argv[0]);
    return 1;
  }
  font_base_addr = (void*)font_ascii_embedded;
  int th = atoi(argv[1]), slide = atoi(argv[2]), filter = atoi(argv[3]);
  const t_cg_theme *t = &cg_themes[th];

  pal[CG_FG] = RGB2GBA(menu_themes[th][0]);
  pal[CG_BG] = RGB2GBA(menu_themes[th][1]);
  pal[CG_FT] = RGB2GBA(menu_themes[th][2]);
  pal[CG_HI] = RGB2GBA(menu_themes[th][3]);
  cg_theme_palette(t, pal);
  for (unsigned y = 0; y < CG_AREA_H; y++)
    cg_bg_row(t, &bg[y * 240], y);

  memset(fb, CG_FG, 240 * 16);
  const uint8_t *tabs[] = { tab_icon_clock, tab_icon_folder, tab_icon_bolt, tab_icon_sliders,
                            tab_icon_globe, tab_icon_wrench, tab_icon_info };
  for (int i = 0; i < 7; i++)
    icon(i * 16, 0, tabs[i], i != 1);

  t_cg_item items[5];
  char titles[5][64];
  memset(items, 0, sizeof(items));
  for (int k = 0; k < 5; k++) {
    const char *a = argv[5 + k];
    if (!strcmp(a, "-"))
      continue;
    if (!strncmp(a, "blank:", 6)) {
      char fn[512];
      const char *c = strchr(a + 6, ':');
      size_t n = c ? (size_t)(c - (a + 6)) : strlen(a + 6);
      memcpy(fn, a + 6, n); fn[n] = 0;
      items[k].crt = load(fn);
      items[k].blank = true;
      snprintf(titles[k], sizeof(titles[k]), "%s", c ? c + 1 : "");
      for (char *u = titles[k]; *u; u++)
        if (*u == '_') *u = ' ';          // "_" = space (shell friendly)
    } else {
      items[k].crt = load(a);
      snprintf(titles[k], sizeof(titles[k]), "%s", items[k].crt->title);
    }
    items[k].title = titles[k];
  }

  static const char *const fnames[] = { "All", "GBA", "GB", "GBC", "NES" };
  t_cg_scene s;
  memset(&s, 0, sizeof(s));
  s.theme = t;
  s.bgtex = bg;
  s.pal = pal;
  s.nfilters = 5;
  s.filter = filter;
  s.filter_names = fnames;
  s.header_minx = 7 * 16 + 2;
  s.user = "Mike";
  s.path = "/Games/";
  s.counter = "12/48";
  cg_place(&s, items, slide);
  if (items[2].crt) {
    s.name = titles[2];
    if (!items[2].blank) {
      s.meta[0] = items[2].crt->year;
      s.meta[1] = items[2].crt->publisher;
      static char pl[24];
      snprintf(pl, sizeof(pl), "%s %s", items[2].crt->players,
               strcmp(items[2].crt->players, "1") ? "players" : "player");
      s.meta[2] = items[2].crt->players[0] ? pl : NULL;   // same text as the firmware
    }
  }
  cg_render_scene(fb, &s);

  pal[251] = 0x7fff;
  { uint32_t f = c555(pal[CG_FG]);
    uint32_t m = ((((f >> 16) & 255) + 255) / 2) << 16 | ((((f >> 8) & 255) + 255) / 2) << 8 | (((f & 255) + 255) / 2);
    pal[250] = RGB2GBA(m); }

  FILE *o = fopen(argv[4], "wb");
  fprintf(o, "P6\n240 160\n255\n");
  for (int i = 0; i < 240 * 160; i++) {
    uint32_t c = c555(pal[fb[i]]);
    fputc(c >> 16, o); fputc((c >> 8) & 255, o); fputc(c & 255, o);
  }
  fclose(o);
  return 0;
}
