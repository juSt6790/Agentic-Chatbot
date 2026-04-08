from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
import os
import json
from typing import List
import requests
from clients.db_method import get_user_tool_access_token
import re


# BASE_URL = "http://3.6.95.164:5000/users"

# # Example: Call get_tool_token endpoint
# def get_tool_token(unified_token, tool_name):
#     url = f"{BASE_URL}/get_tool_token"
#     payload = {
#         "unified_token": unified_token,
#         "tool_name": tool_name
#     }

#     response = requests.post(url, json=payload)
#     print("abc")
#     if response.status_code == 200:
#         print("Access Token:", response.json())
#         return response.json()
#     else:
#         print("Error:", response.status_code, response.text)


def get_gsheets_service(unified_token):
    tool_name = "Gsuite"
    # result = get_tool_token(unified_token, tool_name)
    result, status = get_user_tool_access_token(unified_token, tool_name)
    
    # Check if credentials exist before accessing
    if status != 200 or not isinstance(result, dict) or "access_token" not in result:
        error_msg = result.get("error", "Failed to retrieve Google Sheets credentials") if isinstance(result, dict) else "Failed to retrieve Google Sheets credentials"
        raise Exception(f"Failed to retrieve Google Sheets credentials. Please connect Google Sheets. {error_msg}")

    access_data = result["access_token"]
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

    sheets_service = build("sheets", "v4", credentials=creds)
    drive_service = build("drive", "v3", credentials=creds)
    return drive_service, sheets_service


def gsheets_list_sheets(page_size: int = 20, unified_token: str = None) -> list:
    try:
        drive_service, _ = get_gsheets_service(unified_token)

        query = "mimeType='application/vnd.google-apps.spreadsheet' and trashed=false"
        response = (
            drive_service.files()
            .list(
                q=query,
                pageSize=page_size,
                fields="files(id, name)",
            )
            .execute()
        )

        files = response.get("files", [])
        return [{"id": f["id"], "title": f["name"]} for f in files]
    except Exception as e:
        return []


def gsheets_create_sheet(title: str, unified_token: str = None) -> dict:
    try:
        _, sheets_service = get_gsheets_service(unified_token)
        if not title:
            return {"status": "error", "message": "Title cannot be empty"}
        
        body = {"properties": {"title": title}}
        spreadsheet = sheets_service.spreadsheets().create(body=body).execute()
        return {"spreadsheetId": spreadsheet["spreadsheetId"], "title": title}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def normalize_range(sheet_name: str, cell_range: str = "A1:Z50") -> str:
    # Fallback to A1:Z50 if cell_range is invalid
    if not cell_range or not any(char.isdigit() for char in cell_range):
        cell_range = "A1:Z50"

    if any(c in sheet_name for c in " -&/\\()[]{}"):
        sheet_name = f"'{sheet_name}'"

    return f"{sheet_name}!{cell_range}"


def column_index_to_letter(col_index: int) -> str:
    """Convert a 0-based column index to A1 notation (A, B, ..., Z, AA, AB, ...)"""
    result = ""
    col_index += 1  # Convert to 1-based
    while col_index > 0:
        col_index -= 1
        result = chr(65 + (col_index % 26)) + result
        col_index //= 26
    return result


def resolve_column_name_to_range(
    column_name: str, 
    sheet_id: str, 
    sheet_name: str, 
    safe_name: str,
    sheets_service,
    create_if_missing: bool = True
) -> str:
    """
    Resolve ANY column name (like "Trello Link", "Status", "Due Date", etc.) to a valid A1 range.
    Handles:
    - Column names with spaces, special characters
    - Case-insensitive matching
    - Empty sheets (creates header row if needed)
    - Missing columns (auto-creates if create_if_missing=True)
    
    Returns None if column not found and create_if_missing=False.
    """
    try:
        if not column_name or not str(column_name).strip():
            return None
        
        column_name = str(column_name).strip()
        
        # Read headers from the sheet (try first row)
        header_range = f"{safe_name}!A1:ZZ1"
        header_result = sheets_service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=header_range
        ).execute()
        
        headers = header_result.get("values", [])
        header_row = headers[0] if headers and len(headers) > 0 and headers[0] else []
        
        # Normalize header row - handle empty cells, None values, etc.
        normalized_headers = []
        for h in header_row:
            header_val = str(h).strip() if h is not None else ""
            normalized_headers.append(header_val)
        
        # Find the column index - try exact match first, then case-insensitive
        col_index = None
        
        # First try exact match (handles spaces, special chars as-is)
        try:
            col_index = normalized_headers.index(column_name)
        except ValueError:
            # Try case-insensitive match with normalized comparison
            column_name_lower = column_name.lower()
            for idx, header in enumerate(normalized_headers):
                if header.lower() == column_name_lower:
                    col_index = idx
                    break
        
        # If column not found and we should create it
        if col_index is None:
            if not create_if_missing:
                return None
            
            # Handle empty sheet - create header row if needed
            if not normalized_headers or all(not h for h in normalized_headers):
                # Sheet is empty or has no headers - create header in A1
                header_update_range = f"{safe_name}!A1"
                header_body = {"values": [[column_name]]}
                sheets_service.spreadsheets().values().update(
                    spreadsheetId=sheet_id,
                    range=header_update_range,
                    valueInputOption="USER_ENTERED",
                    body=header_body,
                ).execute()
                col_index = 0
                print(f"📋 Created header row with column '{column_name}' at column A")
            else:
                # Add the new column header at the end
                next_col_index = len(normalized_headers)
                next_col_letter = column_index_to_letter(next_col_index)
                
                # Update the header cell with the new column name
                header_update_range = f"{safe_name}!{next_col_letter}1"
                header_body = {"values": [[column_name]]}
                sheets_service.spreadsheets().values().update(
                    spreadsheetId=sheet_id,
                    range=header_update_range,
                    valueInputOption="USER_ENTERED",
                    body=header_body,
                ).execute()
                
                print(f"📋 Added new column header '{column_name}' at column {next_col_letter}")
                col_index = next_col_index
        
        # Convert index to column letter (A, B, C, etc.)
        col_letter = column_index_to_letter(col_index)
        
        # Return full column range (e.g., 'Due Last Week'!B:B)
        return f"{safe_name}!{col_letter}:{col_letter}"
    
    except HttpError as e:
        print(f"⚠️ HTTP Error resolving column name '{column_name}': {e}")
        return None
    except Exception as e:
        print(f"⚠️ Error resolving column name '{column_name}': {e}")
        return None


