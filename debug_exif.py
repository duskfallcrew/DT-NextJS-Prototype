#!/usr/bin/env python3
"""Debug script to see ALL metadata in an image"""

import sys
from PIL import Image
from PIL.ExifTags import TAGS

def debug_image_metadata(image_path):
    print(f"Analyzing: {image_path}\n")
    print("=" * 80)

    with Image.open(image_path) as img:
        print(f"Format: {img.format}")
        print(f"Size: {img.size}")
        print(f"Mode: {img.mode}\n")

        # Check img.info (PNG text chunks)
        print("=" * 80)
        print("IMG.INFO (PNG text chunks):")
        print("=" * 80)
        if img.info:
            for key, value in img.info.items():
                print(f"{key}: {str(value)[:200]}")
        else:
            print("(empty)")

        # Check EXIF data
        print("\n" + "=" * 80)
        print("EXIF DATA:")
        print("=" * 80)
        try:
            exif = img.getexif()
            if exif:
                # Get IFD (Image File Directory) data which contains UserComment
                ifd = exif.get_ifd(0x8769)  # ExifIFD

                for tag_id, value in exif.items():
                    tag_name = TAGS.get(tag_id, tag_id)
                    if isinstance(value, bytes):
                        # Try multiple decodings
                        decoded = None
                        for encoding in ['utf-8', 'utf-16', 'utf-16-le', 'utf-16-be', 'latin1']:
                            try:
                                decoded = value.decode(encoding, errors='ignore')
                                if decoded and len(decoded.strip()) > 0:
                                    break
                            except:
                                continue
                        value = decoded or f"<bytes: {len(value)} bytes>"
                    print(f"{tag_name} ({tag_id}): {str(value)[:500]}")

                # Check IFD for UserComment specifically
                if ifd:
                    print("\n" + "=" * 80)
                    print("EXIF IFD DATA:")
                    print("=" * 80)
                    for tag_id, value in ifd.items():
                        tag_name = TAGS.get(tag_id, tag_id)
                        if isinstance(value, bytes):
                            # Handle UNICODE prefix for UserComment
                            if value.startswith(b'UNICODE\x00'):
                                value = value[8:]  # Skip UNICODE\x00

                            # Civitai stores as UTF-16-LE, decode and strip null bytes
                            decoded = None
                            try:
                                # Try UTF-16-LE first
                                decoded = value.decode('utf-16-le', errors='ignore')
                                # Remove null characters that appear between actual characters
                                decoded = decoded.replace('\x00', '')
                            except:
                                # Fallback to other encodings
                                for encoding in ['utf-16', 'utf-8', 'latin1']:
                                    try:
                                        decoded = value.decode(encoding, errors='ignore')
                                        if decoded and len(decoded.strip()) > 10:
                                            break
                                    except:
                                        continue
                            value = decoded or f"<bytes: {len(value)} bytes>"
                        print(f"{tag_name} ({tag_id}): {str(value)[:1000]}")
            else:
                print("(no EXIF data)")
        except Exception as e:
            print(f"Error reading EXIF: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 debug_exif.py <image_file>")
        sys.exit(1)

    debug_image_metadata(sys.argv[1])
