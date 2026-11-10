/*
 * Cartridge carousel v2 -- drawing. See carousel_gfx.h.
 *
 * Everything is written with 16-bit accesses only (GBA VRAM and the cart's
 * SDRAM do not take byte writes), clipped to the screen.
 *
 * Copyright (C) 2026 Retroid. GPL-3.0-or-later (same license as SuperFW).
 */

// Mostly compiled for size (EWRAM is tight on the cart); the pixel copy loop
// is placed in IWRAM as ARM code instead.
#pragma GCC optimize ("Os")

#include <stdint.h>
#include <stdbool.h>
#include <string.h>

#include "carousel_gfx.h"

#ifdef USE_CAROUSEL

#include "fonts/font_render.h"

#ifdef CAROUSEL_HOST
  #define CG_COPY16(d, s, n)   memcpy((void*)(d), (s), (n) * 2)
  #define CG_FAST
#else
  #include "gbahw.h"
  #include "compiler.h"
  #define CG_COPY16(d, s, n)   dma_memcpy16((d), (s), (n))
  #define CG_FAST              ARM_CODE IWRAM_CODE NOINLINE
#endif

#define SW        240
#define DOTS_W      9

static inline int imin(int a, int b) { return a < b ? a : b; }
static inline int imax(int a, int b) { return a > b ? a : b; }

static int clip_y0 = CG_AREA_Y0, clip_y1 = CG_AREA_Y1;

static uint16_t rgb555(uint32_t c) {
  return ((c >> 19) & 31) | (((c >> 11) & 31) << 5) | (((c >> 3) & 31) << 10);
}

static uint32_t mix(uint32_t a, uint32_t b, unsigned t, unsigned n) {
  uint32_t r = 0;
  for (unsigned s = 0; s < 24; s += 8) {
    unsigned ca = (a >> s) & 255, cb = (b >> s) & 255;
    r |= ((ca * (n - t) + cb * t) / n) << s;
  }
  return r;
}

// ---------------------------------------------------------------------------
// Primitives

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

static void text(volatile uint8_t *fb, const char *t, int x, int y, uint8_t c) {
  draw_text_idx8_bus16(t, (uint8_t*)&fb[y * SW + x], SW, c);
}

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

// Copies one rendered pose (spans of pre-indexed pixels) to the frame.
CG_FAST
static void blit_pose(volatile uint8_t *fb, int x, int y, const uint8_t *spans, const uint8_t *px,
                      unsigned h, int cy0, int cy1) {
  for (unsigned r = 0; r < h; r++, spans += 2) {
    int x0 = spans[0], len = spans[1];
    const uint8_t *src = px;
    px += len;
    int yy = y + (int)r;
    if (!len || yy < cy0 || yy >= cy1)
      continue;
    int xs = x + x0, xe = xs + len;
    if (xs < 0) { src -= xs; xs = 0; }
    if (xe > SW) xe = SW;
    if (xs >= xe)
      continue;
    volatile uint16_t *row = (volatile uint16_t*)&fb[yy * SW];
    if (xs & 1) {
      row[xs >> 1] = (row[xs >> 1] & 0x00FF) | (*src++ << 8);
      xs++;
    }
    volatile uint16_t *d = &row[xs >> 1];
    int pairs = (xe - xs) >> 1;
    for (int i = 0; i < pairs; i++, src += 2)
      *d++ = src[0] | (src[1] << 8);
    xs += pairs * 2;
    if (xs < xe)
      *d = (*d & 0xFF00) | *src;
  }
}

// ---------------------------------------------------------------------------
// Theme / background

const t_cg_theme cg_themes[CG_THEME_CNT] = {
  // Red/Dark
  { 0x26262e, 0x0b0b0e, 0x30303a, 0x4c4c58, 0x18181d, 0xf4f4f6, 0x000000, 0x9a9aa8, false, false },
  // Red/White
  { 0xffffff, 0xd8d8de, 0xcdcdd4, 0xf6f6f8, 0xa4a4ae, 0x1a1a1e, 0xffffff, 0x686874, false, true },
  // Wood
  { 0x5e4029, 0x22160d, 0x8a5a32, 0xb27c4a, 0x5a3a20, 0xf6e7c8, 0x100804, 0xc9a983, true,  false },
  // Dark
  { 0x2c303a, 0x0c0d11, 0x363a46, 0x585e6e, 0x1a1c22, 0xf0f2f6, 0x000000, 0x8f96a8, false, false },
  // Light
  { 0xf8f9fb, 0xd0d4dc, 0xc3c8d2, 0xeff1f5, 0x989eac, 0x1b1d24, 0xffffff, 0x5b6272, false, true },
};

