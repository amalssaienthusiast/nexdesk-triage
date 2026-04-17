# NexDesk Shadow-Testing Connectors
# Adapter interfaces for pulling tickets from external ITSM platforms

from .jira_connector import JiraTicketAdapter
from .servicenow_connector import ServiceNowAdapter

__all__ = ["JiraTicketAdapter", "ServiceNowAdapter"]
