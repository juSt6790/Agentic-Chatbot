"""
Gmail MCP Server Implementation

This module provides a Model Context Protocol server for interacting with Gmail.
It exposes Gmail messages as resources and provides tools for composing and sending emails.
"""

import base64
import re
from datetime import datetime

# from typing import Optional
from typing import Optional, List, Dict, Any
import requests
import json, os
from requests.auth import HTTPBasicAuth
from googleapiclient.errors import HttpError
import asyncio
from mcp.server.fastmcp import FastMCP
from config.config import settings

# from config.config_calender import settings_config_calender

# import config_salesforce
# from simple_salesforce import Salesforce, SalesforceAuthenticationFailed
from googleapiclient.errors import HttpError

###########################***********************SALESFORCE
# from salesforce_mcp import (
#     get_salesforce_service,
#     create_lead,
#     update_lead_status,
#     delete_lead,
#     get_all_leads,
#     add_event,
#     get_lead,
# )

# Trello MCP
from services.trello_mcp import (
    trello_list_boards,
    trello_list_members,
    trello_list_lists,
    trello_create_list,
    trello_list_cards,
    trello_create_card,
    trello_create_card_by_names,
    trello_update_card,
    trello_move_card,
    trello_delete_card,
    trello_search,
    trello_find_board_by_name,
    trello_find_list_by_name,
    trello_get_card,
    trello_add_comment,
    trello_list_card_comments,
    trello_update_comment,
    trello_delete_comment,
    trello_add_members,
    trello_remove_member,
    trello_add_label,
    trello_remove_label,
    trello_list_board_labels,
    trello_create_board_label,
    trello_update_label,
    trello_create_checklist,
    trello_list_checklists,
    trello_add_checkitem,
    trello_update_checkitem,
    trello_delete_checkitem,
    trello_add_attachment_url,
    trello_set_custom_field,
)

###########################***********************GMAIL
from services.gmail_mcp import (
    get_gmail_service,
    create_draft,
    list_drafts,
    get_draft,
    send_draft,
    get_message,
    list_messages,
    search_messages,
    search_or_fetch_gmail_messages,
    get_labels,
    modify_message_labels,
    get_headers_dict,
    parse_message_body,
    parse_raw_message_body,
    create_message,
    create_multipart_message,
    send_email as gmail_send_email,
    create_label,
    delete_label,
)
from clients.mongo_email_client import (
    mongo_search_emails,
    mongo_query_emails,
    mongo_get_emails,
    unread_email_search,
    starred_email_search,
    from_email_search,
    to_email_search,
    # search_emails_by_date,
)
from clients.mongo_docs_client import (
    mongo_search_docs,
    mongo_query_docs,
    mongo_get_docs,
    search_docs_by_date,
    list_docs,
)
from services.slack_mcp import (
    send_slack_messages,
    list_channels as slack_list_channels,
    slack_get_channel_messages as get_channel_messages,
    # get_channel_info as slack_get_channel_info,
    list_users as slack_list_users,
    get_channel_members as slack_get_channel_members,
    get_user_info as slack_get_user_info,
    create_channel as slack_create_channel,
    archive_channel as slack_archive_channel,
    invite_user_to_channel as slack_invite_user_to_channel,
    kick_user_from_channel as slack_kick_user_from_channel,
    pin_message as slack_pin_message,
    unpin_message as slack_unpin_message,
    # react_to_message as slack_react_to_message,
    open_dm_with_user as slack_open_dm,
    slack_reply_message as reply_message,
    send_dm as slack_send_dm,
    get_dm_messages as slack_get_dm_messages,
    # upload_file as slack_upload_file,
)

from services.docs_mcp import (
    gdocs_get_user_documents,
    gdocs_get_document_content,
    gdocs_get_document_with_structure,
    gdocs_create_document,
    gdocs_delete_document,
    gdocs_share_document,
    gdocs_update_document,
    gdocs_update_image,
    gdocs_update_table,
    gdocs_get_table_content,
    gdocs_search_in_document,
    search_docs_by_title,
    get_doc_history,
    gdocs_generate_doc_from_link,
    gdocs_add_comment,
)

from services.sheets_mcp import (
    gsheets_list_sheets,
    gsheets_create_sheet,
    gsheets_read_data,
    gsheets_write_data,
    gsheets_append_data,
    gsheets_clear_range,
    gsheets_add_tab,
    gsheets_delete_tab,
    gsheets_share_sheet,
    search_sheets_by_title,
    get_sheet_history,
    gsheets_add_comment,
    gsheets_get_structure,
    gsheets_update_data,
    gsheets_get_chart_metadata,
    gsheets_create_chart,
    gsheets_update_chart,
    create_pivot_table,
)

from services.slides_mcp import (
    gslides_list_presentations,
    gslides_create_presentation,
    gslides_share_presentation,
    gslides_extract_text,
    gslides_get_slide_content,
    gslides_get_specific_slide,
    gslides_replace_text,
    gslides_add_text_box,
    gslides_add_slide,
    gslides_format_text,
    search_slides_by_title,
    get_slide_history,
    gslides_add_table,
    gslides_update_table_cell,
    gslides_populate_table,
    gslides_add_table_rows,
    gslides_add_table_columns,
    gslides_delete_table_rows,
    gslides_delete_table_columns,
    gslides_insert_row_above,
    gslides_insert_row_below,
    gslides_insert_column_left,
    gslides_insert_column_right,
    # New powerful tools from gSlides_ai
    gslides_list_slide_elements,
    gslides_list_tables,
    gslides_get_table_info,
    gslides_read_table_data,
    gslides_replace_table_text,
    gslides_search_presentation,
    gslides_get_element_text,
    gslides_delete_element,
    gslides_delete_slide,
    gslides_insert_text,
    gslides_insert_image,
    gslides_list_slides_info,
    gslides_add_rows_and_populate,
    gslides_append_table_row,
    gslides_add_columns_and_populate,
    gslides_append_table_column,
)


from services.notion_mcp import (
    notion_list_databases,
    notion_list_pages,
    notion_create_page,
    notion_create_database,
    notion_create_parent_page,
    notion_update_block,
    notion_delete_block,
    notion_find_or_create_database,
    notion_list_parent_pages,
    notion_list_all_database_parents,
    notion_list_child_pages,
    notion_search_notion,
    notion_append_block,
    notion_get_page_content,
    notion_update_page_title,
    notion_update_page_properties,
    notion_delete_page,
    notion_add_todo,
    notion_query_database,
    notion_get_documents,
    notion_get_tasks_detailed,
    notion_create_task,
    notion_find_tasks_tracker_db,
    notion_get_comments,
    add_notion_comment,
    notion_get_database_schema,
)


# import get_calendar_service, create_event, list_events, delete_event, get_event
###########################***********************CALENDER
from services.calendar_mcp import (
    get_calendar_service,
    create_event,
    list_events,
    delete_event,
    get_event,
    search_events,
    delete_events_by_filter,
    update_event as calendar_update_event,
)
from clients.mongo_calendar_client import (
    mongo_search_events,
    mongo_query_events,
    mongo_get_events,
)
from services.transcript_mcp import get_meeting_transcript

# from google_calender.calendar_mcp import
from datetime import datetime, timedelta

# import google_calender.calendar_mcp
import tzlocal, pytz

# # Jira (use env vars — never commit credentials)
# # your_domain_url = os.environ.get("JIRA_DOMAIN_URL", "")
# # auth = HTTPBasicAuth(
# #     os.environ.get("JIRA_EMAIL", ""),
# #     os.environ.get("JIRA_API_TOKEN", ""),
# # )


headers = {"Accept": "application/json"}
#     "Content-Type": "application/json"
# }


# Initialize JIRA MCP server
# mcp_jira = FastMCP(
#     "Jira MCP", instructions="Access and manage Jira projects and issues."
# )

# Initialize the Gmail service
# service_gmail = get_gmail_service(
#     credentials_path=settings.credentials_path, scopes=settings.scopes
# )
# service_calender = get_calendar_service()
mcp_gmail = FastMCP(
    "Gmail MCP Server",
    instructions="Access and interact with Gmail. You can get messages, threads, search emails, and send or compose new messages.",  # noqa: E501
)
mcp_calender = FastMCP(
    "Google Calendar MCP", instructions="Access and manage Google Calendar"
)
mcp_transcript = FastMCP(
    "Meeting transcripts",
    instructions="Schedule meeting notetaker bots and read stored transcripts.",
)
local_tz = tzlocal.get_localzone_name()
EMAIL_PREVIEW_LENGTH = 200
# Salesforce credentials (use environment variables in production)
# SF_USERNAME = config_salesforce.SF_USERNAME
# SF_PASSWORD = config_salesforce.SF_PASSWORD
# SF_TOKEN = config_salesforce.SF_TOKEN

# sf = get_salesforce_service()
# if not sf:
#     print("Salesforce authentication failed. Ensure credentials are correct.")

# Initialize MCP server
# mcp_salesforce = FastMCP(
#     "Salesforce MCP", instructions="Access and manage Salesforce resources."
# )


mcp_slack = FastMCP(
    "Slack MCP", instructions="Send messages and retrieve Slack channel info."
)
mcp_docs = FastMCP(
    "Google Docs MCP", instructions="Access and manage Google Docs files."
)

mcp_sheets = FastMCP(
    "Google Sheets MCP", instructions="Access and manage Google Sheets files."
)

mcp_slides = FastMCP(
    "Google Slides MCP", instructions="Access and manage Google Slides files."
)

mcp_notion = FastMCP(
    "Notion MCP", instructions="Manage and query Notion pages and databases."
)

# Task Manager (Trello) MCP
mcp_trello = FastMCP(
    "Task Manager MCP",
    instructions="Manage tasks using Trello: list boards/lists/cards, create/update/move/delete cards, and search tasks.",
)


@mcp_notion.tool()
def list_databases(token: str = None) -> dict:
    return notion_list_databases(unified_token=token)


@mcp_notion.tool()
def list_pages(database_id: str, token: str = None) -> dict:
    return notion_list_pages(database_id, unified_token=token)


@mcp_notion.tool()
def create_page(
    parent_id: str = None,
    title: str = "Untitled",
    content: str = "",
    token: str = None,
    database_id: str = None,
    database_name: str = None,
    properties: dict | None = None,
) -> dict:
    """
    Create a new Notion page.

    - For standalone pages (parent_id or database_name pointing to a page),
      properties is ignored.
    - For database rows (database_id or database_name pointing to a database),
      the page is created first, then any provided properties are applied via
      update_page_properties so they are validated against the database schema.
    """
    if not parent_id and not database_id and not database_name:
        return {
            "success": False,
            "error": "Either parent_id, database_id or database_name must be provided",
        }

    # First create the page/row
    result = notion_create_page(
        parent_id=parent_id,
        title=title,
        unified_token=token,
        content=content,
        database_id=database_id,
        database_name=database_name,
    )

    # If this is a row in a database and properties were provided, apply them
    # using update_page_properties which respects the database schema.
    if (
        result.get("success")
        and properties
        and (database_id or result.get("type") == "page_in_database")
    ):
        page_id = result.get("id")
        if page_id:
            notion_update_page_properties(
                page_id=page_id,
                properties=properties,
                unified_token=token,
            )

    return result


@mcp_notion.tool()
def search_notion(query: str, token: str = None) -> dict:
    return notion_search_notion(query, unified_token=token)


@mcp_notion.tool()
def append_block(
    page_id: str,
    content: str | None = None,
    mode: str | None = None,
    table: dict | None = None,
    token: str = None,
    heading_level: int | None = None,
    after_block_id: str | None = None,
    parent_block_id: str | None = None,
) -> dict:
    return notion_append_block(
        page_id=page_id,
        content=content,
        mode=mode,
        table=table,
        unified_token=token,
        heading_level=heading_level,
        after_block_id=after_block_id,
        parent_block_id=parent_block_id,
    )


@mcp_notion.tool()
def update_block(
    block_id: str,
    content: str | None = None,
    token: str = None,
    bold: bool | None = None,
    italic: bool | None = None,
    underline: bool | None = None,
    strikethrough: bool | None = None,
    text_color: str | None = None,
    **kwargs,
) -> dict:
    """Update/edit a specific block in a Notion page by its block ID."""
    # Accept style hints from rich_text payloads often produced by LLM tool calls.
    annotations: dict = {}
    rich_text = kwargs.get("rich_text")
    if isinstance(rich_text, list) and rich_text:
        first = rich_text[0] if isinstance(rich_text[0], dict) else {}
        ann = first.get("annotations")
        if isinstance(ann, dict):
            annotations = ann
        if bold is None and isinstance(annotations.get("bold"), bool):
            bold = annotations.get("bold")
        if italic is None and isinstance(annotations.get("italic"), bool):
            italic = annotations.get("italic")
        if underline is None and isinstance(annotations.get("underline"), bool):
            underline = annotations.get("underline")
        if strikethrough is None and isinstance(annotations.get("strikethrough"), bool):
            strikethrough = annotations.get("strikethrough")

    text_fmt: dict = {}
    formatting = kwargs.get("formatting")
    if isinstance(formatting, dict):
        text_fmt = formatting.get("text") if isinstance(formatting.get("text"), dict) else {}

        def _pick_bool(key: str):
            if key in formatting and isinstance(formatting.get(key), bool):
                return formatting.get(key)
            if key in text_fmt and isinstance(text_fmt.get(key), bool):
                return text_fmt.get(key)
            return None

        if bold is None:
            bold = _pick_bool("bold")
        if italic is None:
            italic = _pick_bool("italic")
        if underline is None:
            underline = _pick_bool("underline")
        if strikethrough is None:
            strikethrough = _pick_bool("strikethrough")

    if text_color is None or (isinstance(text_color, str) and not text_color.strip()):
        kc = kwargs.get("text_color")
        if isinstance(kc, str) and kc.strip():
            text_color = kc
        else:
            text_color = None
    if text_color is None:
        co = annotations.get("color")
        if isinstance(co, str) and co.strip():
            text_color = co
    if text_color is None and isinstance(formatting, dict):
        tc = formatting.get("color")
        if isinstance(tc, str) and tc.strip():
            text_color = tc
        elif isinstance(text_fmt, dict):
            tc2 = text_fmt.get("color")
            if isinstance(tc2, str) and tc2.strip():
                text_color = tc2

    return notion_update_block(
        block_id=block_id,
        content=content,
        unified_token=token,
        bold=bold,
        italic=italic,
        underline=underline,
        strikethrough=strikethrough,
        text_color=text_color,
    )


@mcp_notion.tool()
def delete_block(
    block_id: str = None, page_id: str = None, content_search: str = None, token: str = None
) -> dict:
    """Delete a specific block from a Notion page by block_id or by searching for content."""
    return notion_delete_block(
        block_id=block_id, 
        page_id=page_id, 
        content_search=content_search, 
        unified_token=token
    )


