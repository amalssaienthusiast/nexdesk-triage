# synthetic ticket generator for NexDesk
# template-based with optional LLM-powered generation
# produces infinite diverse tickets that never repeat

import hashlib
import logging
import os
import random
import string
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Personality traits for synthetic submitters ──
_TONES = ["angry", "panicked", "calm", "informal", "technical", "vague", "demanding", "apologetic"]
_DEPARTMENTS = ["Engineering", "Sales", "Marketing", "Finance", "HR", "Legal", "Operations", "Design", "IT Security", "Customer Success"]
_FIRST_NAMES = ["Alex", "Jordan", "Sam", "Morgan", "Casey", "Riley", "Taylor", "Quinn", "Avery", "Dakota", "Priya", "Wei", "Fatima", "Carlos", "Arjun", "Elena", "Marcus", "Aisha", "David", "Nicole"]
_LAST_NAMES = ["Johnson", "Chen", "Patel", "Williams", "Martinez", "Kim", "Okonkwo", "Thompson", "Santos", "Al-Hassan", "Mehta", "Foster", "Turner", "Anderson", "Lee", "Green", "Hernandez", "Miller", "Wu", "Vasquez"]

# ── Ticket templates by category ──
_TEMPLATES: Dict[str, List[Dict[str, Any]]] = {
    "network": [
        {
            "subject_tpl": "{severity_prefix}Cannot connect to {network_resource}",
            "description_tpl": "My {device} {cant_connect} to {network_resource} since {time_ago}. {impact_statement} {extra_detail}",
            "gt_affected_system_options": ["laptop", "desktop", "wifi", "VPN", "ethernet"],
            "gt_keywords_response": ["looking into", "connectivity", "investigate", "help"],
            "gt_keywords_resolution": ["wifi", "driver", "ip", "dhcp", "network adapter", "cable", "dns", "reconnect"],
            "gt_team": "network-ops",
            "gt_team_ok": ["helpdesk", "sysadmin"],
            "gt_sla_hours_range": [2, 8],
        },
        {
            "subject_tpl": "{severity_prefix}VPN keeps {vpn_problem}",
            "description_tpl": "Working from home and my VPN {vpn_problem_detail}. {impact_statement} Using {vpn_client} on {os}. {extra_detail}",
            "gt_affected_system_options": ["VPN"],
            "gt_keywords_response": ["vpn", "remote", "investigate", "help"],
            "gt_keywords_resolution": ["openvpn", "config", "keepalive", "timeout", "split tunnel", "logs", "reinstall"],
            "gt_team": "network-ops",
            "gt_team_ok": ["helpdesk", "sysadmin"],
            "gt_sla_hours_range": [4, 12],
        },
    ],
    "hardware": [
        {
            "subject_tpl": "{severity_prefix}{hardware_device} {hardware_problem}",
            "description_tpl": "My {hardware_device} {hardware_problem_detail}. {impact_statement} {device_info}",
            "gt_affected_system_options": ["laptop", "desktop", "monitor", "printer", "mouse", "keyboard"],
            "gt_keywords_response": ["replacement", "check", "diagnose", "help"],
            "gt_keywords_resolution": ["power supply", "cable", "driver", "replacement", "firmware", "hardware"],
            "gt_team": "helpdesk",
            "gt_team_ok": ["sysadmin"],
            "gt_sla_hours_range": [4, 48],
        },
    ],
    "software": [
        {
            "subject_tpl": "{severity_prefix}{software_app} {software_problem}",
            "description_tpl": "{software_app} {software_problem_detail}. {impact_statement} Running on {os}. {extra_detail}",
            "gt_affected_system_options": ["Excel", "Outlook", "Slack", "Zoom", "CRM", "Teams"],
            "gt_keywords_response": ["troubleshoot", "investigating", "help", "update"],
            "gt_keywords_resolution": ["reinstall", "update", "cache", "repair", "compatibility", "permissions"],
            "gt_team": "helpdesk",
            "gt_team_ok": ["dev", "sysadmin"],
            "gt_sla_hours_range": [4, 24],
        },
    ],
    "access": [
        {
            "subject_tpl": "{severity_prefix}Can't {access_action} {access_resource}",
            "description_tpl": "I'm unable to {access_action} {access_resource}. {access_detail} {impact_statement}",
            "gt_affected_system_options": ["email", "SSO", "MFA", "shared drive", "Salesforce", "VPN"],
            "gt_keywords_response": ["access", "verify", "reset", "help"],
            "gt_keywords_resolution": ["password reset", "mfa", "active directory", "permissions", "unlock", "sso"],
            "gt_team": "helpdesk",
            "gt_team_ok": ["sysadmin", "security"],
            "gt_sla_hours_range": [2, 8],
        },
    ],
    "security": [
        {
            "subject_tpl": "{severity_prefix}{security_event}",
            "description_tpl": "{security_detail} {impact_statement} {extra_detail}",
            "gt_affected_system_options": ["email", "admin account", "workstation", "laptop", "server"],
            "gt_keywords_response": ["immediately", "block", "investigate", "incident"],
            "gt_keywords_resolution": ["disable account", "block ip", "audit logs", "forensic", "incident response", "quarantine"],
            "gt_team": "security",
            "gt_team_ok": [],
            "gt_sla_hours_range": [1, 4],
        },
    ],
    "other": [
        {
            "subject_tpl": "{other_subject}",
            "description_tpl": "{other_description} {extra_detail}",
            "gt_affected_system_options": ["Concur", "thermostat", "project management tool"],
            "gt_keywords_response": ["help", "guide", "assist"],
            "gt_keywords_resolution": ["documentation", "knowledge base", "training", "redirect"],
            "gt_team": "helpdesk",
            "gt_team_ok": [],
            "gt_sla_hours_range": [24, 72],
        },
    ],
}

