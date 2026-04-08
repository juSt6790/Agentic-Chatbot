#!/usr/bin/env python3
"""
Check if Google Docs inline image URLs are accessible using the same
unified token / Gsuite auth as services/docs_mcp.py.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def collect_image_urls_from_doc_json(doc_json: dict) -> list[str]:
    """Extract all contentUri image URLs from a doc JSON (body + inlineObjects)."""
    urls = []
    for obj_id, obj in (doc_json.get("inlineObjects") or {}).items():
        try:
            uri = (
                obj.get("inlineObjectProperties", {})
                .get("embeddedObject", {})
                .get("imageProperties", {})
                .get("contentUri")
            )
            if uri:
                urls.append(uri)
        except (KeyError, TypeError):
            continue
    return urls


def _request(url: str, headers: dict, timeout: int = 15) -> dict:
    import requests
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        return {
            "status_code": r.status_code,
            "content_type": r.headers.get("Content-Type", ""),
            "content_length": r.headers.get("Content-Length", "(unknown)"),
            "ok": 200 <= r.status_code < 300,
        }
    except requests.RequestException as e:
        return {"status_code": None, "error": str(e), "ok": False}


def check_url_access(url: str, access_token: str, timeout: int = 15) -> dict:
    """Try several strategies to access the image URL; return best result + attempts."""
    import requests
    attempts = []

    # 1) Bearer only
    r = _request(url, {"Authorization": f"Bearer {access_token}"}, timeout)
    r["strategy"] = "Bearer"
    attempts.append(r)
    if r.get("ok"):
        return {"attempts": attempts, "best": r, "ok": True}

    # 2) Bearer + browser-like headers (docs origin)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Origin": "https://docs.google.com",
        "Referer": "https://docs.google.com/",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    r2 = _request(url, headers, timeout)
    r2["strategy"] = "Bearer + Origin/Referer"
    attempts.append(r2)
    if r2.get("ok"):
        return {"attempts": attempts, "best": r2, "ok": True}

    # 3) Same but with lh7-rt host in Origin (some CDNs check)
    headers["Origin"] = "https://lh7-rt.googleusercontent.com"
    r3 = _request(url, headers, timeout)
    r3["strategy"] = "Bearer + lh7 Origin"
    attempts.append(r3)
    if r3.get("ok"):
        return {"attempts": attempts, "best": r3, "ok": True}

    return {"attempts": attempts, "best": attempts[0], "ok": False}


def main():
    parser = argparse.ArgumentParser(
        description="Check Google Docs image URL access using unified token."
    )
    parser.add_argument(
        "--url",
        action="append",
        dest="urls",
        help="Image URL to check (can be repeated)",
    )
    parser.add_argument(
        "--json",
        dest="json_path",
        help="Doc JSON file: extract image URLs from inlineObjects and check them",
    )
    parser.add_argument(
        "--token",
        dest="token",
        default=os.getenv("UNIFIED_TOKEN"),
        help="Unified token (default: UNIFIED_TOKEN env)",
    )
    args = parser.parse_args()

    urls = list(args.urls or [])
    if args.json_path:
        with open(args.json_path, "r", encoding="utf-8") as f:
            doc = json.load(f)
        urls.extend(collect_image_urls_from_doc_json(doc))
        print(f"Collected {len(urls)} image URL(s) from {args.json_path}", file=sys.stderr)

    if not urls:
        print("No URLs to check. Use --url <url> and/or --json <path>.", file=sys.stderr)
        sys.exit(1)

    if not args.token:
        print("Set UNIFIED_TOKEN or pass --token.", file=sys.stderr)
        sys.exit(1)

    from services.docs_mcp import get_gdocs_access_token
    token = get_gdocs_access_token(args.token)
    print("Using Gsuite access token (same auth as docs_mcp)\n", file=sys.stderr)

    for i, url in enumerate(urls, 1):
        short = url[:80] + "..." if len(url) > 80 else url
        print(f"[{i}] {short}")
        info = check_url_access(url, token)
        if info.get("attempts"):
            for a in info["attempts"]:
                status = a.get("status_code") or a.get("error", "?")
                print(f"    {a.get('strategy', '?')}: {status}")
            print(f"    Accessible: {info.get('ok', False)}")
        elif info.get("error"):
            print(f"    Error: {info['error']}")
        else:
            print(f"    Status: {info['status_code']}  Accessible: {info.get('ok', False)}")
        print()

    # Optional: try Drive export (get doc as HTML) to see if we can access content that way
    doc_id = None
    if args.json_path:
        with open(args.json_path, "r", encoding="utf-8") as f:
            doc_id = json.load(f).get("documentId")
    if doc_id and args.token:
        print("--- Drive export (doc as HTML) ---", file=sys.stderr)
        try:
            from services.docs_mcp import get_gdocs_service
            drive_service, _ = get_gdocs_service(args.token)
            from io import BytesIO
            from googleapiclient.http import MediaIoBaseDownload
            # Export as HTML (same auth)
            request = drive_service.files().export_media(
                fileId=doc_id,
                mimeType="text/html",
            )
            buf = BytesIO()
            downloader = MediaIoBaseDownload(buf, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            html = buf.getvalue().decode("utf-8", errors="replace")
            print(f"Export OK: {len(html)} bytes HTML", file=sys.stderr)
            # Check for embedded images (data URIs or img src)
            import re
            data_uris = re.findall(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+", html)
            img_srcs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html)
            print(f"  Embedded data URIs: {len(data_uris)}, img src refs: {len(img_srcs)}", file=sys.stderr)
        except Exception as e:
            print(f"Export failed: {e}", file=sys.stderr)
        else:
            print("Use Drive export (text/html) when you need doc content including images.", file=sys.stderr)


if __name__ == "__main__":
    main()