@mcp_notion.tool()
def get_page_content(page_id: str, token: str = None) -> dict:
    return notion_get_page_content(page_id, unified_token=token)


@mcp_notion.tool()
def get_notion_comment(
    page_id: str, token: str = None, comment_type: str = "page", block_id: str = None
) -> dict:
    return notion_get_comments(
        page_id, unified_token=token, comment_type=comment_type, block_id=block_id
    )


@mcp_notion.tool()
def notion_add_comment(
    page_id: str,
    content: str,
    token: str = None,
    target_type: str = "page",
    block_id: str = None,
) -> dict:
    return add_notion_comment(
        page_id,
        content,
        unified_token=token,
        target_type=target_type,
        block_id=block_id,
    )


@mcp_notion.tool()
def update_page_title(
    page_id: str, new_title: str, token: str = None, **kwargs
) -> dict:
    """
    Update the title of a Notion page.

    Extra keyword arguments are accepted and ignored so that tool calls
    passing additional metadata (e.g. created_time) do not cause errors.
    """
    return notion_update_page_title(page_id, new_title, unified_token=token)


@mcp_notion.tool()
def update_page_properties(
    page_id: str, properties: dict, token: str = None
) -> dict:
    """
    Update properties of a Notion database page (row). Use get_database_schema
    to get exact property names and allowed values. Note: Notion's built-in
    'Created time' cannot be changed via the API.
    """
    return notion_update_page_properties(
        page_id=page_id, properties=properties, unified_token=token
    )


@mcp_notion.tool()
def delete_page(page_id: str = None, document_id: str = None, token: str = None) -> dict:
    # Handle both page_id and document_id for backward compatibility
    target_id = page_id or document_id
    if not target_id:
        return {"status": "error", "message": "Either page_id or document_id must be provided"}
    return notion_delete_page(target_id, unified_token=token)


@mcp_notion.tool()
def add_todo(page_id: str, todo_text: str, token: str = None) -> dict:
    return notion_add_todo(page_id, todo_text, unified_token=token)


@mcp_notion.tool()
def query_database(database_id: str, status_value: str, token: str = None) -> dict:
    return notion_query_database(database_id, status_value, unified_token=token)


@mcp_notion.tool()
def get_database_schema(
    database_id: str, sample_page_limit: int = 10, token: str = None
) -> dict:
    """
    Return the schema for a Notion database, including property types,
    select/status options, and example values from up to `sample_page_limit` rows.
    """
    return notion_get_database_schema(
        database_id=database_id,
        unified_token=token,
        sample_page_limit=sample_page_limit,
    )


@mcp_notion.tool()
def get_documents(token: str = None) -> dict:
    return notion_get_documents(unified_token=token)


@mcp_notion.tool()
def get_tasks_detailed(token: str = None) -> dict:
    """Return detailed tasks from Notion task tracker databases."""
    return notion_get_tasks_detailed(unified_token=token)


@mcp_notion.tool()
def create_task(data: dict, database_id: str | None = None, token: str = None) -> dict:
    """Create a task in Notion. If database_id is not provided, tries to use 'tasks_tracker'."""
    return notion_create_task(unified_token=token, database_id=database_id, data=data)


@mcp_notion.tool()
def find_tasks_tracker_db(token: str = None) -> dict:
    """Find the user's Notion database named 'tasks_tracker' (case-insensitive)."""
    return notion_find_tasks_tracker_db(unified_token=token)


@mcp_notion.tool()
def find_or_create_database(database_name: str, token: str = None) -> dict:
    """Find a database by name, or get suggestions for creating one if not found."""
    return notion_find_or_create_database(database_name, unified_token=token)


@mcp_notion.tool()
def create_database(
    parent_id: str,
    title: str,
    properties: dict | None = None,
    token: str = None,
) -> dict:
    """
    Create a new Notion database under any page (top-level, child page, or a page inside a database).

    - If `properties` is provided, it is passed directly as the Notion database schema.
      Use this to define custom columns (selects with options, dates, numbers, etc.)
      matching the topic (e.g. sports + needed energy).
    - If `properties` is omitted, a minimal schema with only a `Name` title property
      is created. No default Status/Priority/Due Date fields are added.
    """
    return notion_create_database(
        parent_id=parent_id,
        title=title,
        unified_token=token,
        properties=properties,
    )


@mcp_notion.tool()
def create_parent_page(
    title: str, parent_page_id: str = None, content: str = "", token: str = None
) -> dict:
    """Create a new parent page. If parent_page_id is provided, creates as child page."""
    return notion_create_parent_page(
        title, parent_page_id, content, unified_token=token
    )


@mcp_notion.tool()
def list_parent_pages(token: str = None) -> dict:
    """List top-level parent pages that can contain databases (not database rows)."""
    return notion_list_parent_pages(unified_token=token)


@mcp_notion.tool()
def list_all_database_parents(token: str = None) -> dict:
    """List all pages that can serve as database parents, including nested pages inside databases."""
    return {"pages": notion_list_all_database_parents(unified_token=token)}


@mcp_notion.tool()
def list_child_pages(page_id: str, token: str = None) -> dict:
    """List child pages and databases within a parent page."""
    return notion_list_child_pages(page_id, unified_token=token)


# ----------------------------
# Trello tools (Task Manager)
# ----------------------------


@mcp_trello.tool()
def task_list_boards(token: str = None) -> list[dict]:
    """List all Trello boards for the current user."""
    return trello_list_boards(unified_token=token)


@mcp_trello.tool()
def task_list_members(board_id: str, token: str = None) -> list[dict]:
    """List all members for a given Trello board."""
    return trello_list_members(board_id=board_id, unified_token=token)


@mcp_trello.tool()
def task_list_lists(board_id: str, token: str = None) -> list[dict]:
    """List all lists for a given Trello board."""
    return trello_list_lists(board_id=board_id, unified_token=token)


@mcp_trello.tool()
def task_list_cards(
    list_id: str | None = None,
    board_id: str | None = None,
    token: str = None,
) -> list[dict]:
    """List cards either by list or by board (provide one of list_id or board_id)."""
    return trello_list_cards(unified_token=token, list_id=list_id, board_id=board_id)


@mcp_trello.tool()
def task_create(
    name: str,
    list_id: str | None = None,
    board_name: str | None = None,
    list_name: str | None = None,
    desc: str | None = None,
    description: str | None = None,
    due: str | None = None,
    member_ids: list[str] | None = None,
    label_ids: list[str] | None = None,
    token: str = None,
) -> dict:
    """
    Create a Trello task (card). Use either:
    - list_id (direct list), or
    - board_name + list_name (resolve board and list by name first).
    """
    final_desc = description if description is not None else desc
    if list_id:
        return trello_create_card(
            list_id=list_id,
            name=name,
            desc=final_desc,
            due=due,
            member_ids=member_ids,
            label_ids=label_ids,
            unified_token=token,
        )
    if board_name and list_name:
        return trello_create_card_by_names(
            board_name=board_name,
            list_name=list_name,
            name=name,
            desc=final_desc,
            due=due,
            member_ids=member_ids,
            label_ids=label_ids,
            unified_token=token,
        )
    return {
        "status": "error",
        "message": "Provide list_id, or both board_name and list_name",
    }


@mcp_trello.tool()
def task_update(
    card_id: str,
    name: str | None = None,
    desc: str | None = None,
    description: str | None = None,
    due: str | None = None,
    closed: bool | None = None,
    list_id: str | None = None,
    token: str = None,
) -> dict:
    """Update fields of a task (card) or move it between lists by providing list_id."""
    # Support both 'desc' and 'description' parameters (description takes precedence)
    final_desc = description if description is not None else desc
    return trello_update_card(
        card_id=card_id,
        name=name,
        desc=final_desc,
        due=due,
        closed=closed,
        list_id=list_id,
        unified_token=token,
    )


@mcp_trello.tool()
def task_move(card_id: str, list_id: str, token: str = None) -> dict:
    """Move a task (card) to another list."""
    return trello_move_card(card_id=card_id, list_id=list_id, unified_token=token)


@mcp_trello.tool()
def task_delete(card_id: str, token: str = None) -> dict:
    """Delete (close) a task (card)."""
    return trello_delete_card(card_id=card_id, unified_token=token)


@mcp_trello.tool()
def task_search(
    query: str, board_id: str | None = None, token: str = None, limit: int = 50
) -> dict:
    """Search Trello tasks (cards). Optionally restrict to a board."""
    return trello_search(
        query=query, board_id=board_id, unified_token=token, limit=limit
    )


@mcp_trello.tool()
def task_list_create(
    name: str,
    board_id: str | None = None,
    board_name: str | None = None,
    pos: str | None = None,
    token: str = None,
) -> dict:
    """Create a Trello list. Pass board_id or board_name to identify the board."""
    if board_id:
        return trello_create_list(
            board_id=board_id, name=name, pos=pos, unified_token=token
        )
    if board_name:
        board = trello_find_board_by_name(board_name, unified_token=token)
        if not board:
            return {"status": "error", "message": f"Board not found: {board_name}"}
        return trello_create_list(
            board_id=board.get("idboard"),
            name=name,
            pos=pos,
            unified_token=token,
        )
    return {"status": "error", "message": "Provide board_id or board_name"}


@mcp_trello.tool()
def task_find_board(board_name: str, token: str = None) -> dict:
    """Find a board by name (exact/starts/contains)."""
    board = trello_find_board_by_name(board_name, unified_token=token)
    return board or {}


@mcp_trello.tool()
def task_find_list(
    list_name: str,
    board_id: str | None = None,
    board_name: str | None = None,
    token: str = None,
) -> dict:
    """Find a list by name within a board (provide board_id or board_name)."""
    bid = board_id
    if board_name and not bid:
        board = trello_find_board_by_name(board_name, unified_token=token)
        if not board:
            return {}
        bid = board.get("idboard")
    if not bid:
        return {"status": "error", "message": "Provide board_id or board_name"}
    lst = trello_find_list_by_name(bid, list_name, unified_token=token)
    return lst or {}


@mcp_trello.tool()
def task_board_label_create(
    name: str | None = None,
    color: str | None = None,
    board_id: str | None = None,
    board_name: str | None = None,
    token: str = None,
) -> dict:
    """
    Create a label on a board. Pass board_id or board_name.
    `name` is the new label name (optional); `color` is a Trello color or None.
    """
    if board_id:
        return trello_create_board_label(
            board_id=board_id, name=name, color=color, unified_token=token
        )
    if board_name:
        board = trello_find_board_by_name(board_name, unified_token=token)
        if not board:
            return {"status": "error", "message": f"Board not found: {board_name}"}
        return trello_create_board_label(
            board_id=board.get("idboard"),
            name=name,
            color=color,
            unified_token=token,
        )
    return {"status": "error", "message": "Provide board_id or board_name"}


@mcp_trello.tool()
def task_board_label_update(
    label_id: str, name: str | None = None, color: str | None = None, token: str = None
) -> dict:
    """Update a board label's name and/or color."""
    return trello_update_label(
        label_id=label_id, name=name, color=color, unified_token=token
    )


@mcp_trello.tool()
def task_get(card_id: str, token: str = None) -> dict:
    """Get a Trello task (card) by ID."""
    return trello_get_card(card_id=card_id, unified_token=token)


@mcp_trello.tool()
def task_comment_add(card_id: str, text: str, token: str = None) -> dict:
    """Add a comment to a card."""
    return trello_add_comment(card_id=card_id, text=text, unified_token=token)


@mcp_trello.tool()
def task_comment_list(card_id: str, token: str = None) -> list:
    """List all comments (actions of type 'commentCard') on a Trello card."""
    return trello_list_card_comments(card_id=card_id, unified_token=token)


@mcp_trello.tool()
def task_comment_update(
    card_id: str, action_id: str, text: str, token: str = None
) -> dict:
    """Update an existing comment on a card (provide the action_id of the comment)."""
    return trello_update_comment(
        card_id=card_id, action_id=action_id, text=text, unified_token=token
    )


@mcp_trello.tool()
def task_comment_delete(card_id: str, action_id: str, token: str = None) -> dict:
    """Delete a comment from a card (provide the action_id of the comment)."""
    return trello_delete_comment(
        card_id=card_id, action_id=action_id, unified_token=token
    )


@mcp_trello.tool()
def task_members_add(
    card_id: str, member_ids: list[str], token: str = None
) -> list[dict]:
    """Add one or more members to a card."""
    return trello_add_members(
        card_id=card_id, member_ids=member_ids, unified_token=token
    )


@mcp_trello.tool()
def task_member_remove(card_id: str, member_id: str, token: str = None) -> dict:
    """Remove a member from a card."""
    return trello_remove_member(
        card_id=card_id, member_id=member_id, unified_token=token
    )


@mcp_trello.tool()
def task_label_add(card_id: str, label_id: str, token: str = None) -> dict:
    """Add an existing label to a card."""
    return trello_add_label(card_id=card_id, label_id=label_id, unified_token=token)


@mcp_trello.tool()
def task_label_remove(card_id: str, label_id: str, token: str = None) -> dict:
    """Remove a label from a card."""
    return trello_remove_label(card_id=card_id, label_id=label_id, unified_token=token)


@mcp_trello.tool()
def task_list_board_labels(board_id: str, token: str = None) -> list[dict]:
    """List labels available on a board."""
    return trello_list_board_labels(board_id=board_id, unified_token=token)


@mcp_trello.tool()
def task_checklist_create(card_id: str, name: str, token: str = None) -> dict:
    """Create a checklist on a card."""
    return trello_create_checklist(card_id=card_id, name=name, unified_token=token)


@mcp_trello.tool()
def task_checklists(card_id: str, token: str = None) -> list[dict]:
    """List all checklists on a card."""
    return trello_list_checklists(card_id=card_id, unified_token=token)


@mcp_trello.tool()
def task_checkitem_add(
    checklist_id: str,
    name: str,
    pos: str | None = None,
    checked: bool | None = None,
    token: str = None,
) -> dict:
    """Add a check item to a checklist."""
    return trello_add_checkitem(
        checklist_id=checklist_id,
        name=name,
        pos=pos,
        checked=checked,
        unified_token=token,
    )


@mcp_trello.tool()
def task_checkitem_update(
    card_id: str,
    checkitem_id: str,
    name: str | None = None,
    state: str | None = None,
    pos: str | None = None,
    token: str = None,
) -> dict:
    """Update a check item on a card (state: complete|incomplete)."""
    return trello_update_checkitem(
        card_id=card_id,
        checkitem_id=checkitem_id,
        name=name,
        state=state,
        pos=pos,
        unified_token=token,
    )


