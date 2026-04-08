from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
import os
import io
import json
import time
import boto3
import logging
import random
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Union, Tuple, BinaryIO
from clients.db_method import get_user_tool_access_token
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Gamma API Configuration
GAMMA_API_KEY = os.getenv("GAMMA_API")
GAMMA_BASE_URL = os.getenv("GAMMA_BASE_URL", "https://public-api.gamma.app/v1.0")

if not GAMMA_API_KEY:
    logger.warning("GAMMA_API environment variable is not set. Gamma API functionality will be limited.")

# BASE_URL = "http://3.6.95.164:5000/users"


# # Example: Call get_tool_token endpoint
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


def get_gslides_service(unified_token: str = None) -> Any:
    """Get Google Slides service with optional unified token.
    
    Args:
        unified_token: Optional unified token for authentication
        
    Returns:
        Tuple of (drive_service, slides_service)
    """
    if not unified_token:
        # Return None for both services if no token provided
        return None, None
        
    tool_name = "Gsuite"
    result, status = get_user_tool_access_token(unified_token, tool_name)
    if isinstance(result, tuple):
        result, status = result
        if status != 200:
            raise ValueError(result.get("error", "Failed to get access token"))

    access_data = result.get("access_token", {})
    if not access_data:
        raise ValueError("No access data found in the response")
        
    # Note: Don't specify scopes - use whatever was originally granted
    # to avoid "invalid_scope" errors during token refresh
    creds = Credentials(
        token=access_data.get("token"),
        refresh_token=access_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=access_data.get("client_id"),
        client_secret=access_data.get("client_secret"),
    )

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as e:
            print(f"Error refreshing token: {e}")
            raise

    drive_service = build('drive', 'v3', credentials=creds) if creds else None
    slides_service = build('slides', 'v1', credentials=creds) if creds else None
    
    return drive_service, slides_service
    #     creds.refresh(Request())
    #     update_user_tool_access_token(unified_token, tool_name, {
    #         "token": creds.token,
    #         "refresh_token": creds.refresh_token,
    #         "client_id": creds.client_id,
    #         "client_secret": creds.client_secret,
    #         "expiry": creds.expiry.isoformat() if creds.expiry else None
    #     })

    drive_service = build("drive", "v3", credentials=creds)
    slides_service = build("slides", "v1", credentials=creds)
    return drive_service, slides_service


def gslides_list_presentations(page_size: int = 20, unified_token: str = None) -> list:
    drive_service, _ = get_gslides_service(unified_token)

    query = "mimeType='application/vnd.google-apps.presentation' and trashed=false"
    response = (
        drive_service.files()
        .list(
            q=query,
            pageSize=page_size,
            fields="files(id, name, modifiedTime, owners, shared)",
        )
        .execute()
    )

    files = response.get("files", [])
    return [
        {
            "id": f["id"],
            "title": f["name"],
            "owner": f["owners"][0]["displayName"] if "owners" in f else "Unknown",
            "modifiedTime": f.get("modifiedTime", "Unknown"),
            "shared": f.get("shared", False),
        }
        for f in files
    ]


def gslides_create_presentation(title: str, unified_token: str = None) -> dict:
    """Create a new Google Slides presentation.
    
    Args:
        title: Title of the presentation
        unified_token: Optional unified token for authentication
        
    Returns:
        Dictionary with presentation ID and title
    """
    try:
        _, slides_service = get_gslides_service(unified_token)
        if not slides_service:
            raise ValueError("Google Slides service not available. Check authentication.")
            
        body = {"title": title}
        pres = slides_service.presentations().create(body=body).execute()
        return {"id": pres["presentationId"], "title": pres["title"]}
    except Exception as e:
        raise Exception(f"Failed to create presentation: {str(e)}")


# Global dictionary to track in-progress presentations
_in_progress_presentations = {}

def gamma_create_presentation(
    title: str,
    input_text: str,
    theme_id: Optional[str] = None,
    num_cards: int = 5,
    format_: str = "presentation",
    text_mode: str = "generate",
    unified_token: str = None,
    token: Optional[str] = None,
    text_only: Optional[bool] = True,
) -> Dict[str, Any]:
    """Create a presentation using Gamma API and optionally save to Google Drive.
    
    This function handles the complete workflow:
    1. Creates a Gamma presentation with exportAs: "pptx"
    2. Polls for completion and extracts pptxUrl
    3. Downloads the PPTX file to a temporary location
    4. Uploads to Google Drive and converts to Google Slides
    
    Args:
        title: Title of the presentation
        input_text: Main content for the presentation
        theme_id: Optional theme ID
        num_cards: Number of slides/cards to generate
        format_: Output format (presentation, document, social, webpage)
        text_mode: Text processing mode (generate, condense, preserve)
        unified_token: Optional unified token for Google Drive export (alias: token)
        token: Alias for unified_token
        text_only: If True, generates text-only slides without images
        
    Returns:
        Dictionary with generation details and optionally Google Drive file info
        
    Raises:
        ValueError: If required parameters are missing or invalid
        Exception: If there's an error creating the presentation
    """
    import tempfile
    
    # Input validation
    if not title or not input_text:
        raise ValueError("Both 'title' and 'input_text' are required parameters")
    
    if not GAMMA_API_KEY:
        raise ValueError("Gamma API key not found in environment variables")
    
    # Allow 'token' alias from callers (e.g., tool calls passing 'token')
    if unified_token is None and token:
        unified_token = token
    
    # Create a unique key for this presentation request
    request_key = f"{title}_{hash(input_text[:100])}"
    
    # Check if this presentation is already being processed
    if request_key in _in_progress_presentations:
        return {
            "status": "in_progress",
            "message": "This presentation is already being processed. Please wait...",
            "request_key": request_key
        }
    
    temp_file_path = None
    
    try:
        # Mark this presentation as in progress
        _in_progress_presentations[request_key] = {
            "status": "processing",
            "start_time": time.time(),
            "title": title
        }
        
        # Step 1: Create Gamma presentation with exportAs: "pptx"
        url = f"{GAMMA_BASE_URL.rstrip('/')}/generations"
        headers = {
            "Content-Type": "application/json",
            "X-API-KEY": GAMMA_API_KEY,
            "Accept": "application/json"
        }
        
        payload = {
            "inputText": input_text,
            "textMode": text_mode,
            "format": format_,
            "numCards": num_cards,
            "exportAs": "pptx",  # 🔥 Request PPTX export
        }
        
        if theme_id:
            payload["themeId"] = theme_id
        if text_only:
            payload["imageOptions"] = {"source": "noImages"}
        
        print(f"Creating Gamma presentation: {title}")
        logger.info("Creating Gamma presentation: %s", title)
        
        # Create the presentation
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        
        generation_id = data.get("generationId")
        if not generation_id:
            raise ValueError("No generation ID in response")
        
        print(f"Polling for completion of generation {generation_id}")
        logger.info("Polling for completion of generation %s", generation_id)
        
        # Step 2: Poll for completion
        result = _poll_gamma_generation(generation_id)
        
        # Log the full response for debugging
        logger.info(f"Poll response keys: {list(result.keys())}")
        logger.debug(f"Full poll response: {json.dumps(result, default=str)[:1000]}")

        # Step 3: Extract pptxUrl from multiple possible locations
        pptx_url: Optional[str] = None
        pdf_url: Optional[str] = None
        gamma_file_id: Optional[str] = None
        
        # Extract gamma file ID from result (needed for export request)
        gamma_file_id = (
            result.get("id") or 
            result.get("gammaId") or 
            result.get("fileId") or
            result.get("docId")
        )
        
        # First check if pptxUrl is directly in the poll response
        exports = result.get("exports") if isinstance(result.get("exports"), dict) else {}
        download_urls = result.get("downloadUrls") if isinstance(result.get("downloadUrls"), dict) else {}
        output = result.get("output") if isinstance(result.get("output"), dict) else {}
        
        pptx_url = (
            result.get("pptxUrl")
            or result.get("exportUrl")
            or (exports.get("pptx") if exports else None)
            or (exports.get("pptxUrl") if exports else None)
            or (download_urls.get("pptx") if download_urls else None)
            or (output.get("pptxUrl") if output else None)
            or (output.get("exportUrl") if output else None)
        )
        pdf_url = (
            result.get("pdfUrl")
            or (exports.get("pdf") if exports else None)
            or (download_urls.get("pdf") if download_urls else None)
            or (output.get("pdfUrl") if output else None)
        )
        
        # If no pptxUrl found, try to request an export explicitly
        if not pptx_url and result.get("status") == "completed":
            logger.info("No pptxUrl in poll response, requesting export explicitly...")
            pptx_url, pdf_url = _request_gamma_export(generation_id, gamma_file_id)
        
        # Step 4: If unified_token provided, download PPTX and upload to Google Drive
        if unified_token and pptx_url:
            print("Downloading PPTX from Gamma and uploading to Google Drive")
            logger.info("Starting PPTX download and Google Drive upload workflow")
            
            try:
                # Download PPTX to temporary file
                print(f"Downloading PPTX from: {pptx_url}")
                logger.info(f"Downloading PPTX from: {pptx_url}")
                
                download_resp = requests.get(pptx_url, stream=True, timeout=120)
                download_resp.raise_for_status()
                
                # Create temporary file
                with tempfile.NamedTemporaryFile(mode='wb', suffix='.pptx', delete=False) as temp_file:
                    for chunk in download_resp.iter_content(chunk_size=8192):
                        if chunk:
                            temp_file.write(chunk)
                    temp_file_path = temp_file.name
                
                logger.info(f"PPTX downloaded to temporary file: {temp_file_path}")
                print(f"PPTX downloaded successfully ({os.path.getsize(temp_file_path)} bytes)")
                
                # Upload to Google Drive and convert to Slides
                print("Uploading to Google Drive and converting to Google Slides...")
                logger.info("Uploading PPTX to Google Drive")
                
                drive_info = upload_local_pptx_to_slides(
                    file_path=temp_file_path,
                    title=title,
                    folder_id=None,
                    unified_token=unified_token
                )
                
                result.update({"driveInfo": drive_info})
                logger.info("Successfully uploaded to Google Drive and converted to Slides")
                print(f"✅ Successfully created Google Slides: {drive_info.get('webViewLink')}")
                
            except Exception as e:
                error_msg = f"Error in download/upload workflow: {str(e)}"
                print(error_msg)
                logger.error(error_msg, exc_info=True)
                result["drive_export_error"] = str(e)
                result["status"] = "success"
            finally:
                # Clean up temporary file
                if temp_file_path and os.path.exists(temp_file_path):
                    try:
                        os.unlink(temp_file_path)
                        logger.info(f"Cleaned up temporary file: {temp_file_path}")
                    except Exception as e:
                        logger.warning(f"Failed to delete temporary file: {e}")
                        
        elif unified_token and pdf_url:
            # Fallback to PDF upload if PPTX is unavailable
            print("PPTX URL missing; attempting PDF export to Google Drive")
            logger.info("PPTX URL missing; attempting PDF export to Google Drive")
            try:
                drive_info = _export_generic_to_google_drive(
                    file_url=pdf_url,
                    filename=f"{title}.pdf",
                    unified_token=unified_token,
                )
                result.update({"driveInfo": drive_info})
                logger.info("Successfully exported PDF to Google Drive")
            except Exception as e:
                error_msg = f"Error exporting PDF to Google Drive: {str(e)}"
                print(error_msg)
                logger.error(error_msg, exc_info=True)
                result["drive_export_error"] = str(e)
                result["status"] = "success"
                result["message"] = f"Presentation created but export to Google Drive failed: {str(e)}"
        else:
            # Add explicit logs for skipped Drive export
            if not unified_token:
                logger.info("Skipping Drive export: no unified_token provided")
            elif not pptx_url and not pdf_url:
                logger.warning("Skipping Drive export: no export URLs (pptxUrl/pdfUrl) returned by Gamma")
        
        # Update status to completed
        _in_progress_presentations[request_key]["status"] = "completed"
        _in_progress_presentations[request_key]["end_time"] = time.time()
        
        # Prepare response data
        response_data = {
            "id": result.get("id"),
            "title": title,
            "status": "completed",
            "gamma_url": result.get("gammaUrl") or result.get("url"),
            "pptx_url": pptx_url,
            "pdf_url": pdf_url,
            "created_at": datetime.now().isoformat()
        }
        
        # Add drive info if available
        if result.get("driveInfo"):
            response_data["drive_info"] = result["driveInfo"]
        elif result.get("drive_export_error"):
            response_data["export_warning"] = result["drive_export_error"]
        # If a Drive upload was requested but pptxUrl is missing, surface a warning
        if unified_token and not pptx_url:
            response_data["export_warning"] = (
                response_data.get("export_warning")
                or "pptxUrl not returned by Gamma. Ensure exportAs='pptx' and sufficient credits."
            )
        
        return {
            "success": True,
            "type": "success",
            "data": response_data,
            "message": "Presentation created successfully" + 
                       (" and uploaded to Google Slides" if result.get("driveInfo") else "") + 
                       (" (but Google Drive export failed)" if result.get("drive_export_error") else ""),
            "request_key": request_key
        }
    
    except requests.exceptions.RequestException as e:
        error_msg = f"Gamma API request failed: {str(e)}"
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_details = e.response.json()
                error_msg += f" - {error_details.get('message', e.response.text)}"
            except:
                error_msg += f" - {e.response.text}"
        
        logger.error(error_msg, exc_info=True)
        
        # Update status to failed
        if request_key in _in_progress_presentations:
            _in_progress_presentations[request_key]["status"] = "failed"
            _in_progress_presentations[request_key]["error"] = error_msg
            _in_progress_presentations[request_key]["end_time"] = time.time()
        
        return {
            "success": False,
            "type": "error",
            "data": {},
            "message": f"Failed to create presentation: {error_msg}",
            "request_key": request_key
        }
    
    except Exception as e:
        error_msg = f"Error creating presentation: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        # Update status to failed
        if request_key in _in_progress_presentations:
            _in_progress_presentations[request_key]["status"] = "failed"
            _in_progress_presentations[request_key]["error"] = error_msg
            _in_progress_presentations[request_key]["end_time"] = time.time()
        
        return {
            "success": False,
            "type": "error",
            "data": {},
            "message": f"An unexpected error occurred: {error_msg}",
            "request_key": request_key
        }
    
    finally:
        # Clean up in-progress tracking after a reasonable timeout (1 hour)
        cleanup_time = time.time() - 3600  # 1 hour ago
        for key in list(_in_progress_presentations.keys()):
            if "end_time" in _in_progress_presentations[key] and \
               _in_progress_presentations[key]["end_time"] < cleanup_time:
                del _in_progress_presentations[key]