def validate_and_normalize_target_range(target: str, safe_name: str) -> str:
    """
    Validate and normalize a target range for Sheets API.
    Handles cases like:
    - "2" → "Sheet!2:2" (entire row)
    - "A2" → "Sheet!A2" (single cell)
    - "A2:Z2" → "Sheet!A2:Z2" (valid range)
    - "2:2" → "Sheet!2:2" (entire row)
    """
    if not target:
        return None

    target = str(target).strip()

    # If target is just a number (row number), use full row range (entire row)
    if target.isdigit():
        row_num = int(target)
        return f"{safe_name}!{row_num}:{row_num}"

    # If target is in format "row:row" (e.g., "2:2"), use as full row
    if ":" in target and target.count(":") == 1:
        parts = target.split(":")
        if parts[0].isdigit() and parts[1].isdigit():
            row_num = int(parts[0])
            return f"{safe_name}!{row_num}:{row_num}"

    # If target doesn't contain "!", add the sheet name
    if "!" not in target:
        return f"{safe_name}!{target}"

    # Already has sheet name, return as-is
    return target

def column_index_to_letter(index: int) -> str:
    result = ""
    while index >= 0:
        result = chr(index % 26 + ord("A")) + result
        index = index // 26 - 1
    return result

def gsheets_read_data(
    sheet_id: str,
    unified_token: str = None,
    sheet_name: str = None,
    column_name: str | list[str] = None,
    range_: str = None,
    all_sheets_info: dict | None = None,
    include_cells: bool = False, 
) -> dict:
    """
    Read data from a Google Sheets file.

    - Uses all_sheets_info (from gsheets_get_structure) if provided.
    - If not provided or sheet_id mismatched, rebuilds structure internally.
    - Supports reading all sheets, specific sheets, and filtering by column names.
    - Returns data in a structure aligned with Slides MCP (spreadsheet → sheets).
    """
    try:
        _, sheets_service = get_gsheets_service(unified_token)

        # --- Step 1: Use provided structure or rebuild if mismatched ---
        if all_sheets_info and all_sheets_info.get("sheet_id") == sheet_id:
            sheets_metadata = all_sheets_info.get("sheets", [])
        else:
            structure = gsheets_get_structure(sheet_id, unified_token=unified_token)
            spreadsheet = structure.get("spreadsheet", {})
            sheets_metadata = spreadsheet.get("sheets", [])

        if not sheets_metadata:
            return {"status": "error", "message": "No sheets found in the spreadsheet."}

        results = []

        # --- Step 2: Normalize input ---
        if isinstance(column_name, str):
            column_name = [column_name]

        # --- Step 3: Determine which sheets to read ---
        if sheet_name:
            match = next(
                (s for s in sheets_metadata if s["sheet_name"].lower() == sheet_name.lower()),
                None,
            )
            if not match:
                return {"status": "error", "message": f"Sheet '{sheet_name}' not found."}
            target_sheets = [match]
        else:
            target_sheets = sheets_metadata  # Read all sheets if no sheet_name provided

        # --- Step 4: Read data from each target sheet ---
        for sheet_meta in target_sheets:
            name = sheet_meta["sheet_name"]
            safe_name = f"'{name}'" if any(c in name for c in " -&/\\()[]{}") else name
            header_row_index = sheet_meta.get("header_row_index") or 1

            # Build read range (use provided or default)
            read_range = range_ or f"{safe_name}!A1:Z1000"

            # Fetch data
            data_result = (
                sheets_service.spreadsheets()
                .values()
                .get(spreadsheetId=sheet_id, range=read_range)
                .execute()
            )

            values = data_result.get("values", [])
            range_str = data_result.get("range", "")
            start_row = 1
            start_col = 0

            if "!" in range_str:
                range_part = range_str.split("!")[1]
                start_cell = range_part.split(":")[0]

                col_part = ''.join(filter(str.isalpha, start_cell))
                row_part = ''.join(filter(str.isdigit, start_cell))

                start_row = int(row_part) if row_part else 1

                start_col = 0
                for c in col_part:
                    start_col = start_col * 26 + (ord(c.upper()) - ord("A") + 1)
                start_col -= 1
            if not values:
                continue

            headers = []
            data_rows = []

            # --- Step 5: Identify header row ---
            for row in values:
                if any(cell.strip() for cell in row if isinstance(cell, str)):
                    headers = row
                    break

            header_index = values.index(headers) + 1 if headers else 0
            # NEW CODE: Build structured rows with cell references
            structured_rows = []

            for r_offset, row in enumerate(values[header_index:]):
                actual_row = start_row + header_index + r_offset

                structured_row = []

                for c_offset, cell_value in enumerate(row):
                    col_letter = column_index_to_letter(start_col + c_offset)
                    cell_ref = f"{col_letter}{actual_row}"

                    if include_cells:
                        structured_row.append({
                            "value": cell_value,
                            "cell": cell_ref
                        })
                    else:
                        structured_row.append(cell_value)

                structured_rows.append(structured_row)

            data_rows = structured_rows

            # --- Step 6: Filter by column(s) if specified ---
            if column_name and headers:
                valid_columns = [c for c in column_name if c in headers]
                if not valid_columns:
                    return {
                        "status": "error",
                        "message": f"Requested column(s) {column_name} not found in sheet '{name}'.",
                    }

                indices = [headers.index(c) for c in valid_columns]
                filtered_data = [
                    [row[i] if i < len(row) else "" for i in indices]
                    for row in data_rows
                ]
                headers = [headers[i] for i in indices]
                data_rows = filtered_data

            results.append(
                {
                    "sheet_name": name,
                    "headers": headers,
                    "data": data_rows,
                }
            )

        if not results:
            return {"status": "error", "message": "No data found in the spreadsheet."}

        # --- Step 7: Return final structured response (Slides-style) ---
        spreadsheet_info = {
            "id": sheet_id,
            "sheet_count": len(results),
            "sheets": results,
        }

        return {
            "status": "success",
            "spreadsheet": spreadsheet_info,
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}
    
def gsheets_get_structure(sheet_id: str, unified_token: str = None) -> dict:
    """
    Retrieve structural metadata for all sheets (tabs) in a Google Spreadsheet.
    Identifies headers even if they are not in the first row.

    Returns:
        {
            "status": "success",
            "Sheet_id": "...",
            "title": "...",
            "sheet_count": int,
            "sheets": [
                {
                    "sheet_name": str,
                    "sheet_id": int,
                    "index": int,
                    "row_count": int,
                    "column_count": int,
                    "headers": list[str],
                    "header_row_index": int | None
                },
                ...
            ]
        }
    """
    try:
        _, sheets_service = get_gsheets_service(unified_token)

        # Fetch spreadsheet metadata
        spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=sheet_id).execute()
        sheets = spreadsheet.get("sheets", [])
        spreadsheet_title = spreadsheet.get("properties", {}).get("title", "Untitled Spreadsheet")

        all_sheets_info = []

        for sheet in sheets:
            props = sheet.get("properties", {})
            sheet_name = props.get("title", "")
            sheet_tab_id = props.get("sheetId", "")
            index = props.get("index", 0)
            grid_props = props.get("gridProperties", {})

            row_count = grid_props.get("rowCount", 0)
            col_count = grid_props.get("columnCount", 0)

            # Safely quote sheet names with special chars
            safe_name = f"'{sheet_name}'" if any(c in sheet_name for c in " -&/\\()[]{}") else sheet_name
            range_ = f"{safe_name}!A1:Z10"

            # Read first 10 rows to detect headers intelligently
            result = (
                sheets_service.spreadsheets()
                .values()
                .get(spreadsheetId=sheet_id, range=range_)
                .execute()
            )
            values = result.get("values", [])

            headers = []
            header_row_index = None

            # Find the first non-empty row
            for idx, row in enumerate(values, start=1):
                if any(cell.strip() for cell in row if isinstance(cell, str)):
                    headers = row
                    header_row_index = idx
                    break

            all_sheets_info.append(
                {
                    "sheet_name": sheet_name,
                    "sheet_id": sheet_tab_id,
                    "index": index,
                    "row_count": row_count,
                    "column_count": col_count,
                    "headers": headers,
                    "header_row_index": header_row_index,
                }
            )

        # print("--------------------------------{all_sheets_info}")
        return {
            "status": "success",
            "spreadsheet": {
                "id": sheet_id,  # ✅ top-level ID, mirrors Slides’ presentation_id
                "title": spreadsheet_title,
                "sheet_count": len(all_sheets_info),
                "sheets": all_sheets_info,
                },
            }

    except Exception as e:
        return {"status": "error", "message": str(e)}

