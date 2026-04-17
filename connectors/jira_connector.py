# jira connector for NexDesk shadow testing
# pulls Jira Service Management issues and converts them to NexDesk ticket format
# includes mock mode with realistic sample data for demo purposes

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Priority Mapping ──
JIRA_PRIORITY_MAP = {
    "highest": "critical",
    "high": "high",
    "medium": "medium",
    "low": "low",
    "lowest": "low",
    "blocker": "critical",
    "critical": "critical",
    "major": "high",
    "minor": "low",
    "trivial": "low",
}

# ── Component / Label → Category Mapping ──
COMPONENT_CATEGORY_MAP = {
    "network": "network",
    "networking": "network",
    "vpn": "network",
    "wifi": "network",
    "connectivity": "network",
    "hardware": "hardware",
    "printer": "hardware",
    "laptop": "hardware",
    "desktop": "hardware",
    "monitor": "hardware",
    "software": "software",
    "application": "software",
    "app": "software",
    "database": "software",
    "email": "access",
    "access": "access",
    "permissions": "access",
    "login": "access",
    "password": "access",
    "security": "security",
    "phishing": "security",
    "malware": "security",
    "incident": "security",
}

# ── Mock Jira Issues ──
MOCK_JIRA_ISSUES = [
    {
        "key": "ITSM-1042",
        "fields": {
            "summary": "WiFi disconnects intermittently on Floor 2",
            "description": "Multiple users on Floor 2 report WiFi drops every 10-15 minutes. "
                           "Started after the weekend maintenance window. Approx 30 people affected. "
                           "AP model: Cisco Meraki MR46.",
            "priority": {"name": "High"},
            "status": {"name": "Open"},
            "issuetype": {"name": "Incident"},
            "reporter": {"displayName": "Tom Bradley", "emailAddress": "tom.bradley@company.com"},
            "components": [{"name": "Network"}],
            "labels": ["floor-2", "wifi"],
            "created": "2025-04-07T08:30:00.000+0000",
            "customfield_10020": "IT Support",  # department
        },
    },
    {
        "key": "ITSM-1043",
        "fields": {
            "summary": "Salesforce SSO login failure for Sales team",
            "description": "Entire sales team cannot log into Salesforce since 9 AM. "
                           "SSO redirects to error page. Azure AD side looks fine. "
                           "30+ sales reps blocked from CRM.",
            "priority": {"name": "Critical"},
            "status": {"name": "Open"},
            "issuetype": {"name": "Incident"},
            "reporter": {"displayName": "Lisa Park", "emailAddress": "lisa.park@company.com"},
            "components": [{"name": "Access"}],
            "labels": ["salesforce", "sso", "sales-blocking"],
            "created": "2025-04-07T09:05:00.000+0000",
            "customfield_10020": "Sales",
        },
    },
    {
        "key": "ITSM-1044",
        "fields": {
            "summary": "Request: Install Docker Desktop on dev workstation",
            "description": "New developer needs Docker Desktop installed on workstation WS-5501. "
                           "Manager approval obtained from Sarah Chen. Asset tag: WS-5501, Windows 11 Pro.",
            "priority": {"name": "Low"},
            "status": {"name": "To Do"},
            "issuetype": {"name": "Service Request"},
            "reporter": {"displayName": "Ravi Kumar", "emailAddress": "ravi.kumar@company.com"},
            "components": [{"name": "Software"}],
            "labels": ["software-install", "docker"],
            "created": "2025-04-07T10:20:00.000+0000",
            "customfield_10020": "Engineering",
        },
    },
    {
        "key": "ITSM-1045",
        "fields": {
            "summary": "Suspicious outbound traffic flagged by IDS",
            "description": "Intrusion Detection System flagged unusual outbound connections from "
                           "workstation WS-3302 to IP 45.33.32.156 on port 4444. User: Kevin Mills. "
                           "Possible C2 beacon pattern. No user-initiated activity at that time.",
            "priority": {"name": "Highest"},
            "status": {"name": "In Progress"},
            "issuetype": {"name": "Incident"},
            "reporter": {"displayName": "SOC Alert", "emailAddress": "soc@company.com"},
            "components": [{"name": "Security"}],
            "labels": ["ids", "c2", "investigation"],
            "created": "2025-04-07T14:45:00.000+0000",
            "customfield_10020": "IT Security",
        },
    },
    {
        "key": "ITSM-1046",
        "fields": {
            "summary": "Printer paper jam — HR department printer",
            "description": "HP OfficeJet Pro in HR has a paper jam that I can't clear. "
                           "There are important payroll documents queued. The display shows error E3.",
            "priority": {"name": "Medium"},
            "status": {"name": "Open"},
            "issuetype": {"name": "Incident"},
            "reporter": {"displayName": "Amanda Foster", "emailAddress": "amanda.foster@company.com"},
            "components": [{"name": "Hardware"}],
            "labels": ["printer", "paper-jam"],
            "created": "2025-04-07T11:15:00.000+0000",
            "customfield_10020": "HR",
        },
    },
]