def _export_to_google_drive(pptx_url: str, filename: str, unified_token: str) -> Dict[str, Any]:
    """Download PPTX from Gamma's direct URL and upload to Google Drive.
    
    Args:
        pptx_url: Direct PPTX URL from Gamma poll response
        filename: Name to save the file as in Google Drive (should end with .pptx)
        unified_token: Unified token for Google Drive authentication
    """
    try:
        from clients.drive_client import get_drive_service

        if not pptx_url:
            raise ValueError("pptx_url is required for Drive export")

        # Download the PPTX bytes
        resp = requests.get(pptx_url, headers={"Accept": "application/octet-stream"}, stream=True, timeout=120)
        resp.raise_for_status()
        content = resp.content

        # Prepare Drive service
        drive_service = get_drive_service(unified_token)
        if not drive_service:
            raise Exception("Failed to initialize Google Drive service")

        # Ensure .pptx extension
        root, ext = os.path.splitext(filename)
        if ext.lower() != ".pptx":
            filename = f"{root}.pptx"

        # Upload to Drive with conversion to Google Slides
        file_metadata = {
            "name": filename,
            "mimeType": "application/vnd.google-apps.presentation",
        }

        media = MediaIoBaseUpload(
            io.BytesIO(content),
            mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            resumable=True,
        )

        file = (
            drive_service.files()
            .create(
                body=file_metadata,
                media_body=media,
                fields="id, name, webViewLink, webContentLink, mimeType, modifiedTime, size",
                supportsAllDrives=True,
            )
            .execute()
        )

        return {
            "id": file.get("id"),
            "name": file.get("name"),
            "webViewLink": file.get("webViewLink"),
            "webContentLink": file.get("webContentLink"),
            "mimeType": file.get("mimeType"),
            "modifiedTime": file.get("modifiedTime"),
            "size": file.get("size", 0),
        }

    except requests.exceptions.RequestException as e:
        error_msg = f"Download failed: {str(e)}"
        if getattr(e, "response", None) is not None:
            try:
                error_msg += f" - {e.response.text[:200]}"
            except Exception:
                pass
        logger.error(error_msg, exc_info=True)
        raise Exception(error_msg)
    except Exception as e:
        logger.error(f"Error exporting to Google Drive: {str(e)}", exc_info=True)
        raise Exception(f"Failed to export to Google Drive: {str(e)}")


def upload_local_pptx_to_slides(
    file_path: str,
    title: Optional[str] = None,
    folder_id: Optional[str] = None,
    unified_token: str = None,
) -> Dict[str, Any]:
    """Upload a local .pptx to Google Drive and convert it to a Google Slides deck.

    Args:
        file_path: Path to local PPTX file
        title: Optional title for the resulting Slides file (defaults to PPTX basename)
        folder_id: Optional Drive folder ID to upload into
        unified_token: OAuth token used to build Drive service

    Returns:
        Dict with file metadata: id, name, webViewLink, webContentLink, mimeType, modifiedTime, size
    """
    try:
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"PPTX file not found: {file_path}")

        from clients.drive_client import get_drive_service

        drive_service = get_drive_service(unified_token)
        if not drive_service:
            raise Exception("Failed to initialize Google Drive service")

        out_name = title or os.path.basename(file_path)
        if not out_name.lower().endswith('.pptx'):
            # keep original extension if not provided
            base, _ = os.path.splitext(out_name)
            out_name = f"{base}.pptx"

        file_metadata: Dict[str, Any] = {
            "name": out_name,
            # Converting by targeting Google Slides mimeType
            "mimeType": "application/vnd.google-apps.presentation",
        }
        if folder_id:
            file_metadata["parents"] = [folder_id]

        media = MediaFileUpload(
            filename=file_path,
            mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            resumable=True,
        )

        created = (
            drive_service.files()
            .create(
                body=file_metadata,
                media_body=media,
                fields="id, name, webViewLink, webContentLink, mimeType, modifiedTime, size",
                supportsAllDrives=True,
            )
            .execute()
        )

        return {
            "id": created.get("id"),
            "name": created.get("name"),
            "webViewLink": created.get("webViewLink"),
            "webContentLink": created.get("webContentLink"),
            "mimeType": created.get("mimeType"),
            "modifiedTime": created.get("modifiedTime"),
            "size": created.get("size", 0),
        }
    except Exception as e:
        logger.error(f"Error uploading PPTX to Slides: {str(e)}", exc_info=True)
        raise