def _normalize_header(h: str) -> str:
    """Normalize a header for comparison: strip and return as string."""
    if h is None:
        return ""
    return str(h).strip()


def _headers_match_set(headers: list) -> set:
    """Return a set of normalized, lowercased headers for consistent comparison."""
    return {_normalize_header(h).lower() for h in headers if _normalize_header(h)}


def _dict_value_for_header(item: dict, header: str) -> str | int | float | bool:
    """
    Get the value from item that corresponds to header, using case-insensitive
    and strip-insensitive matching. Ensures consistent mapping when sheet headers
    differ in spacing/casing from dict keys.
    """
    norm = _normalize_header(header).lower()
    if not norm:
        return ""
    for key, val in item.items():
        if _normalize_header(key).lower() == norm:
            return val
    return ""


def _ensure_primitives(value):
    """
    Recursively convert any value to a primitive (string, number, bool, None).
    Handles dicts, lists, and nested structures.
    This ensures the Sheets API receives only primitive types, not struct objects.
    """
    if value is None:
        return ""
    elif isinstance(value, (str, int, float, bool)):
        return value
    elif isinstance(value, dict):
        # If it's a dict, try to extract a meaningful string representation
        # or convert to JSON string
        try:
            return json.dumps(value)
        except:
            return str(value)
    elif isinstance(value, list):
        # If it's a list, convert to comma-separated string
        return ", ".join(str(_ensure_primitives(item)) for item in value)
    else:
        # Fallback: convert to string
        return str(value)


def handle_sheets_http_error(e: HttpError) -> dict:
    """
    Centralized error handler for Google Sheets API HttpError exceptions.
    Returns a structured error response with appropriate messages.
    """
    error_code = e.resp.status if hasattr(e, 'resp') else None
    error_details = str(e)
    
    if error_code == 403:
        return {
            "status": "error",
            "message": "Permission denied. The caller does not have permission to access this spreadsheet. Please check that the spreadsheet is shared with the authenticated user and that the OAuth token has the required scopes.",
            "error_code": 403,
            "details": error_details
        }
    elif error_code == 400:
        # Parse range errors specifically
        if "Unable to parse range" in error_details or "Invalid values" in error_details:
            return {
                "status": "error",
                "message": f"Invalid range or data format: {error_details}",
                "error_code": 400,
                "details": error_details
            }
        return {
            "status": "error",
            "message": f"Bad request: {error_details}",
            "error_code": 400,
            "details": error_details
        }
    elif error_code == 404:
        return {
            "status": "error",
            "message": "Spreadsheet or sheet not found. Please verify the spreadsheet ID and sheet name.",
            "error_code": 404,
            "details": error_details
        }
    else:
        return {
            "status": "error",
            "message": f"Google Sheets API error: {error_details}",
            "error_code": error_code,
            "details": error_details
        }