@mcp_trello.tool()
def task_checkitem_delete(
    checklist_id: str, checkitem_id: str, token: str = None
) -> dict:
    """Delete a check item from a checklist."""
    return trello_delete_checkitem(
        checklist_id=checklist_id, checkitem_id=checkitem_id, unified_token=token
    )


@mcp_trello.tool()
def task_attachment_add_url(
    card_id: str, url: str, name: str | None = None, token: str = None
) -> dict:
    """Attach a URL to a card."""
    return trello_add_attachment_url(
        card_id=card_id, url=url, name=name, unified_token=token
    )


@mcp_trello.tool()
def task_set_custom_field(
    card_id: str, custom_field_id: str, value: dict, token: str = None
) -> dict:
    """Set a custom field on a card. Provide a value object per Trello's API (e.g., {"text": "value"})."""
    return trello_set_custom_field(
        card_id=card_id,
        custom_field_id=custom_field_id,
        value=value,
        unified_token=token,
    )


def parse_message_body(message: Dict[str, Any]) -> str:
    """
    Parse the body of a Gmail message.

    Args:
        message: The Gmail message object

    Returns:
        The extracted message body text
    """

    # Helper function to find text/plain parts
    def get_text_part(parts):
        text = ""
        for part in parts:
            if part["mimeType"] == "text/plain":
                if "data" in part["body"]:
                    text += base64.urlsafe_b64decode(part["body"]["data"]).decode()
            elif "parts" in part:
                text += get_text_part(part["parts"])
        return text

    # Check if the message is multipart
    if "parts" in message["payload"]:
        return get_text_part(message["payload"]["parts"])
    else:
        # Handle single part messages
        if "data" in message["payload"]["body"]:
            data = message["payload"]["body"]["data"]
            return base64.urlsafe_b64decode(data).decode()
        return ""


###########################***********************GMAIL TOOLS
# Helper functions
def format_message(message):
    """Format a Gmail message for display."""
    headers = get_headers_dict(message)
    body = parse_message_body(message)

    # Extract relevant headers
    from_header = headers.get("From", "Unknown")
    to_header = headers.get("To", "Unknown")
    subject = headers.get("Subject", "No Subject")
    date = headers.get("Date", "Unknown Date")

    return f"""
From: {from_header}
To: {to_header}
Subject: {subject}
Date: {date}

{body}
"""


def extract_email_body(message) -> str:
    """Extract plain text body from Gmail message payload"""
    payload = message.get("payload", {})
    parts = payload.get("parts", [])

    def get_text_from_parts(parts_list):
        for part in parts_list:
            if part.get("mimeType") == "text/plain":
                return base64.urlsafe_b64decode(part["body"]["data"]).decode(
                    "utf-8", errors="ignore"
                )
            elif "parts" in part:
                # Recursively check nested parts
                result = get_text_from_parts(part["parts"])
                if result:
                    return result
        return ""

    # Check if the message is single-part
    if payload.get("mimeType") == "text/plain" and "data" in payload.get("body", {}):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode(
            "utf-8", errors="ignore"
        )

    # Otherwise, traverse the parts
    return get_text_from_parts(parts)


def validate_date_format(date_str):
    """
    Validate that a date string is in the format YYYY/MM/DD.

    Args:
        date_str: The date string to validate

    Returns:
        bool: True if valid, False otherwise
    """
    if not date_str:
        return True

    # Check format with regex
    if not re.match(r"^\d{4}/\d{2}/\d{2}$", date_str):
        return False

    # Validate the date is a real date
    try:
        datetime.strptime(date_str, "%Y/%m/%d")
        return True
    except ValueError:
        return False


# # Resources
# @mcp_gmail.resource("gmail://messages/{message_id}")
# def get_email_message(message_id: str) -> str:
#     """
#     Get the content of an email message by its ID.

#     Args:
#         message_id: The Gmail message ID

#     Returns:
#         The formatted email content
#     """
#     service_gmail=get_gmail_service()
#     message = get_message(service_gmail, message_id, user_id=settings.user_id)
#     formatted_message = format_message(message)
#     return {
#         "message_id": message_id,
#         "email": formatted_message
#     }


# @mcp_gmail.resource("gmail://threads/{thread_id}")
# def get_email_thread(thread_id: str,token: str) -> str:
#     """
#     Get all messages in an email thread by thread ID.

#     Args:
#         thread_id: The Gmail thread ID

#     Returns:
#         The formatted thread content with all messages
#     """
#     service_gmail=get_gmail_service(token)
#     thread = get_thread(service_gmail, thread_id, user_id=settings.user_id)
#     messages = thread.get("messages", [])

#      # Assume format_message returns a dict now
#     formatted_messages = [format_message(msg) for msg in messages]

#     return {
#         "thread_id": thread_id,
#         "messages": formatted_messages
#     }


# Tools
@mcp_gmail.tool()
def draft_email(
    to: str,
    subject: str,
    body: Optional[str] = None,
    body_text: Optional[str] = None,
    body_html: Optional[str] = None,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
    mode: str = "create",
    draft_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    token: str = None,
) -> str:
    """
    Compose a new email draft. Supports both plain text and HTML formats.

    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body content (legacy parameter, used if body_text not provided)
        body_text: Plain text email body (optional, falls back to body if not provided)
        body_html: HTML email body (optional)
        cc: Carbon copy recipients (optional)
        bcc: Blind carbon copy recipients (optional)
        thread_id: Gmail thread ID for reply drafts (optional)

    Returns:
        Structured JSON with the created draft information
    """
    service_gmail = get_gmail_service(token)
    sender = (
        service_gmail.users()
        .getProfile(userId=settings.user_id)
        .execute()
        .get("emailAddress")
    )
    
    # Support legacy 'body' parameter for backward compatibility
    text_content = body_text or body or ""
    
    if mode == "edit" and draft_id:
        # Update existing draft instead of creating a new one
        if body_html:
            message = create_multipart_message(
                sender, to, subject, text_content, body_html, cc, bcc
            )
        else:
            message = create_message(sender, to, subject, text_content, cc, bcc)

        draft_body = {"id": draft_id, "message": message}
        draft = (
            service_gmail.users()
            .drafts()
            .update(userId=settings.user_id, id=draft_id, body=draft_body)
            .execute()
        )
    else:
        # Default behaviour: create a new draft
        draft = create_draft(
            service_gmail,
            sender=sender,
            to=to,
            subject=subject,
            body_text=text_content,
            body_html=body_html,
            user_id=settings.user_id,
            cc=cc,
            bcc=bcc,
            thread_id=thread_id,
        )

    draft_id = draft.get("id")
    resolved_thread_id = (
        thread_id
        or ((draft.get("message") or {}).get("threadId") if isinstance(draft, dict) else None)
    )
    body_preview = text_content[:EMAIL_PREVIEW_LENGTH] + (
        "..." if len(text_content) > EMAIL_PREVIEW_LENGTH else ""
    )

    # Return structured format matching system prompt expectations
    return {
        "success": True,
        "type": "email_draft",
        "data": {
            "emails": [
                {
                    "id": draft_id,
                    "threadId": resolved_thread_id,
                    "from": sender,
                    "to": to,
                    "subject": subject,
                    "cc": cc or "",
                    "bcc": bcc or "",
                    "body_preview": body_preview,
                }
            ]
        },
        "message": f"📧 Email draft created successfully.\n\n**To:** {to}\n**Subject:** {subject}\n**Preview:** {body_preview}",
        "ui_hint": ["open_emails_panel"],
    }


@mcp_gmail.tool()
def list_email_drafts(
    max_results: int = 10,
    query: str | None = None,
    from_email: str | None = None,
    to_email: str | None = None,
    subject: str | None = None,
    has_attachment: bool = False,
    is_unread: bool = False,
    start_date: str | None = None,  # YYYY-MM-DD
    end_date: str | None = None,    # YYYY-MM-DD
    gmail_query: str | None = None,
    token: str | None = None,
) -> dict:
    """
    List Gmail drafts directly from Gmail (not Mongo). Use this when the user
    wants to review or choose an existing draft to edit or send.
    """
    service_gmail = get_gmail_service(token)

    # Build Gmail search query (draft-aware)
    query_parts: list[str] = ["in:drafts"]
    if query:
        query_parts.append(query)
    if from_email:
        query_parts.append(f"from:{from_email}")
    if to_email:
        query_parts.append(f"to:{to_email}")
    if subject:
        query_parts.append(f"subject:{subject}")
    if start_date:
        query_parts.append(f"after:{start_date.replace('-', '/')}")
    if end_date:
        query_parts.append(f"before:{end_date.replace('-', '/')}")
    if has_attachment:
        query_parts.append("has:attachment")
    if is_unread:
        query_parts.append("is:unread")
    if gmail_query:
        query_parts.append(gmail_query)
    final_q = " ".join([p for p in query_parts if p]).strip()

    # 1) Get message IDs that match draft query
    matched_message_ids = set()
    page_token = None
    while len(matched_message_ids) < max_results:
        remaining = max_results - len(matched_message_ids)
        response = (
            service_gmail.users()
            .messages()
            .list(
                userId=settings.user_id,
                q=final_q,
                maxResults=min(500, max(remaining, 50)),
                pageToken=page_token,
            )
            .execute()
        )
        for m in response.get("messages", []) or []:
            mid = m.get("id")
            if mid:
                matched_message_ids.add(mid)
                if len(matched_message_ids) >= max_results:
                    break
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    # 2) Resolve draft IDs by scanning drafts and matching draft.message.id
    draft_refs = []
    draft_page_token = None
    max_scan = max(max_results * 12, 120)
    scanned = 0
    while scanned < max_scan:
        resp = (
            service_gmail.users()
            .drafts()
            .list(
                userId=settings.user_id,
                maxResults=min(200, max_scan - scanned),
                pageToken=draft_page_token,
            )
            .execute()
        )
        batch = resp.get("drafts", []) or []
        draft_refs.extend(batch)
        scanned += len(batch)
        draft_page_token = resp.get("nextPageToken")
        if not draft_page_token or not batch:
            break

    formatted = []
    for ref in draft_refs:
        if len(formatted) >= max_results:
            break
        draft_id = ref.get("id")
        if not draft_id:
            continue

        draft = get_draft(
            service_gmail, draft_id=draft_id, user_id=settings.user_id, format="full"
        )
        message = draft.get("message", {}) or {}
        message_id = message.get("id")
        if message_id not in matched_message_ids:
            continue

        headers = message.get("payload", {}).get("headers", []) or []
        header_map = {
            (h.get("name") or ""): (h.get("value") or "")
            for h in headers
            if isinstance(h, dict)
        }
        subj = header_map.get("Subject") or header_map.get("subject") or ""
        to = header_map.get("To") or header_map.get("to") or ""
        from_ = header_map.get("From") or header_map.get("from") or ""

        date_str = ""
        internal_date_raw = message.get("internalDate")
        try:
            if internal_date_raw is not None:
                ts_ms = int(internal_date_raw)
                date_str = datetime.fromtimestamp(ts_ms / 1000).isoformat()
        except Exception:
            date_str = ""

        snippet = message.get("snippet") or ""
        body_preview = snippet[:EMAIL_PREVIEW_LENGTH] + (
            "..." if len(snippet) > EMAIL_PREVIEW_LENGTH else ""
        )

        formatted.append(
            {
                "id": draft_id,
                "message_id": message_id,
                "from": from_,
                "to": to,
                "subject": subj,
                "date": date_str,
                "body_preview": body_preview,
            }
        )

    return {
        "success": True,
        "type": "email_draft",
        "data": {"emails": formatted},
        "message": f"📧 Found {len(formatted)} Gmail drafts.",
        "gmail_query_used": final_q,
        "ui_hint": ["open_emails_panel"],
    }


@mcp_gmail.tool()
def get_email_draft(
    draft_id: str,
    token: str | None = None,
) -> dict:
    """
    Get full details of a single Gmail draft directly from Gmail (not Mongo).
    Use this when the user wants to inspect or edit a specific draft by ID.
    If Gmail returns an error for this draft (e.g. 404 or permission issue),
    return a structured error instead of raising so the caller sees the cause.
    """
    service_gmail = get_gmail_service(token)
    try:
        # For drafts, request format="raw" so we can parse the MIME body reliably
        draft = get_draft(
            service_gmail, draft_id=draft_id, user_id=settings.user_id, format="raw"
        )
    except Exception as e:
        error_msg = str(e)
        print(f"[DEBUG] get_email_draft failed for {draft_id}: {error_msg}")
        return {
            "success": False,
            "type": "error",
            "data": {},
            "message": f"Failed to load Gmail draft {draft_id}: {error_msg}",
            "ui_hint": [],
        }

    message = draft.get("message", {}) or {}
    headers = message.get("payload", {}).get("headers", [])
    header_map = {h.get("name"): h.get("value") for h in headers if isinstance(h, dict)}

    subject = header_map.get("Subject", "")
    to = header_map.get("To", "")
    from_ = header_map.get("From", "")

    # Use raw parser first (recommended for drafts); fall back to structured parser
    body_text = ""
    try:
        raw = message.get("raw")
        if raw:
            body_text = parse_raw_message_body(raw) or ""
        if not body_text:
            body_text = parse_message_body(message) or ""
    except Exception:
        body_text = ""

    # Fallback: if draft's embedded message has no body, try fetching
    # the underlying Gmail message directly by its message ID.
    if not body_text:
        try:
            msg_id = message.get("id")
            if msg_id:
                full_msg = get_message(
                    service_gmail,
                    message_id=msg_id,
                    user_id=settings.user_id,
                    format="full",
                )
                body_text = parse_message_body(full_msg) or ""
        except Exception as e:
            print(f"[DEBUG] get_email_draft fallback get_message failed for {draft_id}: {e}")

    body_preview = body_text[:EMAIL_PREVIEW_LENGTH] + (
        "..." if len(body_text) > EMAIL_PREVIEW_LENGTH else ""
    )

    email_obj = {
        "id": draft_id,
        "from": from_,
        "to": to,
        "subject": subject or "",
        "body": body_text,
        "body_preview": body_preview,
    }

    return {
        "success": True,
        "type": "email_draft",
        "data": {"emails": [email_obj]},
        "message": f"📧 Loaded draft “{subject or ''}”.",
        "ui_hint": ["open_emails_panel"],
    }

