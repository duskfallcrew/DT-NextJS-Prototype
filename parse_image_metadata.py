#!/usr/bin/env python3
"""
Simplified image metadata parser for A1111, ComfyUI, and NovelAI formats.
Extracted from PromptInspectorBot - works with PNG and JPEG (though JPEG often strips metadata).
"""

import io
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path
from PIL import Image


def sanitize_text(text, max_length=10000):
    """Sanitize text content to only allow specific characters"""
    if not isinstance(text, str):
        return ""

    text = re.sub(r"https?://\S+|ftp://\S+|www\.\S+", "", text)
    text = text[:max_length]
    text = re.sub(r'[^A-Za-z0-9\(\)_\-<>:,\{\}\'"\ \n\r\\\[\]\.\|]', "", text)
    return text


def safe_json_loads(json_str, default=None):
    """Safely parse JSON with limits on size and recursion"""
    if not isinstance(json_str, str) or len(json_str) > 1_000_000:
        return default
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, RecursionError, MemoryError):
        return default


class MetadataA1111:
    """Parse Automatic1111/Civitai format metadata"""
    NAME = "A1111"

    def __init__(self, param_str):
        self.raw_text = param_str
        self.params = self.parse(param_str)

    def parse(self, param_str: str) -> OrderedDict:
        param_str = sanitize_text(param_str, 50000)
        output_dict = OrderedDict()

        try:
            parts = param_str.split("Steps: ", 1)
            if len(parts) != 2:
                raise ValueError("Can't parse A1111 metadata: missing Steps key")

            prompts = parts[0]
            params = "Steps: " + parts[1]
            neg_parts = prompts.split("Negative prompt: ", 1) if "Negative prompt: " in prompts else ()

            if neg_parts:
                output_dict["Prompt"] = sanitize_text(neg_parts[0].strip(), 1000)
                output_dict["Negative Prompt"] = sanitize_text(neg_parts[1].strip(), 1000)
            else:
                output_dict["Prompt"] = sanitize_text(prompts.strip(), 1000)

            params = params.split(", ")
            for param in params:
                parts = param.split(": ", 1)
                if len(parts) == 2:
                    key = sanitize_text(parts[0].strip(), 100)
                    value = sanitize_text(parts[1].strip(), 1000)
                    output_dict[key] = value

        except Exception as e:
            output_dict["Error"] = f"Could not parse metadata: {e}"

        return output_dict


class MetadataComfyUI:
    """Parse ComfyUI format metadata"""
    NAME = "ComfyUI"

    def __init__(self, prompt_str, workflow_str=None):
        self.raw_text = prompt_str
        self.workflow_text = workflow_str
        self.params = self.parse(prompt_str, workflow_str)

    def parse(self, prompt_str: str, workflow_str: str = None) -> OrderedDict:
        promptdata = safe_json_loads(prompt_str, {})
        workflowdata = safe_json_loads(workflow_str, {}) if workflow_str else {}

        output_dict = OrderedDict()

        # Extract key information from ComfyUI nodes
        for node_id, node_data in promptdata.items():
            try:
                inputs = node_data.get("inputs", {})
                class_type = node_data.get("class_type", "")

                # Extract common useful fields
                if "text" in inputs:
                    key = f"{class_type} ({node_id})"
                    output_dict[key] = sanitize_text(str(inputs["text"]), 1000)

                if "ckpt_name" in inputs:
                    output_dict[f"Checkpoint ({node_id})"] = inputs["ckpt_name"]

                if "seed" in inputs or "noise_seed" in inputs:
                    seed = inputs.get("seed") or inputs.get("noise_seed")
                    output_dict[f"Seed ({node_id})"] = str(seed)

                if "steps" in inputs:
                    output_dict[f"Steps ({node_id})"] = str(inputs["steps"])

                if "cfg" in inputs:
                    output_dict[f"CFG ({node_id})"] = str(inputs["cfg"])

            except Exception:
                pass

        return output_dict


class MetadataNovelAI:
    """Parse NovelAI format metadata"""
    NAME = "NovelAI"

    def __init__(self, comment_str):
        self.raw_text = comment_str
        self.params = self.parse(comment_str)

    def parse(self, param_str: str) -> OrderedDict:
        param_str = sanitize_text(param_str, 50000)
        output_dict = OrderedDict()

        try:
            data = safe_json_loads(param_str, {})

            # Extract prompts
            output_dict["Prompt"] = sanitize_text(data.get("prompt", ""), 1000)
            output_dict["Negative Prompt"] = sanitize_text(data.get("uc", ""), 1000)

            # Extract parameters
            output_dict["Steps"] = str(data.get("steps", ""))
            output_dict["Sampler"] = sanitize_text(data.get("sampler", ""), 100)
            output_dict["CFG scale"] = str(data.get("scale", ""))
            output_dict["Seed"] = str(data.get("seed", ""))

            width = data.get("width", "")
            height = data.get("height", "")
            if width and height:
                output_dict["Size"] = f"{width}x{height}"

            if "Source" in data:
                output_dict["Model"] = sanitize_text(data.get("Source", ""), 100)

        except Exception as e:
            output_dict["Error"] = f"Could not parse metadata: {e}"

        return output_dict


