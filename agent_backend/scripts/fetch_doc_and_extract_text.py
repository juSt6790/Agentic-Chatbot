#!/usr/bin/env python3
"""
Fetch a Google Doc by ID (full JSON metadata) and run extract_text_with_image_urls.
Use either a document ID (with UNIFIED_TOKEN) or a local JSON file for quick testing.
"""
import argparse
import json
import os
import sys

# Add project root for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def extract_text_with_image_urls(doc_json: dict) -> str:
    """
    Extracts text from Google Docs content and inserts image URLs
    inline where images appear, using explicit <imageurl> tags.
    """
    content = doc_json.get("body", {}).get("content", [])
    inline_objects = doc_json.get("inlineObjects", {})

    # 1 Build inlineObjectId → image URL map
    image_map = {}
    for obj_id, obj in inline_objects.items():
        try:
            image_props = (
                obj["inlineObjectProperties"]["embeddedObject"]["imageProperties"]
            )
            content_uri = image_props.get("contentUri")
            if content_uri:
                image_map[obj_id] = content_uri
        except KeyError:
            continue

    lines = []

    # 2 Walk document content in order
    for elem in content:
        if "paragraph" not in elem:
            continue

        paragraph_text = []

        for pe in elem["paragraph"].get("elements", []):
            if "textRun" in pe:
                txt = pe["textRun"].get("content", "")
                if txt:
                    paragraph_text.append(txt)

            elif "inlineObjectElement" in pe:
                inline_id = pe["inlineObjectElement"].get("inlineObjectId")
                image_url = image_map.get(inline_id)
                if image_url:
                    paragraph_text.append(f"\n<imageurl>{image_url}</imageurl>\n")

            elif "person" in pe:
                person_props = pe.get("person", {}).get("personProperties", {})
                name = person_props.get("name", "")
                email = person_props.get("email", "")
                if name:
                    paragraph_text.append(name)
                if email and email != name:
                    paragraph_text.append(f" ({email})")

        paragraph_str = "".join(paragraph_text).strip()
        if paragraph_str:
            lines.append(paragraph_str)

    return "\n\n".join(lines).strip()


def get_doc_json_by_id(document_id: str, unified_token: str) -> dict:
    """Fetch full document JSON using Google Docs API (same approach as docs_mcp)."""
    from services.docs_mcp import get_gdocs_service

    _, docs_service = get_gdocs_service(unified_token)
    return docs_service.documents().get(documentId=document_id).execute()


def main():
    parser = argparse.ArgumentParser(
        description="Get Google Doc JSON and extract text with image URLs."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--id",
        dest="document_id",
        help="Google Doc ID (requires UNIFIED_TOKEN in env)",
    )
    group.add_argument(
        "--json",
        dest="json_path",
        help="Path to a local doc JSON file (no auth needed)",
    )
    parser.add_argument(
        "--out-json",
        dest="out_json",
        help="Optional: write fetched doc JSON to this file",
    )
    args = parser.parse_args()

    if args.json_path:
        with open(args.json_path, "r", encoding="utf-8") as f:
            doc_json = json.load(f)
        print("Loaded doc from", args.json_path, file=sys.stderr)
    else:
        token = os.getenv("UNIFIED_TOKEN")
        if not token:
            print("UNIFIED_TOKEN not set. Set it or use --json <path>", file=sys.stderr)
            sys.exit(1)
        doc_json = get_doc_json_by_id(args.document_id, token)
        print("Fetched doc id:", doc_json.get("documentId"), file=sys.stderr)
        if args.out_json:
            with open(args.out_json, "w", encoding="utf-8") as f:
                json.dump(doc_json, f, indent=2)
            print("Wrote full JSON to", args.out_json, file=sys.stderr)

    text = extract_text_with_image_urls(doc_json)
    print("--- extracted text (with <imageurl> tags) ---")
    print(text)


if __name__ == "__main__":
    main()