bool cg_layout(int u, int16_t *x, uint8_t *pose) {
  const int sp = 100, far = 60;
  int a = u < 0 ? -u : u, px;
  if (a <= CG_U_ONE)
    px = a * sp / CG_U_ONE;
  else
    px = sp + (a - CG_U_ONE) * far / CG_U_ONE;
  *x = SW / 2 + (u < 0 ? -px : px);
  if (a < 64)
    *pose = CG_POSE_F;
  else if (a < 192)
    *pose = u < 0 ? CG_POSE_ML : CG_POSE_MR;
  else
    *pose = u < 0 ? CG_POSE_L : CG_POSE_R;
  return a < 410;
}

void cg_theme_palette(const t_cg_theme *t, uint16_t *pal) {
  for (unsigned i = 0; i < 8; i++)
    pal[CG_PAL_GRAD + i] = rgb555(mix(t->top, t->bottom, i, 7));
  pal[CG_PAL_SHELF_HI] = rgb555(t->shelf_hi);
  pal[CG_PAL_SHELF]    = rgb555(t->shelf);
  pal[CG_PAL_SHELF_LO] = rgb555(t->shelf_lo);
  pal[CG_PAL_SHADOW]   = rgb555(mix(t->shelf_lo, 0, 1, 2));
  pal[CG_PAL_TEXT]     = rgb555(t->text);
  pal[CG_PAL_TEXTSH]   = rgb555(t->textsh);
  pal[CG_PAL_META]     = rgb555(t->meta);
}

static uint32_t hash32(uint32_t x) {
  x ^= x >> 16; x *= 0x7feb352dU;
  x ^= x >> 15; x *= 0x846ca68bU;
  x ^= x >> 16;
  return x;
}

static const uint8_t bayer4[4][4] = {
  { 0, 8, 2, 10 }, { 12, 4, 14, 6 }, { 3, 11, 1, 9 }, { 15, 7, 13, 5 }
};

void cg_bg_row(const t_cg_theme *t, uint8_t *row, unsigned y) {
  const unsigned ay = y + CG_AREA_Y0;
  const unsigned shelf_y = CG_FLOOR_Y;
  if (ay < shelf_y) {
    // Wall: smooth gradient over 8 entries, ordered dithering between them.
    unsigned span = shelf_y - CG_AREA_Y0;
    unsigned v = (y * 7 * 16) / span;           // 0 .. 7*16
    for (unsigned x = 0; x < SW; x++) {
      unsigned lvl = (v + bayer4[ay & 3][x & 3]) >> 4;
      row[x] = CG_PAL_GRAD + (lvl > 7 ? 7 : lvl);
    }
    // Soft spotlight behind the centre cart: one level lighter in an ellipse.
    for (int x = 0; x < SW; x++) {
      int dx = x - SW / 2, dy = (int)ay - 62;
      int d = dx * dx * 4 / 9 + dy * dy * 3;
      if (d < 3600 && row[x] > CG_PAL_GRAD && (d < 2000 || bayer4[ay & 3][x & 3] > 7))
        row[x]--;
    }
    return;
  }
  unsigned sy = ay - shelf_y;
  if (sy == 0) {
    memset(row, CG_PAL_SHELF_HI, SW);
  } else if (sy < 7) {
    for (unsigned x = 0; x < SW; x++) {
      uint8_t c = CG_PAL_SHELF;
      if (t->wood) {
        // Wood grain: streaks that wobble slowly along the plank.
        unsigned g = hash32((x + (hash32(sy) & 63)) / 9 + sy * 977) & 15;
        if (g < 3)
          c = CG_PAL_SHELF_LO;
        else if (g > 13)
          c = CG_PAL_SHELF_HI;
      } else if (sy >= 5 && bayer4[ay & 3][x & 3] < (sy == 5 ? 6 : 12)) {
        c = CG_PAL_SHELF_LO;
      }
      row[x] = c;
    }
  } else if (sy == 7) {
    memset(row, CG_PAL_SHELF_LO, SW);
  } else {
    // Floor below the shelf: darkest wall colours.
    for (unsigned x = 0; x < SW; x++)
      row[x] = CG_PAL_GRAD + 6 + (bayer4[ay & 3][x & 3] < 10 ? 1 : 0);
  }
}

