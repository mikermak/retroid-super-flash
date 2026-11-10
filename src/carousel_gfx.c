/*
 * Cartridge carousel -- drawing primitives. See carousel_gfx.h.
 *
 * Everything is drawn with 16-bit writes only (GBA VRAM cannot take byte
 * writes), clipped to the screen and to the current vertical clip band.
 *
 * Copyright (C) 2026 Retroid. GPL-3.0-or-later (same license as SuperFW).
 */
// Compiled for size: on the cart this code lives in (nearly full) EWRAM.
#pragma GCC optimize ("Os")

#include <stdint.h>
#include <stdbool.h>
#include <string.h>

#include "carousel_gfx.h"

#ifdef USE_CAROUSEL

#include "fonts/font_render.h"

#ifdef CAROUSEL_HOST
  #define CG_COPY16(d, s, n)   memcpy((void*)(d), (s), (n) * 2)
#else
  #include "gbahw.h"
  #define CG_COPY16(d, s, n)   dma_memcpy16((d), (s), (n))
#endif

#define SW        240
#define CART_CY    70      // Vertical center of the carts
#define DOTS_W      9      // Width of "..."

// Vertical clip band for the span primitives.
static int clip_y0 = CG_AREA_Y0, clip_y1 = CG_AREA_Y1;

static inline int imin(int a, int b) { return a < b ? a : b; }
static inline int imax(int a, int b) { return a > b ? a : b; }
static inline int iabs(int a) { return a < 0 ? -a : a; }

// Horizontal span [x0, x1) on row y.
static void hspan(volatile uint8_t *fb, int y, int x0, int x1, uint8_t c) {
  if (y < clip_y0 || y >= clip_y1)
    return;
  if (x0 < 0) x0 = 0;
  if (x1 > SW) x1 = SW;
  if (x0 >= x1)
    return;
  volatile uint16_t *row = (volatile uint16_t*)&fb[y * SW];
  if (x0 & 1) {
    unsigned i = x0 >> 1;
    row[i] = (row[i] & 0x00FF) | (c << 8);
    x0++;
  }
  if (x1 & 1) {
    unsigned i = x1 >> 1;
    row[i] = (row[i] & 0xFF00) | c;
    x1--;
  }
  uint16_t cc = c | (c << 8);
  for (int i = x0 >> 1; i < (x1 >> 1); i++)
    row[i] = cc;
}

static void rect(volatile uint8_t *fb, int x, int y, int w, int h, uint8_t c) {
  for (int r = 0; r < h; r++)
    hspan(fb, y + r, x, x + w, c);
}

static void vline(volatile uint8_t *fb, int x, int y0, int y1, uint8_t c) {
  for (int y = y0; y < y1; y++)
    hspan(fb, y, x, x + 1, c);
}

// Rectangle with cut corners (radius 1 or 2).
static void rrect(volatile uint8_t *fb, int x, int y, int w, int h, int rad, uint8_t c) {
  for (int r = 0; r < h; r++) {
    int ins = 0;
    if (r < rad)
      ins = rad - r;
    else if (r >= h - rad)
      ins = rad - (h - 1 - r);
    hspan(fb, y + r, x + ins, x + w - ins, c);
  }
}

// True if the whole rectangle is visible (safe for the unclipped font code).
static bool fully_visible(int x, int y, int w, int h) {
  return x >= 0 && x + w <= SW && y >= clip_y0 && y + h <= clip_y1;
}

static void text(volatile uint8_t *fb, const char *t, int x, int y, uint8_t c) {
  draw_text_idx8_bus16(t, (uint8_t*)&fb[y * SW + x], SW, c);
}

// Copies `t` into `out` so that it fits in `maxw` pixels (adds "...").
static unsigned fit_text(const char *t, char *out, unsigned outsz, unsigned maxw) {
  unsigned tw = font_width(t);
  if (tw <= maxw) {
    strncpy(out, t, outsz - 1);
    out[outsz - 1] = 0;
    return tw;
  }
  unsigned n = font_width_cap(t, maxw > DOTS_W ? maxw - DOTS_W : 0);
  if (n > outsz - 4)
    n = outsz - 4;
  memcpy(out, t, n);
  memcpy(&out[n], "...", 4);
  return font_width(out);
}