# ── Fill-in fragments ──
_FRAGMENTS = {
    "severity_prefix": {
        "critical": ["URGENT: ", "CRITICAL: ", "EMERGENCY — ", "🚨 "],
        "high": ["IMPORTANT: ", "HIGH PRIORITY: ", ""],
        "medium": ["", ""],
        "low": ["", "FYI: "],
    },
    "network_resource": ["the internet", "the company network", "WiFi", "internal servers", "the intranet", "our cloud services"],
    "cant_connect": ["can't connect", "is unable to connect", "stopped connecting", "fails to connect", "has no connectivity"],
    "device": ["laptop", "desktop", "MacBook", "ThinkPad", "Dell workstation"],
    "vpn_problem": ["disconnecting", "dropping randomly", "failing to connect", "timing out"],
    "vpn_problem_detail": ["keeps dropping every few minutes", "disconnects after 2-3 minutes", "won't establish a connection at all", "connects briefly then drops"],
    "vpn_client": ["OpenVPN", "Cisco AnyConnect", "WireGuard", "the company VPN client"],
    "os": ["Windows 11", "Windows 10", "macOS Sonoma", "macOS Ventura", "Ubuntu 22.04"],
    "hardware_device": ["laptop", "monitor", "desktop", "keyboard", "printer", "mouse"],
    "hardware_problem": ["not turning on", "screen flickering", "making loud noise", "completely dead", "overheating"],
    "hardware_problem_detail": ["won't power on at all — no lights, no fan", "the screen flickers every few seconds", "is making a grinding noise from the fan area", "has been intermittently shutting down", "gets extremely hot after 15 minutes"],
    "device_info": ["It's a Dell laptop, about 2 years old.", "ThinkPad X1 Carbon.", "HP EliteBook.", "MacBook Pro 16-inch.", "It's a standard issue workstation."],
    "software_app": ["Excel", "Outlook", "Slack", "Zoom", "Teams", "Chrome", "VS Code"],
    "software_problem": ["keeps crashing", "won't open", "is extremely slow", "showing errors", "freezing constantly"],
    "software_problem_detail": ["crashes every time I try to open large files", "won't launch — just shows a loading spinner forever", "has become unbearably slow since the last update", "shows a cryptic error code and closes itself", "freezes for 30 seconds whenever I switch tabs"],
    "access_action": ["log into", "access", "connect to", "open", "use"],
    "access_resource": ["my email", "Salesforce", "the shared drive", "our SSO portal", "Jira", "the admin panel"],
    "access_detail": ["My account seems to be locked out.", "It says my password expired.", "MFA codes aren't arriving.", "I get an 'Access Denied' error.", "It says my account has been disabled."],
    "security_event": ["Suspicious login attempts detected", "Possible phishing email reported", "Unusual network activity flagged", "Data breach suspected", "Malware alert on workstation"],
    "security_detail": ["Our SIEM flagged multiple failed login attempts from an unknown IP range.", "Several employees received suspicious emails asking for credential verification.", "Firewall logs show unusual outbound traffic from a department workstation.", "Sensitive files appear to have been accessed from an unauthorized device.", "Antivirus flagged a suspicious executable running in the background."],
    "other_subject": ["How do I use the new expense system?", "Conference room booking issue", "Request for software demo", "Office temperature complaint", "General IT inquiry"],
    "other_description": ["I need help with the new internal tool.", "The booking system isn't letting me reserve Room B.", "Can our team get a demo of the new project management tool?", "The AC in our wing has been broken for days.", "I have a general question about our IT policies."],
    "impact_statement": [
        "I have a deadline today.",
        "This is blocking my work completely.",
        "Multiple people on my team are affected.",
        "No rush, but would appreciate help when available.",
        "I have a client meeting in an hour.",
        "This is impacting about 20 people on our floor.",
        "I need this resolved before end of day.",
        "",
    ],
    "extra_detail": [
        "I've already tried restarting.",
        "Let me know if you need remote access to check.",
        "My asset tag is WS-{rand_digits}.",
        "I've tried the basic troubleshooting steps.",
        "This started happening after the last update.",
        "",
        "",
    ],
    "time_ago": ["this morning", "about an hour ago", "yesterday afternoon", "since Monday", "30 minutes ago", "last night"],
}

