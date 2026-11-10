/*
 * Cartridge carousel ROM browser ("slot."-style skin) -- menu logic.
 *
 * Included once from menu.c (it needs menu.c's static state). Replaces the
 * SD-card file list on the ROM browser tab when the "Browser view" setting is
 * set to "Carousel"; all other tabs stay as they are. Drawing is done by
 * carousel_gfx.c.
 *
 *  - Left/Right: previous/next cart (hold = fast scroll)
 *  - L/R: system filter All / GBA / GB / GBC; past the ends L/R go to the
 *    previous/next tab like before.
 *  - A: start the game (or open a folder)
 *  - B: one folder up; in the root folder: start options of the selected game
 *  - Up: start options (GBA load pop-up: saves, patches, cheats, RTC...)
 *  - Select: file manager (delete / hide / write to NOR), as in the list view
 *  - Start: UI settings tab (B or Start there brings you back)
 *
 * Label art is cached in SDRAM (8 labels), the wood texture is rendered once
 * into SDRAM as well, so the carousel costs almost no EWRAM.
 *
 * Copyright (C) 2026 Retroid. GPL-3.0-or-later (same license as SuperFW).
 */

#ifdef USE_CAROUSEL

#define CAR_SPACING     256      // Slide units per cart
#define CAR_ABS(x)      ((x) < 0 ? -(x) : (x))
#define CAR_HOLD_DELAY   18      // Frames before auto-repeat kicks in
#define CAR_SETTLE        4      // Frames without movement before loading art

enum { CarAll = 0, CarGBA, CarGB, CarGBC, CarFiltCNT };
static const char *const car_filter_names[CarFiltCNT] = { "All", "GBA", "GB", "GBC" };

// Functions defined further down in menu.c.
static void browser_open(const char *fn, uint32_t fs);
static void browser_open_gba(const char *fn, uint32_t fs, bool prompt_patchgen);
static void browser_reload();
static void keypress_popup_loadgba(unsigned newkeys);
const t_emu_loader * get_emu_info(const char *ext);
int movedir_up();

static struct {
  uint8_t filter;           // CarAll..CarGBC
  bool built;               // carlist is valid for (filter, gen)
  bool fading;              // the blend registers are in "fade" mode
  bool wood_ready;          // wood texture rendered into SDRAM
  unsigned gen;             // browser_gen the list was built for
  int count, pos;           // entries in carlist, selected position
  int slide;                // animation offset (CAR_SPACING = one cart)
  unsigned hold, repacc;    // Left/Right auto-repeat
  unsigned settle;          // frames since the last move
  int fade;                 // fade-in level (16 = black, 0 = done)
  unsigned lastkeys;        // key state seen on the previous frame
  bool via_start;           // UI settings were opened with Start (B returns)
  struct {
    uint16_t idx;           // fileorder index
    uint16_t pos;           // carlist position when loaded (eviction hint)
    unsigned gen;           // browser_gen it belongs to
    uint8_t state;          // 0 = empty, 1 = label art, 2 = no art (generic)
  } lc[CAR_CACHE_N];
  char user[12];            // From /USERNAME.TXT (max 10 chars)
} car;

static bool carousel_on(void) {
  return browser_view != 0;
}

static int car_type(const t_centry *e) {
  if (e->isdir)
    return CG_CART_FOLDER;
  const char *ext = find_extension(e->fname);
  if (!ext)
    return -1;
  if (!strcasecmp(ext, ".gba"))
    return CG_CART_GBA;
  if (!strcasecmp(ext, ".gb"))
    return CG_CART_GB;
  if (!strcasecmp(ext, ".gbc"))
    return CG_CART_GBC;
  if (get_emu_info(&ext[1]) || !strcasecmp(ext, ".fw"))
    return CG_CART_OTHER;   // Other emulated systems + firmware updates ("All")
  return -1;                // .sav, .txt ... only in the list view
}

static bool car_match(int type, unsigned filter) {
  if (type < 0)
    return false;
  if (type == CG_CART_FOLDER || filter == CarAll)
    return true;
  return (filter == CarGBA && type == CG_CART_GBA) ||
         (filter == CarGB  && type == CG_CART_GB)  ||
         (filter == CarGBC && type == CG_CART_GBC);
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
  car.slide += (np - car.pos) * CAR_SPACING;
  car.slide = MAX(-2 * CAR_SPACING, MIN(2 * CAR_SPACING, car.slide));
  car.pos = np;
  car_sync();
}