// Word-wrapped, centered text block (max `maxlines`), vertically centered in
// [y0, y0 + h). Only call when the area is fully visible.
static void text_block(volatile uint8_t *fb, const char *t, int cx, int y0, int h,
                       unsigned maxw, unsigned maxlines, uint8_t c) {
  const unsigned lh = 14;
  char lines[3][64];
  unsigned widths[3];
  unsigned n = 0;
  if (maxlines > 3)
    maxlines = 3;

  while (*t && n < maxlines) {
    while (*t == ' ')
      t++;
    if (!*t)
      break;
    unsigned outw, cnt;
    if (n == maxlines - 1 && font_width(t) > maxw) {
      // Last line and the text does not fit: cut it with "..."
      widths[n] = fit_text(t, lines[n], sizeof(lines[n]), maxw);
      n++;
      break;
    }
    cnt = font_width_cap_space(t, maxw, &outw);
    if (!cnt) {
      // A single word wider than the line: hard cut.
      cnt = font_width_cap(t, maxw);
      if (!cnt)
        break;
    }
    if (cnt > sizeof(lines[n]) - 1)
      cnt = sizeof(lines[n]) - 1;
    memcpy(lines[n], t, cnt);
    lines[n][cnt] = 0;
    widths[n] = font_width(lines[n]);
    t += cnt;
    n++;
  }

  int ty = y0 + (h - (int)(n * lh)) / 2 - 1;
  for (unsigned i = 0; i < n; i++)
    text(fb, lines[i], cx - (int)widths[i] / 2, ty + i * lh, c);
}

// ---------------------------------------------------------------------------
// Label art

// Scales the 120x80 label to w x h (nearest neighbour) at (x0, y0).
static void blit_label(volatile uint8_t *fb, int x0, int y0, int w, int h, const uint8_t *src) {
  if (w == CG_LABEL_W && h == CG_LABEL_H && !(x0 & 1) && x0 >= 0 && x0 + w <= SW) {
    // 1:1 and aligned: copy whole rows.
    for (int r = 0; r < h; r++) {
      int y = y0 + r;
      if (y >= clip_y0 && y < clip_y1)
        CG_COPY16(&fb[y * SW + x0], &src[r * CG_LABEL_W], CG_LABEL_W / 2);
    }
    return;
  }

  int xs = imax(x0, 0), xe = imin(x0 + w, SW);
  if (xs >= xe)
    return;
  uint8_t sxt[SW];
  for (int x = xs; x < xe; x++)
    sxt[x - xs] = ((x - x0) * CG_LABEL_W) / w;

  for (int r = 0; r < h; r++) {
    int y = y0 + r;
    if (y < clip_y0 || y >= clip_y1)
      continue;
    const uint8_t *srow = &src[((r * CG_LABEL_H) / h) * CG_LABEL_W];
    volatile uint16_t *row = (volatile uint16_t*)&fb[y * SW];
    int x = xs;
    if (x & 1) {
      row[x >> 1] = (row[x >> 1] & 0x00FF) | (srow[sxt[0]] << 8);
      x++;
    }
    for (; x + 1 < xe; x += 2)
      row[x >> 1] = srow[sxt[x - xs]] | (srow[sxt[x + 1 - xs]] << 8);
    if (x < xe)
      row[x >> 1] = (row[x >> 1] & 0xFF00) | srow[sxt[x - xs]];
  }
}

