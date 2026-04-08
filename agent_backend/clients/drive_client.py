"""
Google Drive client for interacting with Google Drive API.
"""
import os
import io
import json
import logging
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaFileUpload
from googleapiclient.errors import HttpError
from typing import Optional, Dict, Any, Union, BinaryIO

logger = logging.getLogger(__name__)

def get_drive_service(unified_token: str = None):
    """
    Get an authenticated Google Drive service instance.
    
    Args:
        unified_token: User's OAuth token (from unified auth system) or path to token file
        
    Returns:
        Google Drive service instance or None if authentication fails
    """
    try:
        if not unified_token:
            logger.error("No token provided for Google Drive authentication")
            return None
            
        # If token is a file path, read the token from the file
        if os.path.isfile(unified_token):
            with open(unified_token, 'r') as f:
                token_data = json.load(f)
            creds = Credentials.from_authorized_user_info(token_data)
        else:
            # It's a unified token - fetch full credentials from database
            try:
                from clients.db_method import get_user_tool_access_token
                
                tool_name = "Gsuite"
                result, status = get_user_tool_access_token(unified_token, tool_name)
                
                if isinstance(result, tuple):
                    result, status = result
                    if status != 200:
                        logger.error(f"Failed to get access token: {result.get('error', 'Unknown error')}")
                        return None
                
                access_data = result.get("access_token", {})
                if not access_data:
                    logger.error("No access data found in the response")
                    return None
                
                # Create credentials with all required fields for refresh
                # Note: Don't specify scopes - use whatever was originally granted
                # to avoid "invalid_scope" errors during token refresh
                creds = Credentials(
                    token=access_data.get("token"),
                    refresh_token=access_data.get("refresh_token"),
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=access_data.get("client_id"),
                    client_secret=access_data.get("client_secret"),
                )
                
                logger.info("Successfully created credentials from unified token")
                
            except ImportError:
                logger.warning("db_method not available, trying direct token")
                # Fallback: try using token directly (may fail on refresh)
                creds = Credentials(unified_token)
            except Exception as e:
                logger.error(f"Error fetching credentials from database: {str(e)}")
                return None
        
        # Refresh token if expired
        if creds and creds.expired and creds.refresh_token:
            try:
                logger.info("Refreshing expired credentials...")
                creds.refresh(Request())
                logger.info("Credentials refreshed successfully")
            except Exception as e:
                logger.error(f"Error refreshing credentials: {str(e)}")
                return None
            
        if not creds or not creds.valid:
            logger.error("Invalid or expired credentials")
            return None
            
        return build('drive', 'v3', credentials=creds)
        
    except Exception as e:
        logger.error(f"Error initializing Google Drive service: {str(e)}")
        return None

def upload_file_to_drive(
    file_content: Union[bytes, str, BinaryIO],
    filename: str,
    mime_type: str,
    folder_id: str = None,
    unified_token: str = None
) -> Dict[str, Any]:
    """
    Upload a file to Google Drive.
    
    Args:
        file_content: File content as bytes, string, or file-like object
        filename: Name to give the file in Drive
        mime_type: MIME type of the file
        folder_id: Optional folder ID to upload to
        unified_token: User's OAuth token or path to token file
        
    Returns:
        Dictionary with file information or error details
    """
    try:
        drive_service = get_drive_service(unified_token)
        if not drive_service:
            return {"status": "error", "message": "Failed to initialize Google Drive service"}
        
        # Prepare file metadata
        file_metadata = {
            'name': filename,
            'mimeType': mime_type
        }
        
        # Add parent folder if specified
        if folder_id:
            file_metadata['parents'] = [folder_id]
        
        # Handle different types of file content
        if isinstance(file_content, bytes):
            media = MediaIoBaseUpload(
                io.BytesIO(file_content),
                mimetype=mime_type,
                resumable=True
            )
        elif isinstance(file_content, str):
            # If it's a string, encode to bytes
            media = MediaIoBaseUpload(
                io.BytesIO(file_content.encode('utf-8')),
                mimetype=mime_type,
                resumable=True
            )
        else:
            # Assume it's a file-like object
            media = MediaIoBaseUpload(
                file_content,
                mimetype=mime_type,
                resumable=True
            )
        
        # Upload the file
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name, webViewLink, webContentLink, mimeType, modifiedTime, size',
            supportsAllDrives=True
        ).execute()
        
        return {
            "status": "success",
            "file_id": file.get('id'),
            "name": file.get('name'),
            "web_view_link": file.get('webViewLink'),
            "web_content_link": file.get('webContentLink'),
            "mime_type": file.get('mimeType'),
            "modified_time": file.get('modifiedTime'),
            "size": file.get('size', 0)
        }
        
    except HttpError as e:
        error_details = str(e)
        try:
            error_details = e.content.decode('utf-8')
        except:
            pass
        logger.error(f"Google Drive API error: {error_details}")
        return {"status": "error", "message": f"Google Drive API error: {error_details}"}
    except Exception as e:
        logger.error(f"Error uploading file to Google Drive: {str(e)}")
        return {"status": "error", "message": f"Failed to upload file to Google Drive: {str(e)}"}