// Soft contact shadow on the shelf under a cart.
static void shadow(volatile uint8_t *fb, int cx, int w) {
  int hw = w / 2;
  // Solid core right under the cart, dithered fringe around it.
  for (int r = 0; r < 3; r++) {
    int y = CG_FLOOR_Y + 1 + r;
    int ins = r * hw / 6;
    int core = hw * 3 / 4 - r * hw / 4;
    hspan(fb, y, cx - core, cx + core, CG_PAL_SHADOW);
    for (int x = cx - hw + ins; x < cx + hw - ins; x++)
      if ((x < cx - core || x >= cx + core) && ((x + y) & 1) == 0 && x >= 0 && x < SW)
        hspan(fb, y, x, x + 1, CG_PAL_SHADOW);
  }
}

// ---------------------------------------------------------------------------
// Carts

static void draw_cart(volatile uint8_t *fb, const t_cg_cart *c, uint16_t *pal) {
  const t_crt *crt = c->crt;
  const t_crt_pose *p = &crt->poses[c->pose];
  const uint8_t *base = (const uint8_t*)crt;
  const uint8_t *data = base + p->off;
  // Palette into the stage (its slot is fixed per pose).
  for (unsigned i = 0; i < p->ncol; i++)
    pal[p->base + i] = data[2 * i] | (data[2 * i + 1] << 8);
  const uint8_t *spans = data + 2 * p->ncol;
  const uint8_t *px = spans + 2 * p->h;
  int x = c->x - p->ax, y = CG_FLOOR_Y - p->ay;

  shadow(fb, c->x, p->w * 9 / 10);
  blit_pose(fb, x, y, spans, px, p->h, clip_y0, clip_y1);

  // Blank cart: print the game name on the label.
  if (c->blank && c->pose == CG_POSE_F && c->title && crt->label[2] > 16) {
    int lx = x + crt->label[0] + 3, ly = y + crt->label[1] + 2;
    int lw = crt->label[2] - 6, lh = crt->label[3] - 4;
    if (lx >= 0 && lx + lw <= SW && ly >= CG_AREA_Y0 && ly + lh <= CG_FLOOR_Y) {
      const char *t = c->title;
      char lines[3][48];
      unsigned n = 0, maxl = lh / 13;
      if (maxl > 3) maxl = 3;
      while (*t && n < maxl) {
        while (*t == ' ') t++;
        if (!*t) break;
        unsigned ow, cnt;
        if (n == maxl - 1 && font_width(t) > (unsigned)lw) {
          fit_text(t, lines[n++], sizeof(lines[0]), lw);
          break;
        }
        cnt = font_width_cap_space(t, lw, &ow);
        if (!cnt) cnt = font_width_cap(t, lw);
        if (!cnt) break;
        if (cnt > sizeof(lines[0]) - 1) cnt = sizeof(lines[0]) - 1;
        memcpy(lines[n], t, cnt);
        lines[n][cnt] = 0;
        t += cnt;
        n++;
      }
      int ty = ly + (lh - (int)n * 13) / 2 - 1;
      for (unsigned i = 0; i < n; i++)
        text(fb, lines[i], lx + (lw - (int)font_width(lines[i])) / 2, ty + i * 13, 0);
    }
  }
}

void cg_place(t_cg_scene *s, const t_cg_item items[5], int slide) {
  int us[5];
  uint8_t order[5], n = 0;
  for (int k = 0; k < 5; k++) {
    us[k] = (k - 2) * CG_U_ONE + slide;
    if (items[k].crt)
      order[n++] = k;
  }
  // Farthest from the centre first.
  for (int i = 0; i < n; i++)
    for (int j = i + 1; j < n; j++) {
      int ai = us[order[i]] < 0 ? -us[order[i]] : us[order[i]];
      int aj = us[order[j]] < 0 ? -us[order[j]] : us[order[j]];
      if (aj > ai) {
        uint8_t t = order[i]; order[i] = order[j]; order[j] = t;
      }
    }
  s->ncarts = 0;
  for (int i = 0; i < n && s->ncarts < CG_MAX_CARTS; i++) {
    const t_cg_item *it = &items[order[i]];
    t_cg_cart *c = &s->carts[s->ncarts];
    if (!cg_layout(us[order[i]], &c->x, &c->pose))
      continue;
    c->crt = it->crt;
    c->blank = it->blank;
    c->title = it->title;
    s->ncarts++;
  }
}

