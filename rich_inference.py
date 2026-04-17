# nexdesk rich terminal UI inference script
# beautiful TUI replacement for the standard inference.py
# uses the `rich` library for panels, tables, progress bars, and syntax highlighting

import json
import os
import re
import textwrap
import time
from typing import Any, Dict, List, Optional

import requests

try:
    from rich.console import Console
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
    from rich.syntax import Syntax
    from rich.table import Table
    from rich.text import Text
    from rich import box
except ImportError:
    raise ImportError(
        "rich is required for the TUI inference script. Install with: pip install rich>=13.0.0"
    )

try:
    from openai import OpenAI
except ImportError:
    raise ImportError("openai is required. Install with: pip install openai>=1.0.0")

# ── Console ──
console = Console()

# ── Env vars ──
API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")
HF_TOKEN = os.getenv("HF_TOKEN") or os.getenv("OPENAI_API_KEY")
ENV_BASE_URL = os.getenv("ENV_BASE_URL", "http://localhost:7860").rstrip("/")

BENCHMARK = "nexdesk-ticket-triage"
TEMPERATURE = 0.15
MAX_TOKENS = 768
MAX_RETRIES = 2

TASKS = ["ticket_classify", "ticket_route", "ticket_resolve", "crisis_surge"]
SUCCESS_THRESHOLDS = {
    "ticket_classify": 0.01,   # single-step, high variance on random tickets
    "ticket_route": 0.20,      # max avg: ~0.48
    "ticket_resolve": 0.04,    # max avg: ~0.33 (3-step, lots of variance)
    "crisis_surge": 0.05,      # max avg: ~0.14
}

TASK_EMOJIS = {
    "ticket_classify": "🏷️",
    "ticket_route": "🔀",
    "ticket_resolve": "🔧",
    "crisis_surge": "🚨",
}

TASK_DIFFICULTY = {
    "ticket_classify": "[green]Easy[/green]",
    "ticket_route": "[yellow]Medium[/yellow]",
    "ticket_resolve": "[red]Hard[/red]",
    "crisis_surge": "[bold red]Hard (Crisis)[/bold red]",
}

# ── Full Few-Shot Examples (from inference.py) ──
FEW_SHOTS = {
    "ticket_classify": """
Example ticket:
Subject: VPN disconnects every 5 minutes
Description: Working from home, VPN keeps dropping. Using OpenVPN on Windows 10.
Submitter: Jane (Legal)
Correct answer: {"plan": "User's VPN drops and they cannot work effectively. VPN is network related. Since it affects a single user, priority is medium.", "priority": "medium", "category": "network"}
""",
    "ticket_route_step1": """
Example ticket:
Subject: PRODUCTION SERVER DOWN
Description: Primary web server offline. All customer services down.
Correct answer: {"plan": "A production server is down causing all services to go offline. This is a critical network issue that requires immediate attention from the network operations team.", "priority": "critical", "category": "network", "team": "network-ops"}
""",
    "ticket_route_step2": """
Example ticket (step 2):
Subject: VPN disconnects every 5 minutes
Identify the primary system affected.
Correct answer: {"plan": "The issue is explicitly about the VPN connection dropping.", "affected_system": "VPN"}
""",
    "ticket_resolve_step1": """
Example ticket:
Subject: Excel keeps crashing when opening large files
Correct answer: {"plan": "Excel crashing is a software issue. Large files causing crashes affects productivity, giving it high priority. The helpdesk can assist with software repairs.", "priority": "high", "category": "software", "team": "helpdesk"}
""",
    "ticket_resolve_step2": """
Example ticket (step 2):
Subject: Excel keeps crashing when opening large files
Category: software, Priority: high, Team: helpdesk
Correct answer: {"plan": "The affected system is Excel. An empathetic first response is required to reassure the user.", "affected_system": "Excel", "first_response": "Hi Jennifer, I understand how frustrating this must be..."}
""",
    "ticket_resolve_step3": """
Example ticket (step 3):
Subject: Excel keeps crashing when opening large files
Correct answer: {"plan": "Standard helpdesk troubleshooting for Excel involves Safe Mode, checking hardware limits, and running a repair tool. This should take about a half day.", "resolution_steps": ["Open in Safe Mode", "Check RAM", "Run Quick Repair"], "sla_hours": 4}
""",
    "crisis_surge": """
CRISIS: You are handling tickets during a production outage. Prioritize critical tickets first.
Example ticket:
Subject: PRODUCTION SERVER DOWN — all services offline
Correct answer: {"plan": "This ticket matches the active crisis of a production server down. It gets the highest SLA urgency and goes straight to network-ops.", "priority": "critical", "category": "network", "team": "network-ops"}
""",
}

