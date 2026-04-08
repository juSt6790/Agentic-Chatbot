def _try_extract_youtube_id(url: str) -> str | None:
    try:
        p = urlparse(url)
        host = (p.netloc or "").lower()
        path = p.path or ""
        if host.endswith("youtu.be"):
            vid = path.strip("/")
            return vid or None
        if "youtube.com" in host or host.startswith("m.youtube.com"):
            qs = parse_qs(p.query)
            if "v" in qs:
                return qs["v"][0]
            if path.startswith("/shorts/"):
                return path.split("/shorts/")[-1].split("/")[0]
            if path.startswith("/embed/"):
                return path.split("/embed/")[-1].split("/")[0]
        return None
    except Exception:
        return None

import io
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
import os
import json
from typing import List
import requests
from clients.db_method import get_user_tool_access_token
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
import re
import base64
from dotenv import load_dotenv

load_dotenv()



# BASE_URL = "http://3.6.95.164:5000/users"


# Example: Call get_tool_token endpoint
# def get_tool_token(unified_token, tool_name):
#     url = f"{BASE_URL}/get_tool_token"
#     payload = {"unified_token": unified_token, "tool_name": tool_name}

#     response = requests.post(url, json=payload)
#     print("abc")
#     if response.status_code == 200:
#         print("Access Token:", response.json())
#         return response.json()
#     else:
#         print("Error:", response.status_code, response.text)


def get_gdocs_service(unified_token):
    tool_name = "Gsuite"
    # result = get_tool_token(unified_token, tool_name)
    result, status = get_user_tool_access_token(unified_token, tool_name)
    if isinstance(result, tuple):
        result, status = result
        if status != 200:
            raise ValueError(result.get("error"))
    access_data = (
        result["access_token"]
        if isinstance(result, dict) and "access_token" in result
        else None
    )
    if not isinstance(access_data, dict):
        raise ValueError("Invalid access token data")
    # Note: Don't specify scopes - use whatever was originally granted
    # to avoid "invalid_scope" errors during token refresh
    creds = Credentials(
        token=access_data.get("token"),
        refresh_token=access_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=access_data.get("client_id"),
        client_secret=access_data.get("client_secret"),
    )

    # if creds.expired and creds.refresh_token:
    #     creds.refresh(Request())
    #     update_user_tool_access_token(unified_token, tool_name, {
    #         "token": creds.token,
    #         "refresh_token": creds.refresh_token,
    #         "client_id": creds.client_id,
    #         "client_secret": creds.client_secret,
    #         "expiry": creds.expiry.isoformat() if creds.expiry else None
    #     })

    return build("drive", "v3", credentials=creds), build(
        "docs", "v1", credentials=creds
    )


def get_gdocs_access_token(unified_token: str) -> str:
    """Return a valid Google OAuth2 access token for Drive/Docs (same auth as get_gdocs_service)."""
    tool_name = "Gsuite"
    result, status = get_user_tool_access_token(unified_token, tool_name)
    if isinstance(result, tuple):
        result, status = result
    if status != 200:
        raise ValueError((result or {}).get("error", "Failed to get token"))
    access_data = (
        result.get("access_token")
        if isinstance(result, dict) and "access_token" in result
        else None
    )
    if not isinstance(access_data, dict):
        raise ValueError("Invalid access token data")
    creds = Credentials(
        token=access_data.get("token"),
        refresh_token=access_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=access_data.get("client_id"),
        client_secret=access_data.get("client_secret"),
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds.token


# def get_gdocs_service(
#     credentials_path: str = DEFAULT_CREDENTIALS_PATH,
#     token_path: str = DEFAULT_TOKEN_PATH,
#     scopes: List[str] = GDRIVE_DOCS_SCOPES,
# ):
#     """
#     Authenticate and return Google Drive API service for Docs access.
#     """
#     creds = None
#     if os.path.exists(token_path):
#         with open(token_path, "r") as token:
#             token_data = json.load(token)
#             creds = Credentials.from_authorized_user_info(token_data)

#     if not creds or not creds.valid:
#         if creds and creds.expired and creds.refresh_token:
#             creds.refresh(Request())
#         else:
#             if not os.path.exists(credentials_path):
#                 raise FileNotFoundError(f"Missing credentials at {credentials_path}")
#             flow = InstalledAppFlow.from_client_secrets_file(credentials_path, scopes)
#             creds = flow.run_local_server(port=0)

#         with open(token_path, "w") as token:
#             json.dump(json.loads(creds.to_json()), token)

#     # Return both Drive and Docs services
#     drive_service = build("drive", "v3", credentials=creds)
#     docs_service = build("docs", "v1", credentials=creds)
#     return drive_service, docs_service


def gdocs_get_user_documents(limit: int = 10, unified_token: str = None) -> dict:
    drive_service, _ = get_gdocs_service(unified_token)
    try:
        response = (
            drive_service.files()
            .list(
                q="mimeType='application/vnd.google-apps.document' and trashed=false",
                pageSize=limit,
                fields="files(id, name)",
            )
            .execute()
        )
        return {"documents": response.get("files", [])}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gdocs_create_document_from_html(
    title: str, html: str, unified_token: str = None
) -> dict:
    """Create a Google Doc by importing HTML via Drive API to preserve formatting."""
    drive_service, _ = get_gdocs_service(unified_token)
    try:
        media = MediaIoBaseUpload(
            io.BytesIO(html.encode("utf-8")), mimetype="text/html", resumable=False
        )
        file_metadata = {
            "name": title,
            "mimeType": "application/vnd.google-apps.document",
        }
        created = (
            drive_service.files()
            .create(body=file_metadata, media_body=media, fields="id, webViewLink")
            .execute()
        )
        return {
            "document_id": created.get("id"),
            "title": title,
            "webViewLink": created.get("webViewLink"),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# === Bedrock-backed HTML generation and Doc creation ===
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID") or "anthropic.claude-sonnet-4-5-20250929-v1:0"
REGION = os.getenv("AWS_REGION", "us-east-1")
# Bearer token for Bedrock authentication (replaces IAM credentials)
AWS_BEARER_TOKEN_BEDROCK = os.getenv("AWS_BEARER_TOKEN_BEDROCK", "")


def _invoke_bedrock_claude(body: dict) -> dict:
    url = f"https://bedrock-runtime.{REGION}.amazonaws.com/model/{BEDROCK_MODEL_ID}/invoke"
    
    # Use bearer token authentication instead of SigV4Auth
    if not AWS_BEARER_TOKEN_BEDROCK:
        raise ValueError("AWS_BEARER_TOKEN_BEDROCK environment variable is not set")
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AWS_BEARER_TOKEN_BEDROCK}"
    }
    
    resp = requests.post(url, headers=headers, data=json.dumps(body))
    resp.raise_for_status()
    return resp.json()


