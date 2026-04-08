# mcp_gmail/db/mongo_client.py
from pymongo import MongoClient
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
def get_mongo_client():
    client = MongoClient(MONGO_URI)
    return client

def get_mongo_client_by_db(db_name: str):
    client = MongoClient(MONGO_URI)
    return client[db_name]  # dynamically return the requested database