def _export_generic_to_google_drive(file_url: str, filename: str, unified_token: str) -> Dict[str, Any]:
    """Download a file (e.g., PDF) from a URL and upload it to Google Drive.
    
    This does not attempt to convert to Google Slides. Useful for PDF fallback.
    """
    try:
        from clients.drive_client import get_drive_service

        if not file_url:
            raise ValueError("file_url is required for Drive export")

        # Download the file bytes
        resp = requests.get(file_url, headers={"Accept": "application/octet-stream"}, stream=True, timeout=120)
        resp.raise_for_status()
        content = resp.content

        # Guess MIME from response headers, fallback by extension
        content_type = (resp.headers.get("content-type") or "").split(";")[0].lower().strip()
        root, ext = os.path.splitext(filename)
        if not ext:
            # infer from content-type
            if content_type == "application/pdf":
                ext = ".pdf"
            filename = f"{root}{ext or ''}"

        if ext.lower() == ".pdf" or content_type == "application/pdf":
            upload_mime = "application/pdf"
            drive_mime = "application/pdf"  # store as regular PDF
        else:
            # default to octet-stream
            upload_mime = content_type or "application/octet-stream"
            drive_mime = upload_mime

        drive_service = get_drive_service(unified_token)
        if not drive_service:
            raise Exception("Failed to initialize Google Drive service")

        file_metadata = {
            "name": filename,
            "mimeType": drive_mime,
        }

        media = MediaIoBaseUpload(
            io.BytesIO(content),
            mimetype=upload_mime,
            resumable=True,
        )

        file = (
            drive_service.files()
            .create(
                body=file_metadata,
                media_body=media,
                fields="id, name, webViewLink, webContentLink, mimeType, modifiedTime, size",
                supportsAllDrives=True,
            )
            .execute()
        )

        return {
            "id": file.get("id"),
            "name": file.get("name"),
            "webViewLink": file.get("webViewLink"),
            "webContentLink": file.get("webContentLink"),
            "mimeType": file.get("mimeType"),
            "modifiedTime": file.get("modifiedTime"),
            "size": file.get("size", 0),
        }

    except requests.exceptions.RequestException as e:
        error_msg = f"Download failed: {str(e)}"
        if getattr(e, "response", None) is not None:
            try:
                error_msg += f" - {e.response.text[:200]}"
            except Exception:
                pass
        logger.error(error_msg, exc_info=True)
        raise Exception(error_msg)
    except Exception as e:
        logger.error(f"Error exporting to Google Drive: {str(e)}", exc_info=True)
        raise Exception(f"Failed to export to Google Drive: {str(e)}")
def _request_gamma_export(generation_id: str, gamma_file_id: str = None) -> Tuple[Optional[str], Optional[str]]:
    """Request an export from Gamma after generation completes.
    
    Gamma's API may require an explicit export request to get PPTX/PDF URLs.
    This function tries multiple approaches to get the export URL.
    
    Args:
        generation_id: The generation ID from the create response
        gamma_file_id: Optional file/doc ID if different from generation_id
        
    Returns:
        Tuple of (pptx_url, pdf_url) - either or both may be None
    """
    pptx_url = None
    pdf_url = None
    
    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": GAMMA_API_KEY,
        "Accept": "application/json"
    }
    
    # Try approach 1: POST to /generations/{id}/export
    try:
        export_endpoint = f"{GAMMA_BASE_URL.rstrip('/')}/generations/{generation_id}/export"
        export_payload = {"format": "pptx"}
        
        logger.info(f"Requesting export via POST {export_endpoint}")
        resp = requests.post(export_endpoint, headers=headers, json=export_payload, timeout=60)
        
        if resp.status_code == 200:
            export_data = resp.json() if resp.content else {}
            pptx_url = (
                export_data.get("url") or 
                export_data.get("pptxUrl") or 
                export_data.get("exportUrl") or
                export_data.get("downloadUrl")
            )
            if pptx_url:
                logger.info(f"Export URL obtained via /export endpoint: {pptx_url[:60]}...")
                return pptx_url, pdf_url
        else:
            logger.warning(f"Export request failed (status {resp.status_code}): {resp.text[:200]}")
    except Exception as e:
        logger.warning(f"Export request approach 1 failed: {e}")
    
    # Try approach 2: GET /generations/{id}/exports or /generations/{id}/download
    for endpoint_suffix in ["/exports", "/download", "/files"]:
        try:
            endpoint = f"{GAMMA_BASE_URL.rstrip('/')}/generations/{generation_id}{endpoint_suffix}"
            logger.info(f"Trying GET {endpoint}")
            resp = requests.get(endpoint, headers=headers, timeout=30)
            
            if resp.status_code == 200:
                data = resp.json() if resp.content else {}
                pptx_url = (
                    data.get("pptxUrl") or 
                    data.get("pptx") or 
                    data.get("url") or
                    data.get("downloadUrl")
                )
                if isinstance(data.get("exports"), dict):
                    pptx_url = pptx_url or data["exports"].get("pptx")
                    pdf_url = data["exports"].get("pdf")
                if pptx_url:
                    logger.info(f"Export URL obtained via {endpoint_suffix}: {pptx_url[:60]}...")
                    return pptx_url, pdf_url
        except Exception as e:
            logger.debug(f"Endpoint {endpoint_suffix} failed: {e}")
    
    # Try approach 3: If we have a gamma_file_id, try file-based endpoints
    if gamma_file_id and gamma_file_id != generation_id:
        try:
            # Try /files/{fileId}/export
            file_export_endpoint = f"{GAMMA_BASE_URL.rstrip('/')}/files/{gamma_file_id}/export"
            logger.info(f"Trying POST {file_export_endpoint}")
            resp = requests.post(file_export_endpoint, headers=headers, json={"format": "pptx"}, timeout=60)
            
            if resp.status_code == 200:
                data = resp.json() if resp.content else {}
                pptx_url = data.get("url") or data.get("pptxUrl") or data.get("downloadUrl")
                if pptx_url:
                    logger.info(f"Export URL obtained via file endpoint: {pptx_url[:60]}...")
                    return pptx_url, pdf_url
        except Exception as e:
            logger.debug(f"File export endpoint failed: {e}")
    
    # Try approach 4: Poll with export params
    try:
        poll_with_export = f"{GAMMA_BASE_URL.rstrip('/')}/generations/{generation_id}?include=exports"
        logger.info(f"Trying GET {poll_with_export}")
        resp = requests.get(poll_with_export, headers=headers, timeout=30)
        
        if resp.status_code == 200:
            data = resp.json() if resp.content else {}
            exports = data.get("exports", {})
            pptx_url = exports.get("pptx") or exports.get("pptxUrl") or data.get("pptxUrl")
            pdf_url = exports.get("pdf") or exports.get("pdfUrl")
            if pptx_url:
                logger.info(f"Export URL obtained via poll with exports: {pptx_url[:60]}...")
                return pptx_url, pdf_url
    except Exception as e:
        logger.debug(f"Poll with exports failed: {e}")
    
    # Try approach 5: Alternative API (api.gamma.app/v1 style from Node.js examples)
    alt_base = "https://api.gamma.app/v1"
    try:
        # Try getting job result which might have pptxUrl
        alt_job_endpoint = f"{alt_base}/jobs/{generation_id}"
        logger.info(f"Trying alternative API: GET {alt_job_endpoint}")
        alt_headers = {
            "Authorization": f"Bearer {GAMMA_API_KEY}",
            "Accept": "application/json"
        }
        resp = requests.get(alt_job_endpoint, headers=alt_headers, timeout=30)
        
        if resp.status_code == 200:
            data = resp.json() if resp.content else {}
            result_data = data.get("result", {})
            pptx_url = (
                result_data.get("pptxUrl") or 
                data.get("pptxUrl") or
                result_data.get("exportUrl")
            )
            if pptx_url:
                logger.info(f"Export URL obtained via alternative API: {pptx_url[:60]}...")
                return pptx_url, pdf_url
    except Exception as e:
        logger.debug(f"Alternative API failed: {e}")
    
    logger.warning("Could not obtain export URL from any endpoint")
    return pptx_url, pdf_url


def _poll_gamma_generation(generation_id: str, timeout: int = 1800, interval: int = 10) -> Dict[str, Any]:
    """Poll Gamma API for generation status until complete or timeout.
    
    Args:
        generation_id: The ID of the generation to poll
        timeout: Maximum time to wait in seconds (default: 1800s/30min)
        interval: Time between polling attempts in seconds (default: 10s)
        
    Returns:
        Dictionary containing the generation result
        
    Raises:
        TimeoutError: If the generation doesn't complete within the timeout
        requests.exceptions.RequestException: For API request failures
    """
    url = f"{GAMMA_BASE_URL.rstrip('/')}/generations/{generation_id}"
    headers = {
        "X-API-KEY": GAMMA_API_KEY,
        "Accept": "application/json"
    }
    
    start_time = time.time()
    last_status = None
    retry_count = 0
    max_retries = 3
    
    while time.time() - start_time < timeout:
        try:
            # Add a small jitter to avoid thundering herd
            jitter = random.uniform(0.5, 1.5)
            time.sleep(interval * jitter)
            
            # Make the API request with a 60-second timeout
            response = requests.get(url, headers=headers, timeout=60)
            response.raise_for_status()
            data = response.json()
            
            # Log status changes
            current_status = data.get("status")
            if current_status != last_status:
                print(f"Generation status: {current_status} (elapsed: {int(time.time() - start_time)}s)")
                last_status = current_status
            
            # Check for completion
            if current_status in ["completed", "succeeded", "ready"]:
                print(f"Generation completed in {int(time.time() - start_time)} seconds")
                # Log full response for debugging export URL extraction
                logger.info(f"Completed response keys: {list(data.keys())}")
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"Full completed response: {json.dumps(data, default=str)}")
                return data
            
            # Handle error states
            if current_status == "failed":
                error_msg = data.get("error", "Unknown error")
                raise Exception(f"Generation failed: {error_msg}")
                
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            retry_count += 1
            if retry_count > max_retries or time.time() - start_time >= timeout:
                raise TimeoutError(f"Failed to get generation status after {retry_count} attempts: {str(e)}")
            
            retry_delay = min(interval * 2, 30)  # Exponential backoff with max 30s
            print(f"Retry {retry_count}/{max_retries} - waiting {retry_delay}s: {str(e)}")
            time.sleep(retry_delay)
    
    raise TimeoutError(f"Generation did not complete within {timeout} seconds")
    
    raise TimeoutError(f"Generation did not complete within {timeout} seconds")


