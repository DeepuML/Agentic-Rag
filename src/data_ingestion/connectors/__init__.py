"""src/data_ingestion/connectors/__init__.py"""
from src.data_ingestion.connectors.gmail_connector import GmailConnector
from src.data_ingestion.connectors.notion_connector import NotionConnector
from src.data_ingestion.connectors.jira_connector import JiraConnector

__all__ = ["GmailConnector", "NotionConnector", "JiraConnector"]
