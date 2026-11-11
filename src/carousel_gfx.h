/*
 * Cartridge carousel ("slot."-style ROM browser) v2 -- drawing.
 *
 * The cartridges are rendered in 3D on a PC beforehand (tools/library/, with
 * the real label of every game) and stored on the SD card as .CRT files. Each
 * .CRT holds 5 poses (front, half-turned and side views, left and right) that
 * are already in the GBA's own format: 8-bit pixels into a fixed palette slot
 * per pose, one opaque span per row, and a 15-bit palette. This module only
 * places them, cover-flow style, on a shaded background.
 *
 * Palette use (Mode 4, double buffered; the palette is staged and swapped in
 * at V-blank together with the frame flip, see menu_flip):
 *   1..8   background gradient     9..11 shelf      12 cart shadow
 *   13     title text   14 text shadow   15 metadata text
 *   16..19 menu theme colours (unchanged)
 *   20..111 front pose (92)   112..143 / 144..175 half-turned left/right (32)
 *   176..207 / 208..239 side left/right (32)
 *
 * Inspired by slot. / slot. advance (GPL-3.0). All artwork is our own.
 * Copyright (C) 2026 Retroid. GPL-3.0-or-later (same license as SuperFW).
 */
#ifndef __CAROUSEL_GFX_H__
#define __CAROUSEL_GFX_H__

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

// Only the chis build has the flash (blank carts) and room for this.
#if defined(SUPPORT_NORGAMES) || defined(CAROUSEL_HOST)
  #define USE_CAROUSEL
#endif

#define CG_AREA_Y0        16
#define CG_AREA_Y1       144
#define CG_AREA_H        (CG_AREA_Y1 - CG_AREA_Y0)
#define CG_FLOOR_Y       104      // Carts stand on the shelf here

// Theme palette indices (shared with menu.c).
#define CG_FG             16
#define CG_BG             17
#define CG_FT             18
#define CG_HI             19

// Own palette entries (see above).
#define CG_PAL_GRAD        1      // 8 entries
#define CG_PAL_SHELF_HI    9
#define CG_PAL_SHELF      10
#define CG_PAL_SHELF_LO   11
#define CG_PAL_SHADOW     12
#define CG_PAL_TEXT       13
#define CG_PAL_TEXTSH     14
#define CG_PAL_META       15

// --- .CRT file (see tools/library/pack.py) ---------------------------------
enum { CG_POSE_F = 0, CG_POSE_ML, CG_POSE_MR, CG_POSE_L, CG_POSE_R, CG_POSE_CNT };
#define CG_POSE_Z     5           // Optional 6th pose: zoomed front (NES)

enum { CG_SYS_GBA = 0, CG_SYS_GB = 1, CG_SYS_GBC = 2 };

typedef struct {
  uint32_t off, size;              // Pose data offset (from file start) + size
  uint8_t w, h;                    // Image size
  uint8_t ax, ay;                  // Anchor (cart bottom centre) in the image
  uint8_t ncol, base;              // Palette size + first palette index
  uint16_t pad;
} t_crt_pose;

typedef struct {
  char magic[4];                   // "RCRT"
  uint8_t version, system, npose, flags;
  char title[48];
  char year[8];
  char publisher[32];
  char players[8];
  char genre[24];
  uint8_t label[4];                // Label rect in the front pose (x, y, w, h)
  uint32_t card_off, card_size;    // Info-card block (0 = none, older files)
  uint8_t pad[4];
  t_crt_pose poses[CG_POSE_Z + 1];  // 5 poses + an optional 6th (CG_POSE_Z)
} t_crt;

// Info card: the label large, pre-scaled, own palette (base..base+ncol-1).
typedef struct {
  char magic[4];                   // "CARD"
  uint8_t w, h, ncol, base;
  uint8_t layout, pad;             // layout 0 = label left, 1 = label on top
  uint16_t synlen;                 // Synopsis length (text after the pixels)
  char region[12];
  // uint16_t pal[ncol]; uint8_t px[w*h]; char synopsis[synlen];
} t_crt_card;

_Static_assert(sizeof(t_crt_card) == 24, "t_crt_card layout");

_Static_assert(offsetof(t_crt, poses) == 0x90, "t_crt layout");

// --- Scene -------------------------------------------------------------------
typedef struct {
  const t_crt *crt;                // Rendered cart (game or blank)
  int16_t x;                       // Screen x of the cart's bottom centre
  uint8_t pose;                    // CG_POSE_*
  bool blank;                      // Blank cart: draw `title` on the label
  int8_t yoff;                     // Extra vertical offset (zoom transition)
  const char *title;
} t_cg_cart;

#define CG_MAX_CARTS  6

// Colours of a carousel theme (RGB888).
typedef struct {
  uint32_t top, bottom;            // Wall gradient
  uint32_t shelf, shelf_hi, shelf_lo;
  uint32_t text, textsh, meta;
  bool wood;                       // Wood grain in the shelf
  bool light;                      // Light theme (footer/pill text uses CG_BG)
} t_cg_theme;

// One carousel theme per menu theme (Red/Dark, Red/White, Wood, Dark, Light).
#define CG_THEME_CNT  5
extern const t_cg_theme cg_themes[CG_THEME_CNT];

typedef struct {
  const t_cg_theme *theme;
  const uint8_t *bgtex;            // CG_AREA_H rows x 240 px (cg_bg_row)
  uint16_t *pal;                   // Palette stage (256 entries), filled here
  uint8_t ncarts;
  t_cg_cart carts[CG_MAX_CARTS];   // Drawn in this order (far ones first)
  const char *name;                // Title under the shelf
  const char *meta[3];             // Year / publisher / players (may be NULL)
  const char *message;             // Shown when the list is empty
  // Header: system "pills" right-aligned in the tab bar.
  uint8_t nfilters, filter;
  const char *const *filter_names;
  unsigned header_minx;
  // Footer.
  const char *user, *path, *counter;
} t_cg_scene;

// Cover-flow layout: screen x and pose for a cart `u` steps away from the
// centre (u in 1/256 cart units, may be fractional during animations).
// Returns false when the cart is off screen.
#define CG_U_ONE      256
bool cg_layout(int u, int16_t *x, uint8_t *pose);

// One list entry around the selection.
typedef struct {
  const t_crt *crt;                // NULL = no entry at this offset
  bool blank;
  const char *title;
} t_cg_item;

// Places the entries at offsets -2..+2 (items[0..4]) with the given slide
// (1/256 cart units) into s->carts, back to front.
void cg_place(t_cg_scene *s, const t_cg_item items[5], int slide);

// Info card of one game (label large + details + synopsis). `scroll` is the
// first text line shown; returns the total number of text lines.
int cg_render_card(volatile uint8_t *frame, const t_cg_scene *s, const t_crt *crt,
                   const char *title, int scroll);

// Fills palette entries 1..15 for a theme.
void cg_theme_palette(const t_cg_theme *t, uint16_t *pal);
// One background row (240 px) for y = 0..CG_AREA_H-1 inside the carousel area.
void cg_bg_row(const t_cg_theme *t, uint8_t *row, unsigned y);
// Draws the whole carousel area + header pills + footer, stages the palette.
void cg_render_scene(volatile uint8_t *frame, const t_cg_scene *s);

#endif