def _export_to_google_drace(file_url: str, filename: str, unified_token: str) -> Dict[str, Any]:
    """Export a file from Gamma to Google Drive.
    
    Args:
        file_url: URL of the file to export
        filename: Name to save the file as in Google Drive
        unified_token: Unified token for Google Drive authentication
        
    Returns:
        Dictionary with Google Drive file information
    """
    try:
        # Download the file from Gamma
        response = requests.get(file_url, stream=True, timeout=60)
        response.raise_for_status()
        
        # Get Google Drive service
        drive_service, _ = get_gslides_service(unified_token)
        if not drive_service:
            raise ValueError("Google Drive service not available. Check authentication.")
        
        # Create file metadata
        file_metadata = {
            'name': filename,
            'mimeType': 'application/vnd.google-apps.presentation' if filename.lower().endswith('.pptx') else 'application/pdf'
        }
        
        # Upload file to Google Drive
        media = {
            'mimeType': 'application/vnd.openxmlformats-officedocument.presentationml.presentation' if filename.lower().endswith('.pptx') else 'application/pdf',
            'body': response.raw
        }
        
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id,name,webViewLink,webContentLink,mimeType'
        ).execute()
        
        return {
            "fileId": file.get('id'),
            "name": file.get('name'),
            "webViewLink": file.get('webViewLink'),
            "webContentLink": file.get('webContentLink'),
            "mimeType": file.get('mimeType')
        }
        
    except Exception as e:
        raise Exception(f"Failed to export to Google Drive: {str(e)}")


def gslides_share_presentation(
    presentation_id: str, email: str, role: str = "writer", unified_token: str = None
) -> dict:
    drive_service, _ = get_gslides_service(unified_token)
    permission = {"type": "user", "role": role, "emailAddress": email}
    result = (
        drive_service.permissions()
        .create(fileId=presentation_id, body=permission, fields="id")
        .execute()
    )
    return {"status": "success", "permissionId": result.get("id")}


def gslides_extract_text(presentation_id: str, unified_token: str = None) -> list:
    """Extract text from all slides - kept for backward compatibility"""
    _, slides_service = get_gslides_service(unified_token)
    pres = slides_service.presentations().get(presentationId=presentation_id).execute()
    text_chunks = []

    for slide in pres.get("slides", []):
        for element in slide.get("pageElements", []):
            text_content = (
                element.get("shape", {}).get("text", {}).get("textElements", [])
            )
            for te in text_content:
                if "textRun" in te:
                    text_chunks.append(te["textRun"]["content"])

    return text_chunks


def gslides_list_slide_elements(presentation_id: str, slide_id: str, unified_token: str = None) -> dict:
    """List all elements on a specific slide with their types and IDs"""
    _, slides_service = get_gslides_service(unified_token)
    
    try:
        presentation = slides_service.presentations().get(presentationId=presentation_id).execute()
        elements = []
        
        for slide in presentation.get("slides", []):
            if slide["objectId"] == slide_id:
                for element in slide.get("pageElements", []):
                    # Determine element type from keys (more reliable approach from gSlides_ai)
                    element_type = "unknown"
                    element_info = {
                        "element_id": element["objectId"],
                    }
                    
                    # Get the first key that's not objectId, size, or transform
                    for key in element.keys():
                        if key not in ["objectId", "size", "transform"]:
                            element_type = key
                            break
                    
                    element_info["type"] = element_type
                    
                    # Add additional info for tables
                    if "table" in element:
                        element_info["rows"] = element["table"]["rows"]
                        element_info["columns"] = element["table"]["columns"]
                    
                    elements.append(element_info)
                
                return {
                    "status": "success",
                    "slide_id": slide_id,
                    "element_count": len(elements),
                    "elements": elements
                }
        
        return {"status": "error", "message": f"Slide {slide_id} not found"}
    
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gslides_list_tables(presentation_id: str, unified_token: str = None) -> dict:
    """List all tables in the presentation with their metadata"""
    _, slides_service = get_gslides_service(unified_token)
    
    try:
        presentation = slides_service.presentations().get(presentationId=presentation_id).execute()
        tables = []
        
        for slide_index, slide in enumerate(presentation.get("slides", []), start=1):
            slide_id = slide["objectId"]
            for element in slide.get("pageElements", []):
                if "table" in element:
                    tables.append({
                        "slide_number": slide_index,
                        "slide_id": slide_id,
                        "table_id": element["objectId"],
                        "rows": element["table"]["rows"],
                        "columns": element["table"]["columns"]
                    })
        
        return {
            "status": "success",
            "presentation_id": presentation_id,
            "table_count": len(tables),
            "tables": tables
        }
    
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gslides_get_table_info(presentation_id: str, table_id: str, unified_token: str = None) -> dict:
    """Get detailed information about a specific table"""
    _, slides_service = get_gslides_service(unified_token)
    
    try:
        presentation = slides_service.presentations().get(presentationId=presentation_id).execute()
        
        for slide in presentation.get("slides", []):
            for element in slide.get("pageElements", []):
                if element["objectId"] == table_id and "table" in element:
                    table = element["table"]
                    return {
                        "status": "success",
                        "table_id": table_id,
                        "rows": table["rows"],
                        "columns": table["columns"],
                        "slide_id": slide["objectId"]
                    }
        
        return {"status": "error", "message": f"Table {table_id} not found"}
    
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gslides_read_table_data(presentation_id: str, table_id: str, unified_token: str = None) -> dict:
    """Read all text data from a table as a 2D array"""
    _, slides_service = get_gslides_service(unified_token)
    
    try:
        presentation = slides_service.presentations().get(presentationId=presentation_id).execute()
        
        for slide in presentation.get("slides", []):
            for element in slide.get("pageElements", []):
                if element.get("objectId") == table_id and "table" in element:
                    table = element["table"]
                    rows = table["rows"]
                    cols = table["columns"]
                    data = []
                    
                    for r in range(rows):
                        row_data = []
                        for c in range(cols):
                            cell = table["tableRows"][r]["tableCells"][c]
                            text_elements = cell.get("text", {}).get("textElements", [])
                            text = "".join(
                                t.get("textRun", {}).get("content", "")
                                for t in text_elements if "textRun" in t
                            ).strip()
                            row_data.append(text or "")
                        data.append(row_data)
                    
                    return {
                        "status": "success",
                        "table_id": table_id,
                        "rows": rows,
                        "columns": cols,
                        "data": data
                    }
        
        return {"status": "error", "message": f"Table {table_id} not found"}
    
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gslides_get_slide_content(presentation_id: str, unified_token: str = None) -> dict:
    """Get detailed content from all slides with slide-by-slide context"""
    _, slides_service = get_gslides_service(unified_token)
    
    try:
        pres = slides_service.presentations().get(presentationId=presentation_id).execute()
        
        presentation_info = {
            "presentation_id": presentation_id,
            "title": pres.get("title", "Untitled"),
            "total_slides": len(pres.get("slides", [])),
            "slides": []
        }
        
        for slide_index, slide in enumerate(pres.get("slides", [])):
            slide_info = {
                "slide_number": slide_index + 1,
                "slide_id": slide.get("objectId"),
                "layout_id": slide.get("slideProperties", {}).get("layoutObjectId"),
                "elements": [],
                "text_content": [],
                "notes": ""
            }
            
            # Extract text elements with their properties
            for element in slide.get("pageElements", []):
                element_info = {
                    "element_id": element.get("objectId"),
                    "element_type": None,
                    "text": "",
                    "position": {},
                    "size": {}
                }
                
                # Handle text elements (shapes with text)
                if "shape" in element:
                    element_info["element_type"] = "text_shape"
                    shape = element["shape"]
                    
                    # Get position and size
                    if "transform" in element:
                        transform = element["transform"]
                        element_info["position"] = {
                            "x": transform.get("translateX", 0),
                            "y": transform.get("translateY", 0)
                        }
                    
                    if "size" in element:
                        size = element["size"]
                        element_info["size"] = {
                            "width": size.get("width", {}).get("magnitude", 0),
                            "height": size.get("height", {}).get("magnitude", 0)
                        }
                    
                    # Extract text content
                    text_elements = shape.get("text", {}).get("textElements", [])
                    text_parts = []
                    for te in text_elements:
                        if "textRun" in te:
                            text_content = te["textRun"]["content"]
                            text_parts.append(text_content)
                            slide_info["text_content"].append(text_content)
                    
                    element_info["text"] = "".join(text_parts)
                
                # Handle images
                elif "image" in element:
                    element_info["element_type"] = "image"
                    image = element["image"]
                    element_info["text"] = f"[Image: {image.get('contentUrl', 'Unknown')}]"
                
                # Handle tables
                elif "table" in element:
                    element_info["element_type"] = "table"
                    table = element["table"]
                    table_info = {
                        "rows": table.get("rows", 0),
                        "columns": table.get("columns", 0),
                        "table_data": []
                    }
                    
                    # Extract table content
                    for row_index, row in enumerate(table.get("tableRows", [])):
                        row_data = []
                        for cell in row.get("tableCells", []):
                            cell_text = ""
                            if "text" in cell:
                                text_elements = cell["text"].get("textElements", [])
                                cell_content = []
                                for te in text_elements:
                                    if "textRun" in te:
                                        cell_content.append(te["textRun"]["content"])
                                cell_text = "".join(cell_content)
                                slide_info["text_content"].append(cell_text)
                            row_data.append(cell_text)
                        table_info["table_data"].append(row_data)
                    
                    element_info["table_info"] = table_info
                    element_info["text"] = f"[Table: {table_info['rows']}x{table_info['columns']}]"
                
                # Handle other elements
                else:
                    element_info["element_type"] = "other"
                
                if element_info["text"] or element_info["element_type"] != "other":
                    slide_info["elements"].append(element_info)
            
            # Get speaker notes if available
            notes_page = slide.get("slideProperties", {}).get("notesPage")
            if notes_page:
                for element in notes_page.get("pageElements", []):
                    if "shape" in element:
                        text_elements = element["shape"].get("text", {}).get("textElements", [])
                        notes_text = []
                        for te in text_elements:
                            if "textRun" in te:
                                notes_text.append(te["textRun"]["content"])
                        if notes_text:
                            slide_info["notes"] = "".join(notes_text)
            
            presentation_info["slides"].append(slide_info)
        
        return {
            "status": "success",
            "presentation": presentation_info
        }
        
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gslides_get_specific_slide(presentation_id: str, slide_number: int, unified_token: str = None) -> dict:
    """Get content from a specific slide by slide number (1-based)"""
    _, slides_service = get_gslides_service(unified_token)
    
    try:
        pres = slides_service.presentations().get(presentationId=presentation_id).execute()
        slides = pres.get("slides", [])
        
        if slide_number < 1 or slide_number > len(slides):
            return {
                "status": "error", 
                "message": f"Slide number {slide_number} out of range. Presentation has {len(slides)} slides."
            }
        
        slide = slides[slide_number - 1]  # Convert to 0-based index
        
        slide_info = {
            "presentation_title": pres.get("title", "Untitled"),
            "slide_number": slide_number,
            "slide_id": slide.get("objectId"),
            "total_slides": len(slides),
            "elements": [],
            "all_text": []
        }
        
        # Extract all elements from the slide
        for element in slide.get("pageElements", []):
            element_data = {
                "element_id": element.get("objectId"),
                "type": "unknown"
            }
            
            if "shape" in element:
                element_data["type"] = "text_shape"
                shape = element["shape"]
                text_elements = shape.get("text", {}).get("textElements", [])
                text_content = []
                
                for te in text_elements:
                    if "textRun" in te:
                        text = te["textRun"]["content"]
                        text_content.append(text)
                        slide_info["all_text"].append(text)
                
                element_data["text"] = "".join(text_content)
                
            elif "image" in element:
                element_data["type"] = "image"
                element_data["description"] = "[Image element]"
            
            elif "table" in element:
                element_data["type"] = "table"
                table = element["table"]
                table_data = {
                    "rows": table.get("rows", 0),
                    "columns": table.get("columns", 0),
                    "table_rows": []
                }
                
                # Extract table content
                for row_index, row in enumerate(table.get("tableRows", [])):
                    row_data = {"cells": []}
                    for cell_index, cell in enumerate(row.get("tableCells", [])):
                        cell_text = ""
                        if "text" in cell:
                            text_elements = cell["text"].get("textElements", [])
                            cell_content = []
                            for te in text_elements:
                                if "textRun" in te:
                                    cell_content.append(te["textRun"]["content"])
                            cell_text = "".join(cell_content)
                            slide_info["all_text"].append(cell_text)
                        
                        row_data["cells"].append({
                            "text": cell_text,
                            "row": row_index,
                            "column": cell_index
                        })
                    table_data["table_rows"].append(row_data)
                
                element_data["table_data"] = table_data
                element_data["text"] = f"[Table: {table_data['rows']}x{table_data['columns']}]"
            
            slide_info["elements"].append(element_data)
        
        return {
            "status": "success",
            "slide": slide_info
        }
        
    except Exception as e:
        return {"status": "error", "message": str(e)}


