# fetch slack------------------------------

import asyncio
import sys
import json
from db.mongo_client import get_mongo_client
import fetch_google_docs as ggb1
import fetch_google_sheets as ggb2
import fetch_google_slides as ggb3
import fetch_notion as ggb4
import fetch_trello as ggb5
import fetch_slack_briefing as ggb8
import generate_autopilot as ggb6
import fetch_slack_new_structure2 as ggb7
import fetch_slack_briefing as ggb9
import fetch_gmail_briefing as ggb10

db = get_mongo_client("unified_workspace")

# Build user list from Mongo:
# 1) read user_id/fullName from users collection
# 2) include only users that have tool_id="t003" in user_tools
# user_docs = list(db["users"].find({}, {"user_id": 1, "fullName": 1}))
# users_collection_ids = {
#     str(u.get("user_id", "")).strip()
#     for u in user_docs
#     if str(u.get("user_id", "")).strip()
# }

# tool_users_cursor = db["user_tools"].find(
#     {"tool_id": "t003"},
#     {"user_id": 1},
# )
# tool_user_ids = {
#     str(t.get("user_id", "")).strip()
#     for t in tool_users_cursor
#     if str(t.get("user_id", "")).strip()
# }

# eligible_user_ids = users_collection_ids.intersection(tool_user_ids)
# slack_user_ids = [
#     str(u.get("user_id", "")).strip()
#     for u in user_docs
#     if str(u.get("user_id", "")).strip() in eligible_user_ids
# ]
# print("slack_user_ids--------------------------: ", slack_user_ids)
# Run Slack fetch for all eligible users simultaneously.
# if sys.platform.startswith("win"):
#     asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# if slack_user_ids:
#     results = ggb7.run_fetch_slack_data_for_users(slack_user_ids, {})
#     print("Slack batch results:", results)
# else:
#     print("No eligible users found for tool_id=t003.")
# Keep single-user vars for other manual tests in this file.
# user_id = slack_user_ids[0] if slack_user_ids else "300"
# user_name = user_docs[0].get("fullName", "Unknown") if user_docs else "Unknown"
#ba872a82-cbe8-42d9-80b7-59be02f08f11
#cf9fcaf6-6a72-4bcc-a882-90795dfb492b


# for u in user_docs:
#     print(u["fullName"])
#     print(u["user_id"])
#     timestamp = "2026-03-29T05:54:12.099+00:00"
# user_id = "9d5681bd-20f6-458d-9d1e-f1785f2eb85e"
user_id = "100"
timestamp = "2026-04-01T05:54:12.099+00:00"

# --- Slack fetch from test.py ---
# One user (async):   asyncio.run(ggb7.fetch_slack_data(user_id, {}))
# Many users (parallel, sync wrapper — recommended from scripts):
#   if sys.platform.startswith("win"):
#       asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
#   # user IDs are already loaded from Mongo into slack_user_ids
#   print(ggb7.run_fetch_slack_data_for_users(slack_user_ids, {}))

# ggb1.fetch_google_docs_data(user_id)
# ggb2.fetch_google_sheets_data(user_id)
# ggb3.fetch_google_slides_data(user_id)
# ggb4.fetch_notion_data(user_id)
# if sys.platform.startswith("win"):
#     # Avoid Proactor shutdown warnings on event-loop close.
#     asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# asyncio.run(ggb5.fetch_trello(user_id, tool_data={}))
# ggb8.brief_slack_output(user_id, user_name)
ggb6.generate_autopilot_drafts_task(user_id, timestamp)

# ggb9.brief_slack_output(user_id,user_name)
# ggb10.generate_gmail_briefing(user_id,user_name)


# # import fetch_slack_new_structure as ggb
# # # db= get_mongo_client("unified_workspace")
# # # # users= db["users"].find({"user_id": "300"})
# # # # user_id = "cf9fcaf6-6a72-4bcc-a882-90795dfb492b"
# # # user_id = "ba872a82-cbe8-42d9-80b7-59be02f08f11"
# # # user_name = "Anmol"
# # # for u in users:
# # #     print(u["fullName"])
# # #     print(u["user_id"])
# # #     timestamp = "2026-02-25T05:38:37.313+00:00"
# #     # ggb.fetch_trello(u["user_id"], u["fullName"])
# # ggb7.fetch_slack_data(user_id)




# #fetch google docs------------------------------




