"""Static function definitions and JSON-like structures extracted from the main app.
This file contains the `function_defs` list (tool schemas) and a `tools` placeholder
that other modules can import to keep `cosi_app.py` lightweight.

OpenAI Chat Completions allows at most 128 function tools; `invoke_openai` truncates
beyond that. Public web search is exposed as the `web_search` tool (Responses API),
not as an extra preflight call.
"""
import json

# NOTE: This file intentionally contains only data (no side-effects).

function_defs = [
    # Gmail function definitions
    {
        "name": "send_email",
        "description": "Send email via Gmail. Two modes: (1) send an existing draft by draft_id, or (2) compose and send a new email using to+subject (optional body/body_html/cc/bcc).",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Email subject"},
                "body": {"type": "string", "description": "Email body content (legacy parameter, used if body_text not provided)"},
                # "body_text": {"type": "string", "description": "Plain text email body (optional, falls back to body if not provided)"},
                "body_html": {"type": "string", "description": "HTML email body (optional). If provided along with body_text, creates a multipart/alternative message"},
                "cc": {"type": "string", "description": "Carbon copy recipients (optional)"},
                "bcc": {"type": "string", "description": "Blind carbon copy recipients (optional)"},
                "draft_id": {"type": "string", "description": "Optional Gmail draft ID. If provided, sends that existing draft and ignores to/subject/body fields."},
            },
            "required": [],
        },
    },
    # {
    #     "name": "search_emails_by_date",
    #     "description": "Strict MongoDB date search for emails sorted by newest first. Provide either on_date (YYYY-MM-DD) or after_date/before_date range.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "after_date": {"type": "string", "description": "Start date (YYYY-MM-DD) inclusive"},
    #             "before_date": {"type": "string", "description": "End date (YYYY-MM-DD) inclusive"},
    #             "on_date": {"type": "string", "description": "Exact date (YYYY-MM-DD), overrides range if provided"},
    #             "max_results": {"type": "integer", "default": 50}
    #         }
    #     }
    # },
    {
        "name": "search_emails",
        "description": "Search emails in MongoDB (synced Gmail). Tool results may include attachment metadata/previews (e.g., PDFs decoded from `compressed_preview`, images with `url`/`note`). IMPORTANT: when building the final chat response, attachment previews must be summarized in the `message` node; do NOT include an `attachments` field inside `data.emails[]`.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keyword or text to search in subject, body, or snippet.",
                },
                "is_unread": {
                    "type": "boolean",
                    "description": "Filter for unread emails only. Default is false.",
                },
                "from_email": {
                    "type": "string",
                    "description": "Filter by sender name or email address.",
                },
                "to_email": {
                    "type": "string",
                    "description": "Filter by recipient name or email address.",
                },
                "start_date": {
                    "type": "string",
                    "description": "Start date (YYYY-MM-DD or full RFC3339 timestamp) to filter emails from.",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date (YYYY-MM-DD or full RFC3339 timestamp) to filter emails until.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return. Overrides max_results if provided.",
                    "default": 10,
                },
            },
        },
    },
    {
        "name": "search_sent_emails",
        "description": "Search or load Gmail messages directly via the Gmail API (not MongoDB). Use for sent mail and anything not stored in the synced inbox. Returns subject, headers, snippet, and full decoded body text. Either pass message_ids to fetch specific messages, OR omit message_ids and search: default scope is sent mail (in:sent) plus optional gmail_query using Gmail operators (from:, to:, subject:, after:YYYY/MM/DD, before:, has:attachment, is:unread, label:, etc.). Use scope 'all' with gmail_query to search the whole mailbox without forcing in:sent.",
        "parameters": {
            "type": "object",
            "properties": {
                "message_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional Gmail message ids to load directly (full body). When set, search parameters are ignored. Max count is limited by max_results.",
                },
                "gmail_query": {
                    "type": "string",
                    "description": "Gmail search string (q). Combined with scope: for scope 'sent' this is appended after in:sent. For scope 'all' this is the full query (defaults to in:inbox if empty).",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max messages to return (search hits or id fetches).",
                    "default": 10,
                },
                "scope": {
                    "type": "string",
                    "enum": ["sent", "all"],
                    "description": "sent: restrict to Sent (in:sent) plus gmail_query. all: gmail_query only, or in:inbox if gmail_query empty.",
                    "default": "sent",
                },
            },
        },
    },
    # {
    #     "name": "get_unread_emails",
    #     "description": "Get unread emails directly from Gmail API (not from MongoDB). Use this specifically when user asks for 'unread emails'.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "max_results": {
    #                 "type": "integer",
    #                 "description": "Maximum number of unread emails to return.",
    #                 "default": 10,
    #             }
    #         },
    #     },
    # },
    # {
    #     "name": "get_unread_emails_db",
    #     "description": "Get unread emails directly from MongoDB (not from Gmail API). Use this specifically when user asks for 'unread emails'.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "max_results": {
    #                 "type": "integer",
    #                 "description": "Maximum number of unread emails to return.",
    #                 "default": 10,
    #             }
    #         },
    #     },
    # },
    # {
    #     "name": "get_starred_emails",
    #     "description": "Get starred emails directly from MongoDB. Use this specifically when user asks for 'starred emails'.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "max_results": {
    #                 "type": "integer",
    #                 "description": "Maximum number of starred emails to return.",
    #                 "default": 10,
    #             }
    #         },
    #     },
    # },
    # {
    #     "name": "get_emails_from",
    #     "description": "Get emails from a specific sender directly from MongoDB. Use this specifically when user asks for 'emails from <sender>'.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "sender": {
    #                 "type": "string",
    #                 "description": "Email address or name of the sender to filter emails by."
    #             },
    #             "max_results": {
    #                 "type": "integer",
    #                 "description": "Maximum number of emails to return from the given sender.",
    #                 "default": 10
    #             }
    #         },
    #         "required": ["sender"]
    #     },
    # },
    # {
    #     "name": "get_emails_to",
    #     "description": "Get emails sent to a specific recipient directly from MongoDB. Use this specifically when user queries contain email sent to <recipient> or <name>.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "recipient": {
    #                 "type": "string",
    #                 "description": "Email address or name of the recipient to filter emails by."
    #             },
    #             "max_results": {
    #                 "type": "integer",
    #                 "description": "Maximum number of emails to return to the given recipient.",
    #                 "default": 10
    #             }
    #         },
    #         "required": ["recipient"]
    #     },
    # },
    {
        "name": "draft_email",
        "description": "Create or edit an email draft without sending it. Default mode is to create a new draft. When mode='edit', update an existing draft by its draft_id. Supports both plain text and HTML formats. Use body_text for plain text and body_html for HTML content. If both are provided, the email will be created as multipart/alternative.",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Email subject"},
                "body": {"type": "string", "description": "Email body content (legacy parameter, used if body_text not provided)"},
                "body_text": {"type": "string", "description": "Plain text email body (optional, falls back to body if not provided)"},
                "body_html": {"type": "string", "description": "HTML email body (optional). If provided along with body_text, creates a multipart/alternative message"},
                "cc": {"type": "string", "description": "Carbon copy recipients (optional)"},
                "bcc": {"type": "string", "description": "Blind carbon copy recipients (optional)"},
                "mode": {
                    "type": "string",
                    "enum": ["create", "edit"],
                    "description": "Whether to create a new draft ('create') or edit an existing one ('edit'). Defaults to 'create'.",
                    "default": "create"
                },
                "draft_id": {
                    "type": "string",
                    "description": "ID of the existing Gmail draft to edit when mode='edit'."
                },
            },
            "required": ["to", "subject"],
        },
    },
    {
        "name": "list_email_drafts",
        "description": "Search/list Gmail drafts directly from Gmail API (not Mongo). Supports keyword and Gmail query filters over drafts (internally uses in:drafts search).",
        "parameters": {
            "type": "object",
            "properties": {
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of drafts to list.",
                    "default": 10,
                },
                "query": {
                    "type": "string",
                    "description": "Free-text keyword search inside drafts.",
                },
                "from_email": {
                    "type": "string",
                    "description": "Filter drafts by sender.",
                },
                "to_email": {
                    "type": "string",
                    "description": "Filter drafts by recipient.",
                },
                "subject": {
                    "type": "string",
                    "description": "Filter drafts by subject terms.",
                },
                "has_attachment": {
                    "type": "boolean",
                    "description": "Only drafts with attachments.",
                },
                "is_unread": {
                    "type": "boolean",
                    "description": "Include unread drafts only.",
                },
                "start_date": {
                    "type": "string",
                    "description": "Optional start date (YYYY-MM-DD), mapped to Gmail after: query.",
                },
                "end_date": {
                    "type": "string",
                    "description": "Optional end date (YYYY-MM-DD), mapped to Gmail before: query.",
                },
                "gmail_query": {
                    "type": "string",
                    "description": "Raw Gmail query fragment to append (e.g. label:^smartlabel_personal has:attachment).",
                },
            },
        },
    },
    {
        "name": "get_email_draft",
        "description": "Get full details of a single Gmail draft by its draft_id directly from Gmail (not Mongo). Use this when editing or inspecting a specific draft.",
        "parameters": {
            "type": "object",
            "properties": {
                "draft_id": {
                    "type": "string",
                    "description": "Gmail draft ID (e.g., 'r-...') returned from draft_email or list_email_drafts.",
                }
            },
            "required": ["draft_id"],
        },
    },
    {
        "name": "list_available_labels",
        "description": "List all Gmail labels available in the user's account.",
        "parameters": {"type": "object", "properties": {}},
    },
    # {
    #     "name": "mark_message_read",
    #     "description": "Mark a Gmail message as read.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "message_id": {
    #                 "type": "string",
    #                 "description": "The ID of the Gmail message to mark as read.",
    #             }
    #         },
    #         "required": ["message_id"],
    #     },
    # },
    # {
    #     "name": "add_label_to_message",
    #     "description": "Add a label to a Gmail message.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "message_id": {
    #                 "type": "string",
    #                 "description": "The ID of the Gmail message.",
    #             },
    #             "label_id": {
    #                 "type": "string",
    #                 "description": "The ID of the Gmail label to add.",
    #             },
    #         },
    #         "required": ["message_id", "label_id"],
    #     },
    # },
    # {
    #     "name": "remove_label_from_message",
    #     "description": "Remove a label from a Gmail message.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "message_id": {
    #                 "type": "string",
    #                 "description": "The ID of the Gmail message.",
    #             },
    #             "label_id": {
    #                 "type": "string",
    #                 "description": "The ID of the Gmail label to remove.",
    #             },
    #         },
    #         "required": ["message_id", "label_id"],
    #     },
    # },
    {
        "name": "get_emails",
        "description": "Retrieve full email rows from MongoDB by message id. Each email includes `attachments` when present (same shape as search_emails: optional `extracted_text_preview` for PDFs, `url`/`note` for images).",
        "parameters": {
            "type": "object",
            "properties": {
                "message_ids": {
                    "type": "array",
                    "description": "List of Gmail message IDs.",
                    "items": {"type": "string"},
                }
            },
            "required": ["message_ids"],
        },
    },
    # {
    #     "name": "get_email_context",
    #     "description": "Fetch extra AI-generated correlation information for email IDs returned from search_emails. This looks up the email IDs in a separate context collection and returns any additional insights like tasks, priorities, projects, collaborators, cross-tool links (Teams, Slack), and events that were extracted from those emails. Use this AFTER search_emails/get_emails to enrich the email data with correlation context.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "email_ids": {
    #                 "type": "array",
    #                 "description": "List of email message IDs to look up context for. These are the message_id values returned from search_emails or get_emails.",
    #                 "items": {"type": "string"},
    #             },
    #             "include_embeddings": {
    #                 "type": "boolean",
    #                 "description": "Whether to include the embedding vectors in the response. Default is false. Usually not needed.",
    #                 "default": False,
    #             }
    #         },
    #         "required": ["email_ids"],
    #     },
    # },
    {
        "name": "get_latest_briefing",
        "description": "Fetch the latest AI-generated briefing for a specific tool that summarizes the user's recent data. This briefing provides a high-level overview without querying individual items. Supports: gmail (emails), calendar (events/meetings), docs (Google Docs), sheets (Google Sheets), slides (Google Slides), trello (tasks/cards), slack (messages/channels). Use this when the user asks for a summary, overview, or briefing of their data from any of these tools.",
        "parameters": {
            "type": "object",
            "properties": {
                "tool_name": {
                    "type": "string",
                    "description": "Name of the tool to fetch briefing for. Options: 'gmail', 'calendar', 'docs', 'sheets', 'slides', 'trello', 'slack'. Default is 'gmail'.",
                    "enum": ["gmail", "calendar", "docs", "sheets", "slides", "trello", "slack"],
                    "default": "gmail",
                },
                "include_metadata": {
                    "type": "boolean",
                    "description": "Whether to include metadata like user preferences and timestamps. Default is true.",
                    "default": True,
                }
            },
            "required": [],
        },
    },
    {
        "name": "vector_context_search",
        "description": "Perform semantic vector search across ALL tool context collections to find content related to keywords from the user's query. This searches across the entire workspace (Gmail, Slack, Calendar, Docs, Sheets, Slides, Trello, Notion) in a single search. This uses AI embeddings to find semantically similar content (not just keyword matches) across all platforms. Use this when the user asks about topics, concepts, or wants to find related information across their workspace. The search understands meaning and context, so it can find relevant content even if exact keywords don't match. Results are grouped by platform, allowing you to inform the user about related content found in different tools.",
        "parameters": {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "string",
                    "description": "Keywords or search query from the user's prompt. Extract the main topic, concept, or question the user is asking about. Can be a phrase or sentence describing what they're looking for.",
                },
                "tool": {
                    "type": "string",
                    "description": "Optional tool hint. If provided, the search will still search all tools but may prioritize this one. Options: 'gmail', 'slack', 'calendar', 'docs' (or 'gdocs'), 'sheets' (or 'gsheets'), 'slides' (or 'gslides'), 'trello', 'notion' (or 'notiondocs'). If not provided, searches all available tools.",
                    "enum": ["gmail", "slack", "calendar", "docs", "gdocs", "sheets", "gsheets", "slides", "gslides", "trello", "notion", "notiondocs"],
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return per tool. Default is 10. Total results may be higher since it searches all tools.",
                    "default": 10,
                },
                "min_similarity": {
                    "type": "number",
                    "description": "Minimum similarity score threshold (0.0 to 1.0). Higher values return only very similar results. Default uses system threshold (0.30).",
                }
            },
            "required": ["keywords"],
        },
    },
    {
        "name": "download_attachments",
        "description": "Download all attachments from a given email.",
        "parameters": {
            "type": "object",
            "properties": {
                "message_id": {
                    "type": "string",
                    "description": "The ID of the email message containing attachments.",
                }
            },
            "required": ["message_id"],
        },
    },
    {
        "name": "update_email",
        "description": "Update email properties like star, read status, labels, trash, archive, and more. This is a unified function that handles all email modification actions.",
        "parameters": {
            "type": "object",
            "properties": {
                "message_id": {
                    "type": "string",
                    "description": "The Gmail message ID to update.",
                },
                "action": {
                    "type": "string",
                    "description": "Action to perform on the email. Options: 'star', 'unstar', 'read', 'unread', 'add_label', 'remove_label', 'trash', 'untrash', 'archive', 'unarchive', 'important', 'unimportant', 'spam', 'not_spam'",
                    "enum": ["star", "unstar", "read", "unread", "add_label", "remove_label", "trash", "untrash", "archive", "unarchive", "important", "unimportant", "spam", "not_spam"],
                },
                "label_id": {
                    "type": "string",
                    "description": "The Gmail label ID (required only for 'add_label' or 'remove_label' actions). Use list_available_labels to get label IDs.",
                },
            },
            "required": ["message_id", "action"],
        },
    },
    # {
    #     "name": "star_email",
    #     "description": "Star an email by its message ID.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "message_id": {
    #                 "type": "string",
    #                 "description": "The Gmail message ID to star.",
    #             }
    #         },
    #         "required": ["message_id"],
    #     },
    # },
    # {
    #     "name": "unstar_email",
    #     "description": "Remove star from an email by its message ID.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "message_id": {
    #                 "type": "string",
    #                 "description": "The Gmail message ID to unstar.",
    #             }
    #         },
    #         "required": ["message_id"],
    #     },
    # },
    # {
    #     "name": "delete_email",
    #     "description": "Move a Gmail message to trash by message ID.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "message_id": {
    #                 "type": "string",
    #                 "description": "The Gmail message ID to delete.",
    #             }
    #         },
    #         "required": ["message_id"],
    #     },
    # },
    # {
    #     "name": "delete_gmail_label",
    #     "description": "Delete an existing Gmail label",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "label_id": {
    #                 "type": "string",
    #                 "description": "The ID of the Gmail label to delete",
    #             }
    #         },
    #         "required": ["label_id"],
    #     },
    # },
    # Calendar function definitions
    {
        "name": "create_event",
        "description": "Create a Google Calendar event (with optional Google Meet). If the user wants a post-meeting transcript, set enable_transcript=true only after they explicitly confirm.",
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
                "attendees": {
                    "oneOf": [
                        {"type": "array", "items": {"type": "string"}, "description": "List of attendee email addresses"},
                        {"type": "string", "description": "Comma-separated list of attendee email addresses (e.g., 'email1@example.com,email2@example.com')"}
                    ],
                    "description": "Attendee email addresses. Can be provided as an array or comma-separated string."
                },
                "enable_transcript": {
                    "type": "boolean",
                    "description": "If true, schedule the workspace meeting notetaker for this event's Meet link after creation. Only set when the user clearly opted in.",
                    "default": False,
                },
                "transcript_mode": {
                    "type": "string",
                    "description": "Transcription quality vs latency when enable_transcript is true.",
                    "enum": ["prioritize_accuracy", "prioritize_low_latency"],
                    "default": "prioritize_accuracy",
                },
            },
            "required": ["summary", "start_time", "end_time"],
        },
    },
    {
        "name": "get_event",
        "description": "Get Google Calendar event details",
        "parameters": {
            "type": "object",
            "properties": {"event_id": {"type": "string"}},
            "required": ["event_id"],
        },
    },
    {
        "name": "update_event",
        "description": "Update an existing Google Calendar event by ID. Provide only the fields you want to change.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The ID of the calendar event to update."},
                "summary": {"type": "string", "description": "New event title."},
                "start_time": {"type": "string", "description": "Start time in 'YYYY-MM-DD HH:MM' or RFC3339 format."},
                "end_time": {"type": "string", "description": "End time in 'YYYY-MM-DD HH:MM' or RFC3339 format."},
                "description": {"type": "string", "description": "Event description."},
                "attendees": {
                    "oneOf": [
                        {"type": "array", "items": {"type": "string"}, "description": "List of attendee email addresses"},
                        {"type": "string", "description": "Comma-separated list of attendee email addresses (e.g., 'email1@example.com,email2@example.com')"}
                    ],
                    "description": "Attendee email addresses. Can be provided as an array or comma-separated string."
                },
                "location": {"type": "string", "description": "Event location."}
            },
            "required": ["event_id"],
        },
    },
    {
        "name": "search_calendar_events",
        "description": "Search calendar events by attendee email, date, or date range. Use 'date' for a single day, or 'start' and 'end' for a date range.",
        "parameters": {
            "type": "object",
            "properties": {
                "email": {"type": "string", "description": "Attendee email address"},
                "date": {
                    "type": "string",
                    "description": "Single event date in YYYY-MM-DD format (use this OR start/end range)",
                },
                "start": {
                    "type": "string",
                    "description": "Start date for date range search in YYYY-MM-DD format",
                },
                "end": {
                    "type": "string",
                    "description": "End date for date range search in YYYY-MM-DD format",
                },
                "query": {
                    "type": "string",
                    "description": "Text query to search in event details",
                },
                "max_results": {
                    "type": "integer",
                    "default": 50,
                    "description": "Maximum number of results to return",
                },
                "limit": {
                    "type": "integer",
                    "description": "Optional override for max_results. If provided and > 0, it limits the number of results.",
                },
            },
        },
    },
    {
        "name": "delete_events",
        "description": "Delete Google Calendar events by attendee email and/or event date",
        "parameters": {
            "type": "object",
            "properties": {
                "email": {"type": "string", "description": "Attendee email"},
                "date": {
                    "type": "string",
                    "description": "Event date in YYYY-MM-DD format",
                },
            },
        },
    },
    {
        "name": "query_events",
        "description": "Search calendar events using the user's query as-is.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keyword or text to search in event fields.",
                },
                "start": {
                    "type": "string",
                    "description": "Start date (YYYY-MM-DD or full RFC3339) for filtering events.",
                },
                "end": {
                    "type": "string",
                    "description": "End date (YYYY-MM-DD or full RFC3339) for filtering events.",
                },
                "email": {
                    "type": "string",
                    "description": "Filter by attendee/organizer/creator email.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return. Overrides max_results if provided.",
                    "default": 10,
                },
            },
            "required": [],
        },
    },
    # {
    #     "name": "get_calendar_context",
    #     "description": "Fetch extra AI-generated correlation information for calendar event IDs returned from search_calendar_events or query_events. Returns additional insights like brief descriptions, change summaries, Slack references, and referenced documents extracted from those events.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "event_ids": {
    #                 "type": "array",
    #                 "description": "List of calendar event IDs to look up context for. These are the event IDs returned from search_calendar_events or query_events.",
    #                 "items": {"type": "string"},
    #             },
    #             "include_embeddings": {
    #                 "type": "boolean",
    #                 "description": "Whether to include the embedding vectors in the response. Default is false.",
    #                 "default": False,
    #             }
    #         },
    #         "required": ["event_ids"],
    #     },
    # },
    {
        "name": "query_docs",
        "description": "Unified Google Docs search using text with optional owner/date filters.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keyword or text to search in doc fields.",
                },
                "owner": {
                    "type": "string",
                    "description": "Filter by owner (name or email).",
                },
                "start_date": {
                    "type": "string",
                    "description": "Start date (YYYY-MM-DD) for created date filtering.",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date (YYYY-MM-DD) for created date filtering.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return. Overrides max_results if provided.",
                    "default": 10,
                },
                "image_analysis": {
                    "type": "boolean",
                    "description": "If true, docs search is explicitly for image analysis and follow-up calls to get_document_content may include image data. Usually set only when the user asks to analyze images in documents.",
                    "default": False,
                },
            },
            "required": [],
        },
    },
    # {
    #     "name": "get_docs_context",
    #     "description": "Fetch extra AI-generated correlation information for Google Docs document IDs returned from query_docs. Returns additional insights like brief descriptions, change summaries, comments, and edit history extracted from those documents.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "document_ids": {
    #                 "type": "array",
    #                 "description": "List of Google Docs document IDs to look up context for. These are the document IDs returned from query_docs.",
    #                 "items": {"type": "string"},
    #             },
    #             "include_embeddings": {
    #                 "type": "boolean",
    #                 "description": "Whether to include the embedding vectors in the response. Default is false.",
    #                 "default": False,
    #             }
    #         },
    #         "required": ["document_ids"],
    #     },
    # },
    {
        "name": "get_events",
        "description": "Retrieve the full content of one or more calendar events.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_ids": {
                    "type": "array",
                    "description": "List of calendar event IDs.",
                    "items": {"type": "string"},
                }
            },
            "required": ["event_ids"],
        },
    },
    {
        "name": "get_meeting_transcript",
        "description": "Fetch meeting transcript data from meet_summaries for summarization/quoting. Returns transcript identity fields (e.g. meet_summary_id, transcript_id) so the exact stored transcript can be referenced. Prefer transcript_summary when available; spoken_transcript is fallback.",
        "parameters": {
            "type": "object",
            "properties": {
                "calendar_id": {
                    "type": "string",
                    "description": "Google Calendar event id for the meeting.",
                },
                "meeting_url": {
                    "type": "string",
                    "description": "Google Meet URL if calendar_id is unknown.",
                },
                "max_transcript_chars": {
                    "type": "integer",
                    "description": "Max characters of spoken_transcript to return (truncates if longer).",
                    "default": 120000,
                },
                "prefer_api": {
                    "type": "boolean",
                    "description": "If true, try workspace GET /meet/transcript before Mongo.",
                    "default": False,
                },
            },
            "required": [],
        },
    },
    {
        "name": "create_gmail_label",
        "description": "Create a new Gmail label",
        "parameters": {
            "type": "object",
            "properties": {
                "label_name": {
                    "type": "string",
                    "description": "The name of the label to create",
                }
            },
            "required": ["label_name"],
        },
    },
    # # Jira function definitions
    # {
    #     "name": "list_projects",
    #     "description": "List all Jira projects",
    #     "parameters": {"type": "object", "properties": {}},
    # },
    # {
    #     "name": "list_issues",
    #     "description": "List all issues for a given Jira project",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {"project_key": {"type": "string"}},
    #         "required": ["project_key"],
    #     },
    # },
    # {
    #     "name": "transition_issue",
    #     "description": "Transition a Jira issue to a new status",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "issue_key": {"type": "string"},
    #             "transition_name": {"type": "string"},
    #         },
    #         "required": ["issue_key", "transition_name"],
    #     },
    # },
    # # Salesforce function definitions
    # {
    #     "name": "create_lead",
    #     "description": "Create a new lead in Salesforce",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "first_name": {"type": "string"},
    #             "last_name": {"type": "string"},
    #             "company": {"type": "string"},
    #             "email": {"type": "string"},
    #             "phone": {"type": "string"},
    #             "status": {"type": "string", "default": "Open - Not Contacted"},
    #             "lead_source": {"type": "string", "default": "Web"},
    #         },
    #         "required": ["first_name", "last_name", "company"],
    #     },
    # },
    # {
    #     "name": "update_lead_status",
    #     "description": "Update the status of a Salesforce lead",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "first_name": {"type": "string"},
    #             "last_name": {"type": "string"},
    #             "status": {"type": "string"},
    #         },
    #         "required": ["first_name", "last_name", "status"],
    #     },
    # },
    # {
    #     "name": "delete_lead",
    #     "description": "Delete a Salesforce lead",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "first_name": {"type": "string"},
    #             "last_name": {"type": "string"},
    #         },
    #         "required": ["first_name", "last_name"],
    #     },
    # },
    # {
    #     "name": "get_all_leads",
    #     "description": "Retrieve all Salesforce leads",
    #     "parameters": {"type": "object", "properties": {}},
    # },
    # {
    #     "name": "add_event",
    #     "description": "Add an event to Salesforce",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "subject": {"type": "string"},
    #             "start_time": {"type": "string"},
    #             "end_time": {"type": "string"},
    #             "first_name": {"type": "string"},
    #             "last_name": {"type": "string"},
    #         },
    #         "required": [
    #             "subject",
    #             "start_time",
    #             "end_time",
    #             "first_name",
    #             "last_name",
    #         ],
    #     },
    # },
    # {
    #     "name": "get_lead",
    #     "description": "Retrieve a Salesforce lead by ID",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {"lead_id": {"type": "string"}},
    #         "required": ["lead_id"],
    #     },
    # },
    # Slack function definitions
    {
        "name": "get_channels",
        "description": "Retrieve a list of all Slack channels",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "send_slack_messages",
        "description": "Send a message to a Slack channel. You can provide either the channel ID (like C01ABC123) or the channel name (like #general or sales-team).",
        "parameters": {
            "type": "object",
            "properties": {
                "channel": {
                    "type": "string",
                    "description": "The name or ID of the Slack channel",
                },
                "message": {
                    "type": "string",
                    "description": "The message content to send",
                },
            },
            "required": ["channel", "message"],
        },
    },
    {
        "name": "get_channel_messages",
        "description": "Fetch recent messages from a Slack PUBLIC or PRIVATE channel (NOT for direct messages/DMs). Use channel ID (like C08LTHJKAH4) or channel name (like #general). DO NOT use this for direct messages with users - use get_dm_messages instead.",
        "parameters": {
            "type": "object",
            "properties": {
                "channel": {
                    "type": "string",
                    "description": "Slack channel ID (like C08LTHJKAH4) or channel name (like #general). NOT a user name - use get_dm_messages for user conversations.",
                },
                "limit": {"type": "integer", "default": 10},
                "order": {"type": "string", "enum": ["asc", "desc"], "default": "desc"},
            },
            "required": ["channel"],
        },
    },
    {
        "name": "list_users",
        "description": "List all Slack users in the workspace",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_channel_members",
        "description": "Get members of a specific Slack channel",
        "parameters": {
            "type": "object",
            "properties": {"channel_id": {"type": "string", "description": "Channel ID"}},
            "required": ["channel_id"],
        },
    },
    # {
    #     "name": "get_channel_info",
    #     "description": "Retrieve basic metadata about a Slack channel such as name, creator, creation time, and archive status.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "channel_id": {
    #                 "type": "string",
    #                 "description": "The ID of the Slack channel to fetch info for (e.g., C01ABC123).",
    #             }
    #         },
    #         "required": ["channel_id"],
    #     },
    # },
    # NOTE: get_channel_info is commented out because the underlying function is not imported
    {
        "name": "get_user_info",
        "description": "Get user profile information for the authenticated user",
        "parameters": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "Optional channel parameter (not currently used)"}
            },
            "required": [],
        },
    },
    {
        "name": "create_channel",
        "description": "Create a new Slack channel",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the new channel"},
                "is_private": {
                    "type": "boolean",
                    "description": "Set to true for private channel",
                },
            },
            "required": ["name"],
        },
    },
    # {
    #     "name": "archive_channel",
    #     "description": "Archive a Slack channel",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {"channel": {"type": "string", "description": "Channel ID"}},
    #         "required": ["channel"],
    #     },
    # },
    {
        "name": "invite_user_to_channel",
        "description": "Invite a user to a channel",
        "parameters": {
            "type": "object",
            "properties": {"channel": {"type": "string"}, "user": {"type": "string"}},
            "required": ["channel", "user", "token"],
        },
    },
    # {
    #     "name": "kick_user_from_channel",
    #     "description": "Remove a user from a channel",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {"channel": {"type": "string"}, "user": {"type": "string"}},
    #         "required": ["channel", "user"],
    #     },
    # },
    {
        "name": "pin_message",
        "description": "Pin a message in a channel",
        "parameters": {
            "type": "object",
            "properties": {
                "channel": {"type": "string"},
                "timestamp": {"type": "string", "description": "Message timestamp"},
            },
            "required": ["channel", "timestamp"],
        },
    },
    # {
    #     "name": "unpin_message",
    #     "description": "Unpin a message in a channel",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "channel": {"type": "string"},
    #             "timestamp": {"type": "string", "description": "Message timestamp"},
    #         },
    #         "required": ["channel", "timestamp"],
    #     },
    # },
    # {
    #     "name": "react_to_message",
    #     "description": "Add a reaction (emoji) to a message",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "channel": {"type": "string"},
    #             "timestamp": {"type": "string"},
    #             "emoji": {"type": "string", "description": "Emoji name (no colons)"},
    #         },
    #         "required": ["channel", "timestamp", "emoji"],
    #     },
    # },
    # {
    #     "name": "open_dm_with_user",
    #     "description": "Open a direct message (DM) channel with a user",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "user": {
    #                 "type": "string",
    #                 "description": "The Slack username or real name of the user to open a DM with",
    #             }
    #         },
    #         "required": ["user"],
    #     },
    # },
    {
        "name": "send_dm",
        "description": "Send a direct message (DM) to a user. Use 'me' as the user parameter to send to the current user's own DM channel.",
        "parameters": {
            "type": "object",
            "properties": {
                "user": {
                    "type": "string",
                    "description": "The Slack username or real name of the recipient. Use 'me' to send to the current user's own DM channel (when user says 'send it to me' or 'send to me').",
                },
                "message": {
                    "type": "string",
                    "description": "The message text to send",
                },
            },
            "required": ["user", "message"],
        },
    },
    {
        "name": "reply_message",
        "description": "send a reply to a message",
        "parameters": {
            "type": "object",
            "properties": {
                "channel": {"type": "string"},
                "timestamp": {"type": "string"},
                "message": {
                    "type": "string",
                    "description": "The message text to send",
                },
            },
            "required": ["channel", "timestamp", "message"],
        },
    },
    {
        "name": "get_dm_messages",
        "description": "**USE THIS TOOL FOR DIRECT MESSAGES (DMs) WITH USERS.** Retrieve the latest messages from a direct message (DM) conversation with a user. Use this when the user asks to fetch, show, review, or get messages from a DM conversation with a person (e.g., 'messages from Amit', 'conversation with John', 'my chat with Sarah'). DO NOT use get_channel_messages for user names - always use get_dm_messages when the user mentions a person's name.",
        "parameters": {
            "type": "object",
            "properties": {
                "user": {
                    "type": "string",
                    "description": "The Slack username or real name of the user (e.g., 'Amit Chowdhary', 'John Doe'). Use 'me' to get messages from the current user's own DM channel.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of recent messages to retrieve (default is 10)",
                },
            },
            "required": ["user"],
        },
    },
    # {
    #     "name": "get_slack_context",
    #     "description": "Fetch AI-generated contextual correlation information for Slack channel IDs. Returns summaries, key points, action items, collaborators, and topic tags extracted from recent channel conversations (last 7 days). Use this AFTER getting channel messages or searching channels to enrich the data with discussion context.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "channel_ids": {
    #                 "type": "array",
    #                 "description": "List of Slack channel IDs to look up context for. These are the channel IDs returned from get_channels or get_channel_messages.",
    #                 "items": {"type": "string"},
    #             },
    #             "lookback_days": {
    #                 "type": "integer",
    #                 "description": "Number of days to look back for channel context. Default is 7 days.",
    #                 "default": 7,
    #             },
    #             "include_embeddings": {
    #                 "type": "boolean",
    #                 "description": "Whether to include the embedding vectors in the response. Default is false.",
    #                 "default": False,
    #             }
    #         },
    #         "required": ["channel_ids"],
    #     },
    # },
    # {
    #     "name": "upload_file",
    #     "description": "Upload a file to a Slack channel",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "channel": {"type": "string"},
    #             "filepath": {"type": "string"},
    #             "title": {"type": "string"},
    #         },
    #         "required": ["channel", "filepath"],
    #     },
    # },
    # Google Docs function definitions
    # {
    #     "name": "get_user_documents",
    #     "description": "Get a list of the user's recent Google Docs files.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "limit": {
    #                 "type": "integer",
    #                 "description": "Maximum number of documents to return (default: 10)",
    #             }
    #         },
    #         "required": [],
    #     },
    # },
    {
        "name": "get_document_content",
        "description": "Fetch full content and metadata of one or more Google Docs by their IDs (Mongo-backed, fast). Use for reading documents. For editing, use update_document which fetches structure (image_positions) automatically. if asked for image set image_analysis to True",
        "parameters": {
            "type": "object",
            "properties": {
                "document_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of Google Doc IDs to retrieve. Can fetch multiple documents in one call for better performance.",
                },
                "token": {
                    "type": "string",
                    "description": "User authentication token (optional, usually auto-injected)",
                },
                "image_analysis": {
                    "type": "boolean",
                    "description": "If true, also fetch image data (as base64) for documents that contain images. Use only when the user explicitly requests image analysis of a document.",
                    "default": False,
                },
                "get_formatting": {
                "type": "boolean",
                "description": "Optional. If true, returns structured paragraphs with startIndex, endIndex, and style metadata for editing. If false (default), returns plain text.",
                "default": False
                }
            },
            "required": ["document_ids"],
        },
    },
    {
        "name": "create_document",
        "description": "Create a new Google Doc with an optional initial text.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Title of the document"},
                "initial_text": {
                    "type": "string",
                    "description": "Initial text to insert in the document",
                },
            },
            "required": ["title"],
        },
    },
    {
        "name": "generate_doc_from_link",
        "description": "Generate a Google Doc by summarizing/structuring content from a provided link using Bedrock, producing clean HTML, and creating the Doc.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Title of the new document"},
                "link": {
                    "type": "string",
                    "description": "Reference URL to base the content on",
                },
                "prompt": {
                    "type": "string",
                    "description": "Instruction for what to produce (e.g., summary, proposal)",
                },
                "tone": {
                    "type": "string",
                    "description": "Writing tone",
                    "default": "Professional",
                },
                "style": {
                    "type": "string",
                    "description": "Writing style",
                    "default": "Concise",
                },
            },
            "required": ["title", "link", "prompt"],
        },
    },
    {
        "name": "update_document_text",
        "description": "Update a Google Doc by index. Automatically fetches document structure before updating. When index is unknown, call with document_id and text='' (omit index) to get document_structure with image_positions; then call again with index (and end_index for range replace). Inserts text at index, or replaces [index, end_index) if end_index is set.",
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "string",
                    "description": "ID of the document to update",
                },
                
                "index": {
                    "type": "integer",
                    "description": "Start index (1-based) of the source range. Used for text deletion or formatting. This range is NOT the insertion location when target_index is provided."
                },
                "text": {
                    "type": "string",
                    "description": "Optional text content to insert. If target_index is provided, text is inserted at target_index. Otherwise text is inserted at index. If empty or null, no text insertion happens. Deletion will occur only when delete=true."
                },
                "end_index": {
                    "type": "integer",
                    "description": "Optional end index (1-based) of the source range. Used together with index for deleting text or applying formatting. "
                },
                "target_index": {
                    "type": "integer",
                    "description": "Optional insertion anchor index (1-based). When provided, text will be inserted at target_index. The index and end_index will be used only for deletion or formatting of the original range."
                    },
                "operation": {
                    "type": "string",
                    "enum": [
                        "insert",
                        "replace",
                        "move",
                        "delete",
                        "format"
                    ],
                    "description": "Type of document edit to perform."
                    },
                "formatting": {
                    "type": "object",
                    "description": "Optional formatting instructions. Supports text formatting (bold, italic, underline, fontSize, fontFamily, color, bullet, highlight(text background color),quote) and paragraph formatting (namedStyleType, alignment)."
                    },
                "token": {
                    "type": "string",
                    "description": "User authentication token (optional, usually auto-injected)",
                },
            },
            "required": ["document_id","text","operation"],
        },
    },
    {
        "name": "update_document_image",
        "description": "Update image blocks in a Google Doc using image_id and known structural indexes returned by the document read tool. Supports moving images, deleting images, and inserting text before or after an image. This tool performs structural operations only and does not apply text formatting.",
        "parameters": {
            "type": "object",
            "properties": {
            "document_id": {
                "type": "string",
                "description": "ID of the document to update."
            },
            "image_id": {
                "type": "string",
                "description": "Unique image identifier returned by get_document_content."
            },
            "index": {
                "type": "integer",
                "description": "Current start index (1-based) of the image block."
            },
            "end_index": {
                "type": "integer",
                "description": "Current end index (1-based) of the image block."
            },
            "operation": {
                "type": "string",
                "enum": ["move","delete","insert_text_before","insert_text_after"],
                "description": "Type of structural image operation to perform."
            },
            "target_index": {
                "type": "integer",
                "description": "Target index (1-based) where the image should be moved. Required only for move operation."
            },
            "text": {
                "type": "string",
                "description": "Text content to insert before or after the image. Used only for insert_text_before or insert_text_after."
            },
            },
            "required": [
            "document_id", "image_id","index","end_index", "operation"]
        }
    },
    {
        "name": "update_document_table",
        "description": "Edit a table inside a Google Doc using structural table operations. All operations are based on table_start_index and optional row_index / column_index.",
        "parameters": {
            "type": "object",
            "properties": {

            "document_id": {
                "type": "string",
                "description": "ID of the Google document"
            },

            "operation": {
                "type": "string",
                "enum": [
                "insert_table",
                "delete_table",
                "add_row",
                "delete_row",
                "add_column",
                "delete_column",
                "update_cell",
                ],
                "description": "Type of table structural operation"
            },

            "table_start_index": {
                "type": "integer",
                "description": "Start index of the table (required for all operations except insert_table)"
            },

            "row_index": {
                "type": "integer",
                "description": "Zero-based row index (required for row operations and update_cell)"
            },

            "column_index": {
                "type": "integer",
                "description": "Zero-based column index (required for column operations and update_cell)"
            },

            "rows": {
                "type": "integer",
                "description": "Number of rows (required for insert_table)"
            },

            "columns": {
                "type": "integer",
                "description": "Number of columns (required for insert_table)"
            },

            "text": {
                "type": "string",
                "description": "Text content to write inside a cell (required for update_cell)"
            },

            "target_index": {
                "type": "integer",
                "description": "Target insertion index in document (required for move_table)"
            },

            "token": {
                "type": "string",
                "description": "User authentication token"
            }

            },
            "required": [
            "document_id",
            "operation"
            ]
        }
    },
    {
        "name": "get_document_table_content",
        "description": "Read full content of a specific table in a Google Doc using table_start_index returned by document reader.",
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "string",
                    "description": "ID of the document"
                },
                "table_start_index": {
                    "type": "integer",
                    "description": "Start index of table returned by get_document_content tool"
                },
                "token": {
                    "type": "string",
                    "description": "User auth token (auto injected usually)"
                }
            },
            "required": ["document_id", "table_start_index"]
        }
    },
    {
        "name": "delete_document",
        "description": "Move a document to trash by its ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "string",
                    "description": "The ID of the document to delete",
                }
            },
            "required": ["document_id"],
        },
    },
    {
        "name": "share_document",
        "description": "Share a document with a user by email and assign a role.",
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "string",
                    "description": "ID of the document to share",
                },
                "email": {
                    "type": "string",
                    "description": "Email of the user to share the document with",
                },
                "role": {
                    "type": "string",
                    "enum": ["reader", "commenter", "writer"],
                    "description": "Permission role to assign (default: writer)",
                },
            },
            "required": ["document_id", "email"],
        },
    },
    {
        "name": "add_document_comment",
        "description": "Add a top-level comment to a Google Doc, Sheet, or Slides file via the Drive API. Used for comment_reply actions and interactive tools.",
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "string",
                    "description": "The ID of the Google Doc, Sheet, or Slides file to comment on",
                },
                "text": {
                    "type": "string",
                    "description": "The comment text to add",
                },
            },
            "required": ["document_id", "text"],
        },
    },
    {
        "name": "search_in_document",
        "description": "Search for a keyword inside a Google Doc and return matching snippets.",
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "string",
                    "description": "The ID of the document to search in",
                },
                "keyword": {
                    "type": "string",
                    "description": "The keyword to search for",
                },
            },
            "required": ["document_id", "keyword"],
        },
    },
    # {
    #     "name": "search_docs",
    #     "description": "Search Google Docs files using MongoDB (text, vector, date range).",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "query": {
    #                 "type": "string",
    #                 "description": "The search query to find documents.",
    #             },
    #             "owner": {
    #                 "type": "string",
    #                 "description": "Filter by document owner email.",
    #             },
    #             "after_date": {
    #                 "type": "string",
    #                 "description": "Filter documents created after this date (YYYY-MM-DD).",
    #             },
    #             "before_date": {
    #                 "type": "string",
    #                 "description": "Filter documents created before this date (YYYY-MM-DD).",
    #             },
    #             "max_results": {
    #                 "type": "integer",
    #                 "description": "Maximum number of documents to return.",
    #                 "default": 10,
    #             },
    #         },
    #         "required": ["query"],
    #     },
    # },
    {
        "name": "search_docs_by_date",
        "description": "Strict MongoDB date search for documents sorted by newest first. Provide either on_date (YYYY-MM-DD) or after_date/before_date range.",
        "parameters": {
            "type": "object",
            "properties": {
                "after_date": {
                    "type": "string",
                    "description": "Start date (YYYY-MM-DD) inclusive",
                },
                "before_date": {
                    "type": "string",
                    "description": "End date (YYYY-MM-DD) inclusive",
                },
                "on_date": {
                    "type": "string",
                    "description": "Exact date (YYYY-MM-DD), overrides range if provided",
                },
                "max_results": {"type": "integer", "default": 50},
            },
        },
    },
    {
        "name": "list_docs",
        "description": "Simple function to list documents in latest order (by created date descending). Takes no query, just returns docs sorted by newest first.",
        "parameters": {
            "type": "object",
            "properties": {"max_results": {"type": "integer", "default": 50}},
        },
    },
    {
        "name": "doc_history",
        "description": "Get metadata and edit history for a Google Docs document.",
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "string",
                    "description": "The ID of the document to get edit history for",
                }
            },
            "required": ["document_id"],
        },
    },
    # Google Sheets function definitions
    {
        "name": "list_sheets",
        "description": "List spreadsheet files accessible to the user from Google Drive.",
        "parameters": {
            "type": "object",
            "properties": {
                "page_size": {
                    "type": "integer",
                    "description": "Maximum number of sheets to return. Default is 20.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "create_sheet",
        "description": "Create a new blank Google Sheet.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Title of the spreadsheet"}
            },
            "required": ["title"],
        },
    },
    {
        "name": "read_sheet_data",
        "description": "Read data from a Google Sheet. Optionally specify a sheet name, column name(s), or range to filter results. If no parameters are provided, reads all sheets.",
        "parameters": {
            "type": "object",
            "properties": {
                "sheet_id": {
                    "type": "string",
                    "description": "The ID of the Google Sheet file to read from."
                },
                "sheet_name": {
                    "type": "string",
                    "description": "Optional. The name of the specific sheet (tab) to read. If omitted, all sheets will be read."
                },
                "column_name": {
                    "type": ["string", "array"],
                    "description": "Optional. One or more column names to filter data by."
                },
                "range": {
                    "type": "string",
                    "description": "Optional. A specific A1-style range (e.g., 'Sheet1!A1:D20'). If omitted, reads the full range automatically."
                },
                "range_": {
                    "type": "string",
                    "description": "Optional. Legacy parameter name for 'range'. Use 'range' instead."
                },
                "all_sheets_info": {
                    "type": "object",
                    "description": "Optional. Cached sheet metadata from gsheets_get_structure, used to avoid refetching."
                },
                "include_cells": {
                    "type": "boolean",
                    "description": "Optional. If true, returns each cell with its A1 cell reference. If false (default), returns only values.",
                    "default": False
                }
            },
            "required": ["sheet_id"],
        },
    },
    {
        "name": "update_sheet_data",
        "description": (
                "Add or update data in a Google Sheet. "
                "The LLM infers whether to append or update based on context — "
                "for example, 'add a new row' appends, while 'update the status cell' updates an existing value. "
                "For column mode, you can use ANY column name (e.g., 'Trello Link', 'Status', 'Due Date') — "
                "the system will automatically find the column or create it if it doesn't exist."
            ),
        "parameters": {
            "type": "object",
            "properties": {
                "sheet_id": {
                    "type": "string",
                    "description": "The ID of the Google Sheet to update."
                },
                "sheet_name": {
                    "type": "string",
                    "description": "The name of the specific sheet (tab) to modify."
                },
                "mode": {
                    "type": "string",
                    "enum": ["cell", "row", "column"],
                    "description": "Scope of the update — single cell, entire row, or column."
                },
                "target": {
                    "type": "string",
                    "description": (
                        "Optional. The target to modify. "
                        "For 'cell' mode: a cell reference like 'B4' or 'A1'. "
                        "For 'row' mode: a row number like '3' or '5'. "
                        "For 'column' mode: ANY column name (e.g., 'Trello Link', 'Status', 'Task Name') or a column letter like 'B'. "
                        "Column names are automatically resolved and created if missing. "
                        "If omitted, data will be appended as a new row/column."
                    )
                },
                "data": {
                    "type": ["string", "array", "object"],
                    "description": "The new data to write to the sheet. For column mode, provide a list of values (one per row)."
                }
            },
            "required": ["sheet_id", "sheet_name", "mode", "data"]
        }
    },
    # {
    #     "name": "write_sheet_data",
    #     "description": "Overwrite a range of cells in the spreadsheet with given values.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "sheet_id": {"type": "string", "description": "ID of the spreadsheet"},
    #             "range": {
    #                 "type": "string",
    #                 "description": "Cell range to write to (e.g. Sheet1!A1)",
    #             },
    #             "values": {
    #                 "type": "array",
    #                 "items": {"type": "array", "items": {"type": "string"}},
    #                 "description": "2D array of strings representing rows and columns",
    #             },
    #         },
    #         "required": ["sheet_id", "range", "values"],
    #     },
    # },
    # {
    #     "name": "append_sheet_data",
    #     "description": "Append rows to the end of a specified range or sheet.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "sheet_id": {"type": "string", "description": "ID of the spreadsheet"},
    #             "range": {
    #                 "type": "string",
    #                 "description": "Target range or sheet name (e.g. Sheet1)",
    #             },
    #             "values": {
    #                 "type": "array",
    #                 "items": {"type": "array", "items": {"type": "string"}},
    #                 "description": "2D array of strings to append",
    #             },
    #         },
    #         "required": ["sheet_id", "range", "values"],
    #     },
    # },
    {
        "name": "clear_sheet_range",
        "description": "Clear the content of a specific range in a spreadsheet.",
        "parameters": {
            "type": "object",
            "properties": {
                "sheet_id": {"type": "string", "description": "ID of the spreadsheet"},
                "range": {
                    "type": "string",
                    "description": "Range to clear (e.g. Sheet1!A1:C10)",
                },
            },
            "required": ["sheet_id", "range"],
        },
    },
    {
        "name": "add_new_tab",
        "description": "Add a new sheet/tab to an existing spreadsheet.",
        "parameters": {
            "type": "object",
            "properties": {
                "sheet_id": {"type": "string", "description": "ID of the spreadsheet"},
                "title": {"type": "string", "description": "Title of the new tab"},
            },
            "required": ["sheet_id", "title"],
        },
    },
    {
        "name": "delete_sheet_tab",
        "description": "Delete a tab from a spreadsheet by its sheet tab ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "sheet_id": {"type": "string", "description": "ID of the spreadsheet"},
                "sheet_tab_id": {
                    "type": "integer",
                    "description": "ID of the sheet tab to delete",
                },
            },
            "required": ["sheet_id", "sheet_tab_id"],
        },
    },
    {
        "name": "share_sheet",
        "description": "Share a spreadsheet with a user via email.",
        "parameters": {
            "type": "object",
            "properties": {
                "sheet_id": {"type": "string", "description": "ID of the spreadsheet"},
                "email": {
                    "type": "string",
                    "description": "Email address to share with",
                },
                "role": {
                    "type": "string",
                    "enum": ["reader", "commenter", "writer"],
                    "description": "Permission level to grant",
                },
            },
            "required": ["sheet_id", "email"],
        },
    },
    {
        "name": "search_sheets",
        "description": "Search Google Sheets files by title keyword.",
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "The keyword to search for in sheet titles.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of sheets to return.",
                },
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "sheet_history",
        "description": "Get metadata and edit history for a Google Sheets file.",
        "parameters": {
            "type": "object",
            "properties": {
                "sheet_id": {
                    "type": "string",
                    "description": "The ID of the Google Sheets file.",
                }
            },
            "required": ["sheet_id"],
        },
    },
    {
        "name": "add_sheet_comment",
        "description": "Add a top-level comment to a Google Sheet. The comment is posted as the currently authenticated user. Use for replying to or adding comments on spreadsheets.",
        "parameters": {
            "type": "object",
            "properties": {
                "spreadsheet_id": {
                    "type": "string",
                    "description": "The ID of the Google Sheet to comment on",
                },
                "text": {
                    "type": "string",
                    "description": "The comment text to add",
                },
            },
            "required": ["spreadsheet_id", "text"],
        },
    },
    {
        "name": "list_sheet_info",
        "description": "Get detailed structural metadata for a Google Sheets file, including sheet names, headers, and dimensions.",
        "parameters": {
            "type": "object",
            "properties": {
                "sheet_id": {
                    "type": "string",
                    "description": "The ID of the Google Sheets file.",
                }
            },
            "required": ["sheet_id"],
        },
    },
    {
        "name": "sheet_chart_metadata",
        "description": "Retrieve metadata for charts in a Google Sheets document or a specific sheet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sheet_id": {
                        "type": "string", 
                        "description": "ID of the spreadsheet."},
                    "sheet_name": {
                        "type": "string", 
                        "description": "Optional: name of the specific sheet to check for charts."}
                },
                "required": ["sheet_id"]
        }
    },
    {
        "name": "sheet_create_chart",
        "description": "Create a chart in a Google Sheet using A1 notation ranges for the data. Automatically places the chart in the first available space.",
            "parameters": {
            "type": "object",
            "properties": {
                "sheet_id": {
                    "type": "string",
                    "description": "The ID of the Google Sheets file where the chart will be created."
                },
                "sheet_name": {
                        "type": "string", 
                        "description": " name of the specific sheet to check for charts."
                },
                "chart_type": {
                    "type": "string",
                    "enum": ["COLUMN", "LINE", "BAR", "AREA", "PIE"],
                    "description": "The type of chart to create."
                },
                "x_range": {
                    "type": "string",
                    "description": "The A1 range for the X-axis data (e.g., 'Sheet1!A2:A10')."
                },
                "y_ranges": {
                    "type": "array",
                    "items": { "type": "string" },
                    "description": "A list of A1 ranges for the Y-axis data (e.g., ['Sheet1!B2:B10', 'Sheet1!C2:C10'])."
                },
                "title": {
                "type": "string",
                "description": "Optional chart title."
                }
            },
            "required": ["sheet_id", "sheet_name","chart_type", "x_range", "y_ranges"]
        }
    },
    {
        "name": "sheet_update_chart",
        "description": "Update an existing chart in Google Sheets. Use this to modify the title, type, or data ranges of an existing chart.",
        "parameters": {
            "type": "object",
            "properties": {
                "sheet_id": {
                    "type": "string",
                    "description": "The ID of the spreadsheet containing the chart."
                },
                "chart_id": {
                    "type": "integer",
                    "description": "The unique ID of the chart to update, from chart metadata."
                },
                "title": {
                    "type": "string",
                    "description": "Optional new title for the chart."
                },
                "chart_type": {
                    "type": "string",
                    "description": "Optional new chart type. Supported types: COLUMN, LINE, BAR, AREA, SCATTER, PIE, COMBO."
                },
                "x_range": {
                    "type": "string",
                    "description": "Optional new X-axis data range in A1 notation (e.g. 'Sheet1!A2:A20')."
                },
                "y_ranges": {
                    "type": "array",
                    "items": { "type": "string" },
                    "description": "Optional list of Y-axis data ranges in A1 notation (e.g. ['Sheet1!B2:B20'])."
                },
                "token": {
                    "type": "string",
                    "description": "Authentication token for Google Sheets API access."
                }
            },
            "required": ["sheet_id", "chart_id"]
        }
    },
    {
        "name": "sheet_create_pivot_table",
        "description": "Creates a pivot table in a Google Sheet using a specified source range, rows, columns, and value fields.",
        "parameters": {
            "type": "object",
            "properties": {
                "sheet_id": {
                    "type": "string",
                    "description": "The ID of the Google Spreadsheet."
                },
                "sheet_tab_id": {
                    "type": "integer",
                    "description": "The ID of the source sheet tab from which data will be pivoted."
                },
                "source_range": {
                    "type": "string",
                    "description": "The range in A1 notation to use as the pivot table source, e.g. 'Sheet1!A1:D100'."
                },
                "pivot_sheet_title": {
                    "type": "string",
                    "description": "The title of the new sheet where the pivot table will be created."
                },
                "rows": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "List of source column indices to use as pivot rows (0-based)."
                },
                "columns": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "List of source column indices to use as pivot columns (0-based)."
                },
                "values": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "column_index": {"type": "integer"},
                            "function": {
                                "type": "string",
                                "enum": ["SUM", "COUNT", "COUNTA", "AVERAGE", "MAX", "MIN"],
                                "description": "The aggregation function to apply (SUM, COUNT, COUNTA, AVERAGE, MAX, MIN). Use COUNTA to count text fields (like names, IDs, or categories), and COUNT only for numeric fields."
                                }
                        },
                        "required": ["column_index", "function"]
                    },
                    "description": "List of aggregation functions for pivot values, e.g. [{'column_index': 3, 'function': 'SUM'}]."
                },
            
            },
            "required": ["sheet_id", "sheet_tab_id", "source_range", "pivot_sheet_title", "rows", "columns", "values"]
        }
    },
    # Google Slides function definitions
    {
        "name": "list_slides",
        "description": "List all Google Slides presentations the user has access to",
        "parameters": {
            "type": "object",
            "properties": {
                "page_size": {
                    "type": "integer",
                    "description": "Maximum number of slides to return",
                    "default": 20,
                }
            },
        },
    },
    # {
    #     "name": "create_slide_deck",
    #     "description": "Create a new Google Slides presentation",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "title": {
    #                 "type": "string",
    #                 "description": "Title of the new presentation",
    #             }
    #         },
    #         "required": ["title"],
    #     },
    # },
    {
        "name": "share_slide_deck",
        "description": "Share a Google Slides deck with another user",
        "parameters": {
            "type": "object",
            "properties": {
                "presentation_id": {
                    "type": "string",
                    "description": "ID of the presentation to share",
                },
                "email": {
                    "type": "string",
                    "description": "Email address to share the deck with",
                },
                "role": {
                    "type": "string",
                    "enum": ["reader", "writer"],
                    "default": "writer",
                    "description": "Access level to grant",
                },
            },
            "required": ["presentation_id", "email"],
        },
    },
    {
        "name": "extract_text_from_slides",
        "description": "Extract all text content from a Google Slides presentation",
        "parameters": {
            "type": "object",
            "properties": {
                "presentation_id": {
                    "type": "string",
                    "description": "ID of the presentation to extract text from",
                }
            },
            "required": ["presentation_id"],
        },
    },
    {
        "name": "search_slides",
        "description": "Search Google Slides files by title keyword.",
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "The keyword to search for in slide deck titles.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of slide decks to return.",
                },
            },
            "required": ["keyword"],
        },
    },
    # {
    #     "name": "slide_history",
    #     "description": "Get metadata and edit history for a Google Slides presentation.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "slide_id": {
    #                 "type": "string",
    #                 "description": "The ID of the Google Slides file.",
    #             }
    #         },
    #         "required": ["slide_id"],
    #     },
    # },
    {
        "name": "web_search",
        "description": "Search the public web for current events, news, weather, sports, stocks, product info, or other facts not in the user's workspace. Does NOT access email, calendar, Docs, Slack, Notion, or Trello. Call only when the user needs live or up-to-date public information; otherwise use workspace tools.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to look up on the web (clear, specific search question or keywords).",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_slide_content",
        "description": "Get detailed content from all slides with slide-by-slide context, including slide numbers, text elements, and layout information",
        "parameters": {
            "type": "object",
            "properties": {
                "presentation_id": {
                    "type": "string",
                    "description": "ID of the presentation to analyze",
                }
            },
            "required": ["presentation_id"],
        },
    },
    {
        "name": "get_specific_slide",
        "description": "Get content from a specific slide by slide number (1-based indexing)",
        "parameters": {
            "type": "object",
            "properties": {
                "presentation_id": {
                    "type": "string",
                    "description": "ID of the presentation",
                },
                "slide_number": {
                    "type": "integer",
                    "description": "Slide number (1-based, e.g., 1 for first slide)",
                },
            },
            "required": ["presentation_id", "slide_number"],
        },
    },
    {
        "name": "replace_text_in_slides",
        "description": "Replace text in presentation. Can target specific slide or entire presentation.",
        "parameters": {
            "type": "object",
            "properties": {
                "presentation_id": {
                    "type": "string",
                    "description": "ID of the presentation to modify",
                },
                "old_text": {
                    "type": "string",
                    "description": "Text to be replaced",
                },
                "new_text": {
                    "type": "string",
                    "description": "New text to replace with",
                },
                "slide_number": {
                    "type": "integer",
                    "description": "Optional: specific slide number (1-based) to target. If not provided, replaces in entire presentation.",
                },
            },
            "required": ["presentation_id", "old_text", "new_text"],
        },
    },
    {
        "name": "add_text_box_to_slide",
        "description": "Add a text box to a specific slide in a Google Slides presentation",
        "parameters": {
            "type": "object",
            "properties": {
                "presentation_id": {
                    "type": "string",
                    "description": "ID of the presentation",
                },
                "slide_index": {
                    "type": "integer",
                    "description": "Index of the slide (0-based)",
                },
                "text": {
                    "type": "string",
                    "description": "Text content for the text box",
                },
                "x": {
                    "type": "number",
                    "description": "X position in points",
                    "default": 100,
                },
                "y": {
                    "type": "number",
                    "description": "Y position in points",
                    "default": 100,
                },
                "width": {
                    "type": "number",
                    "description": "Width in points",
                    "default": 300,
                },
                "height": {
                    "type": "number",
                    "description": "Height in points",
                    "default": 100,
                },
            },
            "required": ["presentation_id", "slide_index", "text"],
        },
    },
    {
        "name": "add_slide_to_presentation",
        "description": "Add a new slide to a Google Slides presentation",
        "parameters": {
            "type": "object",
            "properties": {
                "presentation_id": {
                    "type": "string",
                    "description": "ID of the presentation",
                },
                "layout": {
                    "type": "string",
                    "description": "Layout type for the new slide",
                    "default": "BLANK",
                },
            },
            "required": ["presentation_id"],
        },
    },
    {
        "name": "format_text_in_slides",
        "description": "Format specific text in a Google Slides presentation (bold, italic, size, color)",
        "parameters": {
            "type": "object",
            "properties": {
                "presentation_id": {
                    "type": "string",
                    "description": "ID of the presentation",
                },
                "text_to_format": {
                    "type": "string",
                    "description": "Text to apply formatting to",
                },
                "bold": {
                    "type": "boolean",
                    "description": "Make text bold",
                },
                "italic": {
                    "type": "boolean",
                    "description": "Make text italic",
                },
                "font_size": {
                    "type": "integer",
                    "description": "Font size in points",
                },
                "color": {
                    "type": "string",
                    "description": "Text color in hex format (e.g., #FF0000 for red)",
                },
            },
            "required": ["presentation_id", "text_to_format"],
        },
    },
    # {
    #     "name": "add_table_to_slide",
    #     "description": "Add a table to a specific slide in a Google Slides presentation",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "presentation_id": {
    #                 "type": "string",
    #                 "description": "ID of the presentation",
    #             },
    #             "slide_index": {
    #                 "type": "integer",
    #                 "description": "Index of the slide (0-based)",
    #             },
    #             "rows": {
    #                 "type": "integer",
    #                 "description": "Number of rows in the table",
    #             },
    #             "columns": {
    #                 "type": "integer",
    #                 "description": "Number of columns in the table",
    #             },
    #             "x": {
    #                 "type": "number",
    #                 "description": "X position in points",
    #                 "default": 100,
    #             },
    #             "y": {
    #                 "type": "number",
    #                 "description": "Y position in points",
    #                 "default": 100,
    #             },
    #             "width": {
    #                 "type": "number",
    #                 "description": "Width in points",
    #                 "default": 400,
    #             },
    #             "height": {
    #                 "type": "number",
    #                 "description": "Height in points",
    #                 "default": 200,
    #             },
    #         },
    #         "required": ["presentation_id", "slide_index", "rows", "columns"],
    #     },
    # },
    # {
    #     "name": "update_table_cell",
    #     "description": "Update text in a specific table cell",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "presentation_id": {
    #                 "type": "string",
    #                 "description": "ID of the presentation",
    #             },
    #             "table_id": {
    #                 "type": "string",
    #                 "description": "ID of the table element",
    #             },
    #             "row": {
    #                 "type": "integer",
    #                 "description": "Row index (0-based)",
    #             },
    #             "column": {
    #                 "type": "integer",
    #                 "description": "Column index (0-based)",
    #             },
    #             "text": {
    #                 "type": "string",
    #                 "description": "Text to insert in the cell",
    #             },
    #         },
    #         "required": ["presentation_id", "table_id", "row", "column", "text"],
    #     },
    # },
    # {
    #     "name": "populate_table",
    #     "description": "Populate table with data (2D array)",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "presentation_id": {
    #                 "type": "string",
    #                 "description": "ID of the presentation",
    #             },
    #             "table_id": {
    #                 "type": "string",
    #                 "description": "ID of the table element",
    #             },
    #             "data": {
    #                 "type": "array",
    #                 "description": "2D array of data to populate the table",
    #                 "items": {"type": "array", "items": {"type": "string"}},
    #             },
    #         },
    #         "required": ["presentation_id", "table_id", "data"],
    #     },
    # },
    # {
    #     "name": "add_table_rows",
    #     "description": "Add rows to a table. If insert_index is not provided or -1, adds rows at the bottom.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "presentation_id": {
    #                 "type": "string",
    #                 "description": "ID of the presentation",
    #             },
    #             "table_id": {
    #                 "type": "string",
    #                 "description": "ID of the table element",
    #             },
    #             "insert_index": {
    #                 "type": "integer",
    #                 "description": "Position to insert rows (0-based). Omit or use -1 to add at bottom.",
    #             },
    #             "number_of_rows": {
    #                 "type": "integer",
    #                 "description": "Number of rows to add",
    #                 "default": 1,
    #             },
    #         },
    #         "required": ["presentation_id", "table_id"],
    #     },
    # },
    # {
    #     "name": "add_table_columns",
    #     "description": "Add columns to a table. If insert_index is not provided or -1, adds columns at the right.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "presentation_id": {
    #                 "type": "string",
    #                 "description": "ID of the presentation",
    #             },
    #             "table_id": {
    #                 "type": "string",
    #                 "description": "ID of the table element",
    #             },
    #             "insert_index": {
    #                 "type": "integer",
    #                 "description": "Position to insert columns (0-based). Omit or use -1 to add at right.",
    #             },
    #             "number_of_columns": {
    #                 "type": "integer",
    #                 "description": "Number of columns to add",
    #                 "default": 1,
    #             },
    #         },
    #         "required": ["presentation_id", "table_id"],
    #     },
    # },
    # {
    #     "name": "delete_table_rows",
    #     "description": "Delete rows from a table starting at specified position",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "presentation_id": {
    #                 "type": "string",
    #                 "description": "ID of the presentation",
    #             },
    #             "table_id": {
    #                 "type": "string",
    #                 "description": "ID of the table element",
    #             },
    #             "start_index": {
    #                 "type": "integer",
    #                 "description": "Starting position to delete rows (0-based)",
    #             },
    #             "number_of_rows": {
    #                 "type": "integer",
    #                 "description": "Number of rows to delete",
    #                 "default": 1,
    #             },
    #         },
    #         "required": ["presentation_id", "table_id", "start_index"],
    #     },
    # },
    # {
    #     "name": "delete_table_columns",
    #     "description": "Delete columns from a table starting at specified position",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "presentation_id": {
    #                 "type": "string",
    #                 "description": "ID of the presentation",
    #             },
    #             "table_id": {
    #                 "type": "string",
    #                 "description": "ID of the table element",
    #             },
    #             "start_index": {
    #                 "type": "integer",
    #                 "description": "Starting position to delete columns (0-based)",
    #             },
    #             "number_of_columns": {
    #                 "type": "integer",
    #                 "description": "Number of columns to delete",
    #                 "default": 1,
    #             },
    #         },
    #         "required": ["presentation_id", "table_id", "start_index"],
    #     },
    # },
    # {
    #     "name": "insert_row_above",
    #     "description": "Insert rows above the specified row",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "presentation_id": {
    #                 "type": "string",
    #                 "description": "ID of the presentation",
    #             },
    #             "table_id": {
    #                 "type": "string",
    #                 "description": "ID of the table element",
    #             },
    #             "row_index": {
    #                 "type": "integer",
    #                 "description": "Row index to insert above (0-based)",
    #             },
    #             "number_of_rows": {
    #                 "type": "integer",
    #                 "description": "Number of rows to insert",
    #                 "default": 1,
    #             },
    #         },
    #         "required": ["presentation_id", "table_id", "row_index"],
    #     },
    # },
    # {
    #     "name": "insert_row_below",
    #     "description": "Insert rows below the specified row",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "presentation_id": {
    #                 "type": "string",
    #                 "description": "ID of the presentation",
    #             },
    #             "table_id": {
    #                 "type": "string",
    #                 "description": "ID of the table element",
    #             },
    #             "row_index": {
    #                 "type": "integer",
    #                 "description": "Row index to insert below (0-based)",
    #             },
    #             "number_of_rows": {
    #                 "type": "integer",
    #                 "description": "Number of rows to insert",
    #                 "default": 1,
    #             },
    #         },
    #         "required": ["presentation_id", "table_id", "row_index"],
    #     },
    # },
    # {
    #     "name": "insert_column_left",
    #     "description": "Insert columns to the left of the specified column",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "presentation_id": {
    #                 "type": "string",
    #                 "description": "ID of the presentation",
    #             },
    #             "table_id": {
    #                 "type": "string",
    #                 "description": "ID of the table element",
    #             },
    #             "column_index": {
    #                 "type": "integer",
    #                 "description": "Column index to insert left of (0-based)",
    #             },
    #             "number_of_columns": {
    #                 "type": "integer",
    #                 "description": "Number of columns to insert",
    #                 "default": 1,
    #             },
    #         },
    #         "required": ["presentation_id", "table_id", "column_index"],
    #     },
    # },
    # {
    #     "name": "insert_column_right",
    #     "description": "Insert columns to the right of the specified column",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "presentation_id": {
    #                 "type": "string",
    #                 "description": "ID of the presentation",
    #             },
    #             "table_id": {
    #                 "type": "string",
    #                 "description": "ID of the table element",
    #             },
    #             "column_index": {
    #                 "type": "integer",
    #                 "description": "Column index to insert right of (0-based)",
    #             },
    #             "number_of_columns": {
    #                 "type": "integer",
    #                 "description": "Number of columns to insert",
    #                 "default": 1,
    #             },
    #         },
    #         "required": ["presentation_id", "table_id", "column_index"],
    #     },
    # },
    # # New powerful Google Slides tools from gSlides_ai
    # {
    #     "name": "list_slide_elements",
    #     "description": "List all elements on a specific slide with their types and IDs (shapes, tables, images, videos, lines)",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "presentation_id": {
    #                 "type": "string",
    #                 "description": "ID of the presentation",
    #             },
    #             "slide_id": {
    #                 "type": "string",
    #                 "description": "ID of the slide to list elements from",
    #             },
    #         },
    #         "required": ["presentation_id", "slide_id"],
    #     },
    # },
    # {
    #     "name": "list_tables",
    #     "description": "List all tables in the presentation with their metadata (slide number, table ID, rows, columns)",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "presentation_id": {
    #                 "type": "string",
    #                 "description": "ID of the presentation",
    #             }
    #         },
    #         "required": ["presentation_id"],
    #     },
    # },
    # {
    #     "name": "get_table_info",
    #     "description": "Get detailed information about a specific table (rows, columns, slide location)",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "presentation_id": {
    #                 "type": "string",
    #                 "description": "ID of the presentation",
    #             },
    #             "table_id": {
    #                 "type": "string",
    #                 "description": "ID of the table element",
    #             },
    #         },
    #         "required": ["presentation_id", "table_id"],
    #     },
    # },
    # {
    #     "name": "read_table_data",
    #     "description": "Read all text data from a table as a 2D array. Returns the complete table content.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "presentation_id": {
    #                 "type": "string",
    #                 "description": "ID of the presentation",
    #             },
    #             "table_id": {
    #                 "type": "string",
    #                 "description": "ID of the table element",
    #             },
    #         },
    #         "required": ["presentation_id", "table_id"],
    #     },
    # },
    # {
    #     "name": "replace_table_text",
    #     "description": "Replace or delete specific text in a table cell. If new_text is not provided or empty, deletes the text.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "presentation_id": {
    #                 "type": "string",
    #                 "description": "ID of the presentation",
    #             },
    #             "table_id": {
    #                 "type": "string",
    #                 "description": "ID of the table element",
    #             },
    #             "old_text": {
    #                 "type": "string",
    #                 "description": "Text to find and replace/delete",
    #             },
    #             "new_text": {
    #                 "type": "string",
    #                 "description": "New text to replace with. Leave empty to delete.",
    #             },
    #         },
    #         "required": ["presentation_id", "table_id", "old_text"],
    #     },
    # },
    # {
    #     "name": "search_presentation",
    #     "description": "Search for a keyword in the presentation. Can search across all slides or limit to a specific table. Returns matches with location details.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "presentation_id": {
    #                 "type": "string",
    #                 "description": "ID of the presentation",
    #             },
    #             "keyword": {
    #                 "type": "string",
    #                 "description": "Keyword to search for",
    #             },
    #             "table_id": {
    #                 "type": "string",
    #                 "description": "Optional: limit search to a specific table ID",
    #             },
    #         },
    #         "required": ["presentation_id", "keyword"],
    #     },
    # },
    # {
    #     "name": "get_element_text",
    #     "description": "Get text content from a specific element (shape, text box, etc.) by its element ID",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "presentation_id": {
    #                 "type": "string",
    #                 "description": "ID of the presentation",
    #             },
    #             "element_id": {
    #                 "type": "string",
    #                 "description": "ID of the element to get text from",
    #             },
    #         },
    #         "required": ["presentation_id", "element_id"],
    #     },
    # },
    # {
    #     "name": "delete_element",
    #     "description": "Delete a specific element (table, shape, image, etc.) from a slide by its element ID",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "presentation_id": {
    #                 "type": "string",
    #                 "description": "ID of the presentation",
    #             },
    #             "element_id": {
    #                 "type": "string",
    #                 "description": "ID of the element to delete",
    #             },
    #         },
    #         "required": ["presentation_id", "element_id"],
    #     },
    # },
    # {
    #     "name": "delete_slide",
    #     "description": "Delete a slide from the presentation by its slide ID",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "presentation_id": {
    #                 "type": "string",
    #                 "description": "ID of the presentation",
    #             },
    #             "slide_id": {
    #                 "type": "string",
    #                 "description": "ID of the slide to delete",
    #             },
    #         },
    #         "required": ["presentation_id", "slide_id"],
    #     },
    # },
    # {
    #     "name": "insert_text",
    #     "description": "Insert text into a shape or text box at a specific index position",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "presentation_id": {
    #                 "type": "string",
    #                 "description": "ID of the presentation",
    #             },
    #             "object_id": {
    #                 "type": "string",
    #                 "description": "ID of the shape or text box to insert text into",
    #             },
    #             "text": {
    #                 "type": "string",
    #                 "description": "Text to insert",
    #             },
    #             "insertion_index": {
    #                 "type": "integer",
    #                 "description": "Index position to insert text at (0-based)",
    #                 "default": 0,
    #             },
    #         },
    #         "required": ["presentation_id", "object_id", "text"],
    #     },
    # },
    # {
    #     "name": "insert_image",
    #     "description": "Insert an image on a slide from a URL",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "presentation_id": {
    #                 "type": "string",
    #                 "description": "ID of the presentation",
    #             },
    #             "slide_id": {
    #                 "type": "string",
    #                 "description": "ID of the slide to insert image on",
    #             },
    #             "image_url": {
    #                 "type": "string",
    #                 "description": "URL of the image to insert",
    #             },
    #             "x": {
    #                 "type": "number",
    #                 "description": "X position in points",
    #                 "default": 100,
    #             },
    #             "y": {
    #                 "type": "number",
    #                 "description": "Y position in points",
    #                 "default": 100,
    #             },
    #             "width": {
    #                 "type": "number",
    #                 "description": "Width in points",
    #                 "default": 300,
    #             },
    #             "height": {
    #                 "type": "number",
    #                 "description": "Height in points",
    #                 "default": 200,
    #             },
    #         },
    #         "required": ["presentation_id", "slide_id", "image_url"],
    #     },
    # },
    # {
    #     "name": "list_slides_info",
    #     "description": "List all slides in a presentation with their IDs and index numbers",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "presentation_id": {
    #                 "type": "string",
    #                 "description": "ID of the presentation",
    #             }
    #         },
    #         "required": ["presentation_id"],
    #     },
    # },
    # {
    #     "name": "add_rows_and_populate",
    #     "description": "Add new rows at the bottom of the table and populate them with data in one operation. This is the recommended way to add data to tables.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "presentation_id": {
    #                 "type": "string",
    #                 "description": "ID of the presentation",
    #             },
    #             "table_id": {
    #                 "type": "string",
    #                 "description": "ID of the table element",
    #             },
    #             "data": {
    #                 "type": "array",
    #                 "description": "2D array of data to add (each inner array is a row)",
    #                 "items": {"type": "array", "items": {"type": "string"}},
    #             },
    #         },
    #         "required": ["presentation_id", "table_id", "data"],
    #     },
    # },
    # {
    #     "name": "append_table_row",
    #     "description": "Append a single row to the bottom of the table with data. Convenience function for adding one row.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "presentation_id": {
    #                 "type": "string",
    #                 "description": "ID of the presentation",
    #             },
    #             "table_id": {
    #                 "type": "string",
    #                 "description": "ID of the table element",
    #             },
    #             "row_data": {
    #                 "type": "array",
    #                 "description": "Array of cell values for the new row",
    #                 "items": {"type": "string"},
    #             },
    #         },
    #         "required": ["presentation_id", "table_id", "row_data"],
    #     },
    # },
    # {
    #     "name": "add_columns_and_populate",
    #     "description": "Add new columns at the right of the table and populate them with data in one operation. This is the recommended way to add column data to tables.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "presentation_id": {
    #                 "type": "string",
    #                 "description": "ID of the presentation",
    #             },
    #             "table_id": {
    #                 "type": "string",
    #                 "description": "ID of the table element",
    #             },
    #             "data": {
    #                 "type": "array",
    #                 "description": "Array of columns, where each column is an array of cell values (top to bottom)",
    #                 "items": {"type": "array", "items": {"type": "string"}},
    #             },
    #         },
    #         "required": ["presentation_id", "table_id", "data"],
    #     },
    # },
    # {
    #     "name": "append_table_column",
    #     "description": "Append a single column to the right of the table with data. Convenience function for adding one column.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "presentation_id": {
    #                 "type": "string",
    #                 "description": "ID of the presentation",
    #             },
    #             "table_id": {
    #                 "type": "string",
    #                 "description": "ID of the table element",
    #             },
    #             "column_data": {
    #                 "type": "array",
    #                 "description": "Array of cell values for the new column (top to bottom)",
    #                 "items": {"type": "string"},
    #             },
    #         },
    #         "required": ["presentation_id", "table_id", "column_data"],
    #     },
    # },
    # Gamma Presentation function definitions
    {
        "name": "create_gamma_presentation",
        "description": "Create a new presentation using Gamma AI and automatically export to Google Slides. This tool handles the complete workflow: generates AI-powered slides using Gamma, exports as PPTX, downloads the file, and uploads it to Google Drive converting to Google Slides format. Provide a token to enable automatic Google Slides export.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Title of the presentation"
                },
                "input_text": {
                    "type": "string",
                    "description": "Main content or prompt for the presentation that Gamma AI will use to generate slides"
                },
                "theme_id": {
                    "type": "string",
                    "description": "Optional theme ID for the presentation (omit for Gamma default)"
                },
                "num_cards": {
                    "type": "integer",
                    "description": "Number of slides/cards to generate (default: 5)",
                    "default": 5
                },
                "format_": {
                    "type": "string",
                    "enum": ["presentation", "document", "social", "webpage"],
                    "description": "Output format (default: presentation)",
                    "default": "presentation"
                },
                "text_mode": {
                    "type": "string",
                    "enum": ["generate", "condense", "preserve"],
                    "description": "How to process the input text: 'generate' creates new content, 'condense' summarizes, 'preserve' keeps original (default: generate)",
                    "default": "generate"
                },
                "token": {
                    "type": "string",
                    "description": "User authentication token (required for automatic Google Drive/Slides export) - alias for unified_token"
                },
                "unified_token": {
                    "type": "string",
                    "description": "User authentication token (required for automatic Google Drive/Slides export) - preferred parameter name"
                }
            },
            "required": ["title", "input_text"]
        }
    },
    # {
    #     "name": "list_gamma_themes",
    #     "description": "List all available Gamma presentation themes",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "token": {
    #                 "type": "string",
    #                 "description": "User authentication token (not required for this endpoint)"
    #             }
    #         }
    #     }
    # },
    # Notion function definitions
    {
        "name": "list_databases",
        "description": "List all Notion databases shared with the integration",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "list_pages",
        "description": "List pages in a specific Notion database",
        "parameters": {
            "type": "object",
            "properties": {"database_id": {"type": "string"}},
            "required": ["database_id"],
        },
    },
    {
        "name": "find_or_create_database",
        "description": "Find a Notion database by name, or get suggestions for creating one if not found. Use this when you need to locate a database before creating pages.",
        "parameters": {
            "type": "object",
            "properties": {
                "database_name": {
                    "type": "string",
                    "description": "Name of the database to search for",
                },
            },
            "required": ["database_name"],
        },
    },
    {
        "name": "create_page",
        "description": "Create a new Notion page in a database or as a child page. Can find database by name or use specific IDs. When creating a row in a database, prefer to first call get_database_schema and then pass a `properties` object with mapped values so the row matches the database columns.",
        "parameters": {
            "type": "object",
            "properties": {
                "parent_id": {
                    "type": "string",
                    "description": "The ID of the parent page (optional)",
                },
                "title": {
                    "type": "string",
                    "description": "The title of the new page",
                    "default": "Untitled",
                },
                "content": {
                    "type": "string",
                    "description": "Optional content for the page",
                },
                "database_id": {
                    "type": "string",
                    "description": "The ID of the database to create the page in (optional)",
                },
                "database_name": {
                    "type": "string",
                    "description": "Name of database to find and create page in (optional)",
                },
                "properties": {
                    "type": "object",
                    "description": "Optional initial database properties when creating a row in a database. Keys are property names from get_database_schema; values are simple values (string/date/number/etc.) that will be validated and applied via update_page_properties.",
                },
            },
            "required": ["title"],
        },
    },
    {
        "name": "create_database",
        "description": "Create a new Notion database in a parent page. Prefer passing an explicit `properties` schema so the database columns match the topic (e.g. sports + needed energy, project tasks, experiments). If `properties` is omitted, only a minimal `Name` title column is created (no default Status/Priority/Due Date).",
        "parameters": {
            "type": "object",
            "properties": {
                "parent_id": {
                    "type": "string",
                    "description": "The ID of the parent page where the database will be created",
                },
                "title": {
                    "type": "string",
                    "description": "The title of the new database",
                },
                "properties": {
                    "type": "object",
                    "description": "Optional custom database schema. Keys are property names; values are Notion property definitions (e.g. select with options, number, date). When provided, these become the database columns and should be derived from the user's request/topic.",
                },
            },
            "required": ["parent_id", "title"],
        },
    },
    {
        "name": "create_parent_page",
        "description": "Create a new parent page in Notion. If parent_page_id is provided, creates as child page. Otherwise attempts workspace-level creation (may fail for internal integrations).",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "The title of the new parent page",
                },
                "parent_page_id": {
                    "type": "string",
                    "description": "Optional: ID of existing page to create this as a child page. If not provided, attempts workspace-level creation.",
                },
                "content": {
                    "type": "string",
                    "description": "Optional initial content for the page",
                },
            },
            "required": ["title"],
        },
    },
    {
        "name": "list_parent_pages",
        "description": "List top-level parent pages that can contain databases (not database rows). Use this to show users available parent pages before creating a database.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "search_notion",
        "description": "Search across all Notion content by keyword",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "append_block",
        "description": "Append NEW content to a Notion page. Use this ONLY when adding completely new content that should be a separate block. DO NOT use this when user refers to 'that block', 'the block', or says 'add to that block' - use update_block instead. If mode='replace', it replaces ALL existing content on the page (use with caution). Supports either plain text (content) or a structured table (table). For native Notion headings: set heading_level to 1, 2, or 3 (H1/H2/H3) instead of relying on markdown # in content alone—plain title text with heading_level=3 matches '###' style. To insert at a specific position (not the end), call get_page_content first and pass after_block_id = the block_id of the sibling immediately BEFORE the insertion point; if that sibling lives under a nested parent (toggle, column, list item), set parent_block_id to that parent's block_id and keep page_id as the page. In content: use [label](url) for hyperlinks; <fg red>text</fg> for foreground color and <bg yellow>text</bg> for highlight (colors: gray, brown, orange, yellow, green, blue, purple, pink, red; combine with **bold**, *italic*, etc.).",
        "parameters": {
            "type": "object",
            "properties": {
                "page_id": {"type": "string"},
                "content": {
                    "type": "string",
                    "description": "Plain text for paragraph/list blocks (not tables). Supports [label](url) links, <fg COLOR>…</fg> and <bg COLOR>…</bg> (Notion colors: gray, brown, orange, yellow, green, blue, purple, pink, red), **bold**, *italic*, __underline__, ~~strike~~. For headings without #, use heading_level.",
                },
                "after_block_id": {
                    "type": "string",
                    "description": "Optional. Notion inserts new blocks after this block. Must be a direct child of the append parent (page root or parent_block_id). From get_page_content, use the block_id of the block before the desired gap.",
                },
                "parent_block_id": {
                    "type": "string",
                    "description": "Optional. Append as children of this block instead of under page_id (for content inside toggles, columns, or list items). Omit for top-level page content.",
                },
                "heading_level": {
                    "type": "integer",
                    "enum": [1, 2, 3],
                    "description": "If set, content lines are appended as native Notion heading blocks: 1=heading_1, 2=heading_2, 3=heading_3 (equivalent to markdown # / ## / ###). Omit for normal paragraphs.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["append", "replace"],
                    "description": "Set to 'replace' to replace existing content; defaults to 'append'.",
                    "default": "append",
                },
                "table": {
                    "type": "object",
                    "description": "Structured table definition. When provided, a Notion table block is created instead of a paragraph. Use this for comparison/price tables, not for databases.",
                    "properties": {
                        "columns": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Column headers, in order (e.g. ['Technology', 'Use Case', 'Complexity', 'Cost']).",
                        },
                        "rows": {
                            "type": "array",
                            "items": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "description": "Table rows. Each row is an array of cell values, in the same order as columns.",
                        },
                        "has_column_header": {
                            "type": "boolean",
                            "description": "Whether the first row should be treated as a header row.",
                            "default": True,
                        },
                        "has_row_header": {
                            "type": "boolean",
                            "description": "Whether the first column is a header column.",
                            "default": False,
                        },
                    },
                    "required": ["columns", "rows"],
                },
            },
            "required": ["page_id"],
        },
    },
    {
        "name": "update_block",
        "description": "Update/edit a specific block in a Notion page by its block ID. Use get_page_content first to get the block_id. For paragraph/heading/text blocks: content is the new full text (merge old+new if adding to existing). Same inline syntax as append_block: [label](url), <fg COLOR>…</fg>, <bg COLOR>…</bg>, **bold**, etc. Optional text_color applies to the whole block when you want a single foreground/background Notion color without tags (e.g. red, blue_background). For table_row: content is cell values tab- or pipe-separated. For table: content is NEW ROWS ONLY (tab-separated, one line per row).",
        "parameters": {
            "type": "object",
            "properties": {
                "block_id": {
                    "type": "string",
                    "description": "The block ID from get_page_content. Use the table block id when appending rows; use the table_row id when editing one row.",
                },
                "content": {
                    "type": "string",
                    "description": "New content: for text blocks the full text with optional [link](url) and color tags; for table new rows (tab-separated); for table_row tab- or pipe-separated cells.",
                },
                "text_color": {
                    "type": "string",
                    "description": "Optional. Apply one Notion color to the entire text when not using <fg>/<bg> in content: default, gray, brown, orange, yellow, green, blue, purple, pink, red, or *_background (e.g. yellow_background). Skips multi-block list restructuring—prefer tags in content for colored lists.",
                },
            },
            "required": ["block_id", "content"],
        },
    },
    {
        "name": "delete_block",
        "description": "Delete a specific block from a Notion page. You can delete by block_id (preferred) or by searching for content within a page. Use this when the user asks to remove or delete a specific block of text.",
        "parameters": {
            "type": "object",
            "properties": {
                "block_id": {
                    "type": "string",
                    "description": "The block ID to delete (preferred method). Get this from get_page_content first.",
                },
                "page_id": {
                    "type": "string",
                    "description": "The page ID to search within (required if block_id not provided)",
                },
                "content_search": {
                    "type": "string",
                    "description": "Text content to search for and delete (required if block_id not provided). This will find and delete the first block containing this text.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_page_content",
        "description": "Retrieve all blocks on a Notion page recursively. Returns a JSON object with `blocks`: each item has `block_id`, `type`, `index` (sibling order, 0-based), `depth`, `path` (e.g. '2/0/1' for nesting), `plain_text` preview, and `has_children`. Use `path`/`index` to understand document order; use `block_id` for update_block/delete_block. Large pages may return `truncated: true`.",
        "parameters": {
            "type": "object",
            "properties": {"page_id": {"type": "string"}},
            "required": ["page_id"],
        },
    },
    {
        "name": "get_notion_comment",
        "description": "Fetch discussion comments or feedback from a Notion page or its blocks. Use this tool only when the user asks for comments, reviews, notes, or feedback — not for page content or text.",
        "parameters": {
            "type": "object",
            "properties": {
                "page_id": {
                    "type": "string",
                    "description": "The Notion page ID (not the name). Use 'search_notion' first if only the page name is known.",
                },
                "comment_type": {
                    "type": "string",
                    "enum": ["page", "block"],
                    "default": "page",
                    "description": "Specifies whether to fetch comments from the page itself ('page') or from blocks within it ('block'). Defaults to 'page'.",
                },
                "block_id": {
                    "type": "string",
                    "description": "Optional block ID. If provided with type='block', fetches comments only from that specific block instead of all blocks under the page.",
                },
            },
            "required": ["page_id"],
        },
    },
    {
        "name": "notion_add_comment",
        "description": "Add a comment in a Notion Page or Particular Block in a Notion page",
        "parameters": {
            "type": "object",
            "properties": {
                "page_id": {
                    "type": "string",
                    "description": "The Notion page ID (not the name). Use 'search_notion' first if only the page name is known.",
                },
                "content": {"type": "string"},
                "target_type": {
                    "type": "string",
                    "enum": ["page", "block"],
                    "default": "page",
                    "description": "Specifies whether to add comments to the page itself ('page') or to blocks within it ('block'). Defaults to 'page'.",
                },
                "block_id": {
                    "type": "string",
                    "description": "Optional block ID. If provided with type='block', add comments only to that specific block instead of all blocks under the page.",
                },
            },
            "required": ["page_id", "content"],
        },
    },
    {
        "name": "update_page_title",
        "description": "Update the title of a Notion page",
        "parameters": {
            "type": "object",
            "properties": {
                "page_id": {"type": "string"},
                "new_title": {"type": "string"},
            },
            "required": ["page_id", "new_title"],
        },
    },
    {
        "name": "update_page_properties",
        "description": "Update one or more properties of a Notion database page (row). Call get_database_schema first to get exact property names and types. Use for date, select, status, etc. Note: Notion's built-in 'Created time' cannot be changed via the API.",
        "parameters": {
            "type": "object",
            "properties": {
                "page_id": {
                    "type": "string",
                    "description": "The Notion page ID (database row) to update.",
                },
                "properties": {
                    "type": "object",
                    "description": "Map of property names (from get_database_schema) to new values. E.g. {\"Due date\": \"2026-02-15\", \"Status\": \"Done\"}.",
                },
            },
            "required": ["page_id", "properties"],
        },
    },
    {
        "name": "delete_page",
        "description": "Delete a Notion page (archives it). Accepts either page_id or document_id parameter.",
        "parameters": {
            "type": "object",
            "properties": {
                "page_id": {
                    "type": "string",
                    "description": "The Notion page ID to delete",
                },
                "document_id": {
                    "type": "string",
                    "description": "Alternative parameter name for page_id (for backward compatibility)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "add_todo",
        "description": "Add a new todo item to a Notion page",
        "parameters": {
            "type": "object",
            "properties": {
                "page_id": {"type": "string"},
                "todo_text": {"type": "string"},
            },
            "required": ["page_id", "todo_text"],
        },
    },
    {
        "name": "query_database",
        "description": "Query a Notion database for items with a specific status",
        "parameters": {
            "type": "object",
            "properties": {
                "database_id": {"type": "string"},
                "status_value": {"type": "string"},
            },
            "required": ["database_id", "status_value"],
        },
    },
    {
        "name": "get_database_schema",
        "description": "Fetch the full schema for a Notion database, including property types, select/status options, and example values from existing rows.",
        "parameters": {
            "type": "object",
            "properties": {
                "database_id": {
                    "type": "string",
                    "description": "The Notion database ID whose schema should be inspected.",
                },
                "sample_page_limit": {
                    "type": "integer",
                    "description": "Maximum number of rows to inspect when collecting example values (default 10, max 100).",
                    "minimum": 1,
                    "maximum": 100,
                },
            },
            "required": ["database_id"],
        },
    },
    {
        "name": "get_notion_documents",
        "description": "List all Notion documents shared with the integration",
        "parameters": {"type": "object", "properties": {}},
    },
    # {
    #     "name": "get_slides_context",
    #     "description": "Fetch extra AI-generated correlation information for Google Slides presentation IDs returned from search_slides. Returns additional insights like brief descriptions, change summaries, comments, and edit history extracted from those presentations.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "presentation_ids": {
    #                 "type": "array",
    #                 "description": "List of Google Slides presentation IDs to look up context for. These are the presentation IDs returned from search_slides or list_slides.",
    #                 "items": {"type": "string"},
    #             },
    #             "include_embeddings": {
    #                 "type": "boolean",
    #                 "description": "Whether to include the embedding vectors in the response. Default is false.",
    #                 "default": False,
    #             }
    #         },
    #         "required": ["presentation_ids"],
    #     },
    # },
    # Trello Task Manager function definitions
    {
        "name": "list_task_boards",
        "description": "List all Trello boards for the current user (Task Manager).",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "find_task_board",
        "description": "Find a Trello board by name (exact, then prefix, then substring match).",
        "parameters": {
            "type": "object",
            "properties": {"board_name": {"type": "string"}},
            "required": ["board_name"],
        },
    },
    {
        "name": "list_task_members",
        "description": "List Trello board members.",
        "parameters": {
            "type": "object",
            "properties": {"board_id": {"type": "string"}},
            "required": ["board_id"],
        },
    },
    {
        "name": "list_task_lists",
        "description": "List Trello lists for a board.",
        "parameters": {
            "type": "object",
            "properties": {"board_id": {"type": "string"}},
            "required": ["board_id"],
        },
    },
    {
        "name": "list_task_cards",
        "description": "List Trello cards either by list or by board (provide one).",
        "parameters": {
            "type": "object",
            "properties": {
                "list_id": {"type": "string"},
                "board_id": {"type": "string"},
            },
        },
    },
    {
        "name": "create_task",
        "description": "Create a Trello task (card). Either pass list_id (direct list) OR board_name + list_name to resolve the list by name. Do not send both styles at once.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Card title"},
                "list_id": {"type": "string", "description": "Trello list id when board/list names are not used"},
                "board_name": {"type": "string", "description": "Board name (use with list_name; resolves ids in the backend)"},
                "list_name": {"type": "string", "description": "List/column name on that board"},
                "desc": {"type": "string", "description": "Task description (legacy parameter, use 'description' instead)"},
                "description": {"type": "string", "description": "Task description (preferred over 'desc')"},
                "due": {"type": "string", "description": "Due datetime (ISO8601)"},
                "member_ids": {"type": "array", "items": {"type": "string"}},
                "label_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["name"],
        },
    },
    {
        "name": "update_task",
        "description": "Update a Trello task (card) fields or move with list_id.",
        "parameters": {
            "type": "object",
            "properties": {
                "card_id": {"type": "string"},
                "name": {"type": "string"},
                "desc": {"type": "string", "description": "Task description (legacy parameter, use 'description' instead)"},
                "description": {"type": "string", "description": "Task description (preferred over 'desc')"},
                "due": {"type": "string"},
                "closed": {"type": "boolean"},
                "list_id": {"type": "string"},
            },
            "required": ["card_id"],
        },
    },
    {
        "name": "move_task",
        "description": "Move a Trello task (card) to another list.",
        "parameters": {
            "type": "object",
            "properties": {
                "card_id": {"type": "string"},
                "list_id": {"type": "string"},
            },
            "required": ["card_id", "list_id"],
        },
    },
    {
        "name": "delete_task",
        "description": "Delete (close) a Trello task (card).",
        "parameters": {
            "type": "object",
            "properties": {"card_id": {"type": "string"}},
            "required": ["card_id"],
        },
    },
    {
        "name": "search_tasks",
        "description": "Search Trello tasks (cards). Optionally restrict to a board.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "board_id": {"type": "string"},
                "limit": {"type": "integer", "default": 50},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_task",
        "description": "Get a Trello task (card) by ID.",
        "parameters": {
            "type": "object",
            "properties": {"card_id": {"type": "string"}},
            "required": ["card_id"],
        },
    },
    {
        "name": "add_task_comment",
        "description": "Add a comment to a Trello card.",
        "parameters": {
            "type": "object",
            "properties": {"card_id": {"type": "string"}, "text": {"type": "string"}},
            "required": ["card_id", "text"],
        },
    },
    {
        "name": "task_comment_list",
        "description": "List all comments for a given Trello card.",
        "parameters": {
            "type": "object",
            "properties": {
                "card_id": { 
                    "type": "string", 
                    "description": "The ID of the Trello card." }
                },
            "required": ["card_id"]
        }
    },
    {
        "name": "update_task_comment",
        "description": "Update an existing comment on a card (requires action_id).",
        "parameters": {
            "type": "object",
            "properties": {
                "card_id": {"type": "string"},
                "action_id": {"type": "string"},
                "text": {"type": "string"},
            },
            "required": ["card_id", "action_id", "text"],
        },
    },
    {
        "name": "delete_task_comment",
        "description": "Delete a comment from a card (requires action_id).",
        "parameters": {
            "type": "object",
            "properties": {
                "card_id": {"type": "string"},
                "action_id": {"type": "string"},
            },
            "required": ["card_id", "action_id"],
        },
    },
    {
        "name": "add_task_members",
        "description": "Add one or more members to a card.",
        "parameters": {
            "type": "object",
            "properties": {
                "card_id": {"type": "string"},
                "member_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["card_id", "member_ids"],
        },
    },
    {
        "name": "remove_task_member",
        "description": "Remove a member from a card.",
        "parameters": {
            "type": "object",
            "properties": {
                "card_id": {"type": "string"},
                "member_id": {"type": "string"},
            },
            "required": ["card_id", "member_id"],
        },
    },
    {
        "name": "add_task_label",
        "description": "Add an existing label to a card.",
        "parameters": {
            "type": "object",
            "properties": {
                "card_id": {"type": "string"},
                "label_id": {"type": "string"},
            },
            "required": ["card_id", "label_id"],
        },
    },
    {
        "name": "remove_task_label",
        "description": "Remove a label from a card.",
        "parameters": {
            "type": "object",
            "properties": {
                "card_id": {"type": "string"},
                "label_id": {"type": "string"},
            },
            "required": ["card_id", "label_id"],
        },
    },
    {
        "name": "list_task_board_labels",
        "description": "List labels available on a board.",
        "parameters": {
            "type": "object",
            "properties": {"board_id": {"type": "string"}},
            "required": ["board_id"],
        },
    },
    {
        "name": "create_task_checklist",
        "description": "Create a checklist on a card.",
        "parameters": {
            "type": "object",
            "properties": {"card_id": {"type": "string"}, "name": {"type": "string"}},
            "required": ["card_id", "name"],
        },
    },
    {
        "name": "list_task_checklists",
        "description": "List all checklists on a card.",
        "parameters": {
            "type": "object",
            "properties": {"card_id": {"type": "string"}},
            "required": ["card_id"],
        },
    },
    {
        "name": "add_task_checkitem",
        "description": "Add a check item to a checklist.",
        "parameters": {
            "type": "object",
            "properties": {
                "checklist_id": {"type": "string"},
                "name": {"type": "string"},
                "pos": {"type": "string"},
                "checked": {"type": "boolean"},
            },
            "required": ["checklist_id", "name"],
        },
    },
    {
        "name": "update_task_checkitem",
        "description": "Update a check item on a card.",
        "parameters": {
            "type": "object",
            "properties": {
                "card_id": {"type": "string"},
                "checkitem_id": {"type": "string"},
                "name": {"type": "string"},
                "state": {"type": "string"},
                "pos": {"type": "string"},
            },
            "required": ["card_id", "checkitem_id"],
        },
    },
    {
        "name": "delete_task_checkitem",
        "description": "Delete a check item from a checklist.",
        "parameters": {
            "type": "object",
            "properties": {
                "checklist_id": {
                    "type": "string",
                    "description": "The ID of the checklist that contains the check item."
                    },
                "checkitem_id": {
                    "type": "string",
                    "description": "The ID of the check item to delete."
                    }
            },
            "required": ["checklist_id", "checkitem_id"],
        },
    },
    {
        "name": "add_task_attachment_url",
        "description": "Attach a URL to a card.",
        "parameters": {
            "type": "object",
            "properties": {
                "card_id": {"type": "string"},
                "url": {"type": "string"},
                "name": {"type": "string"},
            },
            "required": ["card_id", "url"],
        },
    },
    {
        "name": "set_task_custom_field",
        "description": "Set a custom field on a card.",
        "parameters": {
            "type": "object",
            "properties": {
                "card_id": {"type": "string"},
                "custom_field_id": {"type": "string"},
                "value": {"type": "object"},
            },
            "required": ["card_id", "custom_field_id", "value"],
        },
    },
    {
        "name": "create_board_label",
        "description": "Create a Trello label on a board. Pass board_id OR board_name (not both required in schema; backend requires one). `name` is the new label name.",
        "parameters": {
            "type": "object",
            "properties": {
                "board_id": {"type": "string"},
                "board_name": {"type": "string"},
                "name": {"type": "string"},
                "color": {"type": "string"},
            },
        },
    },
    {
        "name": "update_board_label",
        "description": "Update a Trello board label's name and/or color.",
        "parameters": {
            "type": "object",
            "properties": {
                "label_id": {"type": "string"},
                "name": {"type": "string"},
                "color": {"type": "string"},
            },
            "required": ["label_id"],
        },
    },
    {
        "name": "create_task_list",
        "description": "Create a Trello list on a board. Pass board_id OR board_name to identify the board.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the new list/column"},
                "board_id": {"type": "string"},
                "board_name": {"type": "string"},
                "pos": {"type": "string"},
            },
            "required": ["name"],
        },
    },
    # {
    #     "name": "find_task_board",
    #     "description": "Find a Trello board by name (exact/starts/contains).",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {"board_name": {"type": "string"}},
    #         "required": ["board_name"],
    #     },
    # },
    {
        "name": "find_task_list",
        "description": "Find a Trello list by name within a board. Pass board_id OR board_name.",
        "parameters": {
            "type": "object",
            "properties": {
                "list_name": {"type": "string"},
                "board_id": {"type": "string"},
                "board_name": {"type": "string"},
            },
            "required": ["list_name"],
        },
    },
    # {
    #     "name": "get_trello_context",
    #     "description": "Fetch extra AI-generated correlation information for Trello card IDs (tasks) returned from task_search or task_list_cards. Returns additional insights like brief descriptions, change summaries, comments, and board/list context extracted from those cards.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "card_ids": {
    #                 "type": "array",
    #                 "description": "List of Trello card IDs (also called page_id in the context collection) to look up context for. These are the card IDs returned from task_search or task_list_cards.",
    #                 "items": {"type": "string"},
    #             },
    #             "include_embeddings": {
    #                 "type": "boolean",
    #                 "description": "Whether to include the embedding vectors in the response. Default is false.",
    #                 "default": False,
    #             }
    #         },
    #         "required": ["card_ids"],
    #     },
    # },
]

# Placeholder 'tools' mapping will be populated by the runtime module.
tools = {}
