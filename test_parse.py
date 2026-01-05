#!/usr/bin/env python3
"""Quick test parser for individual images"""

import sys
from pathlib import Path

# Add PromptInspectorBot to path
sys.path.insert(0, '/mnt/c/Users/dusk/Development/PromptInspectorBot')

from PromptInspector import populate_attachment_metadata
from collections import OrderedDict

def parse_image(file_path):
    """Parse a single image file"""
    try:
        with open(file_path, 'rb') as f:
            image_data = f.read()

        metadata = OrderedDict()
        populate_attachment_metadata(0, image_data, metadata)

        if not metadata:
            print("❌ No metadata found")
            return

        md = metadata[0]
        print(f"✅ Format: {md.NAME}\n")
        print("=" * 80)
        print("PARAMETERS:")
        print("=" * 80)

        for key, value in md.params.items():
            print(f"\n{key}:")
            print(f"  {value}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 test_parse.py <image_file>")
        sys.exit(1)

    parse_image(sys.argv[1])