def create_folder(name: str, parent_id: str = None, unified_token: str = None) -> Dict[str, Any]:
    """
    Create a folder in Google Drive.
    
    Args:
        name: Name of the folder to create
        parent_id: Optional parent folder ID
        unified_token: User's OAuth token or path to token file
        
    Returns:
        Dictionary with folder information or error details
    """
    try:
        drive_service = get_drive_service(unified_token)
        if not drive_service:
            return {"status": "error", "message": "Failed to initialize Google Drive service"}
        
        file_metadata = {
            'name': name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        
        if parent_id:
            file_metadata['parents'] = [parent_id]
            
        folder = drive_service.files().create(
            body=file_metadata,
            fields='id, name, webViewLink',
            supportsAllDrives=True
        ).execute()
        
        return {
            "status": "success",
            "folder_id": folder.get('id'),
            "name": folder.get('name'),
            "web_view_link": folder.get('webViewLink')
        }
        
    except Exception as e:
        logger.error(f"Error creating folder in Google Drive: {str(e)}")
        return {"status": "error", "message": f"Failed to create folder: {str(e)}"}

def find_or_create_folder(folder_name: str, parent_id: str = None, unified_token: str = None) -> Dict[str, Any]:
    """
    Find a folder by name or create it if it doesn't exist.
    
    Args:
        folder_name: Name of the folder to find or create
        parent_id: Optional parent folder ID
        unified_token: User's OAuth token or path to token file
        
    Returns:
        Dictionary with folder information or error details
    """
    try:
        drive_service = get_drive_service(unified_token)
        if not drive_service:
            return {"status": "error", "message": "Failed to initialize Google Drive service"}
        
        # Build query to search for the folder
        query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        if parent_id:
            query += f" and '{parent_id}' in parents"
        
        # Search for the folder
        results = drive_service.files().list(
            q=query,
            fields="files(id, name, webViewLink)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        
        # If folder exists, return it
        if 'files' in results and len(results['files']) > 0:
            folder = results['files'][0]
            return {
                "status": "success",
                "folder_id": folder.get('id'),
                "name": folder.get('name'),
                "web_view_link": folder.get('webViewLink'),
                "exists": True
            }
        
        # If not found, create it
        return create_folder(folder_name, parent_id, unified_token)
        
    except Exception as e:
        logger.error(f"Error finding or creating folder in Google Drive: {str(e)}")
        return {"status": "error", "message": f"Failed to find or create folder: {str(e)}"}

def download_file(file_id: str, unified_token: str = None) -> Dict[str, Any]:
    """
    Download a file from Google Drive.
    
    Args:
        file_id: ID of the file to download
        unified_token: User's OAuth token or path to token file
        
    Returns:
        Dictionary with file content and metadata or error details
    """
    try:
        drive_service = get_drive_service(unified_token)
        if not drive_service:
            return {"status": "error", "message": "Failed to initialize Google Drive service"}
        
        # Get file metadata
        file_metadata = drive_service.files().get(
            fileId=file_id,
            fields='id, name, mimeType, modifiedTime, size',
            supportsAllDrives=True
        ).execute()
        
        # Download file content
        request = drive_service.files().get_media(fileId=file_id)
        file_content = request.execute()
        
        return {
            "status": "success",
            "content": file_content,
            "metadata": {
                "file_id": file_metadata.get('id'),
                "name": file_metadata.get('name'),
                "mime_type": file_metadata.get('mimeType'),
                "modified_time": file_metadata.get('modifiedTime'),
                "size": file_metadata.get('size', 0)
            }
        }
        
    except Exception as e:
        logger.error(f"Error downloading file from Google Drive: {str(e)}")
        return {"status": "error", "message": f"Failed to download file: {str(e)}"}