class JiraTicketAdapter:
    """
    Adapter that connects to Jira Service Management and converts issues
    into NexDesk-compatible ticket format for shadow testing.

    Supports both live API mode and mock mode (default).

    Usage:
        adapter = JiraTicketAdapter(mode="mock")
        tickets = adapter.fetch_tickets(limit=10)
        # tickets are now in NexDesk format, ready for environment.reset()
    """

    def __init__(
        self,
        base_url: str = "",
        email: str = "",
        api_token: str = "",
        project_key: str = "ITSM",
        mode: str = "mock",
        department_field: str = "customfield_10020",
    ):
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.api_token = api_token
        self.project_key = project_key
        self.mode = mode
        self.department_field = department_field
        self._counter = 0

    def fetch_tickets(self, limit: int = 10, jql: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Fetch tickets from Jira and convert to NexDesk format.

        Args:
            limit: Maximum number of tickets to fetch
            jql: Optional JQL query (only for live mode)

        Returns:
            List of NexDesk-compatible ticket dicts
        """
        if self.mode == "mock":
            return self._fetch_mock(limit)
        return self._fetch_live(limit, jql)

    def _fetch_mock(self, limit: int) -> List[Dict[str, Any]]:
        """Return mock Jira issues converted to NexDesk format."""
        issues = MOCK_JIRA_ISSUES[:limit]
        return [self._convert_issue(issue) for issue in issues]

    def _fetch_live(self, limit: int, jql: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch real issues from Jira REST API."""
        try:
            import requests
            from requests.auth import HTTPBasicAuth

            if not jql:
                jql = f"project={self.project_key} AND status in (Open, 'To Do', 'In Progress') ORDER BY priority DESC, created DESC"

            url = f"{self.base_url}/rest/api/3/search"
            auth = HTTPBasicAuth(self.email, self.api_token)
            params = {
                "jql": jql,
                "maxResults": limit,
                "fields": "summary,description,priority,status,issuetype,reporter,components,labels,created," + self.department_field,
            }

            response = requests.get(url, params=params, auth=auth, timeout=30)
            response.raise_for_status()
            data = response.json()

            return [self._convert_issue(issue) for issue in data.get("issues", [])]

        except ImportError:
            logger.error("requests library required for live Jira mode")
            return self._fetch_mock(limit)
        except Exception as e:
            logger.error(f"Jira API error: {e}")
            return self._fetch_mock(limit)

    def _convert_issue(self, issue: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a Jira issue to NexDesk ticket format."""
        self._counter += 1
        fields = issue.get("fields", {})

        # Extract fields
        summary = fields.get("summary", "Untitled Issue")
        description = fields.get("description", "")
        if isinstance(description, dict):
            # Jira v3 ADF format — extract text
            description = self._extract_adf_text(description)

        priority_name = (fields.get("priority") or {}).get("name", "Medium").lower()
        reporter = (fields.get("reporter") or {}).get("displayName", "Unknown")
        department = fields.get(self.department_field, "IT")
        created = fields.get("created", datetime.now(timezone.utc).isoformat())

        # Map components/labels to category
        components = [c.get("name", "").lower() for c in (fields.get("components") or [])]
        labels = [l.lower() for l in (fields.get("labels") or [])]
        category = self._infer_category(components + labels)

        # Map priority
        priority = JIRA_PRIORITY_MAP.get(priority_name, "medium")

        # Infer team
        team = self._infer_team(category)

        # Build NexDesk ticket
        return {
            "id": f"JIRA-{issue.get('key', self._counter)}",
            "subject": summary,
            "description": description[:500] if description else summary,
            "submitter": reporter,
            "department": department if isinstance(department, str) else "IT",
            "submitted_at": created,
            "gt_priority": priority,
            "gt_priority_ok": self._priority_alternatives(priority),
            "gt_category": category,
            "gt_category_ok": [],
            "gt_team": team,
            "gt_team_ok": self._team_alternatives(team),
            "gt_affected_system": self._infer_affected_system(summary, description or ""),
            "gt_sla_hours": self._estimate_sla(priority),
            "gt_keywords_response": ["investigating", "looking into", "help", "update"],
            "gt_keywords_resolution": self._infer_resolution_keywords(category),
            "_source": "jira",
            "_jira_key": issue.get("key", ""),
        }

    def _infer_category(self, tags: List[str]) -> str:
        for tag in tags:
            tag_lower = tag.lower().strip()
            if tag_lower in COMPONENT_CATEGORY_MAP:
                return COMPONENT_CATEGORY_MAP[tag_lower]
        return "other"

    def _infer_team(self, category: str) -> str:
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

    def _estimate_sla(self, priority: str) -> int:
        sla = {"critical": 1, "high": 4, "medium": 8, "low": 24}
        return sla.get(priority, 8)

    def _infer_affected_system(self, summary: str, description: str) -> str:
        text = (summary + " " + description).lower()
        systems = [
            ("salesforce", "Salesforce"), ("email", "email"), ("vpn", "VPN"),
            ("wifi", "WiFi"), ("printer", "printer"), ("laptop", "laptop"),
            ("desktop", "desktop"), ("database", "database"), ("excel", "Excel"),
            ("zoom", "Zoom"), ("slack", "Slack"), ("docker", "Docker"),
        ]
        for keyword, system in systems:
            if keyword in text:
                return system
        return "workstation"

    def _infer_resolution_keywords(self, category: str) -> List[str]:
        keywords = {
            "network": ["connectivity", "dns", "dhcp", "cable", "restart"],
            "hardware": ["replacement", "driver", "firmware", "repair"],
            "software": ["reinstall", "update", "repair", "cache"],
            "access": ["permissions", "reset", "unlock", "mfa"],
            "security": ["block", "quarantine", "forensic", "incident"],
            "other": ["investigate", "redirect", "documentation"],
        }
        return keywords.get(category, ["investigate"])

    def _extract_adf_text(self, adf: Dict) -> str:
        """Extract plain text from Jira Atlassian Document Format."""
        if not isinstance(adf, dict):
            return str(adf)
        texts = []
        for node in adf.get("content", []):
            if node.get("type") == "paragraph":
                for child in node.get("content", []):
                    if child.get("type") == "text":
                        texts.append(child.get("text", ""))
        return " ".join(texts) if texts else str(adf)

    def get_info(self) -> Dict[str, Any]:
        """Return adapter configuration info."""
        return {
            "adapter": "jira",
            "mode": self.mode,
            "project_key": self.project_key,
            "base_url": self.base_url or "(mock)",
            "mock_issues_available": len(MOCK_JIRA_ISSUES),
        }
