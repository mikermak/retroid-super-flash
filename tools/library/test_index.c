/*
 * Host test for src/lib_index.c (the firmware's library lookup).
 *
 *   test_index find <INDEX.BIN> <keys.txt>   one key per line -> cart id or -1
 *   test_index crc  <file> [nes]             CRC32 like the firmware computes it
 *                                            (nes: skips a 16-byte iNES header)
 * Driven by tools/library/test_index.py.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "lib_index.h"

static bool rd(void *ctx, uint32_t off, void *buf, unsigned len) {
  FILE *f = ctx;
  return !fseek(f, off, SEEK_SET) && fread(buf, 1, len, f) == len;
}

int main(int argc, char **argv) {
  if (argc >= 4 && !strcmp(argv[1], "find")) {
    FILE *f = fopen(argv[2], "rb"), *k = fopen(argv[3], "rb");
    if (!f || !k) return 2;
    char line[512];
    while (fgets(line, sizeof(line), k)) {
      line[strcspn(line, "\r\n")] = 0;
      uint32_t cart;
      if (libidx_find(rd, f, line, &cart))
        printf("%u\n", cart);
      else
        printf("-1\n");
    }
    return 0;
  }
  if (argc >= 3 && !strcmp(argv[1], "crc")) {
    FILE *f = fopen(argv[2], "rb");
    if (!f) return 2;
    libidx_crc_init();
    unsigned char hdr[16];
    size_t skip = 0;
    if (argc >= 4 && fread(hdr, 1, 16, f) == 16 && !memcmp(hdr, "NES\x1a", 4))
      skip = 16;
    fseek(f, skip, SEEK_SET);
    uint32_t crc = 0xFFFFFFFFu;
    unsigned char buf[2048];
    size_t n;
    while ((n = fread(buf, 1, sizeof(buf), f)) > 0)
      crc = libidx_crc(crc, buf, n);
    printf("%08X\n", crc ^ 0xFFFFFFFFu);
    return 0;
  }
  fprintf(stderr, "usage\n");
  return 1;
}
