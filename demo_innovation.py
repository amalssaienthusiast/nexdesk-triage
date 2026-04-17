#!/usr/bin/env python3
"""
AEDI Demo — Autonomous Error Discovery & Iterative Escalation
Standalone demo (no server needed). Run from project root:
    python demo_innovation.py
"""

import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server.innovation.discovery import AEDIEngine
from server.innovation.iteration import IterationEngine
from server.innovation.notifier import HelpdeskNotifier


def main():
    engine = AEDIEngine()
    iterator = IterationEngine()
    notifier = HelpdeskNotifier()

    # Simulated incoming logs and tickets — mix of known and novel
    inputs = [
        ("log",    "FATAL: kernel panic - quantum memory corruption at 0xDEADBEEF"),
        ("ticket", "User reports: application freezes when GPU temp exceeds 94C on Floor 3 workstations"),
        ("log",    "ERROR: disk full on /var/log — no space left on device"),  # known
        ("log",    "ERROR: connection timed out to auth.internal.corp"),       # known
        ("ticket", "WiFi disconnects only during video calls on Floor 3 — very strange"),
        ("log",    "CRITICAL: ML inference pipeline deadlock after model swap on gpu-node-07"),
        ("log",    "WARNING: login failed for user admin from 185.220.101.42"),  # known
        ("ticket", "Outlook calendar sync fails silently — meetings not appearing for 12 users"),
        ("log",    "ALERT: unusual lateral movement detected from compromised service account svc-backup"),
        ("ticket", "VPN keeps dropping every 5 minutes when connected to US-East gateway"),  # known
    ]

    discovered = {}

    print()
    print("=" * 70)
    print("  AEDI ENGINE — Autonomous Error Discovery & Iterative Escalation")
    print("=" * 70)

    # ── Phase 1: Error Discovery ──
    print("\n" + "─" * 70)
    print("  PHASE 1: ERROR DISCOVERY")
    print("─" * 70)

    for source, text in inputs:
        event = engine.ingest(source, text)
        if event:
            print(f"\n  [NOVEL] {event['id']} from {source}:")
            print(f"    Severity : {event['severity'].upper()}")
            print(f"    Category : {event['category']}")
            print(f"    Title    : {event['suggested_title']}")
            print(f"    Action   : {event['suggested_action'][:80]}")
            notifier.notify_new_issue(event)
            ticket_id = f"AUTO-{len(discovered) + 1:03d}"
            discovered[ticket_id] = event
        else:
            print(f"  [KNOWN/SKIP] {text[:60]}...")

    stats = engine.get_stats()
    print(f"\n  Discovery Stats:")
    print(f"    Total ingested     : {stats['total_ingested']}")
    print(f"    Known (skipped)    : {stats['total_known_skipped']}")
    print(f"    Novel (discovered) : {stats['total_novel_found']}")

    # ── Phase 2: Flag Unresolved ──
    print("\n" + "─" * 70)
    print("  PHASE 2: FLAGGING UNRESOLVED ISSUES")
    print("─" * 70)

    flag_reasons = [
        "agent_low_confidence",
        "resolution_timed_out",
        "user_reported_unresolved",
    ]

    for i, (tid, issue) in enumerate(list(discovered.items())[:3]):
        reason = flag_reasons[i % len(flag_reasons)]
        iterator.flag(tid, issue, reason=reason)
        print(f"  [FLAGGED] {tid}: {issue.get('suggested_title', '?')[:50]} — reason: {reason}")

    # ── Phase 3: Iteration Ladder ──
    print("\n" + "─" * 70)
    print("  PHASE 3: ITERATIVE ESCALATION")
    print("─" * 70)

    for tid in list(iterator.flagged_issues.keys()):
        print(f"\n  --- Ticket {tid} ---")
        for cycle in range(4):
            result = iterator.iterate(tid)
            action = result["action"]
            retry = result["retry_num"]
            severity = result["updated_issue"].get("severity", "?")

            icons = {
                "re_classify": "  [1] RE-CLASSIFY",
                "retry_new_strategy": "  [2] RETRY",
                "escalate_human": "  [3] ESCALATE TO HUMAN",
                "close_with_postmortem": "  [4] CLOSE + POST-MORTEM",
            }
            label = icons.get(action, f"  [?] {action}")
            print(f"    {label} (retry #{retry}, severity: {severity.upper()})")

            notifier.notify_iteration(tid, result)

            if action in ("escalate_human", "close_with_postmortem"):
                break

    # ── Phase 4: Summary ──
    print("\n" + "─" * 70)
    print("  PHASE 4: SUMMARY")
    print("─" * 70)

    iter_stats = iterator.get_stats()
    alert_stats = notifier.get_stats()

    print(f"\n  Iteration Engine:")
    print(f"    Flagged issues     : {iter_stats['total_flagged']}")
    print(f"    Total iterations   : {iter_stats['total_iterations']}")
    print(f"    Post-mortems       : {iter_stats['total_post_mortems']}")
    print(f"    Status breakdown   : {iter_stats['status_breakdown']}")

    print(f"\n  Alert System:")
    print(f"    Total alerts       : {alert_stats['total_alerts']}")
    print(f"    Alert types        : {alert_stats['alert_types']}")

    if iterator.get_post_mortems():
        print(f"\n  Post-Mortem Records:")
        for pm in iterator.get_post_mortems():
            print(f"    [{pm['ticket_id']}] {pm['title'][:50]}")
            print(f"      Original severity: {pm['original_severity']} -> Final: {pm['final_severity']}")
            print(f"      Total retries: {pm['total_retries']}, Outcome: {pm['outcome']}")

    print("\n" + "=" * 70)
    print("  AEDI DEMO COMPLETE")
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()