# ── System prompt (same as inference.py) ──
SYSTEM_PROMPT = textwrap.dedent("""\
    You are an expert IT helpdesk triage agent. Analyze the support ticket carefully.

    === PRIORITY CLASSIFICATION RULES (FOLLOW STRICTLY) ===
    - CRITICAL: Production systems down, revenue loss, security breach, ALL users affected, words like "URGENT", "DOWN", "revenue", "outage", "all services"
    - HIGH: Single user blocked from working, upcoming deadline mentioned, VIP/executive, words like "cannot work", "presentation", "urgent"
    - MEDIUM: Degraded functionality but workaround exists, intermittent issues, moderate impact
    - LOW: Minor inconvenience, cosmetic issue, feature request, "nice to have"

    === CATEGORY RULES ===
    - network: Internet, VPN, WiFi, DNS, DHCP, firewall, connectivity, server down
    - hardware: Physical device, printer, monitor, laptop, battery, dock, BSOD
    - software: Application crash, Office apps, browser, OS update, installation
    - access: Login, password, MFA, permissions, locked out, SSO, account
    - security: Phishing, malware, data breach, suspicious activity, stolen device
    - other: Does not fit above categories

    === TEAM ROUTING ===
    - network-ops: Network infrastructure, server outages, VPN issues
    - sysadmin: Hardware setup, system administration, Active Directory
    - security: Security incidents, phishing, compromised accounts
    - dev: Application bugs, code deployment issues
    - helpdesk: General user support, password resets, software installation

    Think step by step:
    1. What is the core issue?
    2. How many people are affected?
    3. Is there a business deadline or revenue impact?
    4. Which team is best equipped to handle this?
    Then respond with a JSON object containing ONLY the fields specified.
    VERY IMPORTANT: The first field in your JSON MUST be "plan" where you write your reasoning.
    Return ONLY valid JSON. No markdown fences, no explanation outside the JSON.
""").strip()


# ── Pretty Helpers ──

def render_banner():
    """Show the NexDesk ASCII banner."""
    banner = Text()
    banner.append("  _   _           ____            _    \n", style="bold blue")
    banner.append(" | \\ | | _____  _|  _ \\  ___  ___| | __\n", style="bold blue")
    banner.append(" |  \\| |/ _ \\ \\/ / | | |/ _ \\/ __| |/ /\n", style="bold cyan")
    banner.append(" | |\\  |  __/>  <| |_| |  __/\\__ \\   < \n", style="bold cyan")
    banner.append(" |_| \\_|\\___/_/\\_\\____/ \\___||___/_|\\_\\\n", style="bold magenta")
    banner.append("                                        \n", style="")
    banner.append(" Mission Control — Rich Terminal UI     \n", style="dim")

    console.print(Panel(banner, border_style="blue", padding=(1, 2)))


