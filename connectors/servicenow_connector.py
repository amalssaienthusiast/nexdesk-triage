# servicenow connector for NexDesk shadow testing
# pulls ServiceNow incidents and converts them to NexDesk ticket format
# includes mock mode with realistic sample data for demo purposes

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── ServiceNow Impact → NexDesk Priority Mapping ──
# Impact: 1=High, 2=Medium, 3=Low
# Urgency: 1=High, 2=Medium, 3=Low
# Priority = Impact × Urgency matrix
SNOW_PRIORITY_MAP = {
    1: "critical",   # P1: Critical
    2: "high",       # P2: High
    3: "medium",     # P3: Moderate
    4: "low",        # P4: Low
    5: "low",        # P5: Planning
}

# ── Category mapping from ServiceNow categories ──
SNOW_CATEGORY_MAP = {
    "network": "network",
    "hardware": "hardware",
    "software": "software",
    "database": "software",
    "email": "access",
    "request": "other",
    "inquiry": "other",
    "security": "security",
}

# ── Mock ServiceNow Incidents ──
MOCK_SNOW_INCIDENTS = [
    {
        "sys_id": "a1b2c3d4e5f6",
        "number": "INC0012345",
        "short_description": "VPN gateway overloaded — 200+ remote users affected",
        "description": (
            "The primary VPN gateway (vpn-gw-01) is showing 98% CPU utilization. "
            "Remote workers are experiencing extremely slow connections or complete "
            "inability to connect. This started at 08:15 when the East Coast office "
            "came online. Failover gateway is not configured. Approx 200 users impacted."
        ),
        "priority": 1,
        "impact": 1,
        "urgency": 1,
        "state": 2,  # In Progress
        "category": "Network",
        "subcategory": "VPN",
        "assignment_group": {"display_value": "Network Operations"},
        "caller_id": {"display_value": "James Rodriguez"},
        "sys_created_on": "2025-04-07T08:20:00Z",
        "business_service": {"display_value": "Remote Access VPN"},
        "cmdb_ci": {"display_value": "vpn-gw-01"},
        "company": {"display_value": "Acme Corp"},
        "u_department": "IT Operations",
    },
    {
        "sys_id": "b2c3d4e5f6a1",
        "number": "INC0012346",
        "short_description": "Exchange server mailbox database dismounted",
        "description": (
            "Exchange 2019 server EX-PROD-02 has its primary mailbox database dismounted. "
            "Approximately 500 users have lost email access. Event log shows ESE error -1022 "
            "(disk read error). Database: MDB-PROD-02, size: 450GB. No recent backup failures."
        ),
        "priority": 1,
        "impact": 1,
        "urgency": 1,
        "state": 1,  # New
        "category": "Email",
        "subcategory": "Exchange",
        "assignment_group": {"display_value": "Messaging Team"},
        "caller_id": {"display_value": "Monitoring Alert"},
        "sys_created_on": "2025-04-07T06:45:00Z",
        "business_service": {"display_value": "Corporate Email"},
        "cmdb_ci": {"display_value": "EX-PROD-02"},
        "company": {"display_value": "Acme Corp"},
        "u_department": "Engineering",
    },
    {
        "sys_id": "c3d4e5f6a1b2",
        "number": "INC0012347",
        "short_description": "End user laptop Blue Screen of Death (BSOD)",
        "description": (
            "User reports frequent BSOD with IRQL_NOT_LESS_OR_EQUAL stop code. "
            "Happens 2-3 times per day, usually when docking/undocking. "
            "Laptop: Lenovo ThinkPad T14s, 1 year old. Windows 11 22H2. "
            "Minidump files available at C:\\Windows\\Minidump."
        ),
        "priority": 3,
        "impact": 3,
        "urgency": 2,
        "state": 1,
        "category": "Hardware",
        "subcategory": "Laptop",
        "assignment_group": {"display_value": "Desktop Support"},
        "caller_id": {"display_value": "Emily Watson"},
        "sys_created_on": "2025-04-07T10:30:00Z",
        "business_service": {"display_value": "End User Computing"},
        "cmdb_ci": {"display_value": "LT-T14S-4421"},
        "company": {"display_value": "Acme Corp"},
        "u_department": "Finance",
    },
    {
        "sys_id": "d4e5f6a1b2c3",
        "number": "INC0012348",
        "short_description": "Ransomware detected on shared file server",
        "description": (
            "CrowdStrike Falcon has alerted on file encryption activity on FS-SHARED-01. "
            "Multiple .locked file extensions appearing in the Finance shared drive. "
            "Process: svchost.exe (suspicious child process tree). "
            "Server has been automatically isolated by EDR. No ransom note found yet."
        ),
        "priority": 1,
        "impact": 1,
        "urgency": 1,
        "state": 2,
        "category": "Security",
        "subcategory": "Malware",
        "assignment_group": {"display_value": "Security Operations"},
        "caller_id": {"display_value": "CrowdStrike Alert"},
        "sys_created_on": "2025-04-07T15:02:00Z",
        "business_service": {"display_value": "File Services"},
        "cmdb_ci": {"display_value": "FS-SHARED-01"},
        "company": {"display_value": "Acme Corp"},
        "u_department": "IT Security",
    },
    {
        "sys_id": "e5f6a1b2c3d4",
        "number": "INC0012349",
        "short_description": "New hire onboarding — accounts and equipment needed",
        "description": (
            "New hire starting Monday: Dr. Sarah Kim, joining Research team as Senior Data Scientist. "
            "Needs: MacBook Pro M3, Python/Jupyter/Docker setup, AWS console access (IAM role: DataSciProd), "
            "VPN config, Slack workspace invite, building badge. Manager: Dr. James Liu."
        ),
        "priority": 4,
        "impact": 3,
        "urgency": 3,
        "state": 1,
        "category": "Request",
        "subcategory": "Onboarding",
        "assignment_group": {"display_value": "IT Service Desk"},
        "caller_id": {"display_value": "HR System"},
        "sys_created_on": "2025-04-07T09:00:00Z",
        "business_service": {"display_value": "Employee Onboarding"},
        "cmdb_ci": {"display_value": "N/A"},
        "company": {"display_value": "Acme Corp"},
        "u_department": "HR",
    },
]


