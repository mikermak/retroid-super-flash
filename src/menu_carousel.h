/*
 * Cartridge carousel ROM browser ("slot."-style skin) v2 -- menu logic.
 *
 * Included once from menu.c (it needs menu.c's static state). Replaces the
 * SD-card file list on the ROM browser tab when "Browser view" is set to
 * "Carousel"; all other tabs stay as they are. Drawing: carousel_gfx.c.
 *
 * Every game is shown as a cartridge rendered in 3D on a PC with its real
 * label (tools/library/maak_bibliotheek.py writes /LIBRARY/ on the SD card):
 *   GBA:     /LIBRARY/<c>/<GAMECODE>.CRT        (game code from the header)
 *   GB/GBC:  /LIBRARY/G<h>/<HASH>.CRT           (FNV-1a of header 0x134..0x14F)
 *   else:    /LIBRARY/N/<rom file name>.CRT   (also all NES games)
 * Games without one get a blank 3D cart (built into the firmware) with the
 * name printed on the label.
 *
 *  - Left/Right: previous/next cart (hold = fast scroll)
 *  - L/R: system filter All / GBA / GB / GBC / NES (empty ones skipped); past
 *    the ends L/R go to the previous/next tab like before.
 *  - A: start the game (or open a folder)
 *  - B: one folder up; in the root folder: start options of the game
 *  - Up: info card (label large, details, synopsis). There: A play, B back,
 *    Up/Down scroll, Select start options (GBA load pop-up)
 *  - Select: file manager (delete / hide / write to NOR)
 *  - Start: UI settings tab (B or Start there brings you back)
 *
 * Memory: the .CRT files are cached in the SDRAM scratch area (2 MiB, only
 * used by firmware updates / NOR writes, after which the cache is dropped);
 * the background is pre-rendered into SDRAM; EWRAM only holds the code.
 *
 * Copyright (C) 2026 Retroid. GPL-3.0-or-later (same license as SuperFW).
 */

#ifdef USE_CAROUSEL

#define CAR_HOLD_DELAY   16      // Frames before auto-repeat kicks in
#define CAR_SETTLE        3      // Frames without movement before loading
#define CAR_ABS(x)       ((x) < 0 ? -(x) : (x))
#define CAR_SLOT_SIZE    (64 * 1024)
#define CAR_ZOOM_WAIT    12      // Frames standing still before zooming in (NES)
#define CAR_SLOTS        (scratch_mem_size / CAR_SLOT_SIZE)
#define CAR_LIB_DIR      "/LIBRARY"

enum { CarAll = 0, CarGBA, CarGB, CarGBC, CarNES, CarFiltCNT };
static const char *const car_filter_names[CarFiltCNT] = { "All", "GBA", "GB", "GBC", "NES" };

// Kinds of list entries.
enum { CarGba = 0, CarGb, CarGbc, CarFolder, CarOther, CarNes };

// Functions defined further down in menu.c.
static void browser_open(const char *fn, uint32_t fs);
static void browser_open_gba(const char *fn, uint32_t fs, bool prompt_patchgen);
static void browser_reload();
static void keypress_popup_loadgba(unsigned newkeys);
const t_emu_loader * get_emu_info(const char *ext);
const void *get_vfile_ptr(const char *fname);
int movedir_up();

static uint16_t car_pal[256];     // Palette stage, copied at V-blank (menu_flip)
static bool car_pal_dirty;

static struct {
  uint8_t filter;           // CarAll..CarGBC
  bool built;               // carlist is valid for (filter, gen)
  bool fading;              // the blend registers are in "fade" mode
  bool via_start;           // UI settings were opened with Start (B returns)
  bool card;                // Info card open
  int card_scroll, card_lines;
  int zoom;                 // Zoom-in progress of the centre cart (0..256)
  int8_t libdir;            // /LIBRARY exists (-1 = not checked yet)
  int8_t bg_theme;          // Theme the background texture was made for
  unsigned gen;             // browser_gen the list was built for
  int count, pos;           // entries in carlist, selected position
  int slide;                // animation offset (CG_U_ONE = one cart)
  unsigned hold, repacc;    // Left/Right auto-repeat
  unsigned settle;          // frames since the last move
  int fade;                 // fade-in level (16 = black, 0 = done)
  unsigned lastkeys;        // key state seen on the previous frame
  const t_crt *blank[5];    // Blank carts (GBA, GB, GBC, folder, NES), from flash
  struct {
    uint16_t idx;           // fileorder index
    uint16_t pos;           // carlist position when loaded (eviction hint)
    unsigned gen;           // browser_gen it belongs to
    uint8_t state;          // 0 = empty, 1 = loaded, 2 = no .CRT for this game
  } lc[CAR_SLOTS];
  char user[12];            // From /USERNAME.TXT (max 10 chars)
} car;