// ---------------------------------------------------------------------------
// Header pills, title block, footer

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
      text(fb, s->filter_names[i], x + 4, 0, s->theme->light ? CG_BG : CG_FT);
    x += w;
  }
}

static void text_shadowed(volatile uint8_t *fb, const char *t, int x, int y) {
  text(fb, t, x + 1, y + 1, CG_PAL_TEXTSH);
  text(fb, t, x, y, CG_PAL_TEXT);
}

static void draw_titles(volatile uint8_t *fb, const t_cg_scene *s) {
  char tmp[96];
  if (s->name) {
    unsigned w = fit_text(s->name, tmp, sizeof(tmp), 226);
    text_shadowed(fb, tmp, SW / 2 - (int)w / 2, CG_FLOOR_Y + 9);
  }
  // Metadata pieces separated by small dots.
  unsigned n = 0, tw = 0, ws[3];
  const char *parts[3];
  for (unsigned i = 0; i < 3; i++)
    if (s->meta[i] && s->meta[i][0]) {
      parts[n] = s->meta[i];
      ws[n] = font_width(parts[n]);
      tw += ws[n] + (n ? 11 : 0);
      n++;
    }
  if (n && tw <= 230) {
    int x = SW / 2 - (int)tw / 2, y = CG_FLOOR_Y + 23;
    for (unsigned i = 0; i < n; i++) {
      if (i) {
        clip_y0 = 0; clip_y1 = 160;
        hspan(fb, y + 8, x + 4, x + 6, CG_PAL_META);
        hspan(fb, y + 9, x + 4, x + 6, CG_PAL_META);
        x += 11;
      }
      text(fb, parts[i], x, y, CG_PAL_META);
      x += ws[i];
    }
  }
  if (s->message) {
    unsigned w = fit_text(s->message, tmp, sizeof(tmp), 220);
    text_shadowed(fb, tmp, SW / 2 - (int)w / 2, 54);
  }
}

static void draw_footer(volatile uint8_t *fb, const t_cg_scene *s) {
  clip_y0 = CG_AREA_Y1; clip_y1 = 160;
  for (int y = CG_AREA_Y1; y < 160; y++)
    hspan(fb, y, 0, SW, CG_FG);

  int left = 4, right = SW - 4;
  char tmp[64];
  const uint8_t ink = s->theme->light ? CG_BG : CG_FT;
  if (s->counter && s->counter[0]) {
    unsigned w = font_width(s->counter);
    text(fb, s->counter, right - w, CG_AREA_Y1, ink);
    right -= w + 8;
  }
  if (s->user && s->user[0]) {
    unsigned w = fit_text(s->user, tmp, sizeof(tmp), 70);
    text(fb, tmp, left, CG_AREA_Y1, ink);
    left += w + 10;
  }
  if (s->path && s->path[0] && !(s->path[0] == '/' && !s->path[1]) && right - left > 20) {
    unsigned maxw = right - left;
    unsigned skip = font_width_lcap(s->path, maxw - DOTS_W);
    if (skip && font_width(s->path) > maxw) {
      text(fb, "...", left, CG_AREA_Y1, ink);
      text(fb, &s->path[skip], left + DOTS_W, CG_AREA_Y1, ink);
    } else
      text(fb, s->path, left, CG_AREA_Y1, ink);
  }
}

void cg_render_scene(volatile uint8_t *fb, const t_cg_scene *s) {
  clip_y0 = CG_AREA_Y0; clip_y1 = CG_AREA_Y1;
  for (unsigned r = 0; r < CG_AREA_H; r++)
    CG_COPY16(&fb[(CG_AREA_Y0 + r) * SW], &s->bgtex[r * SW], SW / 2);

  for (unsigned i = 0; i < s->ncarts && i < CG_MAX_CARTS; i++)
    draw_cart(fb, &s->carts[i], s->pal);

  clip_y0 = 0; clip_y1 = 160;
  draw_titles(fb, s);
  draw_header(fb, s);
  draw_footer(fb, s);
  clip_y0 = CG_AREA_Y0; clip_y1 = CG_AREA_Y1;
}

#endif  // USE_CAROUSEL