// Whether the current folder has any game for a system filter (All: always).
static bool car_filter_has(unsigned filter) {
  if (filter == CarAll)
    return true;
  for (int i = 0; i < smenu.browser.dispentries; i++) {
    int t = car_type(sdr_state->fileorder[i]);
    if (t != CG_CART_FOLDER && car_match(t, filter))
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
  car.slide = d * 2 * CAR_SPACING;    // New row slides in from that side
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
  car.fade = 16;            // Fade in the first time the carousel shows up
}

// ---------------------------------------------------------------------------
// Label cache (SDRAM)

static int car_cache_find(unsigned idx) {
  for (unsigned i = 0; i < CAR_CACHE_N; i++)
    if (car.lc[i].state && car.lc[i].idx == idx && car.lc[i].gen == browser_gen)
      return i;
  return -1;
}

static void car_cache_load(int lpos) {
  unsigned idx = sdr_state->carlist[lpos];
  const t_centry *e = sdr_state->fileorder[idx];
  int type = car_type(e);

  // Victim: an empty/stale slot, else the one farthest away from the cursor.
  int v = 0, best = -1;
  for (unsigned i = 0; i < CAR_CACHE_N; i++) {
    int score = (!car.lc[i].state || car.lc[i].gen != browser_gen) ? 0x7FFF :
                CAR_ABS((int)car.lc[i].pos - car.pos);
    if (score > best) {
      best = score;
      v = i;
    }
  }

  char path[MAX_FN_LEN * 2];
  npf_snprintf(path, sizeof(path), "%s%s", smenu.browser.cpath, e->fname);
  bool ok = coverart_load_label(path, e->filesize, type == CG_CART_GBA, sdr_state->carlabels[v]);

  car.lc[v].idx = idx;
  car.lc[v].pos = lpos;
  car.lc[v].gen = browser_gen;
  car.lc[v].state = ok ? 1 : 2;
}

// Loads (at most) one missing label per frame: center first, then neighbours.
static void car_cache_step(void) {
  static const int8_t order[5] = { 0, 1, -1, 2, -2 };
  for (unsigned i = 0; i < 5; i++) {
    int lp = car.pos + order[i];
    if (lp < 0 || lp >= car.count)
      continue;
    unsigned idx = sdr_state->carlist[lp];
    if (sdr_state->fileorder[idx]->isdir)
      continue;             // Folders have no label
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
  coverart_load_cube();

  if (menu_theme == THEME_WOOD && !car.wood_ready) {
    uint8_t row[SCREEN_WIDTH] __attribute__((aligned(4)));
    for (unsigned y = 0; y < CG_AREA_H; y++) {
      cg_wood_row(row, y);
      dma_memcpy16(&sdr_state->woodtex[y * SCREEN_WIDTH], row, SCREEN_WIDTH / 2);
    }
    car.wood_ready = true;
  }

  // Hold Left/Right to scroll fast.
  unsigned keys = (~REG_KEYINPUT) & 0x3FF;
  bool lr = (keys & (KEY_BUTTLEFT | KEY_BUTTRIGHT)) && !spop.alert_msg;
  if (lr && car.count) {
    car.hold += fcnt;
    if (car.hold > CAR_HOLD_DELAY) {
      unsigned period = car.hold > 90 ? 2 : 4;
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

  // Slide animation (ease out).
  for (unsigned i = 0; i < fcnt && car.slide; i++) {
    car.slide = (car.slide * 5) / 8;
    if (CAR_ABS(car.slide) < 6)
      car.slide = 0;
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

  // Load label art once the cursor stopped moving.
  if (car.settle >= CAR_SETTLE && car.count && !car.hold)
    car_cache_step();

  // Build the scene.
  t_cg_scene s;
  memset(&s, 0, sizeof(s));
  char titles[CG_MAX_CARTS][96];
  char counter[24];

  s.bgstyle = (menu_theme == THEME_WOOD && car.wood_ready) ? CG_BG_WOOD : CG_BG_SOLID;
  s.woodtex = sdr_state->woodtex;
  s.nfilters = CarFiltCNT;
  s.filter = car.filter;
  s.filter_names = car_filter_names;
  int mintab = (recent_menu && smenu.recent.maxentries) ? MENUTAB_RECENT : MENUTAB_ROMBROWSE;
  s.header_minx = (MENUTAB_MAX - mintab) * 16 + 2;
  s.user = car.user;
  s.path = smenu.browser.cpath;
  s.clock = NULL;           // The cart has no RTC the menu can read: no clock.

  if (!car.count) {
    s.message = msgs[lang_id][MSG_BROW_EMPTY];
    npf_snprintf(counter, sizeof(counter), "0/0");
  } else {
    npf_snprintf(counter, sizeof(counter), "%d/%d", car.pos + 1, car.count);
    int slide100 = (car.slide * 100) / CAR_SPACING;
    for (int k = -3; k <= 3; k++) {
      int lp = car.pos + k;
      int x100 = k * 100 + slide100;
      if (lp < 0 || lp >= car.count || x100 < -260 || x100 > 260)
        continue;
      unsigned idx = sdr_state->carlist[lp];
      const t_centry *e = sdr_state->fileorder[idx];
      t_cg_cart *c = &s.carts[s.ncarts];
      car_title(e, titles[s.ncarts], sizeof(titles[0]));
      int ci = car_cache_find(idx);
      c->x100 = x100;
      c->type = car_type(e);
      c->title = titles[s.ncarts];
      c->label = (ci >= 0 && car.lc[ci].state == 1) ? sdr_state->carlabels[ci] : NULL;
      if (!k)
        s.name = titles[s.ncarts];
      s.ncarts++;
    }
  }
  s.counter = counter;

  cg_render_scene(frame, &s);
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
    if (type == CG_CART_GBA)
      browser_open_gba(path, e->filesize, true);
    return;
  }

  const char *ext = find_extension(path);
  if (!ext || strcasecmp(ext, ".fw"))
    car_fade_out();         // No fade for the firmware update pop-up
  if (type == CG_CART_GBA) {
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
      car_open_selected(true);
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