@mcp_gmail.tool()
def send_email(
    to: Optional[str] = None,
    subject: Optional[str] = None,
    body: Optional[str] = None,
    body_text: Optional[str] = None,
    body_html: Optional[str] = None,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
    draft_id: Optional[str] = None,
    token: str = None,
) -> str:
    """
    Compose and send an email. Supports both plain text and HTML formats.

    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body content (legacy parameter, used if body_text not provided)
        body_text: Plain text email body (optional, falls back to body if not provided)
        body_html: HTML email body (optional)
        cc: Carbon copy recipients (optional)
        bcc: Blind carbon copy recipients (optional)

    Returns:
        Structured JSON with the sent email information
    """
    service_gmail = get_gmail_service(token)
    sender = (
        service_gmail.users()
        .getProfile(userId=settings.user_id)
        .execute()
        .get("emailAddress")
    )

    # Mode 1: send an existing draft by draft_id
    if draft_id:
        draft = get_draft(
            service_gmail,
            draft_id=draft_id,
            user_id=settings.user_id,
            format="full",
        )
        draft_msg = draft.get("message", {}) if isinstance(draft, dict) else {}
        headers = get_headers_dict(draft_msg) if draft_msg.get("payload") else {}
        resolved_to = headers.get("To", "")
        resolved_subject = headers.get("Subject", "")
        resolved_cc = headers.get("Cc", "")
        resolved_bcc = headers.get("Bcc", "")
        draft_body = parse_message_body(draft_msg) if draft_msg else ""

        message = send_draft(service_gmail, draft_id=draft_id, user_id=settings.user_id)
        message_id = message.get("id")
        body_preview = draft_body[:EMAIL_PREVIEW_LENGTH] + (
            "..." if len(draft_body) > EMAIL_PREVIEW_LENGTH else ""
        )
        return {
            "success": True,
            "type": "email_sent",
            "data": {
                "emails": [
                    {
                        "id": message_id,
                        "draft_id": draft_id,
                        "from": sender,
                        "to": resolved_to,
                        "subject": resolved_subject,
                        "cc": resolved_cc,
                        "bcc": resolved_bcc,
                        "body_preview": body_preview,
                    }
                ]
            },
            "message": f"✅ Draft {draft_id} sent successfully to {resolved_to or 'recipient'}.\n\n**Subject:** {resolved_subject or ''}\n**Preview:** {body_preview}",
            "ui_hint": ["open_emails_panel"],
        }

    # Mode 2: compose and send a new email
    if not to or not subject:
        raise ValueError("Either provide draft_id, or provide both to and subject.")

    # Support legacy 'body' parameter for backward compatibility
    text_content = body_text or body or ""

    message = gmail_send_email(
        service_gmail,
        sender=sender,
        to=to,
        subject=subject,
        body_text=text_content,
        body_html=body_html,
        user_id=settings.user_id,
        cc=cc,
        bcc=bcc,
    )

    message_id = message.get("id")
    body_preview = text_content[:EMAIL_PREVIEW_LENGTH] + (
        "..." if len(text_content) > EMAIL_PREVIEW_LENGTH else ""
    )

    # Return structured format matching system prompt expectations
    return {
        "success": True,
        "type": "email_sent",
        "data": {
            "emails": [
                {
                    "id": message_id,
                    "from": sender,
                    "to": to,
                    "subject": subject,
                    "cc": cc or "",
                    "bcc": bcc or "",
                    "body_preview": body_preview,
                }
            ]
        },
        "message": f"✅ Email sent successfully to {to}.\n\n**Subject:** {subject}\n**Preview:** {body_preview}",
        "ui_hint": ["open_emails_panel"],
    }


@mcp_gmail.tool()
def search_emails(
    from_email: Optional[str] = None,
    to_email: Optional[str] = None,
    subject: Optional[str] = None,
    has_attachment: bool = False,
    is_unread: bool = False,
    after_date: Optional[str] = None,
    before_date: Optional[str] = None,
    label: Optional[str] = None,
    max_results: int = 10,
    token: str = None,
    get_thread: bool | None = None,
) -> str:
    return mongo_search_emails(
        from_email=from_email,
        to_email=to_email,
        subject=subject,
        has_attachment=has_attachment,
        is_unread=is_unread,
        after_date=after_date,
        before_date=before_date,
        label=label,
        max_results=max_results,
        token=token,
        get_thread=get_thread,
    )


@mcp_gmail.tool()
def search_sent_emails(
    message_ids: Optional[List[str]] = None,
    gmail_query: Optional[str] = None,
    max_results: int = 10,
    scope: str = "sent",
    token: str = None,
) -> dict:
    """
    Search Gmail directly (not Mongo)—optimized for sent mail, which is often not synced.
    Returns full decoded bodies for the model.

    - Pass ``message_ids`` to load specific messages by Gmail id (ignores search).
    - Otherwise searches with Gmail's ``q`` syntax: ``scope`` ``sent`` prepends ``in:sent``;
      ``scope`` ``all`` uses ``gmail_query`` only, defaulting to ``in:inbox`` if empty.
    """
    service_gmail = get_gmail_service(token)
    payload = search_or_fetch_gmail_messages(
        service_gmail,
        user_id=settings.user_id,
        message_ids=message_ids,
        gmail_query=gmail_query,
        max_results=max_results,
        scope=scope,
    )
    emails = payload.get("emails") or []
    q_used = payload.get("gmail_query_used")
    mode = payload.get("mode", "search")

    hint = (
        f"Loaded {len(emails)} message(s) by id."
        if mode == "by_id"
        else (
            f"Found {len(emails)} message(s) for query: {q_used!r}."
            if q_used is not None
            else f"Found {len(emails)} message(s)."
        )
    )

    return {
        "success": True,
        "type": "gmail_sent_search",
        "data": {"emails": emails},
        "gmail_query_used": q_used,
        "mode": mode,
        "message": hint,
        "ui_hint": ["open_emails_panel"],
    }


@mcp_gmail.tool()
def query_emails(
    query: str,
    max_results: int = 10,
    token: str = None,
    limit: int | None = None,
    get_thread: bool | None = None,
) -> str:
    return mongo_query_emails(
        query=query,
        max_results=max_results,
        token=token,
        limit=limit,
        get_thread=get_thread,
    )


@mcp_gmail.tool()
def query_docs(
    query: str | None = None,
    max_results: int = 10,
    token: str | None = None,
    owner: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = None,
) -> dict:
    """Unified query for Google Docs stored in MongoDB."""
    return mongo_query_docs(
        query=query,
        max_results=max_results,
        token=token,
        owner=owner,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )


@mcp_gmail.tool()
def query_events(
    query: str | None = None,
    max_results: int = 10,
    token: str | None = None,
    start: str | None = None,
    end: str | None = None,
    email: str | None = None,
    limit: int | None = None,
) -> dict:
    """Unified query for Calendar events stored in MongoDB."""
    return mongo_query_events(
        query=query,
        max_results=max_results,
        token=token,
        start=start,
        end=end,
        email=email,
        limit=limit,
    )


# @mcp_gmail.tool()
# def search_emails_by_date_tool(
#     after_date: str | None = None,
#     before_date: str | None = None,
#     on_date: str | None = None,
#     max_results: int = 50,
#     token: str | None = None,
# ) -> dict:
#     """
#     Strict Mongo date search for emails, sorted by newest first. Use either on_date (YYYY-MM-DD)
#     or a combination of after_date/before_date (YYYY-MM-DD).
#     """
#     return search_emails_by_date(
#         after_date=after_date,
#         before_date=before_date,
#         on_date=on_date,
#         max_results=max_results,
#         token=token,
#     )


@mcp_gmail.tool()
def list_available_labels(token: str = None) -> str:
    """
    Get all available Gmail labels for the user.

    Returns:
        Formatted list of labels with their IDs
    """
    service_gmail = get_gmail_service(token)
    labels = get_labels(service_gmail, user_id=settings.user_id)

    result = {"total_labels": len(labels), "labels": []}

    for label in labels:
        result["labels"].append(
            {
                "label_id": label.get("id", "Unknown"),
                "name": label.get("name", "Unknown"),
                "type": label.get("type", "user"),
            }
        )

    return result


@mcp_gmail.tool()
def mark_message_read(message_id: str, token: str = None) -> str:
    """
    Mark a message as read by removing the UNREAD label.

    Args:
        message_id: The Gmail message ID to mark as read

    Returns:
        Confirmation message
    """
    service_gmail = get_gmail_service(token)
    # Remove the UNREAD label
    result = modify_message_labels(
        service_gmail,
        user_id=settings.user_id,
        message_id=message_id,
        remove_labels=["UNREAD"],
        add_labels=[],
    )

    # Get message details to show what was modified
    headers = get_headers_dict(result)
    subject = headers.get("Subject", "No Subject")

    return {
        "status": "success",
        "message": "Message marked as read",
        "data": {"id": message_id, "subject": subject},
    }


# @mcp_gmail.tool()  # DEPRECATED: Merged into update_email
# def add_label_to_message(message_id: str, label_id: str, token: str = None) -> str:
#     """
#     Add a label to a message.
#     DEPRECATED: Use update_email(message_id, action="add_label", label_id=label_id) instead
#     """
#     service_gmail = get_gmail_service(token)
#     result = modify_message_labels(
#         service_gmail,
#         user_id=settings.user_id,
#         message_id=message_id,
#         remove_labels=[],
#         add_labels=[label_id],
#     )
#     headers = get_headers_dict(result)
#     subject = headers.get("Subject", "No Subject")
#     label_name = label_id
#     labels = get_labels(service_gmail, user_id=settings.user_id)
#     for label in labels:
#         if label.get("id") == label_id:
#             label_name = label.get("name", label_id)
#             break
#     return {
#         "status": "success",
#         "message": "Label added to message",
#         "data": {
#             "message_id": message_id,
#             "subject": subject,
#             "label_id": label_id,
#             "label_name": label_name,
#         },
#     }


# @mcp_gmail.tool()  # DEPRECATED: Merged into update_email
# def remove_label_from_message(message_id: str, label_id: str, token: str = None) -> str:
#     """
#     Remove a label from a message.
#     DEPRECATED: Use update_email(message_id, action="remove_label", label_id=label_id) instead
#     """
#     service_gmail = get_gmail_service(token)
#     label_name = label_id
#     labels = get_labels(service_gmail, user_id=settings.user_id)
#     for label in labels:
#         if label.get("id") == label_id:
#             label_name = label.get("name", label_id)
#             break
#     result = modify_message_labels(
#         service_gmail,
#         user_id=settings.user_id,
#         message_id=message_id,
#         remove_labels=[label_id],
#         add_labels=[],
#     )
#     headers = get_headers_dict(result)
#     subject = headers.get("Subject", "No Subject")
#     return {
#         "status": "success",
#         "message": "Label removed from message",
#         "data": {
#             "message_id": message_id,
#             "subject": subject,
#             "label_id": label_id,
#             "label_name": label_name,
#         },
#     }


@mcp_gmail.tool()
def get_emails(message_ids: list[str], token: str = None) -> str:
    """
    Get the content of multiple email messages by their IDs.

    Args:
        message_ids: A list of Gmail message IDs

    Returns:
        The formatted content of all requested emails
    """
    # Use MongoDB instead of Gmail API
    return mongo_get_emails(message_ids=message_ids, token=token)


# @mcp_gmail.tool()  # DEPRECATED: Merged into update_email
# def star_email(message_id: str, token: str = None) -> dict:
#     """
#     Star an email.
#     DEPRECATED: Use update_email(message_id, action="star") instead
#     """
#     service_gmail = get_gmail_service(token)
#     result = modify_message_labels(
#         service_gmail,
#         user_id=settings.user_id,
#         message_id=message_id,
#         add_labels=["STARRED"],
#         remove_labels=[],
#     )
#     return {"status": "success", "message": "Email starred", "message_id": message_id}


# @mcp_gmail.tool()  # DEPRECATED: Merged into update_email
# def unstar_email(message_id: str, token: str = None) -> dict:
#     """
#     Unstar an email.
#     DEPRECATED: Use update_email(message_id, action="unstar") instead
#     """
#     service_gmail = get_gmail_service(token)
#     result = modify_message_labels(
#         service_gmail,
#         user_id=settings.user_id,
#         message_id=message_id,
#         add_labels=[],
#         remove_labels=["STARRED"],
#     )
#     return {"status": "success", "message": "Email unstarred", "message_id": message_id}


# @mcp_gmail.tool()  # DEPRECATED: Merged into update_email
# def delete_email(message_id: str, token: str) -> dict:
#     """
#     Move email to trash.
#     DEPRECATED: Use update_email(message_id, action="trash") instead
#     """
#     service = get_gmail_service(token)
#     email_id = message_id
#     action = "trash"
#     label_actions = {
#         "read": {"add": [], "remove": ["UNREAD"]},
#         "unread": {"add": ["UNREAD"], "remove": []},
#         "star": {"add": ["STARRED"], "remove": []},
#         "unstar": {"add": [], "remove": ["STARRED"]},
#         "important": {"add": ["IMPORTANT"], "remove": []},
#         "unimportant": {"add": [], "remove": ["IMPORTANT"]},
#         "archive": {"add": [], "remove": ["INBOX"]},
#         "unarchive": {"add": ["INBOX"], "remove": []},
#         "spam": {"move": "spam"},
#         "not_spam": {"move": "unspam"},
#         "trash": {"move": "trash"},
#         "restore": {"move": "restore"},
#     }
#     if action not in label_actions:
#         raise ValueError(f"Unsupported action: {action}")
#     config = label_actions[action]
#     if config.get("move") == "trash":
#         service.users().messages().trash(userId="me", id=email_id).execute()
#     elif config.get("move") == "restore":
#         service.users().messages().untrash(userId="me", id=email_id).execute()
#     elif config.get("move") == "spam":
#         service.users().messages().modify(
#             userId="me", id=email_id, body={"addLabelIds": ["SPAM"]}
#         ).execute()
#     elif config.get("move") == "unspam":
#         service.users().messages().modify(
#             userId="me", id=email_id, body={"removeLabelIds": ["SPAM"]}
#         ).execute()
#     else:
#         service.users().messages().modify(
#             userId="me",
#             id=email_id,
#             body={
#                 "addLabelIds": config.get("add", []),
#                 "removeLabelIds": config.get("remove", []),
#             },
#         ).execute()
#     return {"status": "success", "email_id": email_id, "action": action}