def render_ticket_panel(obs: Dict[str, Any], task: str, step: int):
    """Render a beautiful ticket observation panel."""
    table = Table(box=box.SIMPLE_HEAVY, show_header=False, pad_edge=False, expand=True)
    table.add_column("Field", style="bold cyan", width=18)
    table.add_column("Value", style="white")

    table.add_row("🆔 Ticket ID", obs.get("ticket_id", "—"))
    table.add_row("📋 Subject", obs.get("subject", "—"))
    table.add_row("📝 Description", (obs.get("description", ""))[:120] + "...")
    table.add_row("👤 Submitter", f"{obs.get('submitter', '—')} ({obs.get('department', '—')})")
    table.add_row("⏰ SLA Deadline", f"{obs.get('sla_deadline_minutes', '—')} minutes")
    table.add_row("📊 Queue Depth", str(obs.get("queue_depth", "—")))
    table.add_row("😰 Stress Level", _stress_bar(obs.get("stress_level", 0)))
    table.add_row("🎯 Task", f"{task} (Step {step})")

    # Similar tickets
    similar = obs.get("similar_tickets", [])
    if similar:
        similar_str = "\n".join(
            f"  → {s.get('subject', '?')[:40]} [{s.get('category', '?')}]"
            for s in similar[:3]
        )
        table.add_row("🔗 Similar", similar_str)

    # RAG Results
    kb = obs.get("knowledge_results", [])
    if kb:
        kb_str = "\n".join(
            f"  📘 {k.get('title', '?')[:40]} [{k.get('relevance_score', 0):.2f}]"
            for k in kb[:2]
        )
        table.add_row("🧠 KB Found", kb_str)
        
    # Active Flags
    flags = obs.get("active_flags", [])
    if flags:
        flag_str = "\n".join(f"  ⚠ {f.get('type')}: {f.get('message')}" for f in flags)
        table.add_row("🚩 Flags", f"[bold red]{flag_str}[/bold red]")

    title = f"  {TASK_EMOJIS.get(task, '📋')}  Ticket Observation  "
    console.print(Panel(table, title=title, border_style="blue", padding=(0, 1)))


def _stress_bar(level: float) -> str:
    """Render an inline stress level bar."""
    pct = int(level * 20)
    if level > 0.7:
        color = "red"
    elif level > 0.4:
        color = "yellow"
    else:
        color = "green"
    filled = "█" * pct
    empty = "░" * (20 - pct)
    return f"[{color}]{filled}{empty}[/{color}] {level:.0%}"


def render_action_json(action: Dict[str, Any]):
    """Pretty-print the LLM's action as syntax-highlighted JSON."""
    json_str = json.dumps(action, indent=2, ensure_ascii=False)
    syntax = Syntax(json_str, "json", theme="monokai", line_numbers=False, padding=1)
    console.print(Panel(syntax, title="  🤖  Agent Action  ", border_style="magenta", padding=(0, 1)))