# Priority weights for random generation
_PRIORITY_WEIGHTS = {
    "critical": 0.1,
    "high": 0.25,
    "medium": 0.4,
    "low": 0.25,
}


class SyntheticTicketGenerator:
    """
    Generates infinite, unique IT support tickets using parameterized templates.

    No two generated tickets are identical thanks to combinatorial randomization of:
    - Category, priority, tone, submitter personality
    - Description fragments, device types, software apps
    - Impact statements and extra detail fragments

    Ground truth labels are deterministically derived from the template metadata,
    ensuring generated tickets can be graded by the existing NexDesk graders.
    """

    def __init__(self, seed: Optional[int] = None):
        self._rng = random.Random(seed)
        self._counter = 0

    def generate(self, count: int = 1) -> List[Dict[str, Any]]:
        """Generate `count` synthetic tickets."""
        return [self._generate_one() for _ in range(count)]

    def _generate_one(self) -> Dict[str, Any]:
        """Generate a single synthetic ticket with full ground truth."""
        self._counter += 1

        # Pick category and template
        category = self._rng.choice(list(_TEMPLATES.keys()))
        template = self._rng.choice(_TEMPLATES[category])

        # Pick priority
        priority = self._weighted_choice(_PRIORITY_WEIGHTS)

        # Pick tone
        tone = self._rng.choice(_TONES)

        # Build the ticket
        ticket_id = f"SYN-{self._counter:04d}"
        submitter = f"{self._rng.choice(_FIRST_NAMES)} {self._rng.choice(_LAST_NAMES)}"
        department = self._rng.choice(_DEPARTMENTS)

        # Generate time
        now = datetime.now(timezone.utc)
        offset = timedelta(minutes=self._rng.randint(0, 480))
        submitted_at = (now - offset).isoformat()

        # Fill in subject
        subject = self._fill_template(
            template["subject_tpl"],
            priority=priority,
        )

        # Fill in description
        description = self._fill_template(
            template["description_tpl"],
            priority=priority,
        )

        # Apply tone modification
        description = self._apply_tone(description, tone)

        # Ground truth
        gt_affected_system = self._rng.choice(template["gt_affected_system_options"])
        sla_range = template.get("gt_sla_hours_range", [4, 24])
        gt_sla_hours = self._rng.randint(sla_range[0], sla_range[1])

        # Adjust SLA by priority
        if priority == "critical":
            gt_sla_hours = max(1, gt_sla_hours // 4)
        elif priority == "high":
            gt_sla_hours = max(1, gt_sla_hours // 2)

        # Priority acceptable alternatives
        priority_ok = []
        if priority == "medium":
            priority_ok = ["high"]
        elif priority == "high":
            priority_ok = ["critical", "medium"]
        elif priority == "critical":
            priority_ok = []
        elif priority == "low":
            priority_ok = ["medium"]

        return {
            "id": ticket_id,
            "subject": subject.strip(),
            "description": description.strip(),
            "submitter": submitter,
            "department": department,
            "submitted_at": submitted_at,
            "gt_priority": priority,
            "gt_priority_ok": priority_ok,
            "gt_category": category,
            "gt_category_ok": template.get("gt_category_ok", []),
            "gt_team": template["gt_team"],
            "gt_team_ok": template.get("gt_team_ok", []),
            "gt_affected_system": gt_affected_system,
            "gt_sla_hours": gt_sla_hours,
            "gt_keywords_response": template["gt_keywords_response"],
            "gt_keywords_resolution": template["gt_keywords_resolution"],
            "_synthetic": True,
            "_tone": tone,
            "_seed": self._counter,
        }

    def _fill_template(self, tpl: str, priority: str = "medium") -> str:
        """Fill a template string with random fragments."""
        result = tpl
        # Handle severity prefix specially
        if "{severity_prefix}" in result:
            prefixes = _FRAGMENTS["severity_prefix"].get(priority, [""])
            result = result.replace("{severity_prefix}", self._rng.choice(prefixes))

        # Handle {rand_digits}
        if "{rand_digits}" in result:
            result = result.replace("{rand_digits}", str(self._rng.randint(1000, 9999)))

        # Fill all other fragment placeholders
        for key, options in _FRAGMENTS.items():
            placeholder = "{" + key + "}"
            if placeholder in result and isinstance(options, list):
                result = result.replace(placeholder, self._rng.choice(options))

        return result

    def _apply_tone(self, text: str, tone: str) -> str:
        """Apply a personality tone to the description text."""
        if tone == "angry":
            text = text.replace(".", "!!").replace("help", "help ASAP")
            text += " This is completely unacceptable."
        elif tone == "panicked":
            text = text.replace(".", "!!!").replace("I need", "I URGENTLY need")
            text += " PLEASE help this is critical."
        elif tone == "informal":
            text = text.lower()
            text = text.replace("i'm", "im").replace("i am", "im")
            text = text.replace("cannot", "cant").replace("will not", "wont")
            text += " thx!"
        elif tone == "vague":
            text += " Not sure what else to add. Something is just off."
        elif tone == "apologetic":
            text = "Sorry to bother you but " + text[0].lower() + text[1:]
            text += " I hope this isn't too much trouble."
        elif tone == "demanding":
            text += " I expect this to be resolved within the hour."
        # "calm" and "technical" keep the text as-is
        return text

    def _weighted_choice(self, weights: Dict[str, float]) -> str:
        """Weighted random selection."""
        items = list(weights.keys())
        probs = list(weights.values())
        return self._rng.choices(items, weights=probs, k=1)[0]