// Label without artwork: colored sticker with the game name.
static void generic_label(volatile uint8_t *fb, int x0, int y0, int w, int h,
                          unsigned type, const char *title, bool big) {
  uint8_t bg, band, fg;
  switch (type) {
  case CG_CART_GB:   bg = CG_CUBE(5, 5, 4); band = CG_CUBE(1, 1, 3); fg = CG_CUBE(1, 1, 1); break;
  case CG_CART_GBC:  bg = CG_CUBE(0, 3, 4); band = CG_CUBE(5, 4, 0); fg = CG_WHITE;         break;
  case CG_CART_OTHER:bg = CG_CUBE(3, 0, 1); band = CG_CUBE(1, 1, 1); fg = CG_WHITE;         break;
  default:           bg = CG_CUBE(1, 1, 3); band = CG_CUBE(5, 3, 0); fg = CG_WHITE;         break;
  }
  int bh = imax(2, h / 7);
  rect(fb, x0, y0, w, h, bg);
  rect(fb, x0, y0 + bh, w, imax(1, bh / 3), band);
  rect(fb, x0, y0 + h - bh, w, imax(1, bh / 3), band);

  int ty = y0 + bh + 2, th = h - 2 * bh - 3;
  if (big && title && fully_visible(x0, ty, w, th))
    text_block(fb, title, x0 + w / 2, ty, th, w - 8, 3, fg);
  else {
    // Too small for text: two "text lines".
    rect(fb, x0 + w / 5, y0 + h / 2 - 3, w * 3 / 5, imax(1, h / 20), fg);
    rect(fb, x0 + w / 4, y0 + h / 2 + 2, w / 2, imax(1, h / 20), fg);
  }
}

static void draw_label(volatile uint8_t *fb, int x, int y, int w, int h,
                       const t_cg_cart *c, bool big) {
  if (c->label)
    blit_label(fb, x, y, w, h, c->label);
  else
    generic_label(fb, x, y, w, h, c->type, c->title, big);
}

// ---------------------------------------------------------------------------
// Cartridges. `lw` is the label width (120 = selected, 60 = neighbours).

// GBA-style (landscape) cartridge; also used for "other" systems.
static void draw_cart_gba(volatile uint8_t *fb, int cx, int lw, const t_cg_cart *c, bool big) {
  const bool other = c->type == CG_CART_OTHER;
  const uint8_t out  = CG_CUBE(0, 0, 0);
  const uint8_t body = other ? CG_CUBE(3, 3, 3) : CG_CUBE(2, 2, 2);
  const uint8_t hl   = other ? CG_CUBE(4, 4, 4) : CG_CUBE(3, 3, 3);
  const uint8_t sh   = other ? CG_CUBE(2, 2, 2) : CG_CUBE(1, 1, 1);

  int lh = lw * 2 / 3;
  int m = lw / 12, t = lw / 8, b = lw / 14;
  int W = lw + 2 * m, H = lh + t + b;
  int x0 = cx - W / 2, y0 = CART_CY - H / 2;
  int rad = big ? 3 : 2;

  rrect(fb, x0, y0, W, H, rad, out);
  rrect(fb, x0 + 1, y0 + 1, W - 2, H - 2, rad - 1, body);
  hspan(fb, y0 + 1, x0 + rad + 1, x0 + W - rad - 1, hl);       // bevel light
  vline(fb, x0 + 1, y0 + rad + 1, y0 + H - rad - 1, hl);
  hspan(fb, y0 + H - 2, x0 + rad + 1, x0 + W - rad - 1, sh);   // bevel dark
  vline(fb, x0 + W - 2, y0 + rad + 1, y0 + H - rad - 1, sh);

  // Grip grooves left and right on the top edge, raised center lip.
  int gw = W / 4, gstep = imax(2, (t - 3) / 3);
  for (int k = 0; k < 3; k++) {
    int gy = y0 + 3 + k * gstep;
    if (gy + 1 >= y0 + t - 1)
      break;
    hspan(fb, gy,     x0 + m,          x0 + m + gw,     sh);
    hspan(fb, gy + 1, x0 + m,          x0 + m + gw,     hl);
    hspan(fb, gy,     x0 + W - m - gw, x0 + W - m,      sh);
    hspan(fb, gy + 1, x0 + W - m - gw, x0 + W - m,      hl);
  }
  int lipw = W - 2 * (m + gw) - 2 * m;
  if (lipw > 4) {
    hspan(fb, y0 + 3, x0 + W / 2 - lipw / 2, x0 + W / 2 + lipw / 2, hl);
    hspan(fb, y0 + t - 3, x0 + W / 2 - lipw / 2, x0 + W / 2 + lipw / 2, sh);
  }

  // Label recess + label.
  rect(fb, x0 + m - 1, y0 + t - 1, lw + 2, lh + 2, out);
  draw_label(fb, x0 + m, y0 + t, lw, lh, c, big);
}