@mcp_gmail.tool()
def update_email(
    message_id: str, action: str, label_id: Optional[str] = None, token: str = None
) -> dict:
    """
    Universal email update function that handles various email modifications.

    Args:
        message_id: The Gmail message ID
        action: Action to perform - one of:
            - "star": Star the email
            - "unstar": Remove star from email
            - "read": Mark email as read
            - "unread": Mark email as unread
            - "add_label": Add a label (requires label_id)
            - "remove_label": Remove a label (requires label_id)
            - "trash": Move email to trash
            - "untrash": Restore email from trash
            - "archive": Archive email (remove from inbox)
            - "unarchive": Move back to inbox
            - "important": Mark as important
            - "unimportant": Remove important flag
            - "spam": Mark as spam
            - "not_spam": Remove spam label
        label_id: Label ID (required only for add_label/remove_label actions)
        token: User authentication token

    Returns:
        dict with status, message, and message_id
    """
    service = get_gmail_service(token)

    # Define all possible actions and their label modifications
    label_actions = {
        "read": {"add": [], "remove": ["UNREAD"]},
        "unread": {"add": ["UNREAD"], "remove": []},
        "star": {"add": ["STARRED"], "remove": []},
        "unstar": {"add": [], "remove": ["STARRED"]},
        "important": {"add": ["IMPORTANT"], "remove": []},
        "unimportant": {"add": [], "remove": ["IMPORTANT"]},
        "archive": {"add": [], "remove": ["INBOX"]},
        "unarchive": {"add": ["INBOX"], "remove": []},
        "spam": {"move": "spam"},
        "not_spam": {"move": "unspam"},
        "trash": {"move": "trash"},
        "untrash": {"move": "untrash"},
        "add_label": {"custom_add": True},
        "remove_label": {"custom_remove": True},
    }

    if action not in label_actions:
        raise ValueError(
            f"Unsupported action: {action}. Supported actions: {', '.join(label_actions.keys())}"
        )

    config = label_actions[action]

    # Handle custom label operations
    if config.get("custom_add"):
        if not label_id:
            raise ValueError("label_id is required for add_label action")
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"addLabelIds": [label_id]},
        ).execute()
        return {
            "status": "success",
            "message": f"Label {label_id} added to email",
            "message_id": message_id,
            "action": action,
        }

    elif config.get("custom_remove"):
        if not label_id:
            raise ValueError("label_id is required for remove_label action")
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": [label_id]},
        ).execute()
        return {
            "status": "success",
            "message": f"Label {label_id} removed from email",
            "message_id": message_id,
            "action": action,
        }

    # Handle special move operations (trash, untrash, spam)
    elif config.get("move") == "trash":
        service.users().messages().trash(userId="me", id=message_id).execute()
        return {
            "status": "success",
            "message": "Email moved to trash",
            "message_id": message_id,
            "action": action,
        }
    elif config.get("move") == "untrash":
        service.users().messages().untrash(userId="me", id=message_id).execute()
        return {
            "status": "success",
            "message": "Email restored from trash",
            "message_id": message_id,
            "action": action,
        }
    elif config.get("move") == "spam":
        service.users().messages().modify(
            userId="me", id=message_id, body={"addLabelIds": ["SPAM"]}
        ).execute()
        return {
            "status": "success",
            "message": "Email marked as spam",
            "message_id": message_id,
            "action": action,
        }
    elif config.get("move") == "unspam":
        service.users().messages().modify(
            userId="me", id=message_id, body={"removeLabelIds": ["SPAM"]}
        ).execute()
        return {
            "status": "success",
            "message": "Email unmarked as spam",
            "message_id": message_id,
            "action": action,
        }

    # Handle standard label modifications
    else:
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={
                "addLabelIds": config.get("add", []),
                "removeLabelIds": config.get("remove", []),
            },
        ).execute()

        # Generate appropriate success message
        action_messages = {
            "read": "Email marked as read",
            "unread": "Email marked as unread",
            "star": "Email starred",
            "unstar": "Email unstarred",
            "important": "Email marked as important",
            "unimportant": "Email unmarked as important",
            "archive": "Email archived",
            "unarchive": "Email moved to inbox",
        }

        return {
            "status": "success",
            "message": action_messages.get(
                action, f"Email updated with action: {action}"
            ),
            "message_id": message_id,
            "action": action,
        }


@mcp_gmail.tool()
def create_gmail_label(label_name: str, token: str = None) -> dict:
    """Create a new Gmail label."""
    print(f"Creating label: {label_name}")
    service_gmail = get_gmail_service(token)
    result = create_label(
        service=service_gmail, user_id=settings.user_id, name=label_name
    )
    print(f"Result: {result}")
    return result


@mcp_gmail.tool()
def delete_gmail_label(label_id: str, token: str = None) -> dict:
    """
    Tool to delete a Gmail label by ID.

    Args:
        label_id: The ID of the label to delete.

    Returns:
        A dictionary with status and message.
    """
    service_gmail = get_gmail_service(token)
    try:
        delete_label(service=service_gmail, user_id=settings.user_id, label_id=label_id)
        return {
            "status": "success",
            "message": f"Label '{label_id}' deleted successfully",
            "label_id": label_id,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to delete label '{label_id}': {str(e)}",
        }


def _guess_attachment_filename(part: Dict[str, Any]) -> str:
    fn = (part.get("filename") or "").strip()
    if fn:
        return os.path.basename(fn.replace("\\", "/"))
    mt = (part.get("mimeType") or "").lower()
    if "pdf" in mt:
        return "attachment.pdf"
    if "png" in mt:
        return "attachment.png"
    if "gif" in mt:
        return "attachment.gif"
    if "webp" in mt:
        return "attachment.webp"
    if "jpeg" in mt or "jpg" in mt:
        return "attachment.jpg"
    return "attachment.bin"


def _iter_gmail_attachment_parts(payload: Optional[Dict[str, Any]]):
    """Walk nested MIME parts; yield leaves that have a Gmail attachmentId."""
    if not payload:
        return
    children = payload.get("parts") or []
    if children:
        for child in children:
            yield from _iter_gmail_attachment_parts(child)
        return
    body = payload.get("body") or {}
    if body.get("attachmentId"):
        yield payload


def _describe_image_with_vision(
    file_path: str, display_name: str, token: Optional[str]
) -> Optional[str]:
    """
    Run the same vision path as /chat image uploads so the model gets text, not only a disk path.
    """
    try:
        from app.switches import ENABLE_IMAGE_ANALYSIS

        if not ENABLE_IMAGE_ANALYSIS:
            return None
    except Exception:
        return None
    ext = os.path.splitext(display_name.lower())[1]
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"):
        return None
    max_bytes = 5 * 1024 * 1024
    try:
        if os.path.getsize(file_path) > max_bytes:
            return None
        with open(file_path, "rb") as f:
            raw = f.read()
    except OSError:
        return None
    media_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }
    media_type = media_map.get(ext, "image/jpeg")
    b64 = base64.b64encode(raw).decode("utf-8")
    try:
        from app.cosi_app import invoke_ai_with_fallback
    except Exception:
        return None
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "temperature": 0.2,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Briefly describe this image: main subjects, any visible text, and overall purpose (1 short paragraph).",
                    },
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64,
                        },
                    },
                ],
            }
        ],
    }
    try:
        resp = invoke_ai_with_fallback(
            body,
            token=token,
            purpose="cosilive",
            ip_address="127.0.0.1",
            start_time=None,
        )
        content = resp.get("content", [])
        if content and isinstance(content, list) and len(content) > 0:
            txt = content[0].get("text")
            if txt:
                return (txt or "").strip()[:4000]
    except Exception as e:
        return f"[vision description failed: {e}]"
    return None


def extract_attachments(service, user_id, message_id):
    try:
        message = (
            service.users().messages().get(userId=user_id, id=message_id).execute()
        )
        payload = message.get("payload") or {}
        saved_files = []

        for part in _iter_gmail_attachment_parts(payload):
            body = part.get("body") or {}
            att_id = body.get("attachmentId")
            if not att_id:
                continue
            filename = _guess_attachment_filename(part)
            attachment = (
                service.users()
                .messages()
                .attachments()
                .get(userId=user_id, messageId=message_id, id=att_id)
                .execute()
            )

            data = base64.urlsafe_b64decode(attachment["data"].encode("UTF-8"))

            file_path = os.path.abspath(filename)
            with open(file_path, "wb") as f:
                f.write(data)

            saved_files.append({"filename": filename, "path": file_path})

        return saved_files

    except HttpError as error:
        return [{"error": str(error)}]


@mcp_gmail.tool()
def download_attachments(message_id: str, token: str = None) -> dict:
    """
    Download all attachments from a given email.

    Args:
        message_id: The Gmail message ID.

    Returns:
        Per-file metadata including local `path`. Image files may include `visual_description`
        when ENABLE_IMAGE_ANALYSIS is on (vision model), so the assistant does not need a user upload.
    """
    service_gmail = get_gmail_service(token)
    attachments = extract_attachments(
        service_gmail, user_id=settings.user_id, message_id=message_id
    )

    for item in attachments:
        if not isinstance(item, dict) or "error" in item:
            continue
        path = item.get("path")
        fn = item.get("filename")
        if path and fn:
            desc = _describe_image_with_vision(path, fn, token)
            if desc:
                item["visual_description"] = desc

    return {
        "message_id": message_id,
        "attachments": attachments,  # e.g., [{"filename": "invoice.pdf", "url": "https://..."}]
    }


@mcp_gmail.tool()
def get_unread_emails_db(max_results: int = 10, token: str = None) -> dict:
    """
    Get unread emails from MongoDB (replaces Gmail API version).
    """
    try:
        results = unread_email_search(token=token, limit=max_results)
        return {
            "success": True,
            "count": len(results),
            "emails": results,
            "source": "MongoDB",
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Error fetching unread emails: {str(e)}",
            "emails": [],
            "count": 0,
        }


@mcp_gmail.tool()
def get_starred_emails(max_results: int = 10, token: str = None) -> dict:
    """
    Tool wrapper: fetch starred emails for the user.
    """
    try:
        results = starred_email_search(token=token, limit=max_results)
        return {
            "success": True,
            "count": len(results),
            "emails": results,
            "source": "MongoDB",
        }
    except Exception as e:
        print(f"Error fetching starred emails in server wrapper: {e}")
        return {
            "success": False,
            "error": f"Error fetching starred emails: {str(e)}",
            "emails": [],
            "count": 0,
        }


@mcp_gmail.tool()
def get_emails_from(sender: str, max_results: int = 10, token: str = None) -> dict:
    """
    Tool wrapper: fetch emails from a specific sender (Gmail 'from:' operator).
    """
    try:
        results = from_email_search(token=token, sender=sender, limit=max_results)
        return {
            "success": True,
            "count": len(results),
            "emails": results,
            "source": "MongoDB",
        }
    except Exception as e:
        print(f"Error fetching emails from {sender}: {e}")
        return {
            "success": False,
            "error": f"Error fetching emails from {sender}: {str(e)}",
            "emails": [],
            "count": 0,
        }


@mcp_gmail.tool()
def get_emails_to(
    recipient: str, max_results: int = 10, token: Optional[str] = None
) -> dict:
    """
    Tool wrapper: fetch emails sent to a specific recipient (Gmail 'to:' operator).
    """
    try:
        results = to_email_search(token=token, recipient=recipient, limit=max_results)
        return {
            "success": True,
            "count": len(results),
            "emails": results,
            "source": "MongoDB",
        }
    except Exception as e:
        print(f"Error fetching emails to {recipient}: {e}")
        return {
            "success": False,
            "error": f"Error fetching emails to {recipient}: {str(e)}",
            "emails": [],
            "count": 0,
        }


@mcp_gmail.tool()
def get_unread_emails(max_results: int = 10, token: str = None) -> dict:
    """
    Get unread emails directly from Gmail API (not from MongoDB).

    Args:
        max_results: Maximum number of unread emails to return (default: 10)
        token: User authentication token

    Returns:
        Dictionary containing unread emails with their details
    """
    try:
        service_gmail = get_gmail_service(token)

        # Search for unread messages using the Gmail API
        unread_messages = search_messages(
            service=service_gmail,
            user_id=settings.user_id,
            max_results=max_results,
            is_unread=True,
        )

        # Get detailed information for each unread message
        detailed_emails = []
        for message in unread_messages:
            try:
                # Get full message details
                full_message = get_message(
                    service_gmail, message["id"], settings.user_id
                )

                # Extract headers
                headers = get_headers_dict(full_message)

                # Parse message body
                body = parse_message_body(full_message)

                # Create email object
                email_data = {
                    "id": message["id"],
                    "thread_id": message.get("threadId", ""),
                    "from": headers.get("From", ""),
                    "to": headers.get("To", ""),
                    "subject": headers.get("Subject", ""),
                    "date": headers.get("Date", ""),
                    "body": body[:500] if body else "",  # Truncate body to 500 chars
                    "snippet": full_message.get("snippet", ""),
                    "labels": full_message.get("labelIds", []),
                    "is_unread": True,
                }
                detailed_emails.append(email_data)

            except Exception as e:
                print(f"Error processing message {message['id']}: {str(e)}")
                continue

        return {
            "success": True,
            "count": len(detailed_emails),
            "emails": detailed_emails,
            "source": "Gmail API Direct",
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Error fetching unread emails: {str(e)}",
            "emails": [],
            "count": 0,
        }


###########################***********************JIRA TOOLS


# @mcp_jira.tool()
# def list_projects(token: str = None) -> str:
#     url = f"{your_domain_url}rest/api/3/project"
#     response = requests.request("GET", url, headers=headers, auth=auth)

#     projects = json.loads(response.text)
#     porjs = []
#     for project in projects:
#         proj = {}

#         proj_nm = project["name"]
#         print(proj_nm)
#         proj["project"] = project["name"]

#         # url = "https://kiratitsolutions-team.atlassian.net/rest/api/3/search?jql=project=TEST2&maxResults=1000"
#         url_issue = (
#             f"{your_domain_url}rest/api/3/search?jql=project={proj_nm}&maxResults=1000"
#         )
#         print(url_issue)
#         response_issue = requests.request("GET", url_issue, headers=headers, auth=auth)
#         issues = json.loads(response_issue.text)
#         isus = []
#         for issue in issues["issues"]:
#             isu = {}
#             # print(issue["fields"]["summary"])
#             # print(issue["fields"]["assignee"]["displayName"])
#             isu["issue"] = issue["fields"]["summary"]
#             isu["issue_key"] = issue["key"]
#             isu["asigned"] = issue["fields"]["assignee"]["displayName"]
#             isu["asigne_email"] = issue["fields"]["assignee"]["emailAddress"]
#             isu["status"] = issue["fields"]["status"]["name"]
#             isu["issue_url"] = f"{your_domain_url}browse/{issue['key']}"
#             isus.append(isu)
#         proj["issue"] = isus
#         porjs.append(proj)
#     return porjs


# print(json.dumps(json.loads(response.text), sort_keys=True, indent=4, separators=(",", ": ")))


# @mcp_jira.tool()
# def list_projects() -> str:
#     """
#     List all Jira projects.
#     """
#     url = f"{your_domain_url}rest/api/3/project"
#     try:
#         # response = requests.get(url, headers=headers, auth=auth)
#         response = requests.request(
#          "GET",
#             url,
#             headers=headers,
#             auth=auth
#         )
#         response.raise_for_status()
#         projects = response.json()
#         return {
#             "status": "success",
#             "message": "Projects fetched successfully.",
#             "projects": [{"id": project["id"], "name": project["name"]} for project in projects]
#         }
#     except Exception as e:
#         return {
#             "status": "error",
#             "message": f"Failed to fetch projects: {str(e)}"
#         }