def _fetch_link_context(context_link: str, max_chars: int = 10000) -> str:
    """Fetch and extract readable text from a URL for grounding the model."""
    def _is_youtube(url: str) -> bool:
        try:
            p = urlparse(url)
            host = (p.netloc or "").lower()
            return "youtube.com" in host or "youtu.be" in host
        except Exception:
            return False

    try:
        if _is_youtube(context_link):
            video_id = _try_extract_youtube_id(context_link)
            if video_id:
                # Try transcript via youtube_transcript_api if available
                transcript_text = ""
                try:
                    from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled

                    # Prefer English variants; allow translated if needed
                    try:
                        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=["en", "en-US", "en-GB"])
                    except Exception:
                        # Try first available and translate to English if possible
                        transcripts = YouTubeTranscriptApi.list_transcripts(video_id)
                        try:
                            transcript_obj = transcripts.find_transcript(["en", "en-US", "en-GB"])  # may raise
                            transcript = transcript_obj.fetch()
                        except Exception:
                            try:
                                transcript_obj = next(iter(transcripts))
                                if transcript_obj.is_translatable:
                                    transcript = transcript_obj.translate("en").fetch()
                                else:
                                    transcript = transcript_obj.fetch()
                            except Exception:
                                transcript = []
                    transcript_text = "\n".join([seg.get("text", "") for seg in transcript])
                except Exception:
                    transcript_text = ""

                # Fallback: fetch page and extract description from initial JSON
                if not transcript_text.strip():
                    r = requests.get(context_link, timeout=20, headers={
                        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                    })
                    r.raise_for_status()
                    html = r.text
                    # Attempt to find shortDescription in ytInitialPlayerResponse
                    m = re.search(r'"shortDescription"\s*:\s*"(.*?)"\s*,', html, re.DOTALL)
                    desc = ""
                    if m:
                        desc = m.group(1)
                        # unescape common sequences
                        desc = desc.encode('utf-8').decode('unicode_escape').replace("\\n", "\n")
                    # As backup, try og:description
                    if not desc:
                        soup = BeautifulSoup(html, "html.parser")
                        og = soup.find("meta", attrs={"property": "og:description"})
                        if og and og.get("content"):
                            desc = og.get("content")
                    composed = f"YouTube Video ID: {video_id}\n\nDescription:\n{desc.strip()}" if desc else f"YouTube Video ID: {video_id}"
                    return composed[:max_chars]

                return transcript_text[:max_chars]

        # Generic web page extraction
        r = requests.get(context_link, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        })
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        # Remove script/style
        for bad in soup(["script", "style", "noscript"]):
            bad.extract()
        text = soup.get_text(separator="\n")
        # Normalize whitespace
        lines = [ln.strip() for ln in text.splitlines()]
        text = "\n".join(ln for ln in lines if ln)
        return text[:max_chars]
    except Exception as e:
        return f"[Could not fetch content from link: {e}]"


def _generate_draft_html(title: str, prompt: str, context_link: str, tone: str, style: str) -> str:
    extracted = _fetch_link_context(context_link)
    full_prompt = f"""
You are a professional document writer, highly skilled in generating clean, structured, and semantic HTML content.

Your task is to generate a clear, structured HTML-formatted document based on the following inputs:

Context: {context_link}
Tone: {tone}
Style: {style}

Instruction: {prompt}

Extracted Page Content (use this as the sole factual source; do not invent details beyond it):
{extracted}

---

Formatting Guidelines:
- Use appropriate HTML tags for headings (<h1>, <h2>, <h3>), paragraphs (<p>), lists (<ul>, <ol>, <li>), etc.
- Ensure proper nesting of HTML tags.
- Use <strong> for bold text and <em> for italic text.
- Structure the content for readability and accessibility.
- Keep paragraphs concise.
- Do not include any CSS or JavaScript, only pure HTML.
- The output should be a complete HTML document, including <!DOCTYPE html>, <html>, <head>, and <body> tags.
- Do not include <title> tag in <head>.

Strict Requirements:
- Base all facts strictly on the Extracted Page Content above.
- If the extracted content is insufficient, provide a high-level outline and include a note indicating limited source content.
- Include a source section at the end with the context link.

Only output the final HTML content.
"""

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1400,
        "temperature": 0.2,
        "system": "You are a professional writer, highly skilled in creating clear, structured, and engaging documents.",
        "messages": [
            {"role": "user", "content": full_prompt}
        ]
    }
    result = _invoke_bedrock_claude(body)
    content = result.get("content", [])
    html = content[0]["text"].strip() if content and isinstance(content, list) and content[0].get("text") else ""
    if html.startswith("```html"):
        html = html[len("```html"):].strip()
    if html.endswith("```"):
        html = html[:-len("```")].strip()
    return html


def gdocs_generate_doc_from_link(
    title: str,
    link: str,
    prompt: str,
    tone: str = "Professional",
    style: str = "Concise",
    unified_token: str = None,
) -> dict:
    try:
        # Pre-validate YouTube links must include a resolvable video ID; otherwise, return error to avoid random content
        if "youtube.com" in (link or "") or "youtu.be" in (link or ""):
            vid = _try_extract_youtube_id(link)
            if not vid:
                return {"status": "error", "message": "YouTube link did not include a resolvable video ID. Please provide a direct watch/share/shorts link."}
        html = _generate_draft_html(
            title=title, prompt=prompt, context_link=link, tone=tone, style=style
        )
        # Import HTML to preserve formatting
        return gdocs_create_document_from_html(
            title=title, html=html, unified_token=unified_token
        )
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gdocs_get_document_content(document_id: str, unified_token: str = None) -> dict:
    _, docs_service = get_gdocs_service(unified_token)
    try:
        doc = docs_service.documents().get(documentId=document_id).execute()
        content = doc.get("body", {}).get("content", [])
        text = ""

        for element in content:
            paragraph = element.get("paragraph")
            if paragraph:
                for elem in paragraph.get("elements", []):
                    text += elem.get("textRun", {}).get("content", "")
        return {"document_id": document_id, "content": text.strip()}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def extract_text_with_image_urls(doc_json: dict) -> str:
    """
    Extracts text from Google Docs content and inserts image placeholders
    inline where images appear, using explicit <imageurl> tags (URLs may be
    inaccessible; use gdocs_get_document_content_with_images to get image bytes).
    """
    content = doc_json.get("body", {}).get("content", [])
    inline_objects = doc_json.get("inlineObjects", {})

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