static bool carousel_on(void) {
  return browser_view != 0 && car.blank[0];
}

static int car_type(const t_centry *e) {
  if (e->isdir)
    return CarFolder;
  const char *ext = find_extension(e->fname);
  if (!ext)
    return -1;
  if (!strcasecmp(ext, ".gba"))
    return CarGba;
  if (!strcasecmp(ext, ".gb"))
    return CarGb;
  if (!strcasecmp(ext, ".gbc"))
    return CarGbc;
  if (!strcasecmp(ext, ".nes"))
    return CarNes;          // Started with PocketNES, like in the list
  if (get_emu_info(&ext[1]) || !strcasecmp(ext, ".fw"))
    return CarOther;        // Other emulated systems + firmware updates ("All")
  return -1;                // .sav, .txt ... only in the list view
}

static bool car_match(int type, unsigned filter) {
  if (type < 0)
    return false;
  if (type == CarFolder || filter == CarAll)
    return true;
  return (filter == CarGBA && type == CarGba) ||
         (filter == CarGB  && type == CarGb)  ||
         (filter == CarGBC && type == CarGbc) ||
         (filter == CarNES && type == CarNes);
}

static const t_crt *car_blank_for(int type) {
  switch (type) {
  case CarGb:     return car.blank[1];
  case CarGbc:    return car.blank[2];
  case CarFolder: return car.blank[3] ? car.blank[3] : car.blank[0];
  case CarNes:    return car.blank[4] ? car.blank[4] : car.blank[0];
  default:        return car.blank[0];
  }
}

// Keeps the list-browser selection in sync (so popups and the list view work).
static void car_sync(void) {
  if (car.count) {
    smenu.browser.selector = sdr_state->carlist[car.pos];
    smenu.browser.seloff = MAX(0, smenu.browser.selector - BROWSER_ROWS / 2);
  }
  car.settle = 0;
  smenu.anim_state = 0;
}

static void car_rebuild(void) {
  int cnt = 0, newpos = -1;
  int cursel = smenu.browser.selector;
  for (int i = 0; i < smenu.browser.dispentries; i++) {
    if (!car_match(car_type(sdr_state->fileorder[i]), car.filter))
      continue;
    if (newpos < 0 && i >= cursel)
      newpos = cnt;
    sdr_state->carlist[cnt++] = i;
  }
  car.count = cnt;
  car.pos = newpos >= 0 ? newpos : (cnt ? cnt - 1 : 0);
  car.gen = browser_gen;
  car.built = true;
  car_sync();
}

static void car_ensure(void) {
  // Rebuild when the file list changed, or the list view moved the cursor.
  if (!car.built || car.gen != browser_gen ||
      (car.count && sdr_state->carlist[car.pos] != smenu.browser.selector))
    car_rebuild();
}

static void car_move(int d) {
  int np = MAX(0, MIN(car.count - 1, car.pos + d));
  if (np == car.pos)
    return;
  car.slide += (np - car.pos) * CG_U_ONE;
  car.slide = MAX(-2 * CG_U_ONE, MIN(2 * CG_U_ONE, car.slide));
  car.pos = np;
  car_sync();
}

// Whether the current folder has any game for a system filter (All: always).
static bool car_filter_has(unsigned filter) {
  if (filter == CarAll)
    return true;
  for (int i = 0; i < smenu.browser.dispentries; i++) {
    int t = car_type(sdr_state->fileorder[i]);
    if (t != CarFolder && car_match(t, filter))
      return true;
  }
  return false;
}