# @mcp_jira.tool()
# def list_issues(project_key: str, token: str = None) -> str:
#     """
#     List all issues for a given Jira project.
#     """
#     url = (
#         f"{your_domain_url}rest/api/3/search?jql=project={project_key}&maxResults=1000"
#     )
#     try:
#         response = requests.get(url, headers=headers, auth=auth)
#         response.raise_for_status()
#         issues = response.json().get("issues", [])
#         return {
#             "status": "success",
#             "message": "Issues fetched successfully.",
#             "issues": [
#                 {
#                     "key": issue["key"],
#                     "summary": issue["fields"]["summary"],
#                     "assignee": (
#                         issue["fields"]["assignee"]["displayName"]
#                         if issue["fields"]["assignee"]
#                         else "Unassigned"
#                     ),
#                     "status": issue["fields"]["status"]["name"],
#                     "issue_url": f"{your_domain_url}browse/{issue['key']}",
#                 }
#                 for issue in issues
#             ],
#         }
#     except Exception as e:
#         return {"status": "error", "message": f"Failed to fetch issues: {str(e)}"}


# @mcp_jira.tool()
# def transition_issue(issue_key: str, transition_name: str, token: str = None) -> str:
#     """
#     Transition a Jira issue to a new status.
#     """

#     def get_transition_id(issue_key, transition_name):
#         url = f"{your_domain_url}rest/api/3/issue/{issue_key}/transitions"
#         try:
#             response = requests.get(url, headers=headers, auth=auth)
#             response.raise_for_status()
#             transitions = response.json().get("transitions", [])
#             for transition in transitions:
#                 if transition["name"].lower() == transition_name.lower():
#                     return transition["id"]
#             return None
#         except Exception as e:
#             return None

#     transition_id = get_transition_id(issue_key, transition_name)
#     if not transition_id:
#         return {
#             "status": "error",
#             "message": f"Transition '{transition_name}' not found for issue {issue_key}.",
#         }

#     url = f"{your_domain_url}rest/api/3/issue/{issue_key}/transitions"
#     payload = {"transition": {"id": transition_id}}
#     try:
#         response = requests.post(url, json=payload, headers=headers, auth=auth)
#         if response.status_code == 204:
#             return {
#                 "status": "success",
#                 "message": f"Issue {issue_key} successfully transitioned to '{transition_name}'.",
#             }
#         else:
#             return {
#                 "status": "error",
#                 "message": f"Failed to transition issue: {response.status_code} - {response.text}",
#             }
#     except Exception as e:
#         return {"status": "error", "message": f"Failed to transition issue: {str(e)}"}


###########################***********************CALENDER TOOL
@mcp_calender.tool()
def add_event(
    summary: str,
    start_time: str,
    end_time: str,
    attendees: list[str] | str = None,
    enable_transcript: bool = False,
    transcript_mode: str = "prioritize_accuracy",
    token: str = None,
) -> str:
    # Normalize attendees: handle both comma-separated string and list
    if attendees:
        if isinstance(attendees, str):
            # Split comma-separated string and clean up whitespace
            attendees_list = [email.strip() for email in attendees.split(",") if email.strip()]
        elif isinstance(attendees, list):
            # Already a list, but ensure all items are strings
            attendees_list = [str(email).strip() for email in attendees if str(email).strip()]
        else:
            attendees_list = []
    else:
        attendees_list = []

    start_dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M")
    end_dt = datetime.strptime(end_time, "%Y-%m-%d %H:%M")

    # # Localize to local timezone
    # local_tz = pytz.timezone("Asia/Kolkata")
    # print(local_tz)
    # start_dt = local_tz.localize(start_dt)
    # end_dt = local_tz.localize(end_dt)
    # Format as RFC3339 strings for Google Calendar API
    start_str = start_dt.isoformat()
    end_str = end_dt.isoformat()
    # Create the event (create_event gets service internally)
    event = create_event(
        summary,
        start_str,
        end_str,
        description=None,
        attendees=attendees_list,
        token=token,
        enable_transcript=enable_transcript,
        transcript_mode=transcript_mode,
    )

    # Check if event creation was successful
    if event.get("status") == "error":
        return event
    
    # Return the event data (create_event already returns the proper structure)
    return event


@mcp_transcript.tool()
def get_meeting_transcript_mcp(
    calendar_id: str | None = None,
    meeting_url: str | None = None,
    max_transcript_chars: int = 120_000,
    prefer_api: bool = False,
    token: str = None,
) -> dict:
    return get_meeting_transcript(
        token=token,
        calendar_id=calendar_id,
        meeting_url=meeting_url,
        max_transcript_chars=max_transcript_chars,
        prefer_api=prefer_api,
    )


@mcp_calender.tool()
def upcoming_events(max_results: int = 100, token: str = None) -> str:
    print("token2", token)
    service_calender = get_calendar_service(token)
    # events = list_events(service, max_results)
    # return "\n".join([f"{e['summary']} at {e['start'].get('dateTime')}" for e in events])
    result = list_events(service_calender, max_results, token=token)
    print(result)
    return {
        "status": "success",
        "message": "Event fetched successfully.",
        "events": result,
    }


@mcp_calender.tool()
def cancel_event(event_id: str, token: str = None) -> str:
    # delete_event(service, event_id)
    # return f"Event {event_id} cancelled"
    service_calender = get_calendar_service(token)
    try:
        service_calender.events().delete(
            calendarId="primary", eventId=event_id
        ).execute()
        return {
            "status": "success",
            "message": f"Event {event_id} cancelled successfully.",
            "event": "Meeting Cancelled",
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to cancel event: {str(e)}",
            "event": "Not Found",
        }


# @mcp_calender.resource("calendar://events/{event_id}")
# def get_event_info(event_id: str,token: str) -> str:
#     # print("token",token)
#     # event =get_event(service, event_id)
#     # return f"{event['summary']} from {event['start']['dateTime']} to {event['end']['dateTime']}"
#     service_calender=get_calendar_service(token)
#     try:
#         event =get_event(service_calender, event_id)
#         # event = service.events().get(calendarId=settings.user_id, eventId=event_id).execute()
#         return {
#             "status": "success",
#             "message": f"Event Created successfully.",
#             "event": {
#                 "id": event.get("id"),
#                 "summary": event.get("summary"),
#                 "description": event.get("description"),
#                 "start": event.get("start", {}).get("dateTime", event.get("start", {}).get("date")),
#                 "end": event.get("end", {}).get("dateTime", event.get("end", {}).get("date")),
#                 "location": event.get("location"),
#                 "attendees": [att.get("email") for att in event.get("attendees", [])] if event.get("attendees") else [],
#                 "htmlLink": event.get("htmlLink")
#             }
#         }
#     except Exception as e:
#         return {
#             "status": "error",
#             "message": f"Failed to retrieve event: {str(e)}"
#         }


@mcp_calender.tool()
def search_calendar_events(
    email: str = None,
    date: str = None,
    start: str = None,
    end: str = None,
    query: str = None,
    max_results: int = 50,
    limit: int | None = None,
    token: str = None,
) -> str:
    """
    Search for calendar events using MongoDB (text, date range, vector).
    """
    # If start/end not provided, try to parse from date
    if date and not (start or end):
        try:
            if len(date) == 7:  # YYYY-MM
                year, month = map(int, date.split("-"))
                start = f"{year:04d}-{month:02d}-01"
                import calendar as cal

                last_day = cal.monthrange(year, month)[1]
                end = f"{year:04d}-{month:02d}-{last_day:02d}"
            elif len(date) == 10:  # YYYY-MM-DD
                start = end = date
        except Exception:
            pass

    # If we have start but no end, or end but no start, try to infer the missing one
    if start and not end:
        # If start is today, assume end is tomorrow
        from datetime import datetime, timedelta

        try:
            start_date = datetime.strptime(start, "%Y-%m-%d")
            today = datetime.now().date()
            if start_date.date() == today:
                end = (start_date + timedelta(days=1)).strftime("%Y-%m-%d")
        except:
            pass
    elif end and not start:
        # If end is tomorrow, assume start is today
        from datetime import datetime, timedelta

        try:
            end_date = datetime.strptime(end, "%Y-%m-%d")
            tomorrow = (datetime.now() + timedelta(days=1)).date()
            if end_date.date() == tomorrow:
                start = (end_date - timedelta(days=1)).strftime("%Y-%m-%d")
        except:
            pass

    text_query = query
    if email:
        text_query = (text_query or "") + f" {email}"

    print(f"🔍 Calendar search: start={start}, end={end}, query='{text_query}'")

    effective_max = (
        int(limit) if isinstance(limit, int) and limit > 0 else int(max_results)
    )
    result = mongo_search_events(
        query=text_query, start=start, end=end, max_results=effective_max, token=token
    )
    return {
        "status": "success",
        "message": "Events fetched successfully.",
        "events": result["events"],
    }


@mcp_calender.tool()
def update_calendar_event(
    event_id: str,
    summary: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    description: str | None = None,
    attendees: list[str] | str | None = None,
    location: str | None = None,
    token: str = None,
) -> dict:
    """
    Update an existing calendar event by ID. Accepts human-friendly time format
    "YYYY-MM-DD HH:MM" or RFC3339. If a naive format is provided, it's converted
    to ISO8601 without timezone; Calendar service will add timezone.
    """
    # Normalize attendees: handle both comma-separated string and list
    attendees_list = None
    if attendees:
        if isinstance(attendees, str):
            # Split comma-separated string and clean up whitespace
            attendees_list = [email.strip() for email in attendees.split(",") if email.strip()]
        elif isinstance(attendees, list):
            # Already a list, but ensure all items are strings
            attendees_list = [str(email).strip() for email in attendees if str(email).strip()]

    def to_iso(s: str | None) -> str | None:
        if not s:
            return None
        try:
            # Try friendly format first
            dt = datetime.strptime(s, "%Y-%m-%d %H:%M")
            return dt.isoformat()
        except Exception:
            # Assume already RFC3339/ISO
            return s

    start_iso = to_iso(start_time)
    end_iso = to_iso(end_time)

    return calendar_update_event(
        event_id=event_id,
        summary=summary,
        start_time=start_iso,
        end_time=end_iso,
        description=description,
        attendees=attendees_list,
        location=location,
        token=token,
    )


###########################***********************SALESFORCE TOOLS
# @mcp_salesforce.tool()
# def create_lead_tool(
#     first_name: str,
#     last_name: str,
#     company: str,
#     email: str = None,
#     phone: str = None,
#     status: str = "Open - Not Contacted",
#     lead_source: str = "Web",
#     token: str = None,
# ) -> str:
#     """
#     Tool to create a new lead in Salesforce.
#     """
#     return create_lead(
#         sf, first_name, last_name, company, email, phone, status, lead_source
#     )


# @mcp_salesforce.tool()
# def update_lead_status_tool(first_name: str, last_name: str, status: str) -> str:
#     """
#     Tool to update the status of a Salesforce lead.
#     """
#     return update_lead_status(sf, first_name, last_name, status)


# @mcp_salesforce.tool()
# def delete_lead_tool(first_name: str, last_name: str, token: str = None) -> str:
#     """
#     Tool to delete a Salesforce lead.
#     """
#     return delete_lead(sf, first_name, last_name)


# @mcp_salesforce.tool()
# def get_all_leads_tool(token: str = None) -> str:
#     """
#     Tool to retrieve all Salesforce leads.
#     """
#     return get_all_leads(sf)


# @mcp_salesforce.tool()
# def add_event_tool(
#     subject: str,
#     start_time: str,
#     end_time: str,
#     first_name: str,
#     last_name: str,
#     token: str = None,
# ) -> str:
#     """
#     Tool to add an event to Salesforce.
#     """
#     return add_event(sf, subject, start_time, end_time, first_name, last_name)


# # === Resources ===


# @mcp_salesforce.resource("salesforce://leads/{lead_id}")
# def get_lead_resource(lead_id: str) -> str:
#     """
#     Resource to retrieve a Salesforce lead by ID.
#     """
#     return get_lead(sf, lead_id)


###########################***********************SLACK TOOLS


@mcp_slack.tool()
def post_message(channel: str, message: str, token: str = None) -> dict:
    return send_slack_messages(channel, message, token)


# @mcp_slack.tool()
# def mention_user_and_send(channel: str, user_id: str, message: str) -> dict:
#     return mention_and_send(channel, user_id, message)


@mcp_slack.tool()
def get_channels(token: str = None) -> dict:
    return slack_list_channels(token)


@mcp_slack.tool()
def slack_get_channel_messages(
    channel_id: str, limit: int = 100, token: str = None, order: str = "desc"
) -> dict:
    return get_channel_messages(channel_id, limit, token, order)


# @mcp_slack.tool()
# def get_channel_info(channel_id: str, token: str = None) -> dict:
#     return slack_get_channel_info(channel_id, token)
# NOTE: get_channel_info is commented out because slack_get_channel_info is not imported


@mcp_slack.tool()
def list_users(token: str = None) -> dict:
    return slack_list_users(token)


@mcp_slack.tool()
def get_channel_members(channel_id: str, token: str = None) -> dict:
    return slack_get_channel_members(channel_id, token)


@mcp_slack.tool()
def get_user_info(token: str = None, channel: str = None) -> dict:
    return slack_get_user_info(token, channel)


@mcp_slack.tool()
def create_channel(name: str, is_private: bool = False, token: str = None) -> dict:
    return slack_create_channel(name, is_private, token)


@mcp_slack.tool()
def archive_channel(channel: str, token: str = None) -> dict:
    return slack_archive_channel(channel, token)


@mcp_slack.tool()
def invite_user_to_channel(channel: str, user: str, token: str = None) -> dict:
    return slack_invite_user_to_channel(channel, user, token)


@mcp_slack.tool()
def kick_user_from_channel(channel: str, user: str, token: str = None) -> dict:
    return slack_kick_user_from_channel(channel, user, token)


@mcp_slack.tool()
def pin_message(channel: str, timestamp: str, token: str = None) -> dict:
    return slack_pin_message(channel, timestamp, token)


@mcp_slack.tool()
def unpin_message(channel: str, timestamp: str, token: str = None) -> dict:
    return slack_unpin_message(channel, timestamp, token)
    # return slack_unpin_message(channel, timestamp)


# @mcp_slack.tool()
# def react_to_message(
#     channel: str, timestamp: str, emoji: str, token: str = None
# ) -> dict:
#     return slack_react_to_message(channel, timestamp, emoji, token)


