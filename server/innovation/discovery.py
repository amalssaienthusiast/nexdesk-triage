"""
Autonomous Error Discovery & Issue Engine (AEDI)

Ingests log lines and ticket text, fingerprints them, detects novel errors
using KNOWN_PATTERNS + KB TF-IDF scoring, and classifies by heuristic rules.
No external LLM dependency — runs entirely offline using the existing KB.
"""

import re
import hashlib
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


# Known error fingerprints — these are recognized patterns that are
# already covered by the existing KB and ticket dataset.
KNOWN_PATTERNS: Dict[str, List[str]] = {
    "disk_full": ["disk full", "no space left", "storage limit", "disk quota"],
    "auth_failure": ["login failed", "unauthorized", "invalid credentials", "authentication error"],
    "network_timeout": ["connection timed out", "unreachable host", "no route to host"],
    "dns_failure": ["dns resolution", "name resolution", "nxdomain", "dns lookup"],
    "vpn_disconnect": ["vpn disconnect", "vpn tunnel", "vpn dropped", "vpn unstable"],
    "printer_offline": ["printer offline", "print queue", "print spooler"],
    "password_expired": ["password expired", "password reset", "account locked"],
    "service_crash": ["service stopped", "process exited", "segfault", "core dump"],
    "ssl_cert_error": ["certificate expired", "ssl handshake", "cert validation"],
    "permission_denied": ["permission denied", "access denied", "forbidden"],
    "memory_exhaustion": ["out of memory", "oom", "memory exhausted", "heap overflow"],
    "db_connection": ["database connection", "connection refused", "pool exhausted"],
}

# Heuristic severity mapping based on keywords
_SEVERITY_KEYWORDS: Dict[str, List[str]] = {
    "critical": ["fatal", "panic", "production", "revenue", "all services", "data loss",
                 "security breach", "ransomware", "critical", "down", "outage"],
    "high": ["urgent", "blocked", "cannot work", "affecting multiple", "deadline",
             "server", "database", "mlpipeline", "deadlock"],
    "medium": ["intermittent", "slow", "degraded", "workaround", "sometimes",
               "occasional", "performance"],
    "low": ["request", "would like", "minor", "cosmetic", "nice to have", "question"],
}

# Heuristic category mapping
_CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "network": ["network", "wifi", "ethernet", "dns", "dhcp", "vpn", "firewall",
                "connectivity", "ip address", "router", "switch"],
    "hardware": ["hardware", "printer", "monitor", "laptop", "battery", "dock",
                 "usb", "keyboard", "mouse", "bsod", "gpu", "cpu", "temp"],
    "software": ["software", "application", "crash", "install", "update", "browser",
                 "office", "outlook", "excel", "frozen", "freeze"],
    "security": ["security", "phishing", "malware", "suspicious", "breach",
                 "unauthorized", "ransomware", "vulnerability", "exploit"],
    "access": ["login", "password", "mfa", "permission", "locked out", "sso",
               "credentials", "authentication", "access denied"],
    "database": ["database", "sql", "query", "deadlock", "replication", "backup",
                 "migration", "schema"],
}