// L/R: switch system (skipping systems without games in this folder).
// Returns false at the ends, then L/R switch tabs as usual.
static bool car_switch_filter(int d) {
  int nf = (int)car.filter + d;
  while (nf > CarAll && nf < CarFiltCNT && !car_filter_has(nf))
    nf += d;
  if (nf < 0 || nf >= CarFiltCNT)
    return false;
  car.filter = nf;
  car.built = false;
  car.slide = d * 2 * CG_U_ONE;     // New row slides in from that side
  return true;
}

// Called when the browser tab is entered via L (from the right) or R.
static void car_enter_tab(bool from_right) {
  car.filter = CarAll;
  if (from_right)
    for (int f = CarFiltCNT - 1; f > CarAll; f--)
      if (car_filter_has(f)) {
        car.filter = f;
        break;
      }
  car.built = false;
}

static void car_fade_stop(void) {
  if (car.fading) {
    REG_BLDCNT = 0x1F40;    // Back to the menu's alpha blending setup
    REG_BLDALPHA = 0x0808;
    REG_BLDY = 0;
    car.fading = false;
  }
  car.fade = 0;
}

static void car_wait_vblank(void) {
  while (REG_VCOUNT >= 160);
  while (REG_VCOUNT < 160);
}

// Fade to black before starting a game (blocking, ~9 frames).
static void car_fade_out(void) {
  REG_BLDCNT = 0x00FF;      // Brightness decrease on everything
  for (unsigned l = 0; l <= 16; l += 2) {
    REG_BLDY = l;
    car_wait_vblank();
  }
  // Blank the visible screen, so restoring the blend does not flash the menu.
  dma_memset16(&MEM_VRAM_U8[0xA000 * (framen ^ 1)], dup8(BG_COLOR), SCREEN_WIDTH * SCREEN_HEIGHT / 2);
  dma_memset16(MEM_OAM, 0, 256);
  car.fading = true;
  car_fade_stop();
  car.fade = 16;            // If we come back (error, pop-up), fade back in.
}

// The SDRAM scratch area was used for something else: drop the cache.
static void car_cache_drop(void) {
  for (unsigned i = 0; i < CAR_SLOTS; i++)
    car.lc[i].state = 0;
}

static void car_load_user(void) {
  car.user[0] = 0;
  FIL fd;
  if (FR_OK != f_open(&fd, "/USERNAME.TXT", FA_READ))
    return;
  char buf[32];
  UINT rd = 0;
  if (FR_OK == f_read(&fd, buf, sizeof(buf) - 1, &rd)) {
    unsigned o = 0, i = 0;
    if (rd >= 3 && (uint8_t)buf[0] == 0xEF && (uint8_t)buf[1] == 0xBB && (uint8_t)buf[2] == 0xBF)
      i = 3;                // Skip an UTF-8 BOM (Notepad)
    for (; i < rd && o < 10; i++) {
      if (buf[i] == '\r' || buf[i] == '\n')
        break;
      if ((uint8_t)buf[i] >= 0x20 && (uint8_t)buf[i] < 0x7F)
        car.user[o++] = buf[i];
    }
    car.user[o] = 0;
  }
  f_close(&fd);
}

static void car_init(void) {
  car_load_user();
  car.built = false;
  car.libdir = -1;
  car.bg_theme = -1;
  car.fade = 16;            // Fade in the first time the carousel shows up
  car_cache_drop();

  // Blank carts live in the firmware ("CART" asset, aplib compressed). The
  // asset area is only visible with the SD interface unmapped, so unpack
  // them into our own SDRAM buffer once.
  const uint8_t *b = sdr_state->blanks;
  set_supercard_mode(MAPPED_SDRAM, true, false);
  const uint8_t *packed = get_vfile_ptr("CART");
  unsigned unpacked = packed ? apunpack16(packed, sdr_state->blanks) : 0;
  set_supercard_mode(MAPPED_SDRAM, true, true);
  if (unpacked > 16 && unpacked <= sizeof(sdr_state->blanks) && !memcmp(b, "RCRB", 4)) {
    uint32_t n = *(const uint32_t*)&b[4];
    for (unsigned i = 0; i < n && i < 5; i++) {
      const t_crt *c = (const t_crt*)&b[*(const uint32_t*)&b[8 + 4 * i]];
      if (!memcmp(c->magic, "RCRT", 4))
        car.blank[i] = c;
    }
  }
}

// ---------------------------------------------------------------------------
// Library (.CRT) cache