def render_step_result(result: Dict[str, Any], step: int):
    """Render step result with reward and score breakdown."""
    reward = result.get("reward", 0)
    done = result.get("done", False)
    info = result.get("info", {})
    breakdown = info.get("score_breakdown", {})

    # Reward gauge
    if reward >= 0.7:
        reward_style = "bold green"
    elif reward >= 0.4:
        reward_style = "bold yellow"
    else:
        reward_style = "bold red"

    table = Table(box=box.ROUNDED, show_header=True, expand=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white", justify="right")
    table.add_column("", width=20)

    # Main reward
    bar_len = int(reward * 20)
    bar = "█" * bar_len + "░" * (20 - bar_len)
    table.add_row("Step Reward", f"[{reward_style}]{reward:.4f}[/{reward_style}]", f"[green]{bar}[/green]")

    # Total
    total = info.get("total_reward", reward)
    table.add_row("Total Reward", f"{total:.4f}", "")

    # Breakdown
    for key, val in breakdown.items():
        if key == "sla_breaches":
            table.add_row(f"  {key}", str(val), "")
        elif isinstance(val, (int, float)):
            table.add_row(f"  {key}", f"{val:.4f}", "")

    status = "[bold green]✅ COMPLETE[/bold green]" if done else f"[blue]Step {step} done[/blue]"
    table.add_row("Status", status, "")

    console.print(Panel(table, title="  📊  Step Result  ", border_style="green" if done else "yellow", padding=(0, 1)))


def render_task_summary(task: str, rewards: List[float], success: bool, elapsed: float):
    """Render a summary panel for a completed task."""
    avg = sum(rewards) / max(len(rewards), 1)
    total = sum(rewards)

    table = Table(box=box.DOUBLE_EDGE, show_header=False, expand=True, pad_edge=False)
    table.add_column("", style="cyan", width=20)
    table.add_column("", style="white")

    table.add_row("Task", f"{TASK_EMOJIS.get(task, '')} {task}")
    table.add_row("Difficulty", TASK_DIFFICULTY.get(task, "—"))
    table.add_row("Steps", str(len(rewards)))
    table.add_row("Total Reward", f"[bold]{total:.4f}[/bold]")
    table.add_row("Avg Reward", f"{avg:.4f}")
    table.add_row("Time", f"{elapsed:.1f}s")

    threshold = SUCCESS_THRESHOLDS.get(task, 0.45)
    table.add_row("Threshold", f"{threshold:.2f}")

    if success:
        table.add_row("Result", "[bold green]✅ PASSED[/bold green]")
    else:
        table.add_row("Result", "[bold red]❌ FAILED[/bold red]")

    # Reward sparkline
    spark = " ".join(f"{r:.2f}" for r in rewards)
    table.add_row("Rewards", f"[dim]{spark}[/dim]")

    border = "green" if success else "red"
    console.print(Panel(table, title=f"  Task Summary: {task}  ", border_style=border, padding=(0, 1)))


def render_final_scoreboard(results: List[Dict[str, Any]]):
    """Render the final scoreboard across all tasks."""
    console.print()
    console.rule("[bold blue]  🏆  Final Scoreboard  [/bold blue]", style="blue")
    console.print()

    table = Table(box=box.HEAVY_EDGE, show_header=True, expand=True)
    table.add_column("Task", style="bold white")
    table.add_column("Difficulty", justify="center")
    table.add_column("Steps", justify="center", style="cyan")
    table.add_column("Avg Reward", justify="right")
    table.add_column("Total", justify="right")
    table.add_column("Time", justify="right", style="dim")
    table.add_column("Result", justify="center")

    total_passed = 0
    for r in results:
        task = r["task"]
        avg = sum(r["rewards"]) / max(len(r["rewards"]), 1)
        total = sum(r["rewards"])
        passed = r["success"]
        if passed:
            total_passed += 1

        avg_style = "green" if avg >= SUCCESS_THRESHOLDS.get(task, 0.45) else "red"
        result_text = "[bold green]✅ PASS[/bold green]" if passed else "[bold red]❌ FAIL[/bold red]"

        table.add_row(
            f"{TASK_EMOJIS.get(task, '')} {task}",
            TASK_DIFFICULTY.get(task, "—"),
            str(len(r["rewards"])),
            f"[{avg_style}]{avg:.4f}[/{avg_style}]",
            f"{total:.4f}",
            f"{r['elapsed']:.1f}s",
            result_text,
        )

    console.print(table)
    console.print()

    # Overall
    overall = f"{total_passed}/{len(results)} tasks passed"
    style = "bold green" if total_passed == len(results) else "bold yellow" if total_passed > 0 else "bold red"
    console.print(Panel(
        f"[{style}]{overall}[/{style}]",
        title="  Overall Result  ",
        border_style="blue",
        padding=(1, 4),
    ))
    console.print()


# ── Environment API ──

def env_reset(task: str) -> Dict[str, Any]:
    r = requests.post(f"{ENV_BASE_URL}/reset", json={"task": task}, timeout=30)
    r.raise_for_status()
    return r.json()


def env_step(session_id: str, action: Dict[str, Any]) -> Dict[str, Any]:
    action = dict(action or {})
    action.pop("session_id", None)
    payload = {"session_id": session_id, **action}
    r = requests.post(f"{ENV_BASE_URL}/step", json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


# ── LLM ──

def build_prompt(obs: Dict[str, Any], step: int) -> str:
    """STRONG prompt builder with clear instructions and proper few-shot examples"""
    task = obs.get("task", "ticket_classify")

    ticket_block = (
        f"Ticket ID: {obs.get('ticket_id', 'N/A')}\n"
        f"Subject: {obs.get('subject', 'N/A')}\n"
        f"Description: {obs.get('description', 'N/A')}\n"
        f"Submitter: {obs.get('submitter', 'N/A')} ({obs.get('department', 'N/A')})\n"
        f"SLA Deadline: {obs.get('sla_deadline_minutes', 'N/A')} minutes\n"
        f"Queue Depth: {obs.get('queue_depth', 'N/A')} tickets\n"
        f"Stress Level: {obs.get('stress_level', 'N/A')}"
    )

    # Add similar tickets context for better classification
    similar = obs.get("similar_tickets", [])
    if similar:
        ticket_block += "\n\n=== SIMILAR PAST TICKETS (use as reference) ===\n"
        for s in similar[:3]:
            ticket_block += f"  - {s.get('subject', '')} → priority={s.get('priority', '')}, category={s.get('category', '')}, team={s.get('team', '')}\n"

    # Select correct few-shot and instructions
    if task == "ticket_classify":
        few_shot = FEW_SHOTS.get("ticket_classify", "")
        instructions = textwrap.dedent("""
            Return ONLY a valid JSON object with exactly these fields:
            {
              "plan": "your step-by-step reasoning",
              "priority": "low|medium|high|critical",
              "category": "network|hardware|software|access|security|other"
            }
        """).strip()

    elif task == "ticket_route":
        if step == 1:
            few_shot = FEW_SHOTS.get("ticket_route_step1", "")
            instructions = textwrap.dedent("""
                Step 1 of 2. Return ONLY a valid JSON object with exactly these fields:
                {
                  "plan": "your step-by-step reasoning",
                  "priority": "low|medium|high|critical",
                  "category": "network|hardware|software|access|security|other",
                  "team": "helpdesk|network-ops|sysadmin|security|dev"
                }
            """).strip()
        else:
            few_shot = FEW_SHOTS.get("ticket_route_step2", "")
            instructions = textwrap.dedent("""
                Step 2 of 2. Return ONLY a valid JSON object with exactly these fields:
                {
                  "plan": "your step-by-step reasoning",
                  "affected_system": "specific name of the system or device affected"
                }
            """).strip()

    elif task == "ticket_resolve":
        if step == 1:
            few_shot = FEW_SHOTS.get("ticket_resolve_step1", "")
            instructions = textwrap.dedent("""
                Step 1 of 3. Return ONLY a valid JSON object with exactly these fields:
                {
                  "plan": "your step-by-step reasoning",
                  "priority": "low|medium|high|critical",
                  "category": "network|hardware|software|access|security|other",
                  "team": "helpdesk|network-ops|sysadmin|security|dev"
                }
            """).strip()
        elif step == 2:
            few_shot = FEW_SHOTS.get("ticket_resolve_step2", "")
            instructions = textwrap.dedent("""
                Step 2 of 3. Return ONLY a valid JSON object with exactly these fields:
                {
                  "plan": "your step-by-step reasoning",
                  "affected_system": "name of the affected system",
                  "first_response": "professional, empathetic response to the user (minimum 30 characters)"
                }
            """).strip()
        else:
            few_shot = FEW_SHOTS.get("ticket_resolve_step3", "")
            instructions = textwrap.dedent("""
                Step 3 of 3. Return ONLY a valid JSON object with exactly these fields:
                {
                  "plan": "your step-by-step reasoning",
                  "resolution_steps": ["specific actionable step 1", "specific actionable step 2", "..."],
                  "sla_hours": integer between 1 and 168
                }
            """).strip()

    elif task == "crisis_surge":
        few_shot = FEW_SHOTS.get("crisis_surge", "")
        instructions = textwrap.dedent("""
            CRISIS MODE: Production outage. Handle tickets FAST.
            Return ONLY a valid JSON object with exactly these fields:
            {
              "plan": "your step-by-step reasoning",
              "priority": "low|medium|high|critical",
              "category": "network|hardware|software|access|security|other",
              "team": "helpdesk|network-ops|sysadmin|security|dev"
            }
        """).strip()
    else:
        few_shot = ""
        instructions = '{"priority": "medium", "category": "other"}'

    # RAG knowledge base injection
    rag_kb_injection = ""
    if "knowledge_results" in obs and obs["knowledge_results"]:
        rag_kb_injection = "\n\n=== INTERNAL KNOWLEDGE BASE RESULTS ===\n"
        for i, res in enumerate(obs["knowledge_results"][:3], 1):
            rag_kb_injection += f"[{i}] {res['title']} (relevance: {res.get('relevance_score', 0):.2f}):\n{res['content_snippet']}\n\n"
        rag_kb_injection += "IMPORTANT: Use the knowledge base articles above to ground your resolution steps. Reference specific procedures from them."

    # Escalation hint for complex tasks  
    escalation_hint = ""
    if task in ("ticket_route", "ticket_resolve", "crisis_surge"):
        escalation_hint = "\n\nNote: If you are highly uncertain about the correct team, you may output {\"action_type\": \"escalate\", \"team\": \"target-team\", \"reason\": \"why\"} instead."

    prompt = f"{few_shot}\n\n{ticket_block}{rag_kb_injection}\n\n{instructions}{escalation_hint}\n\nVERY IMPORTANT: Respond with valid JSON ONLY. No explanations."
    return prompt


def get_action(client: "OpenAI", obs: Dict[str, Any], step: int) -> Dict[str, Any]:
    """Get action from LLM with retry."""
    prompt = build_prompt(obs, step)

    for attempt in range(MAX_RETRIES + 1):
        try:
            completion = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
            )
            raw = (completion.choices[0].message.content or "{}").strip()
            raw = re.sub(r"```(?:json)?", "", raw).strip()
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end > start:
                raw = raw[start:end + 1]
            parsed = json.loads(raw)
            # Strip the plan field — it's for reasoning only, not for the environment
            parsed.pop("plan", None)
            return parsed
        except Exception as e:
            if attempt == MAX_RETRIES:
                import sys; print(f"Exception in get_action: {e}", file=sys.stderr)
                return _defaults(obs.get("task", "ticket_classify"), step)
    return _defaults(obs.get("task", "ticket_classify"), step)


def _defaults(task: str, step: int) -> Dict[str, Any]:
    if task == "ticket_classify":
        return {"priority": "medium", "category": "other"}
    if task in ("ticket_route", "crisis_surge"):
        return {"priority": "medium", "category": "other", "team": "helpdesk"}
    if task == "ticket_resolve":
        if step == 1:
            return {"priority": "medium", "category": "other", "team": "helpdesk"}
        if step == 2:
            return {"affected_system": "unknown", "first_response": "Thank you for contacting IT support. We are investigating your issue."}
        return {"resolution_steps": ["Investigate issue", "Apply fix", "Verify"], "sla_hours": 8}
    return {"priority": "medium", "category": "other"}


# ── Main Loop ──

def run_task(client: "OpenAI", task: str) -> Dict[str, Any]:
    """Run a single task with rich output."""
    console.print()
    console.rule(f"[bold blue]  {TASK_EMOJIS.get(task, '📋')}  {task}  —  {TASK_DIFFICULTY.get(task, '')}  [/bold blue]", style="blue")
    console.print()

    rewards = []
    start_time = time.time()

    try:
        # Reset
        with console.status("[bold cyan]Resetting environment...[/bold cyan]", spinner="dots"):
            reset_result = env_reset(task)

        obs = reset_result["observation"]
        session_id = reset_result["session_id"]
        max_steps = obs["max_steps"]

        console.print(f"  [dim]Session: {session_id[:16]}…  |  Max steps: {max_steps}[/dim]")
        console.print()

        for step in range(1, max_steps + 1):
            console.print(f"[bold]── Step {step}/{max_steps} ──[/bold]")
            console.print()
            
            # OPT-IN FEATURE: RAG Knowledge Search before resolution step 3
            if task == "ticket_resolve" and step == 3:
                with console.status("[bold cyan]Searching Knowledge Base...[/bold cyan]", spinner="dots"):
                    query = f"{obs.get('subject', '')} {obs.get('description', '')[:150]}"
                    try:
                        search_res = env_step(session_id, {"action_type": "search_kb", "query": query})
                        obs = search_res["observation"]
                        kb_count = len(obs.get("knowledge_results", []))
                        if kb_count > 0:
                            console.print(f"  [green]\u2713[/green] Found {kb_count} relevant KB articles")
                            for kb in obs.get("knowledge_results", [])[:3]:
                                console.print(f"    [dim]  {kb.get('title', '')} (score: {kb.get('relevance_score', 0):.2f})[/dim]")
                        else:
                            console.print(f"  [yellow]![/yellow] No relevant KB articles found")
                    except Exception as e:
                        console.print(f"  [red]\u2717[/red] KB search failed: {str(e)[:60]}")

            # Show ticket
            render_ticket_panel(obs, task, step)

            # Get LLM action
            with console.status(f"[bold magenta]🤖 {MODEL_NAME} thinking...[/bold magenta]", spinner="dots"):
                action = get_action(client, obs, step)

            render_action_json(action)

            # Submit step
            try:
                result = env_step(session_id, action)
                obs = result["observation"]
                reward = max(0.01, min(0.99, float(result["reward"])))
                done = bool(result["done"])
            except Exception as e:
                console.print(f"[red]  ⚠ Step error: {str(e)[:80]}[/red]")
                reward = 0.01
                done = True
                result = {"reward": 0.01, "done": True, "info": {"step": step, "total_reward": 0.01, "task": task}}

            rewards.append(reward)
            render_step_result(result, step)
            console.print()

            if done:
                break

    except Exception as e:
        console.print(f"[bold red]  ❌ Task error: {str(e)[:100]}[/bold red]")
        if not rewards:
            rewards = [0.01]

    elapsed = time.time() - start_time
    avg = sum(rewards) / max(len(rewards), 1)
    threshold = SUCCESS_THRESHOLDS.get(task, 0.45)
    success = avg >= threshold

    render_task_summary(task, rewards, success, elapsed)

    return {
        "task": task,
        "rewards": rewards,
        "success": success,
        "elapsed": elapsed,
    }


def main():
    if not HF_TOKEN:
        console.print("[bold red]❌ HF_TOKEN or OPENAI_API_KEY environment variable is required.[/bold red]")
        console.print("[dim]  Set it with: export HF_TOKEN=your_token[/dim]")
        return

    render_banner()

    # Health check
    console.print("[dim]  Checking environment health...[/dim]")
    try:
        r = requests.get(f"{ENV_BASE_URL}/health", timeout=10)
        health = r.json()
        console.print(f"  [green]✓[/green] Connected to {ENV_BASE_URL}")
        console.print(f"  [green]✓[/green] Environment: {health.get('env', '—')} v{health.get('version', '—')}")
        console.print(f"  [green]✓[/green] Features: {', '.join(health.get('features', []))}")
    except Exception:
        console.print(f"  [red]✗[/red] Cannot reach {ENV_BASE_URL}")
        console.print("  [dim]Start the server with: uvicorn server.app:app --port 7860[/dim]")
        return

    console.print(f"\n  [dim]Model: {MODEL_NAME}[/dim]")
    console.print(f"  [dim]API: {API_BASE_URL}[/dim]")
    console.print()

    # Run all tasks
    client = OpenAI(base_url=API_BASE_URL, api_key=HF_TOKEN)
    results = []

    for task in TASKS:
        result = run_task(client, task)
        results.append(result)

    # Final scoreboard
    render_final_scoreboard(results)

    # Generate Report
    console.print()
    console.print("[dim]  Generating final report...[/dim]")
    try:
        r = requests.get(f"{ENV_BASE_URL}/api/report/generate", timeout=10)
        report = r.json()
        with open("final_report.json", "w") as f:
            json.dump(report, f, indent=2)
        console.print(f"  [green]✓[/green] Report generated: [bold]final_report.json[/bold]")
    except Exception as e:
        console.print(f"  [red]✗[/red] Failed to generate report: {e}")


if __name__ == "__main__":
    main()
