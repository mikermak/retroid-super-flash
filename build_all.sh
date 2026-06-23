#!/bin/bash
# Build all three Supercard board variants and stage them as superfw-<board>.fw
cd /mnt/c/Users/aruur/Downloads/superfw || exit 1
for B in sd lite chis; do
  make clean >/dev/null 2>&1
  if make BOARD="$B" COMPRESSION_RATIO=9 >/tmp/build_$B.log 2>&1; then
    cp -f superfw.gba "superfw-$B.fw"
    echo "$B: OK ($(stat -c%s superfw-$B.fw) bytes)"
  else
    echo "$B: FAILED"
    tail -4 /tmp/build_$B.log
  fi
done
echo "=== .fw files ==="
ls -la superfw-*.fw