// Game Boy / Game Boy Color style (portrait, cut top-right corner, ridges).
static void draw_cart_gb(volatile uint8_t *fb, int cx, int lw, const t_cg_cart *c, bool big) {
  uint8_t out, body, hl, sh;
  if (c->type == CG_CART_GBC) {
    out = CG_CUBE(1, 0, 2); body = CG_CUBE(3, 2, 4); hl = CG_CUBE(4, 3, 5); sh = CG_CUBE(2, 1, 3);
  } else {
    out = CG_CUBE(2, 2, 2); body = CG_CUBE(4, 4, 4); hl = CG_CUBE(5, 5, 5); sh = CG_CUBE(3, 3, 3);
  }

  int llw = lw * 4 / 5, llh = llw * 2 / 3;
  int m = llw / 8, t = llw / 5, b = llw / 6;
  int W = llw + 2 * m, H = t + llh + b;
  int cut = llw / 8;
  int x0 = cx - W / 2, y0 = CART_CY - H / 2;

  for (int r = 0; r < H; r++) {
    int rins = r < cut ? cut - r : (r >= H - 1 ? 1 : 0);
    int lins = (r == 0 || r == H - 1) ? 1 : 0;
    int y = y0 + r;
    hspan(fb, y, x0 + lins, x0 + W - rins, out);
    if (r > 0 && r < H - 1)
      hspan(fb, y, x0 + 1, x0 + W - rins - 1, body);
  }
  hspan(fb, y0 + 1, x0 + 2, x0 + W - cut - 1, hl);
  vline(fb, x0 + 1, y0 + 2, y0 + H - 2, hl);
  hspan(fb, y0 + H - 2, x0 + 2, x0 + W - 2, sh);
  vline(fb, x0 + W - 2, y0 + cut + 1, y0 + H - 2, sh);

  // Ridges along the top.
  for (int gy = y0 + 3; gy + 1 < y0 + t - 2; gy += 3) {
    int r = gy - y0;
    int xe = x0 + W - m - (r < cut + 2 ? cut + 2 - r : 0);
    hspan(fb, gy,     x0 + m, xe, sh);
    hspan(fb, gy + 1, x0 + m, xe, hl);
  }

  // Label recess + label.
  rect(fb, x0 + m - 1, y0 + t - 1, llw + 2, llh + 2, sh);
  draw_label(fb, x0 + m, y0 + t, llw, llh, c, big);

  // Small embossed arrow at the bottom.
  int ah = imax(2, b / 3), ay = y0 + t + llh + (b - ah) / 2;
  for (int i = 0; i < ah; i++)
    hspan(fb, ay + i, cx - i - 1, cx + i + 1, sh);
}

// Folder ("map-cart"): opens a sub directory.
static void draw_folder(volatile uint8_t *fb, int cx, int lw, const t_cg_cart *c, bool big) {
  const uint8_t out = CG_CUBE(2, 1, 0), back = CG_CUBE(4, 3, 1);
  const uint8_t front = CG_CUBE(5, 4, 2), hl = CG_CUBE(5, 5, 3);
  int lh = lw * 2 / 3;
  int W = lw + 8, H = lh + 14;
  int x0 = cx - W / 2, y0 = CART_CY - H / 2;
  int tabw = W * 2 / 5, tabh = imax(3, H / 9);
  int fy = y0 + tabh + H / 7;   // Front flap top

  rrect(fb, x0, y0, tabw, tabh + 2, 1, out);
  rect(fb, x0 + 1, y0 + 1, tabw - 2, tabh + 1, back);
  rrect(fb, x0, y0 + tabh, W, H - tabh, 1, out);
  rect(fb, x0 + 1, y0 + tabh + 1, W - 2, H - tabh - 2, back);
  // Paper sheet peeking out.
  rect(fb, x0 + 4, y0 + tabh + 3, W - 8, fy - (y0 + tabh + 3), CG_CUBE(5, 5, 5));
  // Front flap.
  hspan(fb, fy, x0 + 1, x0 + W - 1, out);
  rect(fb, x0 + 1, fy + 1, W - 2, y0 + H - 1 - (fy + 1), front);
  hspan(fb, fy + 1, x0 + 1, x0 + W - 1, hl);

  int ty = fy + 3, th = y0 + H - 3 - ty;
  if (big && c->title && fully_visible(x0 + 4, ty, W - 8, th))
    text_block(fb, c->title, cx, ty, th, W - 12, 3, out);
}