def _extract_content_and_structure(doc_json: dict) -> tuple[str, list[dict]]:
    """
    Extract content string with [IMAGE] placeholders and image positions (start_index, end_index, order).
    Returns (content_str, image_positions). Indices are 1-based per Google Docs API.
    """
    content = doc_json.get("body", {}).get("content", [])
    inline_objects = doc_json.get("inlineObjects", {})

    image_map = {}
    for obj_id, obj in inline_objects.items():
        try:
            image_props = (
                obj["inlineObjectProperties"]["embeddedObject"]["imageProperties"]
            )
            if image_props.get("contentUri"):
                image_map[obj_id] = True
        except KeyError:
            continue

    lines = []
    image_positions = []
    order = 0

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
                if inline_id in image_map:
                    order += 1
                    start_i = pe.get("startIndex")
                    end_i = pe.get("endIndex")
                    if start_i is not None and end_i is not None:
                        image_positions.append(
                            {"start_index": start_i, "end_index": end_i, "order": order}
                        )
                    paragraph_text.append("\n[IMAGE]\n")
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
    content_str = "\n\n".join(lines).strip()
    return content_str, image_positions


def _extract_images_from_exported_html(html: str) -> list[dict]:
    """
    Parse exported Google Doc HTML and return image bytes in document order.
    Images are embedded as data URIs in img src. Returns list of
    {"content_type": str, "bytes": bytes}.
    """
    # Match data:image/<type>;base64,<payload>
    data_uri_pattern = re.compile(
        r"data:(image/[a-zA-Z0-9+.]+);base64,([A-Za-z0-9+/=]+)"
    )
    out = []
    for m in data_uri_pattern.finditer(html):
        try:
            ct = m.group(1)
            b64 = m.group(2)
            out.append({"content_type": ct, "bytes": base64.b64decode(b64)})
        except Exception:
            continue
    return out


def gdocs_export_doc_as_html(document_id: str, unified_token: str = None) -> str:
    """Export a Google Doc as HTML using Drive API (same auth). Returns HTML string."""
    drive_service, _ = get_gdocs_service(unified_token)
    request = drive_service.files().export_media(
        fileId=document_id,
        mimeType="text/html",
    )
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue().decode("utf-8", errors="replace")