def search_slides_by_title(
    keyword: str, limit: int = 10, unified_token: str = None
) -> dict:
    drive_service, _ = get_gslides_service(unified_token)
    try:
        query = f"name contains '{keyword}' and mimeType='application/vnd.google-apps.presentation' and trashed=false"
        response = (
            drive_service.files()
            .list(q=query, pageSize=limit, fields="files(id, name, modifiedTime)")
            .execute()
        )
        return {"matches": response.get("files", [])}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_slide_history(slide_id: str, unified_token: str = None) -> dict:
    drive_service, _ = get_gslides_service(unified_token)
    try:
        metadata = (
            drive_service.files()
            .get(
                fileId=slide_id,
                fields="id, name, modifiedTime, createdTime, owners, lastModifyingUser",
            )
            .execute()
        )
        return {
            "slide_id": metadata.get("id"),
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


def gslides_replace_text(presentation_id: str, old_text: str, new_text: str, slide_number: int = None, unified_token: str = None) -> dict:
    """Replace text in presentation. If slide_number is provided, only replace in that specific slide."""
    _, slides_service = get_gslides_service(unified_token)
    
    try:
        if slide_number is not None:
            # Get presentation to validate slide number
            pres = slides_service.presentations().get(presentationId=presentation_id).execute()
            slides = pres.get("slides", [])
            
            if slide_number < 1 or slide_number > len(slides):
                return {
                    "status": "error",
                    "message": f"Slide number {slide_number} out of range. Presentation has {len(slides)} slides."
                }
            
            # Replace text only in specific slide
            slide_id = slides[slide_number - 1].get("objectId")
            requests = [
                {
                    'replaceAllText': {
                        'containsText': {
                            'text': old_text,
                            'matchCase': False
                        },
                        'replaceText': new_text,
                        'pageObjectIds': [slide_id]
                    }
                }
            ]
            
            body = {'requests': requests}
            response = slides_service.presentations().batchUpdate(
                presentationId=presentation_id, body=body
            ).execute()
            
            return {
                "status": "success", 
                "message": f"Replaced '{old_text}' with '{new_text}' in slide {slide_number}",
                "slide_number": slide_number,
                "replacements": response.get('replies', [{}])[0].get('replaceAllText', {}).get('occurrencesChanged', 0)
            }
        else:
            # Replace text in entire presentation (original behavior)
            requests = [
                {
                    'replaceAllText': {
                        'containsText': {
                            'text': old_text,
                            'matchCase': False
                        },
                        'replaceText': new_text
                    }
                }
            ]
            
            body = {'requests': requests}
            response = slides_service.presentations().batchUpdate(
                presentationId=presentation_id, body=body
            ).execute()
            
            return {
                "status": "success", 
                "message": f"Replaced '{old_text}' with '{new_text}' in entire presentation",
                "replacements": response.get('replies', [{}])[0].get('replaceAllText', {}).get('occurrencesChanged', 0)
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gslides_add_text_box(presentation_id: str, slide_index: int, text: str, 
                        x: float = 100, y: float = 100, width: float = 300, height: float = 100,
                        unified_token: str = None) -> dict:
    """Add a text box to a specific slide"""
    _, slides_service = get_gslides_service(unified_token)
    
    try:
        # Get the presentation to find the slide ID
        presentation = slides_service.presentations().get(presentationId=presentation_id).execute()
        slides = presentation.get('slides', [])
        
        if slide_index >= len(slides):
            return {"status": "error", "message": f"Slide index {slide_index} out of range"}
        
        slide_id = slides[slide_index]['objectId']
        element_id = f"textbox_{slide_index}_{len(slides)}"
        
        requests = [
            {
                'createShape': {
                    'objectId': element_id,
                    'shapeType': 'TEXT_BOX',
                    'elementProperties': {
                        'pageObjectId': slide_id,
                        'size': {
                            'width': {'magnitude': width, 'unit': 'PT'},
                            'height': {'magnitude': height, 'unit': 'PT'}
                        },
                        'transform': {
                            'scaleX': 1,
                            'scaleY': 1,
                            'translateX': x,
                            'translateY': y,
                            'unit': 'PT'
                        }
                    }
                }
            },
            {
                'insertText': {
                    'objectId': element_id,
                    'text': text,
                    'insertionIndex': 0
                }
            }
        ]
        
        body = {'requests': requests}
        response = slides_service.presentations().batchUpdate(
            presentationId=presentation_id, body=body
        ).execute()
        
        return {
            "status": "success",
            "message": f"Added text box with text: '{text}'",
            "element_id": element_id
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gslides_add_slide(presentation_id: str, layout: str = "BLANK", unified_token: str = None) -> dict:
    """Add a new slide to the presentation"""
    _, slides_service = get_gslides_service(unified_token)
    
    try:
        # Get the presentation to find layout ID
        presentation = slides_service.presentations().get(presentationId=presentation_id).execute()
        layouts = presentation.get('layouts', [])
        
        # Find the layout ID for the specified layout
        layout_id = None
        for layout_obj in layouts:
            if layout.upper() in layout_obj.get('layoutProperties', {}).get('displayName', '').upper():
                layout_id = layout_obj['objectId']
                break
        
        # If no specific layout found, use the first one
        if not layout_id and layouts:
            layout_id = layouts[0]['objectId']
        
        slide_id = f"slide_{len(presentation.get('slides', []))}"
        
        requests = [
            {
                'createSlide': {
                    'objectId': slide_id,
                    'slideLayoutReference': {
                        'layoutId': layout_id
                    }
                }
            }
        ]
        
        body = {'requests': requests}
        response = slides_service.presentations().batchUpdate(
            presentationId=presentation_id, body=body
        ).execute()
        
        return {
            "status": "success",
            "message": f"Added new slide with layout: {layout}",
            "slide_id": slide_id
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gslides_format_text(presentation_id: str, text_to_format: str, 
                       bold: bool = None, italic: bool = None, 
                       font_size: int = None, color: str = None,
                       unified_token: str = None) -> dict:
    """Format specific text in the presentation"""
    _, slides_service = get_gslides_service(unified_token)
    
    try:
        # First, find all text ranges that match the text_to_format
        presentation = slides_service.presentations().get(presentationId=presentation_id).execute()
        
        requests = []
        
        # Build formatting requests
        text_style = {}
        if bold is not None:
            text_style['bold'] = bold
        if italic is not None:
            text_style['italic'] = italic
        if font_size is not None:
            text_style['fontSize'] = {'magnitude': font_size, 'unit': 'PT'}
        if color is not None:
            # Convert hex color to RGB
            if color.startswith('#'):
                color = color[1:]
            r = int(color[0:2], 16) / 255.0
            g = int(color[2:4], 16) / 255.0
            b = int(color[4:6], 16) / 255.0
            text_style['foregroundColor'] = {
                'opaqueColor': {
                    'rgbColor': {'red': r, 'green': g, 'blue': b}
                }
            }
        
        # For simplicity, we'll format all instances of the text
        # In a more advanced implementation, you'd specify exact ranges
        for slide in presentation.get('slides', []):
            for element in slide.get('pageElements', []):
                if 'shape' in element and 'text' in element['shape']:
                    text_elements = element['shape']['text'].get('textElements', [])
                    for i, text_element in enumerate(text_elements):
                        if 'textRun' in text_element and text_to_format in text_element['textRun']['content']:
                            requests.append({
                                'updateTextStyle': {
                                    'objectId': element['objectId'],
                                    'style': text_style,
                                    'textRange': {
                                        'type': 'ALL'
                                    },
                                    'fields': ','.join(text_style.keys())
                                }
                            })
        
        if requests:
            body = {'requests': requests}
            response = slides_service.presentations().batchUpdate(
                presentationId=presentation_id, body=body
            ).execute()
            
            return {
                "status": "success",
                "message": f"Formatted text: '{text_to_format}'",
                "changes_made": len(requests)
            }
        else:
            return {
                "status": "warning",
                "message": f"No text found matching: '{text_to_format}'"
            }
            
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gslides_add_table(presentation_id: str, slide_index: int, rows: int, columns: int, 
                     x: float = 100, y: float = 100, width: float = 400, height: float = 200,
                     unified_token: str = None) -> dict:
    """Add a table to a specific slide"""
    _, slides_service = get_gslides_service(unified_token)
    
    try:
        # Get the presentation to find the slide ID
        presentation = slides_service.presentations().get(presentationId=presentation_id).execute()
        slides = presentation.get('slides', [])
        
        if slide_index >= len(slides):
            return {"status": "error", "message": f"Slide index {slide_index} out of range"}
        
        slide_id = slides[slide_index]['objectId']
        table_id = f"table_{slide_index}_{rows}x{columns}"
        
        requests = [
            {
                'createTable': {
                    'objectId': table_id,
                    'elementProperties': {
                        'pageObjectId': slide_id,
                        'size': {
                            'width': {'magnitude': width, 'unit': 'PT'},
                            'height': {'magnitude': height, 'unit': 'PT'}
                        },
                        'transform': {
                            'scaleX': 1,
                            'scaleY': 1,
                            'translateX': x,
                            'translateY': y,
                            'unit': 'PT'
                        }
                    },
                    'rows': rows,
                    'columns': columns
                }
            }
        ]
        
        body = {'requests': requests}
        response = slides_service.presentations().batchUpdate(
            presentationId=presentation_id, body=body
        ).execute()
        
        return {
            "status": "success",
            "message": f"Added {rows}x{columns} table to slide {slide_index + 1}",
            "table_id": table_id,
            "rows": rows,
            "columns": columns
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gslides_update_table_cell(presentation_id: str, table_id: str, row: int, column: int, 
                             text: str, unified_token: str = None) -> dict:
    """Update text in a specific table cell (replaces existing content)"""
    _, slides_service = get_gslides_service(unified_token)
    
    try:
        # Create cell location
        cell_location = {
            'rowIndex': row,
            'columnIndex': column
        }
        
        # First delete existing text, then insert new text
        requests = [
            {
                'deleteText': {
                    'objectId': table_id,
                    'cellLocation': cell_location,
                    'textRange': {'type': 'ALL'}
                }
            },
            {
                'insertText': {
                    'objectId': table_id,
                    'cellLocation': cell_location,
                    'text': text,
                    'insertionIndex': 0
                }
            }
        ]
        
        body = {'requests': requests}
        response = slides_service.presentations().batchUpdate(
            presentationId=presentation_id, body=body
        ).execute()
        
        return {
            "status": "success",
            "message": f"Updated cell ({row}, {column}) with text: '{text}'",
            "table_id": table_id,
            "row": row,
            "column": column
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gslides_populate_table(presentation_id: str, table_id: str, data: list, 
                           unified_token: str = None) -> dict:
    """Populate table with data (2D array) - replaces existing content"""
    _, slides_service = get_gslides_service(unified_token)
    
    try:
        requests = []
        
        for row_index, row_data in enumerate(data):
            for col_index, cell_value in enumerate(row_data):
                cell_location = {
                    'rowIndex': row_index,
                    'columnIndex': col_index
                }
                
                # First delete existing text in the cell
                requests.append({
                    'deleteText': {
                        'objectId': table_id,
                        'cellLocation': cell_location,
                        'textRange': {'type': 'ALL'}
                    }
                })
                
                # Then insert new text if cell_value is not empty
                if cell_value:
                    requests.append({
                        'insertText': {
                            'objectId': table_id,
                            'cellLocation': cell_location,
                            'text': str(cell_value),
                            'insertionIndex': 0
                        }
                    })
        
        if requests:
            body = {'requests': requests}
            response = slides_service.presentations().batchUpdate(
                presentationId=presentation_id, body=body
            ).execute()
            
            return {
                "status": "success",
                "message": f"Populated table with {len(data)} rows of data",
                "table_id": table_id,
                "cells_updated": len(requests)
            }
        else:
            return {
                "status": "warning",
                "message": "No data provided to populate table"
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gslides_add_table_rows(presentation_id: str, table_id: str, insert_index: int = None, 
                          number_of_rows: int = 1, unified_token: str = None) -> dict:
    """Add rows to a table. If insert_index is None or -1, adds at bottom."""
    _, slides_service = get_gslides_service(unified_token)
    
    try:
        # Get current table info to determine row count
        presentation = slides_service.presentations().get(presentationId=presentation_id).execute()
        
        table_element = None
        for slide in presentation.get("slides", []):
            for element in slide.get("pageElements", []):
                if element.get("objectId") == table_id:
                    table_element = element.get("table")
                    break
            if table_element:
                break
        
        if not table_element:
            return {"status": "error", "message": f"Table {table_id} not found"}
        
        num_rows = len(table_element.get("tableRows", []))
        
        # Determine where to insert
        if insert_index is None or insert_index < 0 or insert_index >= num_rows:
            # Add at bottom
            cell_row_index = num_rows - 1
            insert_below = True
            location = "bottom"
        elif insert_index == 0:
            # Add at top
            cell_row_index = 0
            insert_below = False
            location = "top"
        else:
            # Add at specific index
            cell_row_index = insert_index - 1
            insert_below = True
            location = f"index {insert_index}"
        
        requests = [
            {
                'insertTableRows': {
                    'tableObjectId': table_id,
                    'cellLocation': {
                        'rowIndex': cell_row_index,
                        'columnIndex': 0
                    },
                    'insertBelow': insert_below,
                    'number': number_of_rows
                }
            }
        ]
        
        body = {'requests': requests}
        response = slides_service.presentations().batchUpdate(
            presentationId=presentation_id, body=body
        ).execute()
        
        return {
            "status": "success",
            "message": f"Added {number_of_rows} row(s) at {location}",
            "table_id": table_id,
            "rows_added": number_of_rows,
            "location": location
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gslides_add_table_columns(presentation_id: str, table_id: str, insert_index: int = None, 
                             number_of_columns: int = 1, unified_token: str = None) -> dict:
    """Add columns to a table. If insert_index is None or -1, adds at right."""
    _, slides_service = get_gslides_service(unified_token)
    
    try:
        # Get current table info to determine column count
        presentation = slides_service.presentations().get(presentationId=presentation_id).execute()
        
        table_element = None
        for slide in presentation.get("slides", []):
            for element in slide.get("pageElements", []):
                if element.get("objectId") == table_id:
                    table_element = element.get("table")
                    break
            if table_element:
                break
        
        if not table_element:
            return {"status": "error", "message": f"Table {table_id} not found"}
        
        num_cols = len(table_element.get("tableColumns", []))
        
        # Determine where to insert
        if insert_index is None or insert_index < 0 or insert_index >= num_cols:
            # Add at right
            cell_col_index = num_cols - 1
            insert_right = True
            location = "rightmost"
        elif insert_index == 0:
            # Add at left
            cell_col_index = 0
            insert_right = False
            location = "leftmost"
        else:
            # Add at specific index
            cell_col_index = insert_index - 1
            insert_right = True
            location = f"index {insert_index}"
        
        requests = [
            {
                'insertTableColumns': {
                    'tableObjectId': table_id,
                    'cellLocation': {
                        'rowIndex': 0,
                        'columnIndex': cell_col_index
                    },
                    'insertRight': insert_right,
                    'number': number_of_columns
                }
            }
        ]
        
        body = {'requests': requests}
        response = slides_service.presentations().batchUpdate(
            presentationId=presentation_id, body=body
        ).execute()
        
        return {
            "status": "success",
            "message": f"Added {number_of_columns} column(s) at {location}",
            "table_id": table_id,
            "columns_added": number_of_columns,
            "location": location
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gslides_delete_table_rows(presentation_id: str, table_id: str, start_index: int, 
                             number_of_rows: int = 1, unified_token: str = None) -> dict:
    """Delete rows from a table starting at specified position"""
    _, slides_service = get_gslides_service(unified_token)
    
    try:
        requests = [
            {
                'deleteTableRow': {
                    'tableObjectId': table_id,
                    'cellLocation': {
                        'rowIndex': start_index,
                        'columnIndex': 0
                    }
                }
            }
        ]
        
        # Delete multiple rows if specified
        for i in range(number_of_rows - 1):
            requests.append({
                'deleteTableRow': {
                    'tableObjectId': table_id,
                    'cellLocation': {
                        'rowIndex': start_index,  # Always delete at same index as rows shift up
                        'columnIndex': 0
                    }
                }
            })
        
        body = {'requests': requests}
        response = slides_service.presentations().batchUpdate(
            presentationId=presentation_id, body=body
        ).execute()
        
        return {
            "status": "success",
            "message": f"Deleted {number_of_rows} row(s) starting at position {start_index}",
            "table_id": table_id,
            "rows_deleted": number_of_rows
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gslides_delete_table_columns(presentation_id: str, table_id: str, start_index: int, 
                                number_of_columns: int = 1, unified_token: str = None) -> dict:
    """Delete columns from a table starting at specified position"""
    _, slides_service = get_gslides_service(unified_token)
    
    try:
        requests = [
            {
                'deleteTableColumn': {
                    'tableObjectId': table_id,
                    'cellLocation': {
                        'rowIndex': 0,
                        'columnIndex': start_index
                    }
                }
            }
        ]
        
        # Delete multiple columns if specified
        for i in range(number_of_columns - 1):
            requests.append({
                'deleteTableColumn': {
                    'tableObjectId': table_id,
                    'cellLocation': {
                        'rowIndex': 0,
                        'columnIndex': start_index  # Always delete at same index as columns shift left
                    }
                }
            })
        
        body = {'requests': requests}
        response = slides_service.presentations().batchUpdate(
            presentationId=presentation_id, body=body
        ).execute()
        
        return {
            "status": "success",
            "message": f"Deleted {number_of_columns} column(s) starting at position {start_index}",
            "table_id": table_id,
            "columns_deleted": number_of_columns
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gslides_insert_row_above(presentation_id: str, table_id: str, row_index: int, 
                            number_of_rows: int = 1, unified_token: str = None) -> dict:
    """Insert rows above the specified row"""
    return gslides_add_table_rows(presentation_id, table_id, row_index, number_of_rows, unified_token)


def gslides_insert_row_below(presentation_id: str, table_id: str, row_index: int, 
                            number_of_rows: int = 1, unified_token: str = None) -> dict:
    """Insert rows below the specified row"""
    _, slides_service = get_gslides_service(unified_token)
    
    try:
        requests = [
            {
                'insertTableRows': {
                    'tableObjectId': table_id,
                    'cellLocation': {
                        'rowIndex': row_index,
                        'columnIndex': 0
                    },
                    'insertBelow': True,
                    'number': number_of_rows
                }
            }
        ]
        
        body = {'requests': requests}
        response = slides_service.presentations().batchUpdate(
            presentationId=presentation_id, body=body
        ).execute()
        
        return {
            "status": "success",
            "message": f"Added {number_of_rows} row(s) below row {row_index}",
            "table_id": table_id,
            "rows_added": number_of_rows
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gslides_insert_column_left(presentation_id: str, table_id: str, column_index: int, 
                              number_of_columns: int = 1, unified_token: str = None) -> dict:
    """Insert columns to the left of the specified column"""
    return gslides_add_table_columns(presentation_id, table_id, column_index, number_of_columns, unified_token)


def gslides_insert_column_right(presentation_id: str, table_id: str, column_index: int, 
                               number_of_columns: int = 1, unified_token: str = None) -> dict:
    """Insert columns to the right of the specified column"""
    _, slides_service = get_gslides_service(unified_token)
    
    try:
        requests = [
            {
                'insertTableColumns': {
                    'tableObjectId': table_id,
                    'cellLocation': {
                        'rowIndex': 0,
                        'columnIndex': column_index
                    },
                    'insertRight': True,
                    'number': number_of_columns
                }
            }
        ]
        
        body = {'requests': requests}
        response = slides_service.presentations().batchUpdate(
            presentationId=presentation_id, body=body
        ).execute()
        
        return {
            "status": "success",
            "message": f"Added {number_of_columns} column(s) to the right of column {column_index}",
            "table_id": table_id,
            "columns_added": number_of_columns
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gslides_replace_table_text(presentation_id: str, table_id: str, old_text: str, 
                               new_text: str = None, unified_token: str = None) -> dict:
    """Replace or delete specific text in a table cell. If new_text is None/empty, deletes the text."""
    _, slides_service = get_gslides_service(unified_token)
    
    try:
        # First, read the table data to find the cell
        table_data_result = gslides_read_table_data(presentation_id, table_id, unified_token)
        
        if table_data_result.get("status") != "success":
            return table_data_result
        
        table_data = table_data_result["data"]
        found = False
        requests = []
        
        for r, row in enumerate(table_data):
            for c, cell_text in enumerate(row):
                if cell_text.strip().lower() == old_text.strip().lower():
                    found = True
                    
                    # Delete existing text
                    requests.append({
                        "deleteText": {
                            "objectId": table_id,
                            "cellLocation": {"rowIndex": r, "columnIndex": c},
                            "textRange": {"type": "ALL"}
                        }
                    })
                    
                    # Insert new text if provided
                    if new_text:
                        requests.append({
                            "insertText": {
                                "objectId": table_id,
                                "cellLocation": {"rowIndex": r, "columnIndex": c},
                                "text": new_text
                            }
                        })
                    break
            if found:
                break
        
        if not found:
            return {
                "status": "error",
                "message": f"Text '{old_text}' not found in table {table_id}"
            }
        
        body = {'requests': requests}
        slides_service.presentations().batchUpdate(
            presentationId=presentation_id, body=body
        ).execute()
        
        action = "replaced" if new_text else "deleted"
        return {
            "status": "success",
            "message": f"Successfully {action} '{old_text}' in table {table_id}",
            "action": action
        }
    
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gslides_search_presentation(presentation_id: str, keyword: str, 
                               table_id: str = None, unified_token: str = None) -> dict:
    """Search for a keyword in the presentation. Optionally limit search to a specific table."""
    _, slides_service = get_gslides_service(unified_token)
    
    try:
        presentation = slides_service.presentations().get(presentationId=presentation_id).execute()
        slides = presentation.get("slides", [])
        results = []
        
        for slide_index, slide in enumerate(slides, start=1):
            for element in slide.get("pageElements", []):
                
                # Search in tables
                if "table" in element:
                    table_object_id = element.get("objectId")
                    
                    # Skip if searching specific table and this isn't it
                    if table_id and table_object_id != table_id:
                        continue
                    
                    table = element["table"]
                    for row_idx, row in enumerate(table.get("tableRows", [])):
                        for col_idx, cell in enumerate(row.get("tableCells", [])):
                            text_elements = cell.get("text", {}).get("textElements", [])
                            text_content = " ".join([
                                te["textRun"]["content"].strip()
                                for te in text_elements if "textRun" in te
                            ])
                            
                            if keyword.lower() in text_content.lower():
                                results.append({
                                    "type": "table_cell",
                                    "slide_number": slide_index,
                                    "table_id": table_object_id,
                                    "row": row_idx,
                                    "column": col_idx,
                                    "cell_text": text_content
                                })
                
                # Search in shapes/text (only if not searching specific table)
                if "shape" in element and not table_id:
                    text_elements = element["shape"].get("text", {}).get("textElements", [])
                    full_text = "".join([
                        te["textRun"]["content"]
                        for te in text_elements if "textRun" in te
                    ])
                    
                    if keyword.lower() in full_text.lower():
                        results.append({
                            "type": "shape",
                            "slide_number": slide_index,
                            "shape_id": element["objectId"],
                            "matched_text": full_text.strip()
                        })
        
        if not results:
            return {
                "status": "success",
                "message": f"No matches found for '{keyword}'",
                "results": []
            }
        
        return {
            "status": "success",
            "keyword": keyword,
            "match_count": len(results),
            "results": results
        }
    
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gslides_get_element_text(presentation_id: str, element_id: str, unified_token: str = None) -> dict:
    """Get text content from a specific element (shape, text box, etc.)"""
    _, slides_service = get_gslides_service(unified_token)
    
    try:
        presentation = slides_service.presentations().get(presentationId=presentation_id).execute()
        
        for slide in presentation.get("slides", []):
            for element in slide.get("pageElements", []):
                if element["objectId"] == element_id:
                    if "shape" in element and "text" in element["shape"]:
                        text_content = ''.join([
                            te["textRun"]["content"]
                            for te in element["shape"]["text"]["textElements"]
                            if "textRun" in te
                        ])
                        return {
                            "status": "success",
                            "element_id": element_id,
                            "text": text_content.strip()
                        }
                    else:
                        return {
                            "status": "error",
                            "message": f"Element {element_id} does not contain text"
                        }
        
        return {"status": "error", "message": f"Element {element_id} not found"}
    
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gslides_delete_element(presentation_id: str, element_id: str, unified_token: str = None) -> dict:
    """Delete a specific element (table, shape, image, etc.) from a slide"""
    _, slides_service = get_gslides_service(unified_token)
    
    try:
        requests = [{
            "deleteObject": {
                "objectId": element_id
            }
        }]
        
        body = {'requests': requests}
        slides_service.presentations().batchUpdate(
            presentationId=presentation_id, body=body
        ).execute()
        
        return {
            "status": "success",
            "message": f"Deleted element {element_id}",
            "element_id": element_id
        }
    
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gslides_delete_slide(presentation_id: str, slide_id: str, unified_token: str = None) -> dict:
    """Delete a slide from the presentation"""
    _, slides_service = get_gslides_service(unified_token)
    
    try:
        requests = [{
            "deleteObject": {
                "objectId": slide_id
            }
        }]
        
        body = {'requests': requests}
        slides_service.presentations().batchUpdate(
            presentationId=presentation_id, body=body
        ).execute()
        
        return {
            "status": "success",
            "message": f"Deleted slide {slide_id}",
            "slide_id": slide_id
        }
    
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gslides_insert_text(presentation_id: str, object_id: str, text: str, 
                        insertion_index: int = 0, unified_token: str = None) -> dict:
    """Insert text into a shape or text box at a specific index"""
    _, slides_service = get_gslides_service(unified_token)
    
    try:
        requests = [{
            "insertText": {
                "objectId": object_id,
                "insertionIndex": insertion_index,
                "text": text
            }
        }]
        
        body = {'requests': requests}
        slides_service.presentations().batchUpdate(
            presentationId=presentation_id, body=body
        ).execute()
        
        return {
            "status": "success",
            "message": f"Inserted text into {object_id}",
            "object_id": object_id
        }
    
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gslides_insert_image(presentation_id: str, slide_id: str, image_url: str,
                        x: float = 100, y: float = 100, width: float = 300, height: float = 200,
                        unified_token: str = None) -> dict:
    """Insert an image on a slide from a URL"""
    _, slides_service = get_gslides_service(unified_token)
    
    try:
        requests = [{
            "createImage": {
                "url": image_url,
                "elementProperties": {
                    "pageObjectId": slide_id,
                    "size": {
                        "width": {"magnitude": width, "unit": "PT"},
                        "height": {"magnitude": height, "unit": "PT"}
                    },
                    "transform": {
                        "scaleX": 1,
                        "scaleY": 1,
                        "translateX": x,
                        "translateY": y,
                        "unit": "PT"
                    }
                }
            }
        }]
        
        body = {'requests': requests}
        response = slides_service.presentations().batchUpdate(
            presentationId=presentation_id, body=body
        ).execute()
        
        image_id = response['replies'][0]['createImage']['objectId']
        
        return {
            "status": "success",
            "message": f"Inserted image on slide {slide_id}",
            "slide_id": slide_id,
            "image_id": image_id
        }
    
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gslides_list_slides_info(presentation_id: str, unified_token: str = None) -> dict:
    """List all slides in a presentation with their IDs and index"""
    _, slides_service = get_gslides_service(unified_token)
    
    try:
        presentation = slides_service.presentations().get(presentationId=presentation_id).execute()
        slides = presentation.get("slides", [])
        slide_info = [
            {
                "slide_index": i + 1,
                "slide_id": slide["objectId"]
            }
            for i, slide in enumerate(slides)
        ]
        
        return {
            "status": "success",
            "presentation_id": presentation_id,
            "slide_count": len(slides),
            "slides": slide_info
        }
    
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gslides_add_rows_and_populate(presentation_id: str, table_id: str, data: list,
                                  unified_token: str = None) -> dict:
    """Add new rows at the bottom of the table and populate them with data."""
    _, slides_service = get_gslides_service(unified_token)
    
    try:
        if not data or len(data) == 0:
            return {"status": "error", "message": "No data provided"}
        
        # Get current table info
        presentation = slides_service.presentations().get(presentationId=presentation_id).execute()
        
        table_element = None
        for slide in presentation.get("slides", []):
            for element in slide.get("pageElements", []):
                if element.get("objectId") == table_id:
                    table_element = element.get("table")
                    break
            if table_element:
                break
        
        if not table_element:
            return {"status": "error", "message": f"Table {table_id} not found"}
        
        current_rows = len(table_element.get("tableRows", []))
        num_cols = len(table_element.get("tableColumns", []))
        num_new_rows = len(data)
        
        # Step 1: Add rows at the bottom
        add_rows_request = [{
            'insertTableRows': {
                'tableObjectId': table_id,
                'cellLocation': {
                    'rowIndex': current_rows - 1,
                    'columnIndex': 0
                },
                'insertBelow': True,
                'number': num_new_rows
            }
        }]
        
        slides_service.presentations().batchUpdate(
            presentationId=presentation_id, body={'requests': add_rows_request}
        ).execute()
        
        # Step 2: Populate the new rows with data (in a separate request)
        populate_requests = []
        for row_offset, row_data in enumerate(data):
            actual_row_index = current_rows + row_offset
            for col_index, cell_value in enumerate(row_data):
                if col_index >= num_cols:
                    break  # Skip if more columns in data than in table
                
                cell_location = {
                    'rowIndex': actual_row_index,
                    'columnIndex': col_index
                }
                
                # Insert new text if cell_value is not empty
                # No need to delete - newly created cells are empty
                if cell_value:
                    populate_requests.append({
                        'insertText': {
                            'objectId': table_id,
                            'cellLocation': cell_location,
                            'text': str(cell_value),
                            'insertionIndex': 0
                        }
                    })
        
        # Execute populate requests
        if populate_requests:
            slides_service.presentations().batchUpdate(
                presentationId=presentation_id, body={'requests': populate_requests}
            ).execute()
        
        return {
            "status": "success",
            "message": f"Added {num_new_rows} row(s) at bottom and populated with data",
            "table_id": table_id,
            "rows_added": num_new_rows,
            "starting_row": current_rows
        }
    
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gslides_append_table_row(presentation_id: str, table_id: str, row_data: list,
                             unified_token: str = None) -> dict:
    """Append a single row to the bottom of the table with data."""
    return gslides_add_rows_and_populate(presentation_id, table_id, [row_data], unified_token)


def gslides_add_columns_and_populate(presentation_id: str, table_id: str, data: list,
                                     unified_token: str = None) -> dict:
    """Add new columns at the right of the table and populate them with data."""
    _, slides_service = get_gslides_service(unified_token)
    
    try:
        if not data or len(data) == 0:
            return {"status": "error", "message": "No data provided"}
        
        # Get current table info
        presentation = slides_service.presentations().get(presentationId=presentation_id).execute()
        
        table_element = None
        for slide in presentation.get("slides", []):
            for element in slide.get("pageElements", []):
                if element.get("objectId") == table_id:
                    table_element = element.get("table")
                    break
            if table_element:
                break
        
        if not table_element:
            return {"status": "error", "message": f"Table {table_id} not found"}
        
        num_rows = len(table_element.get("tableRows", []))
        current_cols = len(table_element.get("tableColumns", []))
        num_new_cols = len(data)
        
        # Step 1: Add columns at the right
        add_cols_request = [{
            'insertTableColumns': {
                'tableObjectId': table_id,
                'cellLocation': {
                    'rowIndex': 0,
                    'columnIndex': current_cols - 1
                },
                'insertRight': True,
                'number': num_new_cols
            }
        }]
        
        slides_service.presentations().batchUpdate(
            presentationId=presentation_id, body={'requests': add_cols_request}
        ).execute()
        
        # Step 2: Populate the new columns with data (in a separate request)
        # data format: list of columns, where each column is a list of cell values
        populate_requests = []
        for col_offset, col_data in enumerate(data):
            actual_col_index = current_cols + col_offset
            for row_index, cell_value in enumerate(col_data):
                if row_index >= num_rows:
                    break  # Skip if more rows in data than in table
                
                cell_location = {
                    'rowIndex': row_index,
                    'columnIndex': actual_col_index
                }
                
                # Insert new text if cell_value is not empty
                # No need to delete - newly created cells are empty
                if cell_value:
                    populate_requests.append({
                        'insertText': {
                            'objectId': table_id,
                            'cellLocation': cell_location,
                            'text': str(cell_value),
                            'insertionIndex': 0
                        }
                    })
        
        # Execute populate requests
        if populate_requests:
            slides_service.presentations().batchUpdate(
                presentationId=presentation_id, body={'requests': populate_requests}
            ).execute()
        
        return {
            "status": "success",
            "message": f"Added {num_new_cols} column(s) at right and populated with data",
            "table_id": table_id,
            "columns_added": num_new_cols,
            "starting_column": current_cols
        }
    
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gslides_append_table_column(presentation_id: str, table_id: str, column_data: list,
                                unified_token: str = None) -> dict:
    """Append a single column to the right of the table with data."""
    return gslides_add_columns_and_populate(presentation_id, table_id, [column_data], unified_token)