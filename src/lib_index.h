/*
 * Game library index (carousel): finds the 3D cart (.CRT) of a ROM.
 *
 * /LIBRARY/INDEX.BIN (base pack) and /LIBRARY/MY.BIN (own library, wins) are
 * sorted tables of key hashes -> cart number. Keys are short strings:
 *   "S:gba:AXVE"                 GBA game code from the ROM header
 *   "N:gb:tetris (world) (rev 1)" ROM file name without extension, lower case
 *   "C:nes:393A432F"             CRC32 of the ROM (NES without iNES header)
 * Families: "gba", "gb" (GB + GBC), "nes".
 *
 * File: "RIDX", u32 version (1), u32 count, u32 reserved, then count entries
 * of { u32 h1, u32 h2, u32 cart } sorted by (h1, h2). h1/h2 = FNV-1a of the
 * key with two different seeds. Cart n lives in /LIBRARY/<C|M>/<n>>8 as %02X>/<n as %04X>.CRT.
 *
 * Portable (no FatFS): reads go through a callback, so it also runs on a PC
 * (tools/library/test_index.c). Same hashing in tools/library/libindex.py.
 *
 * Copyright (C) 2026 Retroid. GPL-3.0-or-later (same license as SuperFW).
 */
#ifndef __LIB_INDEX_H__
#define __LIB_INDEX_H__

#include <stdint.h>
#include <stdbool.h>

#define LIBIDX_SEED1   0x811C9DC5u
#define LIBIDX_SEED2   0x050C5D1Fu

typedef bool (*libidx_read_fn)(void *ctx, uint32_t off, void *buf, unsigned len);

uint32_t libidx_fnv(const char *s, uint32_t seed);

// Builds "<kind>:<family>:<value>" (value lower-cased for kind 'N').
void libidx_key(char *out, unsigned outsz, char kind, const char *family, const char *value);

// Binary search; true + *cart when found.
bool libidx_find(libidx_read_fn rd, void *ctx, const char *key, uint32_t *cart);

// CRC32 (zlib/No-Intro). Start with 0xFFFFFFFF, xor the result with it at the end.
void libidx_crc_init(void);
uint32_t libidx_crc(uint32_t crc, const uint8_t *p, unsigned len);

#endif