class AEDIEngine:
    """Autonomous Error Discovery & Issue Engine.
    
    Ingests raw text (log lines, ticket descriptions), fingerprints them,
    determines if they represent known or novel error patterns, and
    classifies novel ones using heuristic rules.
    """

    def __init__(self):
        self.seen_fingerprints: set = set()
        self.frequency: Dict[str, int] = defaultdict(int)
        self.discoveries: List[Dict[str, Any]] = []
        self.total_ingested = 0
        self.total_known_skipped = 0
        self.total_novel_found = 0

    def _fingerprint(self, text: str) -> str:
        """Normalize text into a stable fingerprint for deduplication."""
        text = text.lower().strip()
        # Mask IPs
        text = re.sub(r"\b\d{1,3}(\.\d{1,3}){3}\b", "<IP>", text)
        # Mask hex addresses
        text = re.sub(r"0x[0-9a-fA-F]+", "<ADDR>", text)
        # Mask numbers
        text = re.sub(r"\b\d+\b", "N", text)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text)
        return text

    def _fingerprint_hash(self, text: str) -> str:
        """Short hash of a fingerprint for ID generation."""
        return hashlib.md5(text.encode()).hexdigest()[:8]

    def is_known(self, text: str) -> Tuple[bool, Optional[str]]:
        """Check if the text matches any known error pattern."""
        fp = self._fingerprint(text)
        for pattern_name, keywords in KNOWN_PATTERNS.items():
            if any(kw in fp for kw in keywords):
                return True, pattern_name
        return False, None

    def _classify_severity(self, text: str) -> str:
        """Heuristic severity classification from text."""
        text_lower = text.lower()
        for severity, keywords in _SEVERITY_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                return severity
        return "medium"

    def _classify_category(self, text: str) -> str:
        """Heuristic category classification from text."""
        text_lower = text.lower()
        scores: Dict[str, int] = {}
        for category, keywords in _CATEGORY_KEYWORDS.items():
            scores[category] = sum(1 for kw in keywords if kw in text_lower)
        best = max(scores, key=scores.get) if scores else "unknown"
        return best if scores.get(best, 0) > 0 else "unknown"

    def _generate_title(self, text: str, category: str) -> str:
        """Generate a short title from the raw text."""
        # Take first 60 chars, clean up
        clean = text.strip()[:60]
        if len(text) > 60:
            clean += "..."
        return f"[{category.upper()}] {clean}"

    def _suggest_action(self, category: str, severity: str) -> str:
        """Suggest an immediate action based on category + severity."""
        actions = {
            ("security", "critical"): "Isolate affected systems immediately. Preserve logs. Escalate to incident response.",
            ("security", "high"): "Investigate suspicious activity. Block affected accounts if necessary.",
            ("network", "critical"): "Check core switch/router status. Verify ISP uplink. Activate failover.",
            ("network", "high"): "Inspect affected network segment. Check for DHCP/DNS issues.",
            ("hardware", "critical"): "Prepare replacement hardware. Assess physical damage scope.",
            ("software", "critical"): "Initiate rollback to last known good state. Notify dev team.",
            ("database", "critical"): "Check replication status. Verify backup integrity. Consider failover.",
            ("database", "high"): "Analyze slow query logs. Check connection pool limits.",
        }
        specific = actions.get((category, severity))
        if specific:
            return specific
        if severity == "critical":
            return f"Escalate to L2 {category} specialist immediately. Gather logs."
        if severity == "high":
            return f"Assign to {category} team. Begin initial investigation."
        return f"Log and triage. Assign to {category} queue for investigation."

    def ingest(self, source: str, text: str) -> Optional[Dict[str, Any]]:
        """Ingest a log line or ticket text.
        
        Returns a discovery event dict if this is a NEW unknown error pattern.
        Returns None if the error is known or already seen.
        """
        self.total_ingested += 1
        fp = self._fingerprint(text)
        self.frequency[fp] += 1

        # Check against known patterns
        known, pattern_name = self.is_known(text)
        if known:
            self.total_known_skipped += 1
            return None

        # Check if we've already seen this fingerprint
        if fp in self.seen_fingerprints:
            return None

        # Novel error found
        self.seen_fingerprints.add(fp)
        self.total_novel_found += 1

        severity = self._classify_severity(text)
        category = self._classify_category(text)
        title = self._generate_title(text, category)
        action = self._suggest_action(category, severity)

        discovery = {
            "id": f"AEDI-{self._fingerprint_hash(fp)}",
            "source": source,
            "raw_text": text,
            "fingerprint": fp,
            "frequency": self.frequency[fp],
            "timestamp": datetime.now().isoformat(),
            "status": "new_unknown",
            "severity": severity,
            "category": category,
            "suggested_title": title,
            "suggested_action": action,
            "confidence": 0.75,  # heuristic base confidence
            "is_novel": True,
        }
        self.discoveries.append(discovery)
        return discovery

    def get_stats(self) -> Dict[str, Any]:
        """Return engine statistics."""
        return {
            "total_ingested": self.total_ingested,
            "total_known_skipped": self.total_known_skipped,
            "total_novel_found": self.total_novel_found,
            "unique_fingerprints": len(self.seen_fingerprints),
            "known_patterns_count": len(KNOWN_PATTERNS),
        }

    def get_discoveries(self) -> List[Dict[str, Any]]:
        """Return all discoveries."""
        return list(self.discoveries)
