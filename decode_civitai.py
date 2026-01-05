#!/usr/bin/env python3
"""Decode Civitai JPEG metadata properly"""

import sys
from PIL import Image

def decode_civitai_metadata(image_path):
    with Image.open(image_path) as img:
        exif = img.getexif()
        if not exif:
            print("No EXIF data")
            return

        ifd = exif.get_ifd(0x8769)  # ExifIFD
        if not ifd:
            print("No IFD data")
            return

        # UserComment tag (37510)
        if 37510 not in ifd:
            print("No UserComment")
            return

        raw_bytes = ifd[37510]
        print(f"Raw bytes length: {len(raw_bytes)}")
        print(f"First 100 bytes (hex): {raw_bytes[:100].hex()}")
        print(f"First 100 bytes (repr): {repr(raw_bytes[:100])}\n")

        # Skip UNICODE\x00 prefix if present
        if raw_bytes.startswith(b'UNICODE\x00'):
            raw_bytes = raw_bytes[8:]
            print("Skipped UNICODE prefix\n")

        # Try different decoding strategies
        print("=" * 80)
        print("DECODING ATTEMPTS:")
        print("=" * 80)

        # Strategy 1: Every other byte (ASCII in UTF-16-LE)
        print("\n1. Every other byte (skip nulls):")
        decoded = bytes(raw_bytes[i] for i in range(0, len(raw_bytes), 2) if raw_bytes[i] != 0).decode('latin1', errors='ignore')
        print(decoded[:500])

        # Strategy 2: Direct UTF-16-LE
        print("\n2. UTF-16-LE:")
        try:
            decoded = raw_bytes.decode('utf-16-le', errors='ignore')
            print(decoded[:500])
        except:
            print("Failed")

        # Strategy 3: Strip all null bytes then decode
        print("\n3. Strip nulls then UTF-8:")
        try:
            no_nulls = raw_bytes.replace(b'\x00', b'')
            decoded = no_nulls.decode('utf-8', errors='ignore')
            print(decoded[:500])
        except Exception as e:
            print(f"Failed: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 decode_civitai.py <jpeg_file>")
        sys.exit(1)

    decode_civitai_metadata(sys.argv[1])