static uint8_t *car_slot_ptr(unsigned i) {
  return &sdr_state->scratch[i * CAR_SLOT_SIZE];
}

static int car_cache_find(unsigned idx) {
  for (unsigned i = 0; i < CAR_SLOTS; i++)
    if (car.lc[i].state && car.lc[i].idx == idx && car.lc[i].gen == browser_gen)
      return i;
  return -1;
}

static uint32_t car_fnv(const uint8_t *p, unsigned n) {
  uint32_t h = 0x811C9DC5;
  while (n--)
    h = (h ^ *p++) * 0x01000193;
  return h;
}

// Path of the key-based .CRT for a ROM (false if there is none).
static bool car_key_path(const char *rompath, uint32_t fs, int type, char *out, unsigned outsz) {
  if (type == CarGba) {
    t_rom_header romh;
    if (preload_gba_rom(rompath, fs, &romh))
      return false;
    for (unsigned i = 0; i < 4; i++) {
      uint8_t ch = romh.gcode[i];
      if (!((ch >= '0' && ch <= '9') || (ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z')))
        return false;
    }
    char c[5];
    for (unsigned i = 0; i < 4; i++)
      c[i] = (romh.gcode[i] >= 'a' && romh.gcode[i] <= 'z') ? romh.gcode[i] - 32 : romh.gcode[i];
    c[4] = 0;
    npf_snprintf(out, outsz, CAR_LIB_DIR "/%c/%s.CRT", c[0], c);
    return true;
  }
  if (type == CarGb || type == CarGbc) {
    FIL fd;
    if (FR_OK != f_open(&fd, rompath, FA_READ))
      return false;
    uint8_t hdr[0x150 - 0x134];
    UINT rd = 0;
    bool ok = FR_OK == f_lseek(&fd, 0x134) && FR_OK == f_read(&fd, hdr, sizeof(hdr), &rd) && rd == sizeof(hdr);
    f_close(&fd);
    if (!ok)
      return false;
    uint32_t h = car_fnv(hdr, sizeof(hdr));
    npf_snprintf(out, outsz, CAR_LIB_DIR "/G%lX/%08lX.CRT", (unsigned long)(h >> 28), (unsigned long)h);
    return true;
  }
  return false;
}

// Reads a .CRT into an SDRAM slot (16-bit writes only) and checks it.
static bool car_read_crt(const char *path, uint8_t *dst) {
  FIL fd;
  if (FR_OK != f_open(&fd, path, FA_READ))
    return false;
  uint32_t size = f_size(&fd);
  bool ok = size >= sizeof(t_crt) && size <= CAR_SLOT_SIZE;
  uint32_t done = 0;
  while (ok && done < size) {
    uint32_t buf[256];
    UINT rd = 0;
    unsigned chunk = MIN(sizeof(buf), size - done);
    if (FR_OK != f_read(&fd, buf, chunk, &rd) || rd != chunk)
      ok = false;
    else {
      dma_memcpy16(&dst[done], buf, (chunk + 1) / 2);
      done += chunk;
    }
  }
  f_close(&fd);
  if (!ok)
    return false;
  const t_crt *c = (const t_crt*)dst;
  if (memcmp(c->magic, "RCRT", 4) || c->version != 1 || c->npose < CG_POSE_CNT || c->npose > CG_POSE_Z + 1)
    return false;
  if (c->card_off) {
    const t_crt_card *cd = (const t_crt_card*)&dst[c->card_off];
    if (c->card_off + c->card_size > size || (c->card_off & 3) || memcmp(cd->magic, "CARD", 4) ||
        sizeof(t_crt_card) + 2u * cd->ncol + (unsigned)cd->w * cd->h + cd->synlen > c->card_size ||
        cd->base < 20 || cd->base + cd->ncol > 240 || cd->w > 232 || cd->h > 140)
      return false;
  }
  for (unsigned i = 0; i < c->npose; i++) {
    const t_crt_pose *p = &c->poses[i];
    if (p->off + p->size > size || p->ncol > 92 || p->base < 20 || p->base + p->ncol > 240 ||
        2u * p->ncol + 2u * p->h > p->size)
      return false;
  }
  return true;
}

static void car_cache_load(int lpos) {
  unsigned idx = sdr_state->carlist[lpos];
  const t_centry *e = sdr_state->fileorder[idx];
  int type = car_type(e);

  // Victim: an empty/stale slot, else the one farthest away from the cursor.
  int v = 0, best = -1;
  for (unsigned i = 0; i < CAR_SLOTS; i++) {
    int score = (!car.lc[i].state || car.lc[i].gen != browser_gen) ? 0x7FFF :
                CAR_ABS((int)car.lc[i].pos - car.pos);
    if (score > best) {
      best = score;
      v = i;
    }
  }

  bool ok = false;
  if (car.libdir < 0) {
    FILINFO info;
    car.libdir = (FR_OK == f_stat(CAR_LIB_DIR, &info) && (info.fattrib & AM_DIR)) ? 1 : 0;
  }
  if (car.libdir) {
    char rompath[MAX_FN_LEN * 2], path[MAX_FN_LEN + 32];
    npf_snprintf(rompath, sizeof(rompath), "%s%s", smenu.browser.cpath, e->fname);
    if (car_key_path(rompath, e->filesize, type, path, sizeof(path)))
      ok = car_read_crt(path, car_slot_ptr(v));
    if (!ok) {
      // Fallback: by file name (No-Intro style names, made with --testset).
      npf_snprintf(path, sizeof(path), CAR_LIB_DIR "/N/%s", e->fname);
      char *dot = strrchr(path, '.');
      if (dot && dot > &path[sizeof(CAR_LIB_DIR) + 2])
        *dot = 0;
      if (strlen(path) + 5 < sizeof(path)) {
        strcat(path, ".CRT");
        ok = car_read_crt(path, car_slot_ptr(v));
      }
    }
  }

  car.lc[v].idx = idx;
  car.lc[v].pos = lpos;
  car.lc[v].gen = browser_gen;
  car.lc[v].state = ok ? 1 : 2;
}

// Loads (at most) one missing game per frame: centre first, then neighbours.
static void car_cache_step(void) {
  static const int8_t order[5] = { 0, 1, -1, 2, -2 };
  for (unsigned i = 0; i < 5; i++) {
    int lp = car.pos + order[i];
    if (lp < 0 || lp >= car.count)
      continue;
    unsigned idx = sdr_state->carlist[lp];
    int type = car_type(sdr_state->fileorder[idx]);
    if (type == CarFolder || type == CarOther)
      continue;             // Always shown as blank carts
    if (car_cache_find(idx) < 0) {
      car_cache_load(lp);
      return;
    }
  }
}

// ---------------------------------------------------------------------------
// Rendering

static void car_title(const t_centry *e, char *out, unsigned outsz) {
  strncpy(out, e->fname, outsz - 1);
  out[outsz - 1] = 0;
  if (!e->isdir) {
    char *dot = strrchr(out, '.');
    if (dot && dot != out)
      *dot = 0;
  }
}

static void render_carousel(volatile uint8_t *frame, unsigned fcnt) {
  car_ensure();

  const unsigned th = menu_theme < CG_THEME_CNT ? menu_theme : 0;
  const t_cg_theme *theme = &cg_themes[th];
  if (car.bg_theme != (int)th) {
    uint8_t row[SCREEN_WIDTH] __attribute__((aligned(4)));
    for (unsigned y = 0; y < CG_AREA_H; y++) {
      cg_bg_row(theme, row, y);
      dma_memcpy16(&sdr_state->bgtex[y * SCREEN_WIDTH], row, SCREEN_WIDTH / 2);
    }
    car.bg_theme = th;
  }

  // Hold Left/Right to scroll fast.
  unsigned keys = (~REG_KEYINPUT) & 0x3FF;
  bool lr = (keys & (KEY_BUTTLEFT | KEY_BUTTRIGHT)) && !spop.alert_msg;
  if (lr && car.count) {
    car.hold += fcnt;
    if (car.hold > CAR_HOLD_DELAY) {
      unsigned period = car.hold > 80 ? 3 : 6;
      car.repacc += fcnt;
      while (car.repacc >= period) {
        car.repacc -= period;
        car_move((keys & KEY_BUTTRIGHT) ? 1 : -1);
      }
    }
  } else {
    car.hold = 0;
    car.repacc = 0;
  }

  // Slide animation (ease out over ~8 frames).
  for (unsigned i = 0; i < fcnt && car.slide; i++) {
    int step = car.slide / 4;
    if (CAR_ABS(step) < 8)
      step = car.slide < 0 ? -MIN(8, -car.slide) : MIN(8, car.slide);
    car.slide -= step;
  }
  car.settle += fcnt;

  // Fade in.
  if (car.fade > 0) {
    REG_BLDCNT = 0x00FF;
    REG_BLDY = car.fade;
    car.fading = true;
    car.fade -= 2 * fcnt;
    if (car.fade <= 0)
      car_fade_stop();
  }

  // Load cartridges once the cursor stopped moving.
  if (car.settle >= CAR_SETTLE && car.count && !car.hold)
    car_cache_step();

  // Build the scene.
  t_cg_scene s;
  memset(&s, 0, sizeof(s));
  char titles[5][96];
  char counter[24], players[16];
  t_cg_item items[5];
  memset(items, 0, sizeof(items));

  s.theme = theme;
  s.bgtex = sdr_state->bgtex;
  s.pal = car_pal;
  s.nfilters = CarFiltCNT;
  s.filter = car.filter;
  s.filter_names = car_filter_names;
  int mintab = (recent_menu && smenu.recent.maxentries) ? MENUTAB_RECENT : MENUTAB_ROMBROWSE;
  s.header_minx = (MENUTAB_MAX - mintab) * 16 + 2;
  s.user = car.user;
  s.path = smenu.browser.cpath;
  cg_theme_palette(theme, car_pal);

  if (!car.count) {
    s.message = msgs[lang_id][MSG_BROW_EMPTY];
    npf_snprintf(counter, sizeof(counter), "0/0");
  } else {
    npf_snprintf(counter, sizeof(counter), "%d/%d", car.pos + 1, car.count);
    for (int k = -2; k <= 2; k++) {
      int lp = car.pos + k;
      if (lp < 0 || lp >= car.count)
        continue;
      unsigned idx = sdr_state->carlist[lp];
      const t_centry *e = sdr_state->fileorder[idx];
      t_cg_item *it = &items[k + 2];
      int ci = car_cache_find(idx);
      if (ci >= 0 && car.lc[ci].state == 1) {
        it->crt = (const t_crt*)car_slot_ptr(ci);
        it->blank = false;
        strncpy(titles[k + 2], it->crt->title[0] ? it->crt->title : e->fname, sizeof(titles[0]) - 1);
        titles[k + 2][sizeof(titles[0]) - 1] = 0;
      } else {
        it->crt = car_blank_for(car_type(e));
        it->blank = true;
        car_title(e, titles[k + 2], sizeof(titles[0]));
      }
      it->title = titles[k + 2];
    }
    cg_place(&s, items, car.slide);

    // NES: once the cart stands still, zoom in on its label (6th pose).
    const t_crt *cc = items[2].crt;
    bool can_zoom = cc && !items[2].blank && cc->npose > CG_POSE_Z && !car.slide && !car.hold &&
                    car.settle >= CAR_ZOOM_WAIT;
    car.zoom = can_zoom ? MIN(256, car.zoom + 40 * (int)fcnt) : 0;
    if (car.zoom)
      for (unsigned i = 0; i < s.ncarts; i++)
        if (s.carts[i].crt == cc && s.carts[i].pose == CG_POSE_F) {
          s.carts[i].pose = CG_POSE_Z;
          s.carts[i].yoff = (256 - car.zoom) * 28 / 256;
        }
    if (items[2].crt) {
      s.name = items[2].title;
      if (!items[2].blank) {
        const t_crt *c = items[2].crt;
        s.meta[0] = c->year;
        s.meta[1] = c->publisher;
        if (c->players[0]) {
          npf_snprintf(players, sizeof(players), "%s %s", c->players,
                       strcmp(c->players, "1") ? "players" : "player");
          s.meta[2] = players;
        }
      }
    }
  }
  s.counter = counter;

  if (car.card && car.count && items[2].crt) {
    car.card_lines = cg_render_card(frame, &s, items[2].crt, items[2].title, car.card_scroll);
    car_pal_dirty = true;
    return;
  }
  car.card = false;
  cg_render_scene(frame, &s);
  car_pal_dirty = true;     // Swapped in at V-blank together with this frame
}

// Copies the staged palette (called from menu_flip, during V-blank).
static void car_flip_palette(void) {
  if (!car_pal_dirty)
    return;
  dma_memcpy16(&MEM_PALETTE[1], &car_pal[1], 15);
  dma_memcpy16(&MEM_PALETTE[20], &car_pal[20], 220);
  car_pal_dirty = false;
}

// ---------------------------------------------------------------------------
// Keys

static void car_open_selected(bool options) {
  const t_centry *e = sdr_state->fileorder[sdr_state->carlist[car.pos]];
  int type = car_type(e);
  char path[MAX_FN_LEN];
  strcpy(path, smenu.browser.cpath);
  strcat(path, e->fname);

  if (options) {
    // Start options: the regular GBA load pop-up (saves, patches, cheats...).
    if (type == CarGba)
      browser_open_gba(path, e->filesize, true);
    return;
  }

  const char *ext = find_extension(path);
  if (!ext || strcasecmp(ext, ".fw"))
    car_fade_out();         // No fade for the firmware update pop-up
  if (type == CarGba) {
    browser_open_gba(path, e->filesize, true);
    // No questions asked (patch prompt / errors)? Then press "Load" for the user.
    if (spop.pop_num == POPUP_GBA_LOAD && !spop.qpop.message && !spop.alert_msg) {
      spop.submenu = GbaLoadPopInfo;
      spop.selector = GBALoadButt;
      keypress_popup_loadgba(KEY_BUTTA);
    }
  } else
    browser_open(path, e->filesize);
}

static void car_keypress(unsigned keys) {
  unsigned newkeys = keys & ~car.lastkeys;   // Only freshly pressed buttons
  car_ensure();

  if (car.card) {
    // Info card.
    if (newkeys & KEY_BUTTB)
      car.card = false;
    else if (newkeys & KEY_BUTTA) {
      car.card = false;
      car_open_selected(false);
    }
    else if (newkeys & KEY_BUTTSEL) {
      car.card = false;
      car_open_selected(true);
    }
    else if (newkeys & KEY_BUTTUP)
      car.card_scroll = MAX(0, car.card_scroll - 1);
    else if (newkeys & KEY_BUTTDOWN)
      car.card_scroll = MIN(MAX(0, car.card_lines - 6), car.card_scroll + 1);
    return;
  }

  if (newkeys & KEY_BUTTSTA) {
    smenu.menu_tab = MENUTAB_UILANG;
    car.via_start = true;
    return;
  }

  if (car.count) {
    if (newkeys & KEY_BUTTLEFT)
      car_move(-1);
    else if (newkeys & KEY_BUTTRIGHT)
      car_move(1);

    if (newkeys & KEY_BUTTA) {
      const t_centry *e = sdr_state->fileorder[sdr_state->carlist[car.pos]];
      if (e->isdir) {
        strcat(smenu.browser.cpath, e->fname);
        strcat(smenu.browser.cpath, "/");
        memmove(&smenu.browser.selhist[1], &smenu.browser.selhist[0],
                sizeof(smenu.browser.selhist) - sizeof(smenu.browser.selhist[0]));
        smenu.browser.selhist[0] = smenu.browser.selector;
        smenu.browser.selector = 0;
        browser_reload();
        car.slide = 0;
        car.fade = 8;
        return;
      }
      car_open_selected(false);
      return;
    }
    if (newkeys & KEY_BUTTUP) {
      if (!sdr_state->fileorder[sdr_state->carlist[car.pos]]->isdir) {
        car.card = true;
        car.card_scroll = 0;
      }
      return;
    }
    if (newkeys & KEY_BUTTSEL) {
      spop.pop_num = POPUP_FILE_MGR;
      spop.anim = 0;
      spop.selector = 0;
      return;
    }
  }

  if (newkeys & KEY_BUTTB) {
    if (movedir_up()) {
      smenu.browser.selector = smenu.browser.selhist[0];
      memmove(&smenu.browser.selhist[0], &smenu.browser.selhist[1],
              sizeof(smenu.browser.selhist) - sizeof(smenu.browser.selhist[0]));
      browser_reload();
      car.slide = 0;
      car.fade = 8;
    }
    else if (car.count)
      car_open_selected(true);
  }
}

#endif  // USE_CAROUSEL