class ServiceNowAdapter:
    """
    Adapter that connects to ServiceNow and converts incidents
    into NexDesk-compatible ticket format for shadow testing.

    Supports both live Table API mode and mock mode (default).

    Usage:
        adapter = ServiceNowAdapter(mode="mock")
        tickets = adapter.fetch_tickets(limit=10)
    """

    def __init__(
        self,
        instance_url: str = "",
        username: str = "",
        password: str = "",
        mode: str = "mock",
        table: str = "incident",
    ):
        self.instance_url = instance_url.rstrip("/")
        self.username = username
        self.password = password
        self.mode = mode
        self.table = table
        self._counter = 0

    def fetch_tickets(self, limit: int = 10, query: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Fetch incidents from ServiceNow and convert to NexDesk format.

        Args:
            limit: Maximum number of incidents to fetch
            query: Optional encoded query string (only for live mode)

        Returns:
            List of NexDesk-compatible ticket dicts
        """
        if self.mode == "mock":
            return self._fetch_mock(limit)
        return self._fetch_live(limit, query)

    def _fetch_mock(self, limit: int) -> List[Dict[str, Any]]:
        """Return mock ServiceNow incidents converted to NexDesk format."""
        incidents = MOCK_SNOW_INCIDENTS[:limit]
        return [self._convert_incident(inc) for inc in incidents]

    def _fetch_live(self, limit: int, query: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch real incidents from ServiceNow Table API."""
        try:
            import requests

            if not query:
                query = "stateIN1,2,3^ORDERBYDESCpriority"

            url = f"{self.instance_url}/api/now/table/{self.table}"
            auth = (self.username, self.password)
            headers = {"Accept": "application/json"}
            params = {
                "sysparm_query": query,
                "sysparm_limit": limit,
                "sysparm_display_value": "true",
                "sysparm_fields": (
                    "sys_id,number,short_description,description,priority,impact,urgency,"
                    "state,category,subcategory,assignment_group,caller_id,sys_created_on,"
                    "business_service,cmdb_ci,company,u_department"
                ),
            }

            response = requests.get(url, params=params, auth=auth, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()

            return [self._convert_incident(inc) for inc in data.get("result", [])]

        except ImportError:
            logger.error("requests library required for live ServiceNow mode")
            return self._fetch_mock(limit)
        except Exception as e:
            logger.error(f"ServiceNow API error: {e}")
            return self._fetch_mock(limit)

    def _convert_incident(self, incident: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a ServiceNow incident to NexDesk ticket format."""
        self._counter += 1

        short_desc = incident.get("short_description", "Untitled Incident")
        description = incident.get("description", short_desc)
        priority_num = incident.get("priority", 3)
        if isinstance(priority_num, str):
            try:
                priority_num = int(priority_num[0]) if priority_num else 3
            except (ValueError, IndexError):
                priority_num = 3

        caller = incident.get("caller_id", {})
        if isinstance(caller, dict):
            submitter = caller.get("display_value", "Unknown")
        else:
            submitter = str(caller) or "Unknown"

        assignment = incident.get("assignment_group", {})
        if isinstance(assignment, dict):
            group_name = assignment.get("display_value", "")
        else:
            group_name = str(assignment)

        department = incident.get("u_department", "IT")
        created = incident.get("sys_created_on", datetime.now(timezone.utc).isoformat())

        category_raw = (incident.get("category") or "other").lower()
        category = SNOW_CATEGORY_MAP.get(category_raw, "other")
        priority = SNOW_PRIORITY_MAP.get(priority_num, "medium")

        ci = incident.get("cmdb_ci", {})
        if isinstance(ci, dict):
            affected_system = ci.get("display_value", "unknown")
        else:
            affected_system = str(ci) or "unknown"

        team = self._infer_team(category, group_name)

        return {
            "id": f"SNOW-{incident.get('number', self._counter)}",
            "subject": short_desc,
            "description": description[:500] if description else short_desc,
            "submitter": submitter,
            "department": department if isinstance(department, str) else "IT",
            "submitted_at": created,
            "gt_priority": priority,
            "gt_priority_ok": self._priority_alternatives(priority),
            "gt_category": category,
            "gt_category_ok": [],
            "gt_team": team,
            "gt_team_ok": self._team_alternatives(team),
            "gt_affected_system": affected_system if affected_system != "N/A" else "workstation",
            "gt_sla_hours": self._estimate_sla(priority_num),
            "gt_keywords_response": ["investigating", "help", "update", "priority"],
            "gt_keywords_resolution": self._infer_resolution_keywords(category),
            "_source": "servicenow",
            "_snow_number": incident.get("number", ""),
            "_snow_sys_id": incident.get("sys_id", ""),
        }

    def _infer_team(self, category: str, group_name: str) -> str:
        """Infer NexDesk team from category and ServiceNow assignment group."""
        group_lower = group_name.lower()
        if "network" in group_lower:
            return "network-ops"
        if "security" in group_lower or "soc" in group_lower:
            return "security"
        if "desktop" in group_lower or "service desk" in group_lower:
            return "helpdesk"
        if "messaging" in group_lower or "server" in group_lower:
            return "sysadmin"
        if "development" in group_lower or "app" in group_lower:
            return "dev"
        # Fallback to category-based
        mapping = {
            "network": "network-ops",
            "hardware": "helpdesk",
            "software": "helpdesk",
            "access": "sysadmin",
            "security": "security",
            "other": "helpdesk",
        }
        return mapping.get(category, "helpdesk")

    def _priority_alternatives(self, priority: str) -> List[str]:
        alts = {"critical": [], "high": ["critical", "medium"], "medium": ["high"], "low": ["medium"]}
        return alts.get(priority, [])

    def _team_alternatives(self, team: str) -> List[str]:
        alts = {
            "network-ops": ["sysadmin"],
            "helpdesk": ["sysadmin"],
            "sysadmin": ["helpdesk"],
            "security": [],
            "dev": ["sysadmin"],
        }
        return alts.get(team, [])

    def _estimate_sla(self, priority_num: int) -> int:
        sla = {1: 1, 2: 4, 3: 8, 4: 24, 5: 48}
        return sla.get(priority_num, 8)

    def _infer_resolution_keywords(self, category: str) -> List[str]:
        keywords = {
            "network": ["connectivity", "restart", "failover", "config", "dns"],
            "hardware": ["replacement", "driver", "firmware", "repair", "diagnostics"],
            "software": ["reinstall", "update", "repair", "cache", "rollback"],
            "access": ["permissions", "reset", "unlock", "provisioning", "mfa"],
            "security": ["contain", "quarantine", "forensic", "incident response", "block"],
            "other": ["investigate", "documentation", "redirect"],
        }
        return keywords.get(category, ["investigate"])

    def get_info(self) -> Dict[str, Any]:
        """Return adapter configuration info."""
        return {
            "adapter": "servicenow",
            "mode": self.mode,
            "instance_url": self.instance_url or "(mock)",
            "table": self.table,
            "mock_incidents_available": len(MOCK_SNOW_INCIDENTS),
        }