@mcp_slack.tool()
def open_dm_with_user(user: str, token: str = None) -> dict:
    return slack_open_dm(user, token)


@mcp_slack.tool()
def slack_reply_message(
    channel: str, timestamp: str, message: str, token: str = None
) -> dict:
    # Convert timestamp string to float if needed
    try:
        timestamp_float = float(timestamp) if isinstance(timestamp, str) else timestamp
    except (ValueError, TypeError):
        timestamp_float = timestamp
    # reply_message is imported from slack_mcp (aliased from slack_reply_message)
    return reply_message(token, channel, timestamp_float, message)


# Note: reply_message is imported from slack_mcp (line 123) and used in slack_reply_message above
# cosi_app.py imports slack_reply_message as reply_message to get the tool function


@mcp_slack.tool()
def send_dm(user: str, message: str, token: str = None) -> dict:
    return slack_send_dm(user, message, token)


@mcp_slack.tool()
def get_dm_messages(user: str, limit: int = 10, token: str = None) -> dict:
    return slack_get_dm_messages(user, limit, token)


# @mcp_slack.tool()
# def upload_file(
#     channel: str, filepath: str, title: str = None, token: str = None
# ) -> dict:
#     return slack_upload_file(channel, filepath, title, token)


# Google Docs Functions


@mcp_docs.tool()
def get_user_documents(limit: int = 10, token: str = None) -> dict:
    return gdocs_get_user_documents(limit, unified_token=token)


@mcp_docs.tool()
def generate_doc_from_link(
    title: str,
    link: str,
    prompt: str,
    tone: str = "Professional",
    style: str = "Concise",
    token: str = None,
) -> dict:
    return gdocs_generate_doc_from_link(
        title=title,
        link=link,
        prompt=prompt,
        tone=tone,
        style=style,
        unified_token=token,
    )


@mcp_docs.tool()
def get_document_content(document_id: str, token: str = None) -> dict:
    return gdocs_get_document_content(document_id, unified_token=token)


@mcp_docs.tool()
def create_document(title: str, initial_text: str = "", token: str = None) -> dict:
    return gdocs_create_document(title, initial_text, unified_token=token)


@mcp_docs.tool()
def update_document_text(
    document_id: str,
    index: int,
    operation: str,
    text: str| None = None,
    end_index: int | None = None,
    formatting: dict | None = None,
    target_index: int | None = None,
    token: str = None,
) -> dict:
    """
    Update a Google Doc by index. Automatically fetches document structure (image_positions) before updating.
    When index is omitted, returns document_structure only (for determining index/end_index). When index is set, performs the update and returns result plus document_structure.
    """
    return gdocs_update_document(
        document_id=document_id,
        text=text,
        index=index,
        operation=operation,
        end_index=end_index,
        formatting=formatting,
        target_index=target_index,
        unified_token=token,
    )

@mcp_docs.tool()
def update_document_image(
    document_id: str,
    image_id: str,
    index: int,
    end_index: int,
    operation: str,
    target_index: int | None = None,
    text: str | None = None,
    token: str = None,
) -> dict:
    """
    Perform structural image operations in a Google Doc.

    This tool expects image structural data (image_id, index, end_index)
    returned by get_document_content.

    Supported operations:
    - move → move image to target_index
    - delete → remove image block
    - insert_text_before → insert text at image start
    - insert_text_after → insert text at image end

    Notes:
    - This tool performs only structural inline object edits.
    - It does NOT apply text formatting.
    - Caller must ensure indexes are fresh (recommended: re-read after image move).
    """

    return gdocs_update_image(
        document_id=document_id,
        image_id=image_id,
        index=index,
        end_index=end_index,
        operation=operation,
        target_index=target_index,
        text=text,
        unified_token=token,
    )

@mcp_docs.tool()
def update_document_table(
    document_id: str,
    operation: str,
    table_start_index: int | None = None,
    row_index: int | None = None,
    column_index: int | None = None,
    rows: int | None = None,
    columns: int | None = None,
    text: str | None = None,
    target_index: int | None = None,
    token: str = None,
) -> dict:

    return gdocs_update_table(
        document_id=document_id,
        operation=operation,
        table_start_index=table_start_index,
        row_index=row_index,
        column_index=column_index,
        rows=rows,
        columns=columns,
        text=text,
        target_index=target_index,
        unified_token=token,
    )
    
@mcp_docs.tool()
def get_document_table_content(
    document_id: str,
    table_start_index: int,
    token: str = None,
) -> dict:
    """
    Reads full structured content of a specific table in a Google Doc.
    """
    return gdocs_get_table_content(
        document_id=document_id,
        table_start_index=table_start_index,
        unified_token=token,
    )

@mcp_docs.tool()
def add_document_comment(
    document_id: str,
    text: str,
    token: str = None,
) -> dict:
    """
    Add a top-level comment to a Google Docs/Sheets/Slides file via the Drive API.

    This is used by autopilot comment_reply actions and by interactive tools.
    """
    return gdocs_add_comment(document_id=document_id, text=text, unified_token=token)


@mcp_docs.tool()
def delete_document(document_id: str, token: str = None) -> dict:
    return gdocs_delete_document(document_id, unified_token=token)


@mcp_docs.tool()
def share_document(
    document_id: str, email: str, role: str = "writer", token: str = None
) -> dict:
    return gdocs_share_document(document_id, email, role, unified_token=token)


@mcp_docs.tool()
def search_in_document(document_id: str, keyword: str, token: str = None) -> dict:
    return gdocs_search_in_document(document_id, keyword, unified_token=token)


# @mcp_docs.tool()
# def search_docs(
#     query: str,
#     owner: str = None,
#     after_date: str = None,
#     before_date: str = None,
#     max_results: int = 10,
#     token: str = None,
# ) -> dict:
#     """
#     Search Google Docs using MongoDB (text, vector, date range).
#     """
#     result = mongo_search_docs(
#         query=query,
#         owner=owner,
#         after_date=after_date,
#         before_date=before_date,
#         max_results=max_results,
#         token=token,
#     )
#     return {
#         "status": "success",
#         "message": "Documents fetched successfully.",
#         "documents": result["documents"],
#     }


@mcp_docs.tool()
def doc_history(document_id: str, token: str = None) -> dict:
    return get_doc_history(document_id, unified_token=token)


@mcp_docs.tool()
def search_docs_by_date_tool(
    after_date: str | None = None,
    before_date: str | None = None,
    on_date: str | None = None,
    max_results: int = 50,
    token: str | None = None,
) -> dict:
    """
    Strict Mongo date search for documents sorted by newest first. Use either on_date (YYYY-MM-DD)
    or a combination of after_date/before_date (YYYY-MM-DD).
    """
    return search_docs_by_date(
        after_date=after_date,
        before_date=before_date,
        on_date=on_date,
        max_results=max_results,
        token=token,
    )


@mcp_docs.tool()
def list_docs_tool(
    max_results: int = 50,
    token: str | None = None,
) -> dict:
    """
    Simple function to list documents in latest order (by created date descending).
    Takes no query, just returns docs sorted by newest first.
    """
    return list_docs(
        max_results=max_results,
        token=token,
    )


# Google Sheets Functions


@mcp_sheets.tool()
def list_sheets(page_size: int = 20, token: str = None) -> dict:
    """
    Tool to list available Google Sheets.
    """
    return {"sheets": gsheets_list_sheets(page_size, unified_token=token)}


@mcp_sheets.tool()
def create_sheet(title: str, token: str = None) -> dict:
    return gsheets_create_sheet(title, unified_token=token)


@mcp_sheets.tool()
def read_sheet_data(
    sheet_id: str,
    sheet_name: str = None,
    column_name: str | list[str] = None,
    range_: str = None,
    range: str = None,  # Support both 'range' and 'range_' for AI compatibility
    all_sheets_info: dict | None = None,
    token: str = None,
    include_cells: bool = False
) -> dict:
    """
    Read data from a Google Sheet.
    Uses existing structure if provided, otherwise fetches it automatically.
    Returns data in a consistent format (spreadsheet → sheets).
    """
    # Support both 'range' and 'range_' parameters (range takes precedence)
    final_range = range if range is not None else range_
    return gsheets_read_data(
        sheet_id,
        unified_token=token,
        sheet_name=sheet_name,
        column_name=column_name,
        range_=final_range,
        all_sheets_info=all_sheets_info,
        include_cells=include_cells,
    )


@mcp_sheets.tool()
def update_sheet_data(
    sheet_id: str,
    sheet_name: str,
    mode: str,
    data: list | dict | str,
    target: str | None = None,
    token: str = None,
) -> dict:
    """
    Add or update data in a Google Sheet.
    Automatically infers whether to update or append based on `target`.
    """
    return gsheets_update_data(
        sheet_id=sheet_id,
        sheet_name=sheet_name,
        mode=mode,
        data=data,
        target=target,
        unified_token=token,
    )


@mcp_sheets.tool()
def sheet_chart_metadata(
    sheet_id: str, sheet_name: str = None, token: str = None
) -> dict:
    return gsheets_get_chart_metadata(
        sheet_id, sheet_name=sheet_name, unified_token=token
    )


@mcp_sheets.tool()
def sheet_create_chart(
    sheet_id: str,
    sheet_name: str,
    chart_type: str,
    x_range: str,
    y_ranges: list[str],
    title: str = None,
    token: str = None,
) -> dict:
    """
    MCP tool to create a chart in Google Sheets using A1-style ranges.
    """
    return gsheets_create_chart(
        sheet_id=sheet_id,
        sheet_name=sheet_name,
        chart_type=chart_type,
        x_range=x_range,
        y_ranges=y_ranges,
        title=title,
        unified_token=token,
    )


@mcp_sheets.tool()
def sheet_update_chart(
    sheet_id: str,
    chart_id: int,
    title: str = None,
    chart_type: str = None,
    x_range: str = None,
    y_ranges: list[str] = None,
    token: str = None,
) -> dict:
    """
    Update an existing chart in Google Sheets.
    Allows changing the title, chart type, or data ranges.
    """
    return gsheets_update_chart(
        sheet_id=sheet_id,
        chart_id=chart_id,
        title=title,
        chart_type=chart_type,
        x_range=x_range,
        y_ranges=y_ranges,
        unified_token=token,
    )


@mcp_sheets.tool()
def sheet_create_pivot_table(
    sheet_id: str,
    sheet_tab_id: int,
    source_range: str,
    pivot_sheet_title: str,
    rows: list,
    columns: list,
    values: list,
    token: str = None,
) -> dict:

    return create_pivot_table(
        sheet_id=sheet_id,
        sheet_tab_id=sheet_tab_id,
        source_range=source_range,
        pivot_sheet_title=pivot_sheet_title,
        rows=rows,
        columns=columns,
        values=values,
        unified_token=token,
    )


@mcp_sheets.tool()
def write_sheet_data(
    sheet_id: str, range: str, values: List[List[str]], token: str = None
) -> dict:
    return gsheets_write_data(sheet_id, range, values, unified_token=token)


@mcp_sheets.tool()
def append_sheet_data(
    sheet_id: str, range: str, values: List[List[str]], token: str = None
) -> dict:
    return gsheets_append_data(sheet_id, range, values, unified_token=token)


@mcp_sheets.tool()
def clear_sheet_range(sheet_id: str, range: str, token: str = None) -> dict:
    return gsheets_clear_range(sheet_id, range, unified_token=token)


@mcp_sheets.tool()
def add_new_tab(sheet_id: str, title: str, token: str = None) -> dict:
    return gsheets_add_tab(sheet_id, title, unified_token=token)


@mcp_sheets.tool()
def delete_sheet_tab(sheet_id: str, sheet_tab_id: int, token: str = None) -> dict:
    return gsheets_delete_tab(sheet_id, sheet_tab_id, unified_token=token)


@mcp_sheets.tool()
def share_sheet(
    sheet_id: str, email: str, role: str = "writer", token: str = None
) -> dict:
    return gsheets_share_sheet(sheet_id, email, role, unified_token=token)


@mcp_sheets.tool()
def search_sheets(keyword: str, limit: int = 10, token: str = None) -> dict:
    return search_sheets_by_title(keyword, limit, unified_token=token)


@mcp_sheets.tool()
def sheet_history(sheet_id: str, token: str = None) -> dict:
    return get_sheet_history(sheet_id, unified_token=token)


@mcp_sheets.tool()
def add_sheet_comment(
    spreadsheet_id: str,
    text: str,
    token: str = None,
) -> dict:
    """
    Add a top-level comment to a Google Sheet. The comment is posted as the
    currently authenticated user. Use for replying to or adding comments on spreadsheets.
    """
    return gsheets_add_comment(
        spreadsheet_id=spreadsheet_id, text=text, unified_token=token
    )


@mcp_sheets.tool()
def list_sheet_info(sheet_id: str, token: str = None) -> dict:
    """
    Retrieve structural metadata for all tabs in a Google Sheets file.
    This includes sheet names, dimensions, and detected headers.
    """
    return gsheets_get_structure(sheet_id, unified_token=token)


# slides functions