def extract_metadata(image_path: str) -> dict:
    """
    Extract metadata from an image file.

    Returns:
        dict with keys: 'format' (str), 'params' (OrderedDict), 'raw_text' (str)
        or None if no metadata found
    """
    try:
        with Image.open(image_path) as img:
            info = img.info

            # For JPEGs, check EXIF data (especially Civitai images)
            exif_comment = None
            try:
                exif = img.getexif()
                if exif:
                    # Try to get EXIF IFD which contains UserComment
                    ifd = exif.get_ifd(0x8769)
                    if ifd and 37510 in ifd:  # 37510 = UserComment
                        raw_bytes = ifd[37510]
                        # Civitai stores metadata as UTF-16-LE with null bytes
                        # Skip UNICODE prefix and strip nulls
                        if raw_bytes.startswith(b'UNICODE\x00'):
                            raw_bytes = raw_bytes[8:]
                        # Strip all null bytes then decode as UTF-8
                        exif_comment = raw_bytes.replace(b'\x00', b'').decode('utf-8', errors='ignore')
            except:
                pass

            # Check for NovelAI format (PNG)
            if "Software" in info and info["Software"] == "NovelAI" and "Comment" in info:
                comment = sanitize_text(info["Comment"], 50000)
                metadata = MetadataNovelAI(comment)
                return {
                    "format": "NovelAI",
                    "params": metadata.params,
                    "raw_text": metadata.raw_text
                }

            # Check for A1111 format in PNG
            if "parameters" in info and isinstance(info["parameters"], str):
                parameters = sanitize_text(info["parameters"], 50000)
                if "Steps:" in parameters:
                    metadata = MetadataA1111(parameters)
                    return {
                        "format": "A1111/Civitai",
                        "params": metadata.params,
                        "raw_text": metadata.raw_text
                    }

            # Check for A1111 format in JPEG EXIF data
            for tag_id, value in exif_data.items():
                if "Steps:" in value:
                    parameters = sanitize_text(value, 50000)
                    metadata = MetadataA1111(parameters)
                    return {
                        "format": "A1111/Civitai (JPEG)",
                        "params": metadata.params,
                        "raw_text": metadata.raw_text
                    }

            # Check for ComfyUI format (PNG)
            if "prompt" in info and isinstance(info["prompt"], str):
                prompt = sanitize_text(info["prompt"], 50000)
                if prompt.lstrip().startswith("{"):
                    workflow = sanitize_text(info.get("workflow", ""), 50000) if "workflow" in info else None
                    metadata = MetadataComfyUI(prompt, workflow)
                    return {
                        "format": "ComfyUI",
                        "params": metadata.params,
                        "raw_text": metadata.raw_text,
                        "workflow_text": metadata.workflow_text
                    }

            # Check for ComfyUI in JPEG EXIF
            for tag_id, value in exif_data.items():
                if value.strip().startswith("{"):
                    prompt = sanitize_text(value, 50000)
                    metadata = MetadataComfyUI(prompt, None)
                    return {
                        "format": "ComfyUI (JPEG)",
                        "params": metadata.params,
                        "raw_text": metadata.raw_text
                    }

            return None

    except Exception as e:
        print(f"Error reading image: {e}", file=sys.stderr)
        return None


def main():
    if len(sys.argv) < 2:
        print("Usage: python parse_image_metadata.py <image_file> [--json]")
        print("       Extracts AI generation metadata from PNG/JPEG images")
        sys.exit(1)

    image_path = sys.argv[1]
    output_json = "--json" in sys.argv

    if not Path(image_path).exists():
        print(f"Error: File not found: {image_path}", file=sys.stderr)
        sys.exit(1)

    metadata = extract_metadata(image_path)

    if not metadata:
        print("No metadata found in image", file=sys.stderr)
        sys.exit(1)

    if output_json:
        # Output as JSON
        output = {
            "format": metadata["format"],
            "params": dict(metadata["params"])
        }
        print(json.dumps(output, indent=2))
    else:
        # Human-readable output
        print(f"Format: {metadata['format']}")
        print("\nParameters:")
        for key, value in metadata["params"].items():
            print(f"\n{key}:")
            print(f"  {value}")


if __name__ == "__main__":
    main()