# # db= get_mongo_client("unified_workspace")
# # users= db["users"].find({"user_id": "ba872a82-cbe8-42d9-80b7-59be02f08f11"})
# # # user_id = "cf9fcaf6-6a72-4bcc-a882-90795dfb492b"
# # user_id = "ba872a82-cbe8-42d9-80b7-59be02f08f11"
# # # user_name = "Anmol"
# # for u in users:
# #     print(u["fullName"])
# #     print(u["user_id"])
# #     timestamp = "2026-02-25T05:38:37.313+00:00"
#     # ggb.fetch_trello(u["user_id"], u["fullName"])
# # ggb1.fetch_google_docs_data(user_id)
# #fetch google sheets------------------------------




# # db= get_mongo_client("unified_workspace")
# # users= db["users"].find({"user_id": "ba872a82-cbe8-42d9-80b7-59be02f08f11"})
# # # user_id = "cf9fcaf6-6a72-4bcc-a882-90795dfb492b"
# # user_id = "ba872a82-cbe8-42d9-80b7-59be02f08f11"
# # user_name = "Anmol"
# # for u in users:
# #     print(u["fullName"])
# #     print(u["user_id"])
# #     timestamp = "2026-02-25T05:38:37.313+00:00"
#     # ggb.fetch_trello(u["user_id"], u["fullName"])
# # ggb2.fetch_google_sheets_data(user_id)

# # #fetch google slides------------------------------



# # import fetch_google_slides as ggb

# # db= get_mongo_client("unified_workspace")
# # users= db["users"].find({"user_id": "ba872a82-cbe8-42d9-80b7-59be02f08f11"})
# # # user_id = "cf9fcaf6-6a72-4bcc-a882-90795dfb492b"
# # user_id = "ba872a82-cbe8-42d9-80b7-59be02f08f11"
# # user_name = "Anmol"
# # for u in users:
# #     print(u["fullName"])
# #     print(u["user_id"])
# #     timestamp = "2026-02-25T05:38:37.313+00:00"
#     # ggb.fetch_trello(u["user_id"], u["fullName"])
# # ggb3.fetch_google_slides_data(user_id)

# #fETCH NOTION------------------------------



# # import fetch_notion as ggb

# # db= get_mongo_client("unified_workspace")
# # # users= db["users"].find({"user_id": "300"})
# # # user_id = "cf9fcaf6-6a72-4bcc-a882-90795dfb492b"
# # user_id = "ba872a82-cbe8-42d9-80b7-59be02f08f11"
# # user_name = "Anmol"
# # for u in users:
# #     print(u["fullName"])
# #     print(u["user_id"])
# #     timestamp = "2026-02-25T05:38:37.313+00:00"
#     # ggb.fetch_trello(u["user_id"], u["fullName"])
# ggb4.fetch_notion_data(user_id)

# #fETCH trello------------------------------


# import fetch_trello as ggb

# # db= get_mongo_client("unified_workspace")
# # # users= db["users"].find({"user_id": "300"})
# # # user_id = "cf9fcaf6-6a72-4bcc-a882-90795dfb492b"
# # user_id = "ba872a82-cbe8-42d9-80b7-59be02f08f11"
# # user_name = "Anmol"
# # for u in users:
# #     print(u["fullName"])
# #     print(u["user_id"])
# #     timestamp = "2026-02-25T05:38:37.313+00:00"
# #     # ggb.fetch_trello(u["user_id"], u["fullName"])
# # ggb5.fetch_trello(user_id)

# #Autopilot------------------------------


# import generate_autopilot as ggb

# db= get_mongo_client("unified_workspace")
# users= db["users"].find({"user_id": "ba872a82-cbe8-42d9-80b7-59be02f08f11"})
# # user_id = "cf9fcaf6-6a72-4bcc-a882-90795dfb492b"
# user_id = "ba872a82-cbe8-42d9-80b7-59be02f08f11"
# user_name = "Soma"
# for u in users:
#     print(u["fullName"])
#     print(u["user_id"])
#     timestamp = "2026-03-04T05:38:37.313+00:00"
#     # ggb.fetch_trello(u["user_id"], u["fullName"])
# ggb6.generate_autopilot_drafts_task(user_id, timestamp)

# Scheduled Emails------------------------------

# import send_schedule_email as ggb
# user_id = "600"
# user_name = "Kanishk"
# ggb.send_scheduled_emails_task(user_id, user_name)