def gsheets_update_data(
    sheet_id: str,
    sheet_name: str,
    mode: str,
    data: list | dict | str,
    target: str | None = None,
    unified_token: str = None,
) -> dict:
    """
    Add or update data in a Google Sheet.

    Automatically infers whether to update or append based on `target`.
    Supports:
        - mode="cell"   → update a specific cell
        - mode="row"    → append or update a row
        - mode="column" → append or update a column
    """
    try:
        _, sheets_service = get_gsheets_service(unified_token)

        # --- Step 1: Prepare safe sheet name ---
        safe_name = f"'{sheet_name}'" if any(c in sheet_name for c in " -&/\\()[]{}") else sheet_name
        
        # --- Normalize data structure for Sheets API ---
        if mode == "cell":
        # Always a single value → wrap twice
            if isinstance(data, (str, int, float, bool)) or data is None:
                normalized_data = [[_ensure_primitives(data)]]
            elif isinstance(data, list):
                # e.g., ["Done"] → [["Done"]]
                normalized_data = [[_ensure_primitives(item) for item in data]]
            else:
                normalized_data = [[_ensure_primitives(data)]]
        elif mode == "row":
            # Expect either:
            #   - a single row → flat list:           ["Date", "Start Time", ...]
            #   - multiple rows → list of lists:      [["Date", ...], ["2026-02-01", ...], ...]
            #   - a single dict → one row:            {"Date": "...", "Task": "..."}
            #   - multiple dicts → multiple rows:    [{"Date": "...", "Task": "..."}, {...}]
            if isinstance(data, dict):
                # Dict → Extract values in order (Sheets needs list of primitives, not objects)
                # Convert {"Date": "...", "Task": "..."} → [["...", "..."]]
                row = [_ensure_primitives(val) for val in data.values()]
                normalized_data = [row]
            elif isinstance(data, list):
                if not data:
                    return {"status": "error", "message": "Data list cannot be empty."}
                
                # Check if it's a list of dicts (multiple rows)
                if all(isinstance(item, dict) for item in data):
                    # List of dicts → convert each dict to a row
                    # First, get all unique keys from all dicts to determine column order
                    all_keys = []
                    seen_keys = set()
                    for item in data:
                        for key in item.keys():
                            if key not in seen_keys:
                                all_keys.append(key)
                                seen_keys.add(key)
                    
                    # Convert each dict to a row using the same key order
                    normalized_data = []
                    for item in data:
                        row = [_ensure_primitives(item.get(key, "")) for key in all_keys]
                        normalized_data.append(row)
                elif any(isinstance(item, (list, tuple)) for item in data):
                    # Already a 2D list → treat as multiple rows
                    normalized_data = [
                        [_ensure_primitives(cell) for cell in row] for row in data
                    ]
                else:
                    # Flat list → single row
                    normalized_data = [[_ensure_primitives(item) for item in data]]
            else:
                # Single scalar → one-column row
                normalized_data = [[_ensure_primitives(data)]]
        elif mode == "column":
            # Expect a list of items, each becomes its own row
            if isinstance(data, list):
                normalized_data = [[_ensure_primitives(val)] for val in data]
            else:
                normalized_data = [[_ensure_primitives(data)]]


        # --- Step 2: Handle different modes ---
        if mode == "cell":
            if not target:
                return {"status": "error", "message": "Target cell (e.g., 'B4') must be provided for cell updates."}

            # Validate and normalize the target range for cell updates
            # If target is just a number, it's invalid for cell mode (should be row mode)
            if target.isdigit():
                return {"status": "error", "message": f"Invalid cell reference '{target}'. For cell updates, use a valid cell reference like 'A1' or 'B4'. For row updates, use mode='row'."}
            
            # Normalize the range
            if "!" not in target:
                range_ref = f"{safe_name}!{target}"
            else:
                range_ref = target

            # Single cell update
            body = {"values": normalized_data}
            response = sheets_service.spreadsheets().values().update(
                spreadsheetId=sheet_id,
                range=range_ref,
                valueInputOption="USER_ENTERED",
                body=body,
            ).execute()

            result = {
                "action": "update_cell",
                "updated_range": response.get("updatedRange"),
                "updated_cells": response.get("updatedCells", 0),
            }

        elif mode == "row":
            if target:
                # --- Step 3A: Update existing row ---
                # target may be a row number or a textual hint (like "Task=Review")
                # Validate and normalize the target range
                range_ref = validate_and_normalize_target_range(target, safe_name)
                if not range_ref:
                    return {"status": "error", "message": "Invalid target range provided for row update."}
                
                body = {"values": normalized_data}
                response = sheets_service.spreadsheets().values().update(
                    spreadsheetId=sheet_id,
                    range=range_ref,
                    valueInputOption="USER_ENTERED",
                    body=body,
                ).execute()

                result = {
                    "action": "update_row",
                    "updated_range": response.get("updatedRange"),
                    "updated_rows": response.get("updatedRows", 0),
                }

            else:
                # --- Step 3B: Append new row(s) ---
                # Handle headers for dict-based data (single dict or list of dicts)
                if isinstance(data, dict) or (isinstance(data, list) and data and isinstance(data[0], dict)):
                    # Check if the sheet has headers already
                    try:
                        header_result = sheets_service.spreadsheets().values().get(
                            spreadsheetId=sheet_id,
                            range=f"{safe_name}!A1:ZZ1"
                        ).execute()
                        existing_headers = header_result.get("values", [[]])[0] if header_result.get("values") else []
                        
                        # Determine header keys
                        if isinstance(data, dict):
                            dict_keys = list(data.keys())
                        else:
                            # List of dicts - get all unique keys in order
                            all_keys = []
                            seen_keys = set()
                            for item in data:
                                for key in item.keys():
                                    if key not in seen_keys:
                                        all_keys.append(key)
                                        seen_keys.add(key)
                            dict_keys = all_keys
                        
                        # If no headers or headers don't match (by normalized name set), add headers
                        existing_set = _headers_match_set(existing_headers)
                        dict_set = _headers_match_set(dict_keys)
                        if not existing_headers or existing_set != dict_set:
                            # Add headers first
                            header_body = {"values": [dict_keys]}
                            sheets_service.spreadsheets().values().update(
                                spreadsheetId=sheet_id,
                                range=f"{safe_name}!A1",
                                valueInputOption="USER_ENTERED",
                                body=header_body,
                            ).execute()
                            print(f"📋 Added headers: {dict_keys}")
                            existing_headers = dict_keys
                        
                        # Reorder normalized_data to match existing headers (match by normalized name for consistency)
                        if existing_headers:
                            if isinstance(data, dict):
                                # Single dict - reorder to match headers; match keys case-insensitively
                                ordered_values = [_ensure_primitives(_dict_value_for_header(data, h)) for h in existing_headers]
                                normalized_data = [ordered_values]
                            else:
                                # List of dicts - reorder each row to match headers
                                normalized_data = []
                                for item in data:
                                    ordered_values = [_ensure_primitives(_dict_value_for_header(item, h)) for h in existing_headers]
                                    normalized_data.append(ordered_values)
                        else:
                            # Fallback: use dict values directly
                            if isinstance(data, dict):
                                row = [_ensure_primitives(val) for val in data.values()]
                                normalized_data = [row]
                            else:
                                normalized_data = [[_ensure_primitives(_dict_value_for_header(item, key)) for key in dict_keys] for item in data]
                    except Exception as e:
                        print(f"⚠️ Could not check/add headers: {e}")
                        # Fallback: use already-normalized data
                        if isinstance(data, dict):
                            row = [_ensure_primitives(val) for val in data.values()]
                            normalized_data = [row]
                        # If it's a list of dicts, normalized_data should already be set correctly above
                
                # Final safety check: ensure all values in normalized_data are primitives
                normalized_data = [[_ensure_primitives(cell) for cell in row] for row in normalized_data]
                
                body = {"values": normalized_data}
                response = sheets_service.spreadsheets().values().append(
                    spreadsheetId=sheet_id,
                    range=safe_name,
                    valueInputOption="USER_ENTERED",
                    insertDataOption="INSERT_ROWS",
                    body=body,
                ).execute()

                result = {
                    "action": "append_row",
                    "updated_range": response.get("updates", {}).get("updatedRange"),
                    "updated_rows": response.get("updates", {}).get("updatedRows", 0),
                }

        elif mode == "column":
            if target:
                # --- Step 4A: Update existing column ---
                # target can be ANY of:
                #   - Column letter: "B" → "'Sheet'!B:B"
                #   - Column name: "Trello Link", "Status", "Due Date", etc. → auto-resolve to column letter
                #   - Already a range: "'Sheet'!B:B" → use as-is
                
                target = str(target).strip()
                
                if not target:
                    return {"status": "error", "message": "Target column cannot be empty."}
                
                # Check if it's already a valid range (contains "!")
                if "!" in target:
                    range_ref = target
                # Check if it's a single letter (column letter like "B")
                elif len(target) == 1 and target.isalpha():
                    range_ref = f"{safe_name}!{target}:{target}"
                # Otherwise, treat as ANY column name and resolve it (will create if missing)
                # This handles: "Trello Link", "Status", "Due Date", "Task Name", etc.
                else:
                    range_ref = resolve_column_name_to_range(
                        target, sheet_id, sheet_name, safe_name, sheets_service, create_if_missing=True
                    )
                    if not range_ref:
                        return {
                            "status": "error",
                            "message": f"Could not resolve or create column '{target}' in sheet '{sheet_name}'. The column name may be invalid or there was an error accessing the sheet."
                        }
                
                body = {"values": normalized_data}
                response = sheets_service.spreadsheets().values().update(
                    spreadsheetId=sheet_id,
                    range=range_ref,
                    valueInputOption="USER_ENTERED",
                    body=body,
                ).execute()

                result = {
                    "action": "update_column",
                    "updated_range": response.get("updatedRange"),
                    "updated_cells": response.get("updatedCells", 0),
                }

            else:
                # --- Step 4B: Append a new column (not common in Sheets) ---
                metadata = sheets_service.spreadsheets().get(spreadsheetId=sheet_id).execute()
                sheet_tab_id = None
                col_index = 0
                
                for sheet in metadata.get("sheets", []):
                    props = sheet.get("properties", {})
                    if props.get("title", "").lower() == sheet_name.lower():
                        sheet_tab_id = props.get("sheetId")
                        col_index = props.get("gridProperties", {}).get("columnCount", 0)
                        break
                
                if sheet_tab_id is None:
                    return {"status": "error", "message": f"Sheet '{sheet_name}' not found."}
                
                insert_request = {
                    "requests": [
                        {
                            "insertDimension": {
                                "range": {
                                    "sheetId": sheet_tab_id,
                                    "dimension": "COLUMNS",
                                    "startIndex": col_index,
                                    "endIndex": col_index + 1,
                                },
                                "inheritFromBefore": True,
                            }
                        }
                    ]
                }
                
                # 3️⃣ Execute the batch update
                sheets_service.spreadsheets().batchUpdate(
                    spreadsheetId=sheet_id,
                    body=insert_request
                    ).execute()
                result = {
                    "action": "append_column",
                    "inserted_at": f"Index {col_index} (after existing {col_index} columns)",
                    }


        else:
            return {"status": "error", "message": f"Invalid mode '{mode}'. Use 'cell', 'row', or 'column'."}

        # --- Step 5: Return consistent response ---
        return {
            "status": "success",
            "spreadsheet": {
                "id": sheet_id,
                "sheet_name": sheet_name,
                "action": result.get("action"),
                "details": result,
            },
        }

    except HttpError as e:
        return handle_sheets_http_error(e)
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gsheets_write_data(
    sheet_id: str, range_: str, values: List[List[str]], unified_token: str = None
) -> dict:
    try:
        _, sheets_service = get_gsheets_service(unified_token)
        # Validate inputs
        if not values:
            return {"status": "error", "message": "Values list cannot be empty"}
        if not range_:
            return {"status": "error", "message": "Range cannot be empty"}
        
        # Ensure all values are primitives
        normalized_values = [[_ensure_primitives(cell) for cell in row] for row in values]
        body = {"values": normalized_values}
        result = (
            sheets_service.spreadsheets()
            .values()
            .update(spreadsheetId=sheet_id, range=range_, valueInputOption="RAW", body=body)
            .execute()
        )
        return {
            "status": "success",
            "updatedCells": result.get("updatedCells", 0)
        }
    except HttpError as e:
        return handle_sheets_http_error(e)
    except Exception as e:
        return {"status": "error", "message": str(e)}