// Cart position on screen for x100 (0 = center, 100 = neighbour slot).
static int cart_x(int x100) {
  int a = iabs(x100), px;
  if (a <= 100)
    px = a * 108 / 100;
  else
    px = 108 + (a - 100) * 74 / 100;
  return SW / 2 + (x100 < 0 ? -px : px);
}

static int cart_lw(int x100) {
  int a = imin(iabs(x100), 100);
  return 120 - (60 * a) / 100;
}

// ---------------------------------------------------------------------------
// Wood texture (procedural, generated once into a buffer by the caller).

static uint32_t hash32(uint32_t x) {
  x ^= x >> 16; x *= 0x7feb352dU;
  x ^= x >> 15; x *= 0x846ca68bU;
  x ^= x >> 16;
  return x;
}

// Smooth 1D value noise, p in 1/16 cell units, result 0..255.
static int vnoise(uint32_t seed, int p) {
  int i = p >> 4, f = p & 15;
  int a = hash32(seed * 7919U + i) & 255;
  int b = hash32(seed * 7919U + i + 1) & 255;
  // Smoothstep-ish interpolation.
  int s = (f * f * (48 - 2 * f)) >> 8;   // 0..15 -> 0..~15
  return a + (((b - a) * s) >> 4);
}

void cg_wood_row(uint8_t *row, unsigned y) {
  // Dark -> light wood tones (all from the color cube).
  static const uint8_t ramp[4] = {
    CG_CUBE(2, 1, 0), CG_CUBE(3, 2, 1), CG_CUBE(4, 2, 1), CG_CUBE(4, 3, 2)
  };
  static const uint8_t bayer4[4][4] = {
    { 0, 8, 2, 10 }, { 12, 4, 14, 6 }, { 3, 11, 1, 9 }, { 15, 7, 13, 5 }
  };
  const unsigned plank_h = 32;
  unsigned plank = y / plank_h, py = y % plank_h;

  if (py == 0) {
    memset(row, CG_CUBE(1, 0, 0), SW);
    return;
  }

  int off = hash32(plank * 131 + 7) & 511;
  for (unsigned x = 0; x < SW; x++) {
    // Grain lines run horizontally and bend slowly along x.
    int wob = vnoise(plank * 3 + 1, (x + off)) / 5;
    int g = vnoise(plank * 3 + 2, (int)py * 9 + wob);
    int fiber = (int)(hash32((x + off) * 977 + y * 131) & 15) - 8;
    int tone = (int)(hash32(plank * 59 + 3) & 31) - 16;    // per-plank shade
    int v = 70 + (g * 5) / 8 + fiber + tone;
    if (py == 1)
      v += 40;                 // Highlight below the seam
    else if (py == plank_h - 1)
      v -= 50;                 // Shadow above the next seam
    // Thin dark grain lines where the noise peaks.
    if (g > 222)
      v = 40;
    if (v < 0) v = 0;
    if (v > 255) v = 255;
    int lvl = (v * 4 + bayer4[y & 3][x & 3] * 8 - 64) / 256;
    if (lvl < 0) lvl = 0;
    if (lvl > 3) lvl = 3;
    row[x] = ramp[lvl];
  }
}

// ---------------------------------------------------------------------------
// Header pills, footer, scene.

static void draw_header(volatile uint8_t *fb, const t_cg_scene *s) {
  if (!s->nfilters)
    return;
  clip_y0 = 0; clip_y1 = CG_AREA_Y0;
  unsigned total = 0;
  for (unsigned i = 0; i < s->nfilters; i++)
    total += font_width(s->filter_names[i]) + 8;
  int x = SW - 2 - (int)total;
  if (x < (int)s->header_minx)
    x = s->header_minx;
  for (unsigned i = 0; i < s->nfilters; i++) {
    int w = font_width(s->filter_names[i]) + 8;
    if (x + w > SW)
      break;
    if (i == s->filter) {
      rrect(fb, x, 1, w, 15, 2, CG_BG);
      text(fb, s->filter_names[i], x + 4, 0, CG_FT);
    } else
      text(fb, s->filter_names[i], x + 4, 0, CG_LGRAY);
    x += w;
  }
}

