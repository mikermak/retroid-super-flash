/*
 * Game library index (carousel). See lib_index.h.
 *
 * Copyright (C) 2026 Retroid. GPL-3.0-or-later (same license as SuperFW).
 */
#pragma GCC optimize ("Os")

#include <string.h>
#include "lib_index.h"

uint32_t libidx_fnv(const char *s, uint32_t seed) {
  uint32_t h = seed;
  while (*s)
    h = (h ^ (uint8_t)*s++) * 0x01000193u;
  return h;
}

void libidx_key(char *out, unsigned outsz, char kind, const char *family, const char *value) {
  unsigned o = 0;
  if (outsz < 8)
    return;
  out[o++] = kind;
  out[o++] = ':';
  while (*family && o < outsz - 2)
    out[o++] = *family++;
  out[o++] = ':';
  while (*value && o < outsz - 1) {
    char c = *value++;
    if (kind == 'N' && c >= 'A' && c <= 'Z')
      c += 32;
    out[o++] = c;
  }
  out[o] = 0;
}

static uint32_t rd32(const uint8_t *p) {
  return p[0] | (p[1] << 8) | (p[2] << 16) | ((uint32_t)p[3] << 24);
}

bool libidx_find(libidx_read_fn rd, void *ctx, const char *key, uint32_t *cart) {
  uint8_t hdr[16];
  if (!rd(ctx, 0, hdr, sizeof(hdr)) || memcmp(hdr, "RIDX", 4) || rd32(&hdr[4]) != 1)
    return false;
  uint32_t n = rd32(&hdr[8]);
  uint32_t h1 = libidx_fnv(key, LIBIDX_SEED1), h2 = libidx_fnv(key, LIBIDX_SEED2);
  int lo = 0, hi = (int)n - 1;
  while (lo <= hi) {
    int mid = (lo + hi) / 2;
    uint8_t e[12];
    if (!rd(ctx, 16 + (uint32_t)mid * 12, e, sizeof(e)))
      return false;
    uint32_t a = rd32(e), b = rd32(&e[4]);
    if (a == h1 && b == h2) {
      *cart = rd32(&e[8]);
      return true;
    }
    if (a < h1 || (a == h1 && b < h2))
      lo = mid + 1;
    else
      hi = mid - 1;
  }
  return false;
}

static uint32_t crc_tab[256];

void libidx_crc_init(void) {
  for (uint32_t i = 0; i < 256; i++) {
    uint32_t c = i;
    for (int k = 0; k < 8; k++)
      c = (c & 1) ? (0xEDB88320u ^ (c >> 1)) : (c >> 1);
    crc_tab[i] = c;
  }
}

uint32_t libidx_crc(uint32_t crc, const uint8_t *p, unsigned len) {
  while (len--)
    crc = crc_tab[(crc ^ *p++) & 0xFF] ^ (crc >> 8);
  return crc;
}