# 5. Append Data
def gsheets_append_data(
    sheet_id: str, range_: str, values: List[List[str]], unified_token: str = None
) -> dict:
    try:
        _, sheets_service = get_gsheets_service(unified_token)
        # Validate inputs
        if not values:
            return {"status": "error", "message": "Values list cannot be empty"}
        if not range_:
            return {"status": "error", "message": "Range cannot be empty"}
        
        # Ensure all values are primitives
        normalized_values = [[_ensure_primitives(cell) for cell in row] for row in values]
        body = {"values": normalized_values}
        result = (
            sheets_service.spreadsheets()
            .values()
            .append(spreadsheetId=sheet_id, range=range_, valueInputOption="RAW", body=body)
            .execute()
        )
        return {
            "status": "success",
            "updates": result.get("updates", {})
        }
    except HttpError as e:
        return handle_sheets_http_error(e)
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gsheets_clear_range(sheet_id: str, range_: str, unified_token: str = None) -> dict:
    try:
        _, sheets_service = get_gsheets_service(unified_token)
        # Validate inputs
        if not range_:
            return {"status": "error", "message": "Range cannot be empty"}
        
        result = (
            sheets_service.spreadsheets()
            .values()
            .clear(spreadsheetId=sheet_id, range=range_, body={})
            .execute()
        )
        return {
            "status": "success",
            "clearedRange": result.get("clearedRange", range_)
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# 7. Add Tab
def gsheets_add_tab(sheet_id: str, title: str, unified_token: str = None) -> dict:
    try:
        _, sheets_service = get_gsheets_service(unified_token)
        if not title:
            return {"status": "error", "message": "Title cannot be empty"}
        
        requests = [{"addSheet": {"properties": {"title": title}}}]
        body = {"requests": requests}
        response = (
            sheets_service.spreadsheets()
            .batchUpdate(spreadsheetId=sheet_id, body=body)
            .execute()
        )
        return {"replies": response.get("replies", [])}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gsheets_rename_tab(
    sheet_id: str, sheet_tab_id: int, new_title: str, unified_token: str = None
) -> dict:
    try:
        _, sheets_service = get_gsheets_service(unified_token)
        if not new_title:
            return {"status": "error", "message": "New title cannot be empty"}
        
        requests = [
            {
                "updateSheetProperties": {
                    "properties": {"sheetId": sheet_tab_id, "title": new_title},
                    "fields": "title",
                }
            }
        ]
        response = (
            sheets_service.spreadsheets()
            .batchUpdate(spreadsheetId=sheet_id, body={"requests": requests})
            .execute()
        )
        return {"status": "renamed"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gsheets_delete_tab(
    sheet_id: str, sheet_tab_id: int, unified_token: str = None
) -> dict:
    try:
        _, sheets_service = get_gsheets_service(unified_token)
        requests = [{"deleteSheet": {"sheetId": sheet_tab_id}}]
        response = (
            sheets_service.spreadsheets()
            .batchUpdate(spreadsheetId=sheet_id, body={"requests": requests})
            .execute()
        )
        return {"status": "deleted"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gsheets_share_sheet(
    sheet_id: str, email: str, role: str = "writer", unified_token: str = None
) -> dict:
    drive_service, _ = get_gsheets_service(unified_token)
    permission = {"type": "user", "role": role, "emailAddress": email}
    try:
        result = (
            drive_service.permissions()
            .create(fileId=sheet_id, body=permission, fields="id")
            .execute()
        )
        return {
            "status": "success",
            "permissionId": result.get("id"),
            "shared_with": email,
            "sheet_id": sheet_id,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def search_sheets_by_title(
    keyword: str, limit: int = 10, unified_token: str = None
) -> dict:
    drive_service, _ = get_gsheets_service(unified_token)
    try:
        query = f"name contains '{keyword}' and mimeType='application/vnd.google-apps.spreadsheet' and trashed=false"
        response = (
            drive_service.files()
            .list(q=query, pageSize=limit, fields="files(id, name, modifiedTime)")
            .execute()
        )
        return {"matches": response.get("files", [])}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_sheet_history(sheet_id: str, unified_token: str = None) -> dict:
    drive_service, _ = get_gsheets_service(unified_token)
    try:
        metadata = (
            drive_service.files()
            .get(
                fileId=sheet_id,
                fields="id, name, modifiedTime, createdTime, owners, lastModifyingUser",
            )
            .execute()
        )
        return {
            "sheet_id": metadata.get("id"),
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


def gsheets_add_comment(
    spreadsheet_id: str,
    text: str,
    unified_token: str = None,
) -> dict:
    """
    Add a top-level comment to a Google Sheet via the Drive API.
    The comment is authored as the currently authenticated user.
    """
    drive_service, _ = get_gsheets_service(unified_token)
    try:
        comment_body = {"content": text}
        comment = (
            drive_service.comments()
            .create(
                fileId=spreadsheet_id,
                body=comment_body,
                fields="id,content,createdTime",
            )
            .execute()
        )
        return {
            "status": "success",
            "spreadsheet_id": spreadsheet_id,
            "comment_id": comment.get("id"),
            "content": comment.get("content"),
            "createdTime": comment.get("createdTime"),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def gsheets_get_chart_metadata(
    sheet_id: str,
    sheet_name: str = None,
    unified_token: str = None
) -> dict:
    """
    Retrieve metadata for all charts in a Google Spreadsheet or a specific sheet.

    Returns:
        {
            "status": "success",
            "id": "...",
            "title": "...",
            "chart_count": int,
            "charts": [
                {
                    "chart_id": int,
                    "title": str,
                    "type": str,
                    "sheet_name": str,
                    "data_ranges": list[str],
                    "position": str,
                },
                ...
            ]
        }
    """
    try:
        _, sheets_service = get_gsheets_service(unified_token)

        # --- Step 1️⃣: Fetch spreadsheet metadata ---
        spreadsheet = sheets_service.spreadsheets().get(
            spreadsheetId=sheet_id,
            includeGridData=False
        ).execute()

        spreadsheet_title = spreadsheet.get("properties", {}).get("title", "Untitled Spreadsheet")
        charts_info = []

        # --- Step 2️⃣: Iterate through all sheets or specific one ---
        for sheet in spreadsheet.get("sheets", []):
            props = sheet.get("properties", {})
            current_sheet_name = props.get("title", "")
            sheet_tab_id = props.get("sheetId", "")

            if sheet_name and current_sheet_name.casefold().strip() != sheet_name.casefold().strip():
                continue  # skip non-matching sheets safely

            charts = sheet.get("charts", [])
            for chart in charts:
                chart_id = chart.get("chartId")
                chart_spec = chart.get("spec", {})
                chart_type = (
                    chart_spec.get("basicChart", {}).get("chartType")
                    or chart_spec.get("pieChart", {}).get("chartType")
                    or "UNKNOWN"
                )
                chart_title = chart_spec.get("title", "Untitled Chart")

                # Extract source data ranges
                data_ranges = []
                if "basicChart" in chart_spec:
                    domains = chart_spec["basicChart"].get("domains", [])
                    series = chart_spec["basicChart"].get("series", [])
                    for d in domains:
                        for src in d.get("domain", {}).get("sourceRange", {}).get("sources", []):
                            start_col = src.get("startColumnIndex")
                            end_col = src.get("endColumnIndex")
                            start_row = src.get("startRowIndex")
                            end_row = src.get("endRowIndex")
                            data_ranges.append(f"{current_sheet_name}!R{start_row+1}C{start_col+1}:R{end_row}C{end_col}")
                    for s in series:
                        for src in s.get("series", {}).get("sourceRange", {}).get("sources", []):
                            start_col = src.get("startColumnIndex")
                            end_col = src.get("endColumnIndex")
                            start_row = src.get("startRowIndex")
                            end_row = src.get("endRowIndex")
                            data_ranges.append(f"{current_sheet_name}!R{start_row+1}C{start_col+1}:R{end_row}C{end_col}")

                # Determine position (overlay vs new sheet)
                pos = chart.get("position", {})
                if pos.get("newSheet"):
                    position = "new_sheet"
                else:
                    overlay = pos.get("overlayPosition", {})
                    anchor = overlay.get("anchorCell", {})
                    position = f"Embedded (row {anchor.get('rowIndex',0)+1}, col {anchor.get('columnIndex',0)+1})"

                charts_info.append({
                    "chart_id": chart_id,
                    "title": chart_title,
                    "type": chart_type,
                    "sheet_name": current_sheet_name,
                    "data_ranges": data_ranges,
                    "position": position
                })

        return {
            "status": "success",
            "id": sheet_id,
            "title": spreadsheet_title,
            "chart_count": len(charts_info),
            "charts": charts_info
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}
    
    
def a1_to_grid_range(a1_range: str, sheet_id: int) -> dict:
    """
    Convert an A1-style range like 'Sheet2!B2:D10' into a grid-based range
    usable by the Sheets API (requires numeric sheet_id).
    """
    # Remove sheet name if present
    if "!" in a1_range:
        a1_range = a1_range.split("!", 1)[1]

    # Split start:end
    parts = a1_range.split(":")
    start = parts[0]
    end = parts[1] if len(parts) > 1 else start

    def col_to_index(cell_ref: str) -> int:
        """Convert letters (A,B,AA,ZZ) → zero-based column index."""
        letters = re.sub(r"\d+", "", cell_ref).upper()
        idx = 0
        for c in letters:
            idx = idx * 26 + (ord(c) - ord("A") + 1)
        return idx - 1

    def row_to_index(cell_ref: str) -> int:
        """Convert digits → zero-based row index."""
        match = re.search(r"(\d+)", cell_ref)
        return int(match.group(1)) - 1 if match else 0

    start_col = col_to_index(start)
    start_row = row_to_index(start)
    end_col = col_to_index(end) + 1
    end_row = row_to_index(end) + 1

    return {
        "sheetId": sheet_id,
        "startRowIndex": start_row,
        "endRowIndex": end_row,
        "startColumnIndex": start_col,
        "endColumnIndex": end_col
    }

def gsheets_create_chart(
    sheet_id: str,
    sheet_name: str,
    chart_type: str,
    x_range: str,
    y_ranges: list[str],
    title: str = None,
    unified_token: str = None,
) -> dict:
    """
    Create a chart in Google Sheets using A1-style ranges for user input.
    Internally converts A1 ranges to grid indices for API compliance.
    """
    try:
        _, sheets_service = get_gsheets_service(unified_token)

        # --- Fetch spreadsheet metadata for numeric sheetId ---
        spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=sheet_id).execute()
        target_sheet = next(
            (
                s["properties"]
                for s in spreadsheet.get("sheets", [])
                if s["properties"]["title"].casefold().strip() == sheet_name.casefold().strip()
            ),
            None,
        )
        # --- Fetch grid info for intelligent range cleanup ---
        row_count = target_sheet.get("gridProperties", {}).get("rowCount", 100)

        if not target_sheet:
            return {"status": "error", "message": f"Sheet '{sheet_name}' not found."}

        sheet_tab_id = target_sheet["sheetId"]
        
        # Remove stray brackets and quotes from LLM output
        x_range = str(x_range).strip("[]").strip().replace("'", "")
        y_ranges = [str(y).strip("[]").strip().replace("'", "") for y in y_ranges]
        # Fill missing end rows using metadata row_count (e.g., "Sheet2!B2:B" → "Sheet2!B2:B14")
        
        #    Example: "Sheet2!B2:B" → "Sheet2!B2:B14"
        if re.match(r".*![A-Z]+\d+:[A-Z]+$", x_range):
            x_range = f"{x_range}{row_count}"

        cleaned_y_ranges = []
        for y in y_ranges:
            if re.match(r".*![A-Z]+\d+:[A-Z]+$", y):
                y = f"{y}{row_count}"
            cleaned_y_ranges.append(y)
        y_ranges = cleaned_y_ranges
        
        # --- Convert A1 ranges to numeric grid ranges ---
        x_grid = a1_to_grid_range(x_range, sheet_tab_id)
        y_grids = [a1_to_grid_range(y, sheet_tab_id) for y in y_ranges]

        # --- Build valid chart spec ---
        if chart_type.upper() == "PIE":
            chart_spec = {
                "title": title,
                "pieChart": {
                    "legendPosition": "RIGHT_LEGEND",
                    "domain": {
                        "sourceRange": {"sources": [x_grid]}
                    },
                    "series": {
                        "sourceRange": {"sources": [y_grids[0]]}
                    },
                },
            }
        else:
            chart_spec = {
                "title": title,
                "basicChart": {
                    "chartType": chart_type.upper(),
                    "legendPosition": "BOTTOM_LEGEND",
                        "domains": [{"domain": {"sourceRange": {"sources": [x_grid]}}}],
                        "series": [
                            {"series": {"sourceRange": {"sources": [y]}}, "targetAxis": "LEFT_AXIS"}
                            for y in y_grids
                        ],
                        "headerCount": 0,
                    },
            }

        # --- Let Sheets auto-place chart (no manual coordinates) ---
        body = {
            "requests": [
                {
                    "addChart": {
                        "chart": {
                            "spec": chart_spec,
                            "position": {   # ✅ required field
                                "overlayPosition": {
                                    "anchorCell": {
                                        "sheetId": sheet_tab_id,
                                        "rowIndex": 1,
                                        "columnIndex": 1
                                    }
                                }
                            }
                        }
                    }
                }
            ]
        }

        # --- Execute API call ---
        response = sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id, body=body
        ).execute()

        chart_id = response["replies"][0]["addChart"]["chart"]["chartId"]

        return {
            "status": "success",
            "id": sheet_id,
            "sheet_name": sheet_name,
            "chart_id": chart_id,
            "chart_type": chart_type,
            "x_range": x_range,
            "y_ranges": y_ranges,
            "message": f"Chart '{title or 'New Chart'}' created successfully.",
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}
    

def gsheets_update_chart(
    sheet_id: str,
    chart_id: int,
    title: str | None = None,
    chart_type: str | None = None,
    x_range: str | None = None,
    y_ranges: list[str] | None = None,
    unified_token: str = None,
) -> dict:
    """
    Update an existing chart in Google Sheets.

    This function modifies an existing chart’s spec using updateChartSpec:
        - Title
        - Chart type
        - Data ranges (X and Y)

    Args:
        sheet_id: ID of the spreadsheet.
        chart_id: Chart ID from metadata.
        title: Optional new title.
        chart_type: Optional new type (COLUMN, LINE, BAR, AREA, etc.).
        x_range: Optional new X-axis range (A1 notation).
        y_ranges: Optional list of new Y-axis ranges (A1 notation).
        unified_token: Auth token.
    """

    try:
        _, sheets_service = get_gsheets_service(unified_token)

        # --- Step 1: Fetch the spreadsheet’s charts ---
        spreadsheet = sheets_service.spreadsheets().get(
            spreadsheetId=sheet_id,
            fields="sheets(charts,properties.sheetId,properties.title)"
        ).execute()

        
        charts = []
        for s in spreadsheet.get("sheets", []):
            sheet_props = s.get("properties", {})
            sheet_id_in_loop = sheet_props.get("sheetId")
            sheet_title = sheet_props.get("title")

            for c in s.get("charts", []):
                # Attach useful metadata so we can later access the correct sheet
                c["sheetId"] = sheet_id_in_loop
                c["sheetTitle"] = sheet_title
                charts.append(c)
        
        if not charts:
            return {"status": "error", "message": "No charts found in this spreadsheet."}

        target_chart = next((c for c in charts if c.get("chartId") == chart_id), None)
        if not target_chart:
            return {"status": "error", "message": f"Chart ID {chart_id} not found."}

        # Get current spec to modify
        chart_spec = target_chart.get("spec", {})
        
        if x_range:
            x_range = str(x_range).strip("[]").strip().replace("'", "")
        if y_ranges:
            y_ranges = [str(y).strip("[]").strip().replace("'", "") for y in y_ranges]
        
        effective_x_range = None
        effective_y_ranges = None
        sheet_tab_id = target_chart.get("sheetId")
        
        if not sheet_tab_id and spreadsheet.get("sheets"):
            sheet_tab_id = spreadsheet["sheets"][0]["properties"]["sheetId"]
        # --- Determine effective x_range ---
        
        
        if x_range:
            # print(f"debug-----------------------------------------sheet_tab_id :{sheet_tab_id}")
            grid = a1_to_grid_range(x_range, sheet_tab_id)
            effective_x_range = {"sources": [grid]}
        else:
            if "basicChart" in chart_spec:
                domains = chart_spec["basicChart"].get("domains", [])
                if domains:
                    effective_x_range = domains[0]["domain"]["sourceRange"]
            elif "pieChart" in chart_spec:
                domain = chart_spec["pieChart"].get("domain", {})
                if domain:
                    effective_x_range = domain["sourceRange"]
            
            
        # --- Determine effective y_ranges ---
        if y_ranges:
            effective_y_ranges = [
                   {"sources": [a1_to_grid_range(y, sheet_tab_id)]}
                    for y in y_ranges
                ]
            
        else:
            if "basicChart" in chart_spec:
                series = chart_spec["basicChart"].get("series", [])
                effective_y_ranges = [s["series"]["sourceRange"] for s in series]
            elif "pieChart" in chart_spec:
                series = chart_spec["pieChart"].get("series", {})
                if series:
                    effective_y_ranges = [series["sourceRange"]]        
                
        # --- Step 2: Update only provided fields ---
        if title:
            chart_spec["title"] = title

        if chart_type:
            # Standardize to valid Sheets API types
            chart_type_map = {
                "COLUMN": "COLUMN",
                "BAR": "BAR",
                "LINE": "LINE",
                "AREA": "AREA",
                "SCATTER": "SCATTER",
                "COMBO": "COMBO",
                "PIE": "PIE"
            }
            resolved_type = chart_type_map.get(chart_type.upper(), "COLUMN")


            # Determine current chart type
            current_type = None
            if "basicChart" in chart_spec:
                current_type = chart_spec["basicChart"].get("chartType", "COLUMN")
            elif "pieChart" in chart_spec:
                current_type = "PIE"
            
            if current_type != resolved_type:
                if resolved_type == "PIE":
                    # Convert from basic → pie
                    chart_spec.pop("basicChart", None)
                    chart_spec["pieChart"] = {
                        "legendPosition": "RIGHT_LEGEND",
                        "domain": {},
                        "series": {},
                    }
                else:
                    # Convert from pie → basic (or update existing basic chart type)
                    chart_spec.pop("pieChart", None)
                    if "basicChart" not in chart_spec:
                        chart_spec["basicChart"] = {"legendPosition": "BOTTOM_LEGEND"}

                    #  Update only the chartType field here
                    chart_spec["basicChart"]["chartType"] = resolved_type
        
        
        if "basicChart" in chart_spec:
            if effective_x_range:
                chart_spec["basicChart"]["domains"] = [
                    {"domain": {"sourceRange": effective_x_range}}
                ]
            if effective_y_ranges:
                chart_spec["basicChart"]["series"] = [
                    {"series": {"sourceRange": y}} for y in effective_y_ranges
                ]

        elif "pieChart" in chart_spec:
            if effective_x_range:
                chart_spec["pieChart"]["domain"] = {"sourceRange": effective_x_range}
            if effective_y_ranges:
                chart_spec["pieChart"]["series"] = {"sourceRange": effective_y_ranges[0]}
        
        # --- Step 3: Build the update request ---
        update_request = {
            "requests": [{
                "updateChartSpec": {
                    "chartId": chart_id,
                    "spec": chart_spec
                }
            }]
        }

        # --- Step 4: Execute the update ---
        response = sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body=update_request
        ).execute()

        return {
            "status": "success",
            "id": sheet_id,
            "chart_id": chart_id,
            "updated_fields": {
                "title": title,
                "chart_type": chart_type,
                "x_range": effective_x_range,
                "y_ranges": effective_y_ranges,
            },
            "message": f"Chart {chart_id} updated successfully."
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}



def create_pivot_table(
    sheet_id: str,
    sheet_tab_id: int,
    source_range: str,
    pivot_sheet_title: str,
    rows: list,
    columns: list,
    values: list,
    unified_token: str = None,
) -> dict:
    try:
        # ------------------------
        # Validate inputs
        # ------------------------
        if not values or len(values) == 0:
            return {"success": False, "error": "Values list cannot be empty. At least one aggregation function is required."}
        
        if not rows or len(rows) == 0:
            return {"success": False, "error": "Rows list cannot be empty. At least one row field is required."}
        
        # ------------------------
        # Parse source range
        # ------------------------
        _, sheets_service = get_gsheets_service(unified_token)
        if "!" not in source_range or ":" not in source_range:
            return {"success": False, "error": "Invalid source_range format. Use 'Sheet1!A1:D100'"}

        sheet_name, cell_range = source_range.split("!")
        start_cell, end_cell = cell_range.split(":")

        def parse_cell(cell):
            col = ''.join(filter(str.isalpha, cell))
            row = int(''.join(filter(str.isdigit, cell)))
            col_index = sum((ord(c.upper()) - ord('A') + 1) * (26 ** i) for i, c in enumerate(reversed(col))) - 1
            return col_index, row - 1

        start_col, start_row = parse_cell(start_cell)
        end_col, end_row = parse_cell(end_cell)

        # ------------------------
        # Fetch headers (first row)
        # ------------------------
        header_range = f"{sheet_name}!{start_cell}:{chr(ord('A') + end_col)}{start_row + 1}"
        header_response = sheets_service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=header_range
        ).execute()
        headers = header_response.get("values", [[]])[0]
        if not headers or all(str(h).strip().isdigit() for h in headers):
            headers = [f"Column {i+1}" for i in range(end_col - start_col + 1)]


        # ------------------------
        # Create or clear pivot sheet
        # ------------------------
        try:
            request_body = {
                "requests": [
                    {
                        "addSheet": {
                            "properties": {
                                "title": pivot_sheet_title,
                                "gridProperties": {"rowCount": 1000, "columnCount": 50}
                            }
                        }
                    }
                ]
            }
            response = sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=sheet_id,
                body=request_body
            ).execute()
            pivot_sheet_id = response["replies"][0]["addSheet"]["properties"]["sheetId"]
        except Exception as e:
            if "already exists" in str(e):
                sheets_metadata = sheets_service.spreadsheets().get(spreadsheetId=sheet_id).execute()
                existing_sheet = next(
                    (s for s in sheets_metadata["sheets"] if s["properties"]["title"] == pivot_sheet_title), None
                )
                pivot_sheet_id = existing_sheet["properties"]["sheetId"]
                sheets_service.spreadsheets().values().clear(
                    spreadsheetId=sheet_id,
                    range=f"{pivot_sheet_title}"
                ).execute()
            else:
                raise e

        # ------------------------
        # Build pivot table
        # ------------------------
        pivot_table = {
            "source": {
                "sheetId": sheet_tab_id,
                "startRowIndex": start_row,
                "endRowIndex": end_row + 1,
                "startColumnIndex": start_col,
                "endColumnIndex": end_col + 1
            },
            "rows": [
                {"sourceColumnOffset": idx - start_col, "showTotals": True, "sortOrder": "ASCENDING"}
                for idx in rows
            ],
            "columns": (
                [
                    {"sourceColumnOffset": idx - start_col, "showTotals": True, "sortOrder": "ASCENDING"}
                    for idx in columns
                ]
                if values and len(values) > 0 and values[0].get("function", "").upper() == "SUM"
                else []
            ),
            "values": [
                {
                    "sourceColumnOffset": val.get("column_index", 0) - start_col,
                    "summarizeFunction": val.get("function", "SUM").upper(),
                    "name": f"{val.get('function', 'SUM').upper()} of {headers[val.get('column_index', 0) - start_col] if val.get('column_index', 0) - start_col < len(headers) else 'Column ' + str(val.get('column_index', 0)+1)}"
                }
                for val in values
            ],
            "valueLayout": "HORIZONTAL"
        }


        # ------------------------
        # Insert pivot table
        # ------------------------
        request_body = {
            "requests": [
                {
                    "updateCells": {
                        "rows": [{"values": [{"pivotTable": pivot_table}]}],
                        "start": {"sheetId": pivot_sheet_id, "rowIndex": 0, "columnIndex": 0},
                        "fields": "pivotTable"
                    }
                }
            ]
        }
        sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body=request_body
        ).execute()

        return {"success": True, "pivot_table_id": pivot_sheet_id,
                "message": f"Pivot table created in '{pivot_sheet_title}' (Sheet ID: {pivot_sheet_id})"}

    except Exception as e:
        return {"success": False, "error": str(e)}