static void draw_footer(volatile uint8_t *fb, const t_cg_scene *s) {
  clip_y0 = CG_AREA_Y1; clip_y1 = 160;
  rect(fb, 0, CG_AREA_Y1, SW, 160 - CG_AREA_Y1, CG_FG);

  int left = 4, right = SW - 4;
  char tmp[64];
  if (s->counter && s->counter[0]) {
    unsigned w = font_width(s->counter);
    text(fb, s->counter, right - w, CG_AREA_Y1, CG_WHITE);
    right -= w + 8;
  }
  if (s->clock && s->clock[0]) {
    unsigned w = font_width(s->clock);
    text(fb, s->clock, right - w, CG_AREA_Y1, CG_WHITE);
    right -= w + 8;
  }
  if (s->user && s->user[0]) {
    unsigned w = fit_text(s->user, tmp, sizeof(tmp), 70);
    text(fb, tmp, left, CG_AREA_Y1, CG_WHITE);
    left += w + 8;
  }
  if (s->path && s->path[0] && !(s->path[0] == '/' && !s->path[1]) && right - left > 20) {
    unsigned maxw = right - left;
    unsigned skip = font_width_lcap(s->path, maxw - DOTS_W);
    if (skip && font_width(s->path) > maxw) {
      text(fb, "...", left, CG_AREA_Y1, CG_LGRAY);
      text(fb, &s->path[skip], left + DOTS_W, CG_AREA_Y1, CG_LGRAY);
    } else
      text(fb, s->path, left, CG_AREA_Y1, CG_LGRAY);
  }
}

static void draw_plate(volatile uint8_t *fb, const char *t, int y) {
  char tmp[96];
  unsigned w = fit_text(t, tmp, sizeof(tmp), 220);
  rrect(fb, SW / 2 - (int)w / 2 - 6, y, w + 12, 17, 3, CG_FG);
  text(fb, tmp, SW / 2 - (int)w / 2, y, CG_WHITE);
}

void cg_render_scene(volatile uint8_t *fb, const t_cg_scene *s) {
  clip_y0 = CG_AREA_Y0; clip_y1 = CG_AREA_Y1;

  // Background
  if (s->bgstyle == CG_BG_WOOD && s->woodtex) {
    for (unsigned r = 0; r < CG_AREA_H; r++)
      CG_COPY16(&fb[(CG_AREA_Y0 + r) * SW], &s->woodtex[r * SW], SW / 2);
  } else
    rect(fb, 0, CG_AREA_Y0, SW, CG_AREA_H, CG_BG);

  // Carts, back to front (farthest from the center first).
  uint8_t order[CG_MAX_CARTS];
  unsigned n = s->ncarts > CG_MAX_CARTS ? CG_MAX_CARTS : s->ncarts;
  for (unsigned i = 0; i < n; i++)
    order[i] = i;
  for (unsigned i = 0; i < n; i++)
    for (unsigned j = i + 1; j < n; j++)
      if (iabs(s->carts[order[j]].x100) > iabs(s->carts[order[i]].x100)) {
        uint8_t t = order[i]; order[i] = order[j]; order[j] = t;
      }

  for (unsigned i = 0; i < n; i++) {
    const t_cg_cart *c = &s->carts[order[i]];
    int cx = cart_x(c->x100), lw = cart_lw(c->x100);
    if (cx + lw < -20 || cx - lw > SW + 20)
      continue;
    bool big = iabs(c->x100) < 20;
    if (c->type == CG_CART_FOLDER)
      draw_folder(fb, cx, lw, c, big);
    else if (c->type == CG_CART_GB || c->type == CG_CART_GBC)
      draw_cart_gb(fb, cx, lw, c, big);
    else
      draw_cart_gba(fb, cx, lw, c, big);
  }

  if (s->message)
    draw_plate(fb, s->message, CART_CY - 8);
  if (s->name)
    draw_plate(fb, s->name, 124);

  draw_header(fb, s);
  draw_footer(fb, s);
  clip_y0 = CG_AREA_Y0; clip_y1 = CG_AREA_Y1;
}

#endif  // USE_CAROUSEL