def gdocs_get_document_content_with_images(
    document_id: str, unified_token: str = None
) -> dict:
    """
    Get document text with <imageurl> placeholders and image bytes in order.
    Use this when you need to analyze images: images[i] corresponds to the i-th
    <imageurl> placeholder in content (same order as in the doc).

    Returns:
        document_id, content (text with <imageurl>...</imageurl> placeholders),
        images (list of {"content_type": str, "bytes": bytes} in doc order).
    """
    drive_service, docs_service = get_gdocs_service(unified_token)
    try:
        doc = docs_service.documents().get(documentId=document_id).execute()
        content_text = extract_text_with_image_urls(doc)

        html = gdocs_export_doc_as_html(document_id, unified_token)
        images = _extract_images_from_exported_html(html)

        return {
            "document_id": document_id,
            "content": content_text,
            "images": images,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gdocs_get_document_with_structure(
    document_id: str,
    unified_token: str = None,
    image_analysis: bool = False,
) -> dict:
    """
    Fetch a single document from Google Docs API with structural indexes.
    Returns content with [IMAGE] placeholders and image_positions (start_index, end_index, order)
    so updates can be done by index. Optionally includes image bytes when image_analysis=True.
    """
    drive_service, docs_service = get_gdocs_service(unified_token)
    try:
        doc = docs_service.documents().get(documentId=document_id).execute()
        title = doc.get("title", "No Title")
        content_str, image_positions = _extract_content_and_structure(doc)

        out = {
            "document_id": document_id,
            "id": document_id,
            "title": title,
            "content": content_str,
            "image_positions": image_positions,
            "has_images": len(image_positions) > 0,
            "image_count": len(image_positions),
        }

        if image_analysis and image_positions:
            with_images = gdocs_get_document_content_with_images(
                document_id, unified_token
            )
            if with_images.get("status") != "error":
                images_raw = with_images.get("images", []) or []
                images_encoded = []
                for img in images_raw:
                    b = img.get("bytes", b"")
                    if b:
                        media_type = img.get("content_type", "image/png")
                        images_encoded.append(
                            {
                                "type": "base64",
                                "media_type": media_type,
                                "data": base64.b64encode(b).decode("utf-8"),
                            }
                        )
                if images_encoded:
                    out["images"] = images_encoded

        return out
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gdocs_get_documents_by_ids(
    document_ids: list,
    unified_token: str = None,
    image_analysis: bool = False,
) -> dict:
    """
    Fetch documents by ID from Google Docs API (direct, no Mongo).
    Returns same shape as mongo_get_docs: status, retrieved_documents_count, documents, errors.
    Each document includes content, image_positions (start_index, end_index, order), and optionally images.
    """
    if not document_ids:
        return {
            "status": "success",
            "retrieved_documents_count": 0,
            "documents": [],
            "errors": [],
        }
    documents = []
    errors = []
    for doc_id in document_ids:
        try:
            one = gdocs_get_document_with_structure(
                doc_id, unified_token=unified_token, image_analysis=image_analysis
            )
            if one.get("status") == "error":
                errors.append({"document_id": doc_id, "error": one.get("message", "unknown")})
                continue
            documents.append(one)
        except Exception as e:
            errors.append({"document_id": doc_id, "error": str(e)})
    return {
        "status": "success" if documents else "error",
        "retrieved_documents_count": len(documents),
        "documents": documents,
        "errors": errors,
    }


def gdocs_create_document(
    title: str, initial_text: str = "", unified_token: str = None
) -> dict:
    _, docs_service = get_gdocs_service(unified_token)
    try:
        doc = docs_service.documents().create(body={"title": title}).execute()
        doc_id = doc.get("documentId")
        if initial_text:
            docs_service.documents().batchUpdate(
                documentId=doc_id,
                body={
                    "requests": [
                        {"insertText": {"location": {"index": 1}, "text": initial_text}}
                    ]
                },
            ).execute()
        # Include a consistent success flag so higher-level orchestration
        # (e.g., autopilot execution tracking) can reliably detect that
        # the document was created and attach it to execution summaries.
        return {"status": "success", "document_id": doc_id, "title": title}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gdocs_update_document(
    document_id: str,
    index: int,
    operation: str,
    text: str| None = None,
    end_index: int | None = None,
    formatting: dict | None = None,
    target_index: int | None = None,
    unified_token: str = None,
) -> dict:
    """
    Update a Google Doc.

    - If end_index is provided → replace range.
    - If end_index is None → insert at index.
    - preserve_style=True → reapply original style (if style provided from read).
    - style overrides preserved style if provided.
    """

    _, docs_service = get_gdocs_service(unified_token)

    try:
        requests = []
        
        if end_index and end_index <= index:
            return {"status": "error", "message": "Invalid index range"}
        if index < 1:
            return {"status":"error","message":"Invalid start index"}
        # ---------------------------------------------------
        # Normalize formatting (LLM may send flat structure)
        # ---------------------------------------------------
        if formatting and isinstance(formatting, dict):

            text_format = formatting.get("text", {})
            paragraph_format = formatting.get("paragraph", {})

            # merge flat keys safely
            for k, v in list(formatting.items()):

                if k in {"bold","italic","underline","fontSize","color","fontFamily",
                        "highlight","backgroundColor","bgColor","background","mark","quote"}:
                    text_format[k] = v

                elif k in {"bullet","alignment","namedStyleType","ordered","quote"}:
                    paragraph_format[k] = v
                    # normalize ordered alias safely
            

            formatting = {}

            if text_format:
                formatting["text"] = text_format

            if paragraph_format:
                formatting["paragraph"] = paragraph_format
            
            if "paragraph" in formatting:
                pf = formatting["paragraph"]

                if pf.get("ordered") is True:
                    pf["bullet"] = "ordered"

                if "ordered" in pf:
                    del pf["ordered"]
        # ---------------------------------------------------
        # 🧠 Detect formatting-only edit (NO extra API call)
        # ---------------------------------------------------

        is_formatting_only = bool(formatting) and (text is None or text == "") 

        try:
            # ---------------------------------------------------
            # 🧠 Decide operation mode
            # ---------------------------------------------------
            

            has_source_range = index is not None and end_index is not None and end_index > index
            has_target = target_index is not None
            has_text = bool(text and not is_formatting_only)

            delete_len = (end_index - index) if has_source_range else 0


            # ---------------------------------------------------
            # 🚫 Guard — destination inside source
            # ---------------------------------------------------

            if has_source_range and has_target and (index <= target_index <= end_index):
                return {
                    "status": "error",
                    "message": "Invalid move target inside source range"
                }


            # ---------------------------------------------------
            # ⭐ MODE 1 — MOVE
            # ---------------------------------------------------

            if has_source_range and has_target and has_text and operation == "move":

                if target_index < index:
                    # ✅ DELETE first (because mutation is earlier)
                    requests.append(
                        {
                            "deleteContentRange": {
                                "range": {
                                    "startIndex": index,
                                    "endIndex": end_index,
                                }
                            }
                        }
                    )

                    # destination unaffected
                    requests.append(
                        {
                            "insertText": {
                                "location": {"index": target_index},
                                "text": text if text.endswith("\n") else text + "\n",
                            }
                        }
                    )

                else:
                    # ✅ INSERT first (because mutation is later)
                    requests.append(
                        {
                            "insertText": {
                                "location": {"index": target_index},
                                "text": text if text.endswith("\n") else text + "\n",
                            }
                        }
                    )

                    
                    requests.append(
                        {
                            "deleteContentRange": {
                                "range": {
                                    "startIndex": index,
                                    "endIndex": end_index,
                                }
                            }
                        }
                    )


            # ---------------------------------------------------
            # ⭐ MODE 2 — PURE INSERT (target anchor)
            # ---------------------------------------------------

            elif has_target and has_text and operation == "insert":

                requests.append(
                    {
                        "insertText": {
                            "location": {"index": target_index},
                            "text": text if text.endswith("\n") else text + "\n",
                        }
                    }
                )


            # ---------------------------------------------------
            # ⭐ MODE 3 — PURE DELETE
            # ---------------------------------------------------

            elif has_source_range and  operation == "delete":

                requests.append(
                    {
                        "deleteContentRange": {
                            "range": {
                                "startIndex": index,
                                "endIndex": end_index,
                            }
                        }
                    }
                )


            # ---------------------------------------------------
            # ⭐ MODE 4 — LEGACY REPLACE
            # ---------------------------------------------------

            elif has_source_range and has_text and operation == "replace":

                requests.append(
                    {
                        "deleteContentRange": {
                            "range": {
                                "startIndex": index,
                                "endIndex": end_index,
                            }
                        }
                    }
                )

                requests.append(
                    {
                        "insertText": {
                            "location": {"index": index},
                            "text": text if text.endswith("\n") else text + "\n",
                        }
                    }
                )


            # ---------------------------------------------------
            # ⭐ MODE 5 — SIMPLE INSERT AT INDEX
            # ---------------------------------------------------

            elif index is not None and has_text:

                requests.append(
                    {
                        "insertText": {
                            "location": {"index": index},
                            "text": text if text.endswith("\n") else text + "\n",
                        }
                    }
                )

            
        except Exception as e:

            msg = str(e)

            if "insertion index must be inside the bounds of an existing paragraph" in msg:
                return {
                    "status": "error",
                    "message": (
                        "Text insertion failed because the index is at a structural boundary "
                        "(e.g., image, table, or section break). "
                        "Retry by inserting inside a nearby paragraph."
                    ),
                    "failed_index": target_index
                }

            if "Invalid requests" in msg:
                return {
                    "status": "error",
                    "message": (
                        "Document structural edit failed. "
                        "Retry with a safer index range or split the operation."
                    )
                }

            return {
                "status": "error",
                "message": msg
            }

        did_insert = bool(text and not is_formatting_only)

        if did_insert:
            insert_len = len(text) if text.endswith("\n") else len(text) + 1
            new_end_index = index + insert_len
        else:
            new_end_index = end_index

        # ---------------------------------------------------
        # 3️⃣ DETERMINE STYLE TO APPLY
        # ---------------------------------------------------
        if formatting:

            range_end = new_end_index or end_index
            # allow horizontal rule without range
            hr_flag = (
                formatting.get("horizontalRule")
                or formatting.get("paragraph", {}).get("horizontalRule")
                or formatting.get("text", {}).get("horizontalRule")
            )

            if not range_end and not hr_flag:
                return {"status": "error", "message": "Formatting requires end_index"}
            

            text_format = formatting.get("text") or {}
            paragraph_format = formatting.get("paragraph") or {}

            # =========================
            # TEXT STYLE NORMALIZATION
            # =========================
            if text_format:

                text_style_fields = []
                style_payload = {}

                # ---------- bold ----------
                if isinstance(text_format.get("bold"), bool):
                    style_payload["bold"] = text_format["bold"]
                    text_style_fields.append("bold")

                # ---------- italic ----------
                if isinstance(text_format.get("italic"), bool):
                    style_payload["italic"] = text_format["italic"]
                    text_style_fields.append("italic")

                # ---------- underline ----------
                if isinstance(text_format.get("underline"), bool):
                    style_payload["underline"] = text_format["underline"]
                    text_style_fields.append("underline")

                # ---------- font size ----------
                fs = text_format.get("fontSize")
                if isinstance(fs, (int, float)) and fs > 0:
                    style_payload["fontSize"] = {
                        "magnitude": fs,
                        "unit": "PT",
                    }
                    text_style_fields.append("fontSize")

                # ---------- highlight ----------
                highlight = text_format.get("highlight")
                if highlight is not None:

                    if highlight is False:
                        style_payload["backgroundColor"] = None
                        text_style_fields.append("backgroundColor")

                    else:
                        if highlight is True:
                            highlight = {"red": 1, "green": 1, "blue": 0}

                        elif isinstance(highlight, str) and highlight.startswith("#"):
                            r = int(highlight[1:3], 16) / 255
                            g = int(highlight[3:5], 16) / 255
                            b = int(highlight[5:7], 16) / 255
                            highlight = {"red": r, "green": g, "blue": b}

                        elif isinstance(highlight, dict):
                            pass

                        else:
                            highlight = {"red": 1, "green": 1, "blue": 0}

                        style_payload["backgroundColor"] = {
                            "color": {"rgbColor": highlight}
                        }
                        text_style_fields.append("backgroundColor")

                # ---------- text color ----------
                color = text_format.get("color")
                if color is not None:

                    if isinstance(color, str) and color.startswith("#"):
                        r = int(color[1:3], 16) / 255
                        g = int(color[3:5], 16) / 255
                        b = int(color[5:7], 16) / 255
                        color = {"red": r, "green": g, "blue": b}

                    elif isinstance(color, dict):
                        pass
                    else:
                        color = None

                    if color:
                        style_payload["foregroundColor"] = {
                            "color": {"rgbColor": color}
                        }
                        text_style_fields.append("foregroundColor")

                # ---------- font family ----------
                ff = text_format.get("fontFamily")
                if isinstance(ff, str) and ff.strip():
                    style_payload["weightedFontFamily"] = {
                        "fontFamily": ff
                    }
                    text_style_fields.append("weightedFontFamily")

                # ---------- apply ----------
                if style_payload:
                    requests.append(
                        {
                            "updateTextStyle": {
                                "range": {
                                    "startIndex": index,
                                    "endIndex": range_end,
                                },
                                "textStyle": style_payload,
                                "fields": ",".join(text_style_fields),
                            }
                        }
                    )

            # =========================
            # PARAGRAPH STYLE NORMALIZATION
            # =========================
            if paragraph_format:

                paragraph_fields = []
                paragraph_payload = {}

                # ---------- named style ----------
                VALID_STYLES = {
                    "NORMAL_TEXT",
                    "HEADING_1",
                    "HEADING_2",
                    "HEADING_3",
                    "HEADING_4",
                    "HEADING_5",
                    "HEADING_6",
                    "TITLE",
                    "SUBTITLE",
                }

                nst = paragraph_format.get("namedStyleType")
                if nst in VALID_STYLES:
                    paragraph_payload["namedStyleType"] = nst
                    paragraph_fields.append("namedStyleType")

                # ---------- alignment ----------
                ALIGN_MAP = {
                    "left": "START",
                    "center": "CENTER",
                    "right": "END",
                    "justify": "JUSTIFIED",
                }

                align = paragraph_format.get("alignment")

                if isinstance(align, str):
                    align = ALIGN_MAP.get(align.lower(), align)

                if align in {"START", "CENTER", "END", "JUSTIFIED"}:
                    paragraph_payload["alignment"] = align
                    paragraph_fields.append("alignment")

                # ---------- apply ----------
                if paragraph_payload:
                    requests.append(
                        {
                            "updateParagraphStyle": {
                                "range": {
                                    "startIndex": index,
                                    "endIndex": range_end,
                                },
                                "paragraphStyle": paragraph_payload,
                                "fields": ",".join(paragraph_fields),
                            }
                        }
                    )
        # ---------------------------------------------------
        # 5️⃣ APPLY BULLETS (if requested)
        # ---------------------------------------------------
        
        bullet_flag = None
        range_end = new_end_index if new_end_index else end_index
        
        
        if formatting and isinstance(formatting, dict):
            paragraph_format = formatting.get("paragraph") or {}

            if isinstance(paragraph_format, dict) and "bullet" in paragraph_format:
                bullet_flag = paragraph_format.get("bullet")
                
        if bullet_flag is not None and not range_end:
            return {"status":"error","message":"Formatting requires end_index"}
        if bullet_flag:

            preset = "BULLET_DISC_CIRCLE_SQUARE"

            if bullet_flag == "ordered":
                preset = "NUMBERED_DECIMAL_ALPHA_ROMAN"

            requests.append(
                {
                    "createParagraphBullets": {
                        "range": {
                            "startIndex": index,
                            "endIndex": range_end - 1,   # ⭐ safer
                        },
                        "bulletPreset": preset,
                    }
                }
            )

        elif bullet_flag is False:
            requests.append(
                {
                    "deleteParagraphBullets": {
                        "range": {
                            "startIndex": index,
                            "endIndex": range_end-1,
                        }
                    }
                }
            )
            
        # ---------- quote ----------
        quote_flag = None

        if "quote" in paragraph_format:
            quote_flag = paragraph_format["quote"]

        elif "quote" in formatting:
            quote_flag = formatting["quote"]

        elif "quote" in formatting.get("text", {}):
            quote_flag = formatting["text"]["quote"]

        # ---------------------------------------------------
        # ⭐ APPLY / REMOVE QUOTE (paragraph wise)
        # ---------------------------------------------------
        print(f"quote_flag: {quote_flag}")
        if quote_flag is not None:
            if not range_end:
                return {"status": "error", "message": "Formatting requires end_index"}

            if quote_flag is True:
                requests.append({
                    "updateParagraphStyle": {
                        "range": {
                            "startIndex": index,
                            "endIndex": range_end,
                        },
                        "paragraphStyle": {
                            "indentStart": {"magnitude": 36, "unit": "PT"},
                            "spaceAbove": {"magnitude": 4, "unit": "PT"},
                            "spaceBelow": {"magnitude": 4, "unit": "PT"},
                            "borderLeft": {
                                "color": {
                                    "color": {
                                        "rgbColor": {
                                            "red": 0.45,
                                            "green": 0.45,
                                            "blue": 0.45
                                        }
                                    }
                                },
                                "width": {"magnitude": 2, "unit": "PT"},
                                "padding": {"magnitude": 8, "unit": "PT"},
                                "dashStyle": "SOLID",
                            },
                        },
                        "fields": "indentStart,spaceAbove,spaceBelow,borderLeft",
                    }
                })

            else:
                # REMOVE quote
                requests.append({
                    "updateParagraphStyle": {
                        "range": {
                            "startIndex": index,
                            "endIndex": range_end,
                        },
                        "paragraphStyle": {
                            "indentStart": {"magnitude": 0, "unit": "PT"},
                            "spaceAbove": {"magnitude": 0, "unit": "PT"},
                            "spaceBelow": {"magnitude": 0, "unit": "PT"},
                            "borderLeft": None,
                        },
                        "fields": "indentStart,spaceAbove,spaceBelow,borderLeft",
                    }
                })
        
        if not requests:
            return {"status": "success", "message": "No changes to apply"}
        # ---------------------------------------------------
        # 5️⃣ EXECUTE BATCH UPDATE
        # ---------------------------------------------------
        docs_service.documents().batchUpdate(
            documentId=document_id,
            body={"requests": requests},
        ).execute()

        return {"status": "success", "document_id": document_id}

    except Exception as e:
        return {"status": "error", "message": str(e)}
    
def gdocs_update_image(
    document_id: str,
    image_id: str,
    index: int,
    end_index: int,
    operation: str,
    target_index: int | None = None,
    text: str | None = None,
    unified_token: str | None = None,
) -> dict:

    try:

        # ---------- validation ----------

        allowed_ops = {
            "move",
            "delete",
            "insert_text_before",
            "insert_text_after",
        }

        if operation not in allowed_ops:
            return {"status": "error", "message": "Unsupported image operation"}

        if end_index is None:
            return {"status": "error", "message": "end_index required for image operation"}

        if index is None:
            return {"status": "error", "message": "index required for image operation"}

        if end_index <= index:
            return {"status": "error", "message": "Invalid image range"}

        if operation == "move" and target_index is None:
            return {"status": "error", "message": "Move operation requires target_index"}

        if operation in ("insert_text_before", "insert_text_after") and not text:
            return {"status": "error", "message": "Insert text operation requires text"}

        image_len = end_index - index

        # ---------- fetch document ----------

        _, docs_service = get_gdocs_service(unified_token)

        doc = docs_service.documents().get(
            documentId=document_id
        ).execute()

        inline_objects = doc.get("inlineObjects", {})

        if image_id not in inline_objects:
            return {"status": "error", "message": "Image not found in document"}

        embedded = (
            inline_objects.get(image_id, {})
            .get("inlineObjectProperties", {})
            .get("embeddedObject", {})
        )

        image_props = embedded.get("imageProperties", {})
        image_uri = image_props.get("contentUri")

        if not image_uri:
            return {"status": "error", "message": "Unable to resolve image source"}

        size = embedded.get("size", {})

        height = size.get("height", {"magnitude": 300, "unit": "PT"})
        width = size.get("width", {"magnitude": 300, "unit": "PT"})

        # ---------- build requests ----------

        requests: list[dict] = []

        if operation == "delete":

            requests.append(
                {
                    "deleteContentRange": {
                        "range": {
                            "startIndex": index,
                            "endIndex": end_index,
                        }
                    }
                }
            )

        elif operation == "insert_text_before":

            requests.append(
                {
                    "insertText": {
                        "location": {"index": index},
                        "text": text,
                    }
                }
            )

        elif operation == "insert_text_after":

            requests.append(
                {
                    "insertText": {
                        "location": {"index": end_index},
                        "text": text,
                    }
                }
            )

        elif operation == "move":

            adjusted_target = target_index

            if target_index > index:
                adjusted_target = target_index - image_len

            requests.append(
                {
                    "deleteContentRange": {
                        "range": {
                            "startIndex": index,
                            "endIndex": end_index,
                        }
                    }
                }
            )

            requests.append(
                {
                    "insertInlineImage": {
                        "location": {"index": adjusted_target},
                        "uri": image_uri,
                        "objectSize": {
                            "height": height,
                            "width": width,
                        },
                    }
                }
            )

        # ---------- execute ----------

        result = (
            docs_service.documents()
            .batchUpdate(
                documentId=document_id,
                body={"requests": requests},
            )
            .execute()
        )

        return {
            "status": "success",
            "operation": operation,
            "image_id": image_id,
            "document_id": document_id,
        }

    except Exception as e:

        return {
            "status": "error",
            "message": str(e),
        }

def gdocs_update_table(
    document_id: str,
    operation: str,
    table_start_index: int | None = None,
    row_index: int | None = None,
    column_index: int | None = None,
    rows: int | None = None,
    columns: int | None = None,
    text: str | None = None,
    cell_start_index: int | None = None,
    cell_end_index: int | None = None,
    target_index: int | None = None,
    unified_token: str = None,
) -> dict:

    _, docs_service = get_gdocs_service(unified_token)
    
    try:

        requests = []

        # ---------------------------------------------------
        # ⭐ INSERT TABLE
        # ---------------------------------------------------
        if operation == "insert_table":

            if table_start_index is None or not rows or not columns:
                return {"status": "error", "message": "table_start_index, rows, columns required"}

            requests.append({
                "insertTable": {
                    "rows": rows,
                    "columns": columns,
                    "location": {
                        "index": table_start_index
                    }
                }
            })

        # ---------------------------------------------------
        # ⭐ INSERT ROW
        # ---------------------------------------------------
        elif operation == "add_row":

            if table_start_index is None:
                return {"status": "error", "message": "table_start_index required"}

            if row_index is None:
                doc = docs_service.documents().get(documentId=document_id).execute()
                for element in doc.get("body", {}).get("content", []):
                    if element.get("table") and abs(element.get("startIndex", 0) - table_start_index) <= 2:
                        row_index = len(element["table"]["tableRows"]) - 1
                        break

            requests.append({
                "insertTableRow": {
                    "tableCellLocation": {
                        "tableStartLocation": {
                            "index": table_start_index
                        },
                        "rowIndex": row_index
                    },
                    "insertBelow": True
                }
            })

        # ---------------------------------------------------
        # ⭐ INSERT COLUMN
        # ---------------------------------------------------
        elif operation == "add_column":

            if table_start_index is None:
                return {"status": "error", "message": "table_start_index required"}

            if column_index is None:
                doc = docs_service.documents().get(documentId=document_id).execute()
                for element in doc.get("body", {}).get("content", []):
                    if element.get("table") and abs(element.get("startIndex", 0) - table_start_index) <= 2:
                        first_row = element["table"]["tableRows"][0]
                        column_index = len(first_row.get("tableCells", [])) - 1
                        break
            
            requests.append({
                "insertTableColumn": {
                    "tableCellLocation": {
                        "tableStartLocation": {
                            "index": table_start_index
                        },
                        "columnIndex": column_index
                    },
                    "insertRight": True
                }
            })

        # ---------------------------------------------------
        # ⭐ DELETE ROW
        # ---------------------------------------------------
        elif operation == "delete_row":

            if table_start_index is None or row_index is None:
                return {"status": "error", "message": "table_start_index and row_index required"}

            doc = docs_service.documents().get(documentId=document_id).execute()

            actual_start = None
            for element in doc.get("body", {}).get("content", []):
                if element.get("table"):
                    el_start = element.get("startIndex", 0)
                    if abs(el_start - table_start_index) <= 2:
                        actual_start = el_start
                        break

            if actual_start is None:
                return {"status": "error", "message": "Table not found near provided index"}

            requests.append({
                "deleteTableRow": {
                    "tableCellLocation": {
                        "tableStartLocation": {
                            "index": actual_start
                        },
                        "rowIndex": row_index
                    }
                }
            })
        # ---------------------------------------------------
        # ⭐ DELETE COLUMN
        # ---------------------------------------------------
        elif operation == "delete_column":

            if table_start_index is None or column_index is None:
                return {"status": "error", "message": "table_start_index and column_index required"}

            doc = docs_service.documents().get(documentId=document_id).execute()
            
            # for element in doc.get("body", {}).get("content", []):
            #     if element.get("table"):
            #         print(f"\nTable at startIndex={element.get('startIndex')}")
            #         for i, row in enumerate(element["table"]["tableRows"]):
            #             cells = row.get("tableCells", [])
            #             print(f"  Row {i}: {len(cells)} cells")
            #             for j, cell in enumerate(cells):
            #                 print(f"    Cell {j}: startIndex={cell.get('startIndex')} endIndex={cell.get('endIndex')}")
            #             for j, cell in enumerate(cells):
            #                 span = cell.get("tableCellStyle", {}).get("columnSpan", 1)
            #                 print(f"    Cell {j}: startIndex={cell.get('startIndex')} endIndex={cell.get('endIndex')} columnSpan={span}")
            actual_start = None
            target_row_index = None

            for element in doc.get("body", {}).get("content", []):
                if element.get("table") and abs(element.get("startIndex", 0) - table_start_index) <= 2:
                    actual_start = element.get("startIndex")
                    rows = element["table"]["tableRows"]
                    max_cells = 0
                    for i, row in enumerate(rows):
                        cells = row.get("tableCells", [])
                        all_single = all(
                            cell.get("tableCellStyle", {}).get("columnSpan", 1) == 1
                            for cell in cells
                        )
                        if all_single and len(cells) > 1:
                            max_cells = len(cells)
                            target_row_index = i
                            break

            if actual_start is None:
                return {"status": "error", "message": "Table not found near provided index"}

            if column_index >= max_cells:
                return {"status": "error", "message": "column_index out of range"}

            requests.append({
                "deleteTableColumn": {
                    "tableCellLocation": {
                        "tableStartLocation": {"index": actual_start},
                        "rowIndex": target_row_index,
                        "columnIndex": column_index
                    }
                }
            })
        # ---------------------------------------------------
        # ⭐ DELETE TABLE
        # ---------------------------------------------------
        elif operation == "delete_table":

            if table_start_index is None:
                return {"status": "error", "message": "table_start_index required"}

            doc = docs_service.documents().get(documentId=document_id).execute()

            table_end_index = None
            for element in doc.get("body", {}).get("content", []):
                if element.get("table") and abs(element.get("startIndex", 0) - table_start_index) <= 2:
                    table_end_index = element.get("endIndex")
                    break

            if table_end_index is None:
                return {"status": "error", "message": "Table not found near provided index"}

            requests.append({
                "deleteContentRange": {
                    "range": {
                        "startIndex": table_start_index,
                        "endIndex": table_end_index
                    }
                }
            })

        # ---------------------------------------------------
        # ⭐ UPDATE CELL TEXT
        # ---------------------------------------------------
        elif operation == "update_cell":

            if not text or row_index is None or column_index is None:
                return {"status": "error", "message": "text, row_index and column_index required"}

            doc = docs_service.documents().get(documentId=document_id).execute()

            cell_start_index = None
            cell_end_index = None

            for element in doc.get("body", {}).get("content", []):
                if element.get("table") and abs(element.get("startIndex", 0) - table_start_index) <= 2:
                    rows = element["table"]["tableRows"]
                    if row_index >= len(rows):
                        return {"status": "error", "message": "row_index out of range"}
                    cells = rows[row_index].get("tableCells", [])
                    if column_index >= len(cells):
                        return {"status": "error", "message": "column_index out of range"}
                    cell = cells[column_index]
                    cell_start_index = cell["content"][0]["startIndex"]
                    cell_end_index = cell["content"][-1]["endIndex"] - 1
                    break

            if cell_start_index is None:
                return {"status": "error", "message": "Cell not found"}

            if cell_start_index < cell_end_index:
                requests.append({
                    "deleteContentRange": {
                        "range": {
                            "startIndex": cell_start_index,
                            "endIndex": cell_end_index
                        }
                    }
                })

            requests.append({
                "insertText": {
                    "location": {
                        "index": cell_start_index
                    },
                    "text": text
                }
            })
        else:
            return {"status": "error", "message": f"Unsupported operation {operation}"}

        # ---------------------------------------------------
        # ⭐ EXECUTE
        # ---------------------------------------------------
        if not requests:
            return {"status": "success", "message": "No changes to apply"}

        docs_service.documents().batchUpdate(
            documentId=document_id,
            body={"requests": requests},
        ).execute()

        return {"status": "success", "document_id": document_id}

    except Exception as e:
        return {"status": "error", "message": str(e)}


def gdocs_get_table_content(
    document_id: str,
    table_start_index: int,
    unified_token: str = None,
) -> dict:

    _, docs_service = get_gdocs_service(unified_token)

    try:
        doc = docs_service.documents().get(
            documentId=document_id
        ).execute()

        content = doc.get("body", {}).get("content", [])

        target_table = None

        # -------------------------------------------------
        # 🔎 FIND TABLE BY START INDEX
        # -------------------------------------------------
        for element in content:
            if element.get("startIndex") == table_start_index and element.get("table"):
                target_table = element.get("table")
                break

        if not target_table:
            return {
                "status": "error",
                "message": "Table not found at provided index"
            }

        rows_data = []
        rows = target_table.get("tableRows", [])

        # -------------------------------------------------
        # 📊 PARSE TABLE CELLS
        # -------------------------------------------------
        for row in rows:

            row_cells = []

            for cell in row.get("tableCells", []):

                cell_text = ""

                for cell_content in cell.get("content", []):

                    paragraph = cell_content.get("paragraph")
                    if not paragraph:
                        continue

                    for elem in paragraph.get("elements", []):

                        text_run = elem.get("textRun")
                        if not text_run:
                            continue

                        cell_text += text_run.get("content", "")

                row_cells.append(cell_text.strip())

            rows_data.append(row_cells)

        return {
            "status": "success",
            "table": {
                "table_start_index": table_start_index,
                "rows": len(rows_data),
                "columns": len(rows_data[0]) if rows_data else 0,
                "grid": rows_data,
            }
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }
def gdocs_add_comment(
    document_id: str,
    text: str,
    unified_token: str = None,
) -> dict:
    """
    Add a top-level comment to a Google Doc / Sheet / Slide file via the Drive API.

    This is the dedicated tool for comment_reply-style actions. The comment is
    always authored as the currently authenticated GSuite user; Google controls
    the actual author email and it cannot be overridden in this request.
    """
    drive_service, _ = get_gdocs_service(unified_token)
    try:
        comment_body = {
            "content": text,
        }

        comment = (
            drive_service.comments()
            .create(
                fileId=document_id,
                body=comment_body,
                fields="id,content,createdTime"
            )
            .execute()
        )

        return {
            "status": "success",
            "document_id": document_id,
            "comment_id": comment.get("id"),
            "content": comment.get("content"),
            "createdTime": comment.get("createdTime"),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}



def gdocs_delete_document(document_id: str, unified_token: str = None) -> dict:
    drive_service, _ = get_gdocs_service(unified_token)
    try:
        drive_service.files().update(
            fileId=document_id, body={"trashed": True}
        ).execute()
        return {"status": "success", "document_id": document_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gdocs_share_document(
    document_id: str, email: str, role: str = "writer", unified_token: str = None
) -> dict:
    drive_service, _ = get_gdocs_service(unified_token)
    try:
        drive_service.permissions().create(
            fileId=document_id,
            body={"type": "user", "role": role, "emailAddress": email},
            fields="id",
        ).execute()
        return {"status": "success", "shared_with": email, "document_id": document_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gdocs_search_in_document(
    document_id: str, keyword: str, unified_token: str = None
) -> dict:
    from difflib import get_close_matches

    _, docs_service = get_gdocs_service(unified_token)
    try:
        doc = docs_service.documents().get(documentId=document_id).execute()
        body_elements = doc.get("body", {}).get("content", [])
        full_text = ""
        matches = []

        for element in body_elements:
            if "paragraph" in element:
                for el in element["paragraph"].get("elements", []):
                    text_run = el.get("textRun", {})
                    content = text_run.get("content", "")
                    if content:
                        if keyword.lower() in content.lower():
                            matches.append(content.strip())
                        full_text += content

        return {
            "document_id": document_id,
            "keyword": keyword,
            "matches": matches,
            "total_occurrences": len(matches),
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}

def search_docs_by_title(
    keyword: str, limit: int = 10, unified_token: str = None
) -> dict:
    drive_service, _ = get_gdocs_service(unified_token)
    try:
        query = f"name contains '{keyword}' and mimeType='application/vnd.google-apps.document' and trashed=false"
        response = (
            drive_service.files()
            .list(q=query, pageSize=limit, fields="files(id, name, modifiedTime)")
            .execute()
        )
        return {"matches": response.get("files", [])}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_doc_history(document_id: str, unified_token: str = None) -> dict:
    drive_service, _ = get_gdocs_service(unified_token)
    try:
        metadata = (
            drive_service.files()
            .get(
                fileId=document_id,
                fields="id, name, modifiedTime, createdTime, owners, lastModifyingUser",
            )
            .execute()
        )
        return {
            "document_id": metadata.get("id"),
            "name": metadata.get("name"),
            "created_time": metadata.get("createdTime"),
            "modified_time": metadata.get("modifiedTime"),
            "owner": metadata.get("owners", [{}])[0].get("emailAddress"),
            "last_modified_by": metadata.get("lastModifyingUser", {}).get(
                "emailAddress"
            ),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
