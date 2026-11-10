/*
 * Cartridge carousel ("slot."-style ROM browser) -- drawing primitives.
 *
 * Inspired by slot. (https://github.com/slot-cfw/slot) and its EZ-Flash Omega
 * port slot. advance; all artwork here (cart shapes, wood grain, layout) is
 * drawn procedurally by this file, nothing is copied from those projects.
 *
 * This module only draws into an 8bpp (Mode 4) 240x160 framebuffer and has no
 * hardware dependencies other than the copy helper below, so it can also be
 * compiled on a PC to render preview screenshots (see tools/carousel/).
 *
 * All colors used here come from the 6x6x6 color cube that coverart.c keeps in
 * MEM_PALETTE[20..235] (plus the 4 theme colors 16..19), so the carousel needs
 * no extra palette entries.
 *
 * Copyright (C) 2026 Retroid. GPL-3.0-or-later (same license as SuperFW).
 */
#ifndef __CAROUSEL_GFX_H__
#define __CAROUSEL_GFX_H__

#include <stdint.h>
#include <stdbool.h>

// The carousel is built where flash allows it (lite + chis). The SD build has
// no room left in its 512KB budget, it keeps the classic list browser.
#if defined(SUPERCARD_LITE_IO) || defined(SUPPORT_NORGAMES) || defined(CAROUSEL_HOST)
  #define USE_CAROUSEL
#endif

// Label art: same format as the cover-art thumbnails (120x80, cube indices).
#define CG_LABEL_W       120
#define CG_LABEL_H        80

// Main carousel area (between the tab bar and the footer).
#define CG_AREA_Y0        16
#define CG_AREA_Y1       144
#define CG_AREA_H        (CG_AREA_Y1 - CG_AREA_Y0)

// Theme palette indices (shared with menu.c).
#define CG_FG             16
#define CG_BG             17
#define CG_FT             18
#define CG_HI             19

// Index into the 6x6x6 cube (each component 0..5).
#define CG_CUBE(r, g, b)  (20 + (r) * 36 + (g) * 6 + (b))
#define CG_WHITE          CG_CUBE(5, 5, 5)
#define CG_LGRAY          CG_CUBE(4, 4, 4)

enum {
  CG_CART_GBA = 0,
  CG_CART_GB,
  CG_CART_GBC,
  CG_CART_OTHER,     // Other emulated systems (NES, SMS...): GBA-shaped, gray label
  CG_CART_FOLDER,
};

enum {
  CG_BG_SOLID = 0,   // Theme background color
  CG_BG_WOOD  = 1,   // Wood grain texture (pre-rendered rows)
};

typedef struct {
  int16_t x100;               // Cart position: 0 = center, +/-100 = neighbour slot
  uint8_t type;               // CG_CART_*
  const uint8_t *label;       // 120x80 label art (cube indices) or NULL = generic
  const char *title;          // Text for generic labels / folders
} t_cg_cart;

#define CG_MAX_CARTS  7

typedef struct {
  uint8_t bgstyle;            // CG_BG_*
  const uint8_t *woodtex;     // CG_AREA_H rows of 240 px (only for CG_BG_WOOD)
  uint8_t ncarts;
  t_cg_cart carts[CG_MAX_CARTS];
  const char *name;           // Shown under the selected cart (NULL = none)
  const char *message;        // Centered message when the list is empty
  // Header (system selector "pills", drawn right-aligned in the tab bar)
  uint8_t nfilters, filter;
  const char *const *filter_names;
  unsigned header_minx;       // Leftmost x the pills may use (after tab icons)
  // Footer
  const char *user;           // User name (may be NULL/empty)
  const char *path;           // Current folder (NULL or "/" = root, hidden)
  const char *counter;        // "3/42"
  const char *clock;          // NULL = no clock (cart has no RTC)
} t_cg_scene;

// Renders one row of the wood texture (240 px). `y` is the row inside the
// carousel area (0..CG_AREA_H-1).
void cg_wood_row(uint8_t *row, unsigned y);

// Draws the whole carousel (background, carts, name, header pills, footer).
// Rows 0..15 (tab bar) are expected to be pre-filled with CG_FG.
void cg_render_scene(volatile uint8_t *frame, const t_cg_scene *s);

#endif