@mcp_slides.tool()
def create_gamma_presentation(
    title: str,
    input_text: str,
    theme_id: str = None,
    num_cards: int = 5,
    format_: str = "presentation",
    text_mode: str = "generate",
    token: str = None,
    unified_token: str = None,
    wait_for_completion: bool = True,
    timeout: int = 1800,
) -> dict:
    """
    Create a presentation using Gamma API and optionally save to Google Drive.

    Args:
        title: Title of the presentation
        input_text: Main content for the presentation
        theme_id: Optional theme ID (use list_gamma_themes to get available themes)
        num_cards: Number of slides/cards to generate (default: 5)
        format_: Output format - "presentation", "document", "social", or "webpage" (default: "presentation")
        text_mode: Text processing mode - "generate", "condense", or "preserve" (default: "generate")
        token: User authentication token (required for Google Drive export) - alias for unified_token
        unified_token: User authentication token (required for Google Drive export) - preferred parameter name
        wait_for_completion: Whether to wait for the presentation to be fully generated (default: True)
        timeout: Maximum time to wait for completion in seconds (default: 1800 = 30 minutes)

    Returns:
        Dictionary with generation details and optionally Google Drive file info
    """
    try:
        # Import here to avoid circular imports
        from services.slides_mcp import (
            gamma_create_presentation,
            _in_progress_presentations,
            _poll_gamma_generation,
        )
        import time

        print(f"Starting Gamma presentation creation: {title}")

        # Use unified_token if provided, otherwise fall back to token
        final_token = unified_token if unified_token is not None else token

        # Create the presentation
        result = gamma_create_presentation(
            title=title,
            input_text=input_text,
            theme_id=theme_id,
            num_cards=num_cards,
            format_=format_,
            text_mode=text_mode,
            unified_token=final_token,
        )

        # gamma_create_presentation now returns a structured response with success/error status
        # Check if we got the new format (with "success" key)
        if "success" in result:
            # New format: return as-is (gamma_create_presentation handles everything)
            return result

        # Legacy format support (for backward compatibility)
        # If we're not waiting for completion, return the initial response
        if not wait_for_completion:
            return {
                "status": "processing",
                "message": "Gamma presentation creation started",
                "data": result,
            }

        # Wait for completion if requested
        if "generation_id" in result:
            print(f"Polling for completion of generation {result['generation_id']}")
            # Poll for completion
            start_time = time.time()
            while time.time() - start_time < timeout:
                # Check if the generation is complete
                if result.get("status") == "completed":
                    break

                # Wait before polling again
                time.sleep(5)

                # Check the status
                if "generation_id" in result:
                    try:
                        generation_info = _poll_gamma_generation(
                            result["generation_id"],
                            timeout=min(30, timeout - (time.time() - start_time)),
                            interval=5,
                        )

                        # Update the result with the latest info
                        result.update(generation_info)

                        # If generation is complete, break the loop
                        if generation_info.get("status") == "completed":
                            break

                    except Exception as e:
                        print(f"Error polling generation status: {str(e)}")
                        # Continue waiting if there's an error
                        pass

            # Final check if we have a result
            if result.get("status") != "completed":
                return {
                    "status": "timeout",
                    "message": "Timed out waiting for presentation generation to complete",
                    "data": result,
                }

        # If we have a presentation ID, get the final details
        if "id" in result:
            # The gamma_create_presentation function already handles the export to Google Drive if token is provided
            # and includes the drive_file in the result if successful
            return {
                "status": "success",
                "message": "Gamma presentation created successfully",
                "data": result,
            }

        # If we got here, something went wrong
        return {
            "status": "error",
            "message": "Failed to create Gamma presentation: Unknown error occurred",
            "data": result,
        }

    except Exception as e:
        import traceback

        error_trace = traceback.format_exc()
        print(f"Error in create_gamma_presentation: {error_trace}")
        return {
            "status": "error",
            "message": f"Failed to create Gamma presentation: {str(e)}",
            "error_details": str(e),
        }


@mcp_slides.tool()
def list_gamma_themes(token: str = None) -> dict:
    """
    List all available Gamma presentation themes.

    Args:
        token: User authentication token (not used currently, here for consistency)

    Returns:
        Dictionary with available themes
    """
    try:
        from services.slides_mcp import GAMMA_API_KEY, GAMMA_BASE_URL
        import requests

        if not GAMMA_API_KEY:
            return {"status": "error", "message": "Gamma API key not configured"}

        url = f"{GAMMA_BASE_URL.rstrip('/')}/themes"
        headers = {"X-API-KEY": GAMMA_API_KEY, "Accept": "application/json"}

        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        themes = response.json()

        return {"status": "success", "count": len(themes), "themes": themes}
    except Exception as e:
        return {"status": "error", "message": f"Failed to fetch Gamma themes: {str(e)}"}


@mcp_slides.tool()
def list_slides(page_size: int = 20, token: str = None) -> dict:
    """
    Tool to list available Google Slides presentations.
    """
    slides = gslides_list_presentations(page_size, unified_token=token)
    return {"slides": slides}


@mcp_slides.tool()
def create_slide_deck(title: str, token: str = None, **kwargs) -> dict:
    """
    Create a new Google Slides presentation.
    """
    return gslides_create_presentation(title, unified_token=token)


@mcp_slides.tool()
def share_slide_deck(
    presentation_id: str, email: str, role: str = "writer", token: str = None, **kwargs
) -> dict:
    """
    Share a Google Slides presentation with a user.
    """
    return gslides_share_presentation(presentation_id, email, role, unified_token=token)


@mcp_slides.tool()
def extract_text_from_slides(presentation_id: str, token: str = None, **kwargs) -> dict:
    """
    Extract all text content from a presentation.
    """
    return {"text": gslides_extract_text(presentation_id, unified_token=token)}


@mcp_slides.tool()
def search_slides(keyword: str, limit: int = 10, token: str = None) -> dict:
    return search_slides_by_title(keyword, limit, unified_token=token)


@mcp_slides.tool()
def slide_history(slide_id: str, token: str = None) -> dict:
    return get_slide_history(slide_id, unified_token=token)


@mcp_slides.tool()
def get_slide_content(presentation_id: str, token: str = None) -> dict:
    """Get detailed content from all slides with slide-by-slide context."""
    return gslides_get_slide_content(presentation_id, unified_token=token)


@mcp_slides.tool()
def get_specific_slide(
    presentation_id: str, slide_number: int, token: str = None
) -> dict:
    """Get content from a specific slide by slide number (1-based)."""
    return gslides_get_specific_slide(
        presentation_id, slide_number, unified_token=token
    )


@mcp_slides.tool()
def replace_text_in_slides(
    presentation_id: str,
    old_text: str,
    new_text: str,
    slide_number: int = None,
    token: str = None,
) -> dict:
    """Replace text in presentation. If slide_number is provided, only replace in that specific slide."""
    return gslides_replace_text(
        presentation_id, old_text, new_text, slide_number, unified_token=token
    )


@mcp_slides.tool()
def add_text_box_to_slide(
    presentation_id: str,
    slide_index: int,
    text: str,
    x: float = 100,
    y: float = 100,
    width: float = 300,
    height: float = 100,
    token: str = None,
) -> dict:
    """Add a text box to a specific slide."""
    return gslides_add_text_box(
        presentation_id, slide_index, text, x, y, width, height, unified_token=token
    )


@mcp_slides.tool()
def add_slide_to_presentation(
    presentation_id: str, layout: str = "BLANK", token: str = None
) -> dict:
    """Add a new slide to the presentation."""
    return gslides_add_slide(presentation_id, layout, unified_token=token)


@mcp_slides.tool()
def format_text_in_slides(
    presentation_id: str,
    text_to_format: str,
    bold: bool = None,
    italic: bool = None,
    font_size: int = None,
    color: str = None,
    token: str = None,
) -> dict:
    """Format specific text in the presentation (bold, italic, size, color)."""
    return gslides_format_text(
        presentation_id,
        text_to_format,
        bold,
        italic,
        font_size,
        color,
        unified_token=token,
    )


@mcp_slides.tool()
def add_table_to_slide(
    presentation_id: str,
    slide_index: int,
    rows: int,
    columns: int,
    x: float = 100,
    y: float = 100,
    width: float = 400,
    height: float = 200,
    token: str = None,
) -> dict:
    """Add a table to a specific slide."""
    return gslides_add_table(
        presentation_id,
        slide_index,
        rows,
        columns,
        x,
        y,
        width,
        height,
        unified_token=token,
    )


@mcp_slides.tool()
def update_table_cell(
    presentation_id: str,
    table_id: str,
    row: int,
    column: int,
    text: str,
    token: str = None,
) -> dict:
    """Update text in a specific table cell."""
    return gslides_update_table_cell(
        presentation_id, table_id, row, column, text, unified_token=token
    )


@mcp_slides.tool()
def populate_table(
    presentation_id: str, table_id: str, data: list, token: str = None
) -> dict:
    """Populate table with data (2D array)."""
    return gslides_populate_table(presentation_id, table_id, data, unified_token=token)


@mcp_slides.tool()
def add_table_rows(
    presentation_id: str,
    table_id: str,
    insert_index: int = None,
    number_of_rows: int = 1,
    token: str = None,
) -> dict:
    """Add rows to a table. If insert_index is not provided or -1, adds rows at the bottom."""
    return gslides_add_table_rows(
        presentation_id, table_id, insert_index, number_of_rows, unified_token=token
    )


@mcp_slides.tool()
def add_table_columns(
    presentation_id: str,
    table_id: str,
    insert_index: int = None,
    number_of_columns: int = 1,
    token: str = None,
) -> dict:
    """Add columns to a table. If insert_index is not provided or -1, adds columns at the right."""
    return gslides_add_table_columns(
        presentation_id, table_id, insert_index, number_of_columns, unified_token=token
    )


@mcp_slides.tool()
def delete_table_rows(
    presentation_id: str,
    table_id: str,
    start_index: int,
    number_of_rows: int = 1,
    token: str = None,
) -> dict:
    """Delete rows from a table starting at specified position."""
    return gslides_delete_table_rows(
        presentation_id, table_id, start_index, number_of_rows, unified_token=token
    )


@mcp_slides.tool()
def delete_table_columns(
    presentation_id: str,
    table_id: str,
    start_index: int,
    number_of_columns: int = 1,
    token: str = None,
) -> dict:
    """Delete columns from a table starting at specified position."""
    return gslides_delete_table_columns(
        presentation_id, table_id, start_index, number_of_columns, unified_token=token
    )


@mcp_slides.tool()
def insert_row_above(
    presentation_id: str,
    table_id: str,
    row_index: int,
    number_of_rows: int = 1,
    token: str = None,
) -> dict:
    """Insert rows above the specified row."""
    return gslides_insert_row_above(
        presentation_id, table_id, row_index, number_of_rows, unified_token=token
    )


@mcp_slides.tool()
def insert_row_below(
    presentation_id: str,
    table_id: str,
    row_index: int,
    number_of_rows: int = 1,
    token: str = None,
) -> dict:
    """Insert rows below the specified row."""
    return gslides_insert_row_below(
        presentation_id, table_id, row_index, number_of_rows, unified_token=token
    )


@mcp_slides.tool()
def insert_column_left(
    presentation_id: str,
    table_id: str,
    column_index: int,
    number_of_columns: int = 1,
    token: str = None,
) -> dict:
    """Insert columns to the left of the specified column."""
    return gslides_insert_column_left(
        presentation_id, table_id, column_index, number_of_columns, unified_token=token
    )


@mcp_slides.tool()
def insert_column_right(
    presentation_id: str,
    table_id: str,
    column_index: int,
    number_of_columns: int = 1,
    token: str = None,
) -> dict:
    """Insert columns to the right of the specified column."""
    return gslides_insert_column_right(
        presentation_id, table_id, column_index, number_of_columns, unified_token=token
    )


# New powerful tools from gSlides_ai integration


@mcp_slides.tool()
def list_slide_elements(presentation_id: str, slide_id: str, token: str = None) -> dict:
    """List all elements on a specific slide with their types and IDs."""
    return gslides_list_slide_elements(presentation_id, slide_id, unified_token=token)


@mcp_slides.tool()
def list_tables(presentation_id: str, token: str = None) -> dict:
    """List all tables in the presentation with their metadata."""
    return gslides_list_tables(presentation_id, unified_token=token)


@mcp_slides.tool()
def get_table_info(presentation_id: str, table_id: str, token: str = None) -> dict:
    """Get detailed information about a specific table."""
    return gslides_get_table_info(presentation_id, table_id, unified_token=token)


@mcp_slides.tool()
def read_table_data(presentation_id: str, table_id: str, token: str = None) -> dict:
    """Read all text data from a table as a 2D array."""
    return gslides_read_table_data(presentation_id, table_id, unified_token=token)


@mcp_slides.tool()
def replace_table_text(
    presentation_id: str,
    table_id: str,
    old_text: str,
    new_text: str = None,
    token: str = None,
) -> dict:
    """Replace or delete specific text in a table cell. If new_text is None/empty, deletes the text."""
    return gslides_replace_table_text(
        presentation_id, table_id, old_text, new_text, unified_token=token
    )


@mcp_slides.tool()
def search_presentation(
    presentation_id: str, keyword: str, table_id: str = None, token: str = None
) -> dict:
    """Search for a keyword in the presentation. Optionally limit search to a specific table."""
    return gslides_search_presentation(
        presentation_id, keyword, table_id, unified_token=token
    )


@mcp_slides.tool()
def get_element_text(presentation_id: str, element_id: str, token: str = None) -> dict:
    """Get text content from a specific element (shape, text box, etc.)."""
    return gslides_get_element_text(presentation_id, element_id, unified_token=token)


@mcp_slides.tool()
def delete_element(presentation_id: str, element_id: str, token: str = None) -> dict:
    """Delete a specific element (table, shape, image, etc.) from a slide."""
    return gslides_delete_element(presentation_id, element_id, unified_token=token)


@mcp_slides.tool()
def delete_slide(presentation_id: str, slide_id: str, token: str = None) -> dict:
    """Delete a slide from the presentation."""
    return gslides_delete_slide(presentation_id, slide_id, unified_token=token)


@mcp_slides.tool()
def insert_text(
    presentation_id: str,
    object_id: str,
    text: str,
    insertion_index: int = 0,
    token: str = None,
) -> dict:
    """Insert text into a shape or text box at a specific index."""
    return gslides_insert_text(
        presentation_id, object_id, text, insertion_index, unified_token=token
    )


@mcp_slides.tool()
def insert_image(
    presentation_id: str,
    slide_id: str,
    image_url: str,
    x: float = 100,
    y: float = 100,
    width: float = 300,
    height: float = 200,
    token: str = None,
) -> dict:
    """Insert an image on a slide from a URL."""
    return gslides_insert_image(
        presentation_id, slide_id, image_url, x, y, width, height, unified_token=token
    )


@mcp_slides.tool()
def list_slides_info(presentation_id: str, token: str = None) -> dict:
    """List all slides in a presentation with their IDs and index."""
    return gslides_list_slides_info(presentation_id, unified_token=token)


@mcp_slides.tool()
def add_rows_and_populate(
    presentation_id: str, table_id: str, data: list, token: str = None
) -> dict:
    """Add new rows at the bottom of the table and populate them with data in one operation."""
    return gslides_add_rows_and_populate(
        presentation_id, table_id, data, unified_token=token
    )


@mcp_slides.tool()
def append_table_row(
    presentation_id: str, table_id: str, row_data: list, token: str = None
) -> dict:
    """Append a single row to the bottom of the table with data."""
    return gslides_append_table_row(
        presentation_id, table_id, row_data, unified_token=token
    )


@mcp_slides.tool()
def add_columns_and_populate(
    presentation_id: str, table_id: str, data: list, token: str = None
) -> dict:
    """Add new columns at the right of the table and populate them with data in one operation."""
    return gslides_add_columns_and_populate(
        presentation_id, table_id, data, unified_token=token
    )


@mcp_slides.tool()
def append_table_column(
    presentation_id: str, table_id: str, column_data: list, token: str = None
) -> dict:
    """Append a single column to the right of the table with data."""
    return gslides_append_table_column(
        presentation_id, table_id, column_data, unified_token=token
    )


if __name__ == "__main__":
    raise RuntimeError(
        "Do not run app/server.py directly. Start the Flask app via app.py. "
        "Tool execution in production flows through assistant_handler.py -> server_parts.tools."
    )