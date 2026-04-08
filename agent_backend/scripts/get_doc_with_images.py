#!/usr/bin/env python3
"""
Get Google Doc content + image bytes (for analysis). Uses Drive HTML export
to obtain image data; images are in the same order as <imageurl> placeholders
in content. Requires UNIFIED_TOKEN.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def main():
    parser = argparse.ArgumentParser(description="Get doc content + image bytes for analysis.")
    parser.add_argument("document_id", help="Google Doc ID")
    parser.add_argument("--token", default=os.getenv("UNIFIED_TOKEN"), help="Unified token")
    parser.add_argument("--save-dir", help="If set, save each image to this dir as image_0.png, ...")
    args = parser.parse_args()

    if not args.token:
        print("Set UNIFIED_TOKEN or pass --token", file=sys.stderr)
        sys.exit(1)

    from services.docs_mcp import gdocs_get_document_content_with_images

    result = gdocs_get_document_content_with_images(args.document_id, args.token)
    if result.get("status") == "error":
        print(result.get("message", "Unknown error"), file=sys.stderr)
        sys.exit(1)

    content = result.get("content", "")
    images = result.get("images", [])

    print("--- content (with <imageurl> placeholders) ---")
    print(content)
    print()
    print(f"--- images: {len(images)} in doc order ---")
    for i, img in enumerate(images):
        ct = img.get("content_type", "application/octet-stream")
        size = len(img.get("bytes", b""))
        print(f"  [{i}] {ct}  {size} bytes")

    if args.save_dir and images:
        os.makedirs(args.save_dir, exist_ok=True)
        for i, img in enumerate(images):
            ext = "png" if "png" in img.get("content_type", "") else "jpg"
            path = os.path.join(args.save_dir, f"image_{i}.{ext}")
            with open(path, "wb") as f:
                f.write(img["bytes"])
            print(f"  Saved {path}", file=sys.stderr)
        print(f"Saved {len(images)} images to {args.save_dir}", file=sys.stderr)

    # Example: analyze images (e.g. pass img["bytes"] to a vision API)
    # for i, img in enumerate(images):
    #     analysis = your_vision_api(img["bytes"], img["content_type"])
    #     ...


if __name__ == "__main__":
    main()
