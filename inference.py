# nexdesk baseline inference script
# talks to the env server and an LLM, logs everything the validator needs

import json
import os
import re
import textwrap
from typing import Any, Dict, List, Optional

import requests
from openai import OpenAI

# ── env vars (the three the validator checks plus our server url) ──

API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")
HF_TOKEN = os.getenv("HF_TOKEN") or os.getenv("OPENAI_API_KEY")
if not HF_TOKEN:
    raise ValueError(
        "Authentication token is required. Set HF_TOKEN or OPENAI_API_KEY environment variable."
    )

ENV_BASE_URL = os.getenv("ENV_BASE_URL", "http://localhost:7860").rstrip("/")

BENCHMARK = "nexdesk-ticket-triage"
MAX_RETRIES = 2
TEMPERATURE = 0.15
MAX_TOKENS = 768
# Per-task success thresholds reflect the fact that multi-step tasks accumulate
# rewards across more steps, and the environment's ceiling formula distributes
# budget across all steps. A single global threshold is meaningless here.
SUCCESS_THRESHOLDS: Dict[str, float] = {
    "ticket_classify": 0.55,  # 1 step; ceiling ~0.90
    "ticket_route": 0.45,  # 2 steps; ceiling budget spread thinner
    "ticket_resolve": 0.38,  # 3 steps; quality scoring makes full marks hard
    "crisis_surge": 0.32,  # 10 steps under time pressure
}

TASKS = ["ticket_classify", "ticket_route", "ticket_resolve", "crisis_surge"]

# ── logging helpers (strict format — do NOT change field names) ──


def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)


def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]) -> None:
    error_val = error if error else "null"
    done_val = str(done).lower()
    print(
        f"[STEP] step={step} action={action} reward={reward:.2f} done={done_val} error={error_val}",
        flush=True,
    )


def log_end(success: bool, steps: int, rewards: List[float]) -> None:
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} rewards={rewards_str}",
        flush=True,
    )


# ── env api wrappers ──


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


# ── few-shot examples so the model has something to work from ──

FEW_SHOTS = {
    "ticket_classify": """
Example ticket:
Subject: VPN disconnects every 5 minutes
Description: Working from home, VPN keeps dropping. Using OpenVPN on Windows 10.
Submitter: Jane (Legal)
Correct answer: {"priority": "medium", "category": "network"}
""",
    "ticket_route_step1": """
Example ticket:
Subject: PRODUCTION SERVER DOWN
Description: Primary web server offline. All customer services down. Revenue impact $12k/min.
Correct answer: {"priority": "critical", "category": "network", "team": "network-ops"}
""",
    "ticket_route_step2": """
Example ticket (step 2):
Subject: VPN disconnects every 5 minutes
Identify the primary system affected.
Correct answer: {"affected_system": "VPN"}
""",
    "ticket_resolve_step1": """
Example ticket:
Subject: Excel keeps crashing when opening large files
Correct answer: {"priority": "high", "category": "software", "team": "helpdesk"}
""",
    "ticket_resolve_step2": """
Example ticket (step 2, you already classified it):
Subject: Excel keeps crashing when opening large files
Category: software, Priority: high, Team: helpdesk
Correct answer: {"affected_system": "Excel", "first_response": "Hi Jennifer, I understand how frustrating this must be, especially with the board meeting tomorrow. I'm looking into this right now and will prioritize getting Excel working for you. In the meantime, could you try opening the file in Excel Safe Mode (hold Ctrl while launching Excel)?"}
""",
    "ticket_resolve_step3": """
Example ticket (step 3, final step):
Subject: Excel keeps crashing when opening large files
Correct answer: {"resolution_steps": ["Open Excel in Safe Mode to rule out add-in conflicts", "Check available RAM — 50MB files need significant memory", "Install 64-bit Office if currently on 32-bit", "Run Office Quick Repair from Control Panel", "Update Office to latest version"], "sla_hours": 4}
""",
    "crisis_surge": """
CRISIS: You are handling tickets during a production outage. Prioritize critical tickets first.
Example ticket:
Subject: PRODUCTION SERVER DOWN — all services offline
Correct answer: {"priority": "critical", "category": "network", "team": "network-ops"}
""",
}


# ── prompt builder ──

SYSTEM_PROMPT = textwrap.dedent("""
    You are an expert IT helpdesk triage agent. Analyze the support ticket carefully.

    Think step by step:
    1. What is the core issue?
    2. How many people are affected?
    3. Is there a business deadline or revenue impact?
    4. Which team is best equipped to handle this?

    Then respond with a JSON object containing ONLY the fields specified.
    Return ONLY valid JSON. No markdown fences, no explanation outside the JSON.
""").strip()


def build_prompt(obs: Dict[str, Any], step: int) -> str:
    task = obs.get("task", "ticket_classify")

    ticket_block = (
        f"Ticket ID: {obs.get('ticket_id', 'N/A')}\n"
        f"Subject: {obs.get('subject', 'N/A')}\n"
        f"Description: {obs.get('description', 'N/A')}\n"
        f"Submitter: {obs.get('submitter', 'N/A')} ({obs.get('department', 'N/A')})\n"
        f"Submitted: {obs.get('submitted_at', 'N/A')}\n"
        f"SLA Deadline: {obs.get('sla_deadline_minutes', 'N/A')} minutes\n"
        f"Queue Depth: {obs.get('queue_depth', 'N/A')} tickets\n"
        f"Stress Level: {obs.get('stress_level', 'N/A')}"
    )

    # include similar tickets if available — helps the model pattern-match
    similar = obs.get("similar_tickets", [])
    if similar:
        ticket_block += "\n\nSimilar past tickets:"
        for st in similar[:3]:
            ticket_block += f"\n  - {st.get('subject', 'N/A')} → category: {st.get('category', '?')}, priority: {st.get('priority', '?')}, team: {st.get('team', '?')}"

    # include knowledge hints if available
    kb_hints = obs.get("knowledge_hints")
    if kb_hints and isinstance(kb_hints, dict):
        common_causes = kb_hints.get("common_causes", [])
        if common_causes:
            ticket_block += "\n\nKnown causes for this type of issue:"
            for i, cause in enumerate(common_causes[:4], 1):
                ticket_block += f"\n  {i}. {cause}"

    # pick the right instructions and few-shot example
    few_shot = ""
    instructions = ""

    if task == "ticket_classify":
        instructions = textwrap.dedent("""
            Return JSON with exactly these fields:
            {
              "priority": "<low|medium|high|critical>",
              "category": "<network|hardware|software|access|security|other>"
            }
        """).strip()
        few_shot = FEW_SHOTS["ticket_classify"]

    elif task == "ticket_route":
        if step == 1:
            instructions = textwrap.dedent("""
                Return JSON with exactly these fields:
                {
                  "priority": "<low|medium|high|critical>",
                  "category": "<network|hardware|software|access|security|other>",
                  "team": "<helpdesk|network-ops|sysadmin|security|dev>"
                }
            """).strip()
            few_shot = FEW_SHOTS["ticket_route_step1"]
        else:
            instructions = textwrap.dedent("""
                Step 2: Identify the primary system affected by this ticket.
                Be specific — name the actual system, device, or service.
                Return JSON with exactly this field:
                {
                  "affected_system": "<name of affected system or device>"
                }
            """).strip()
            few_shot = FEW_SHOTS["ticket_route_step2"]

    elif task == "ticket_resolve":
        if step == 1:
            instructions = textwrap.dedent("""
                Step 1 of 3. Return JSON with exactly these fields:
                {
                  "priority": "<low|medium|high|critical>",
                  "category": "<network|hardware|software|access|security|other>",
                  "team": "<helpdesk|network-ops|sysadmin|security|dev>"
                }
            """).strip()
            few_shot = FEW_SHOTS["ticket_resolve_step1"]
        elif step == 2:
            instructions = textwrap.dedent("""
                Step 2 of 3. Write a professional first response AND identify the affected system.
                The response should: acknowledge the issue, show empathy, and mention next steps.
                Return JSON with exactly these fields:
                {
                  "affected_system": "<name of affected system or device>",
                  "first_response": "<professional response to the user>"
                }
            """).strip()
            few_shot = FEW_SHOTS["ticket_resolve_step2"]
        else:
            instructions = textwrap.dedent("""
                Step 3 of 3. Provide resolution steps and estimated SLA.
                Steps should be specific and actionable (not generic).
                Return JSON with exactly these fields:
                {
                  "resolution_steps": ["<specific step 1>", "<specific step 2>", "<specific step 3>"],
                  "sla_hours": <estimated hours to resolve as integer>
                }
            """).strip()
            few_shot = FEW_SHOTS["ticket_resolve_step3"]

    elif task == "crisis_surge":
        instructions = textwrap.dedent("""
            CRISIS MODE: Production outage in progress. Handle tickets FAST.
            Prioritize: critical tickets first, then high, then medium.
            Return JSON with exactly these fields:
            {
              "priority": "<low|medium|high|critical>",
              "category": "<network|hardware|software|access|security|other>",
              "team": "<helpdesk|network-ops|sysadmin|security|dev>"
            }
        """).strip()
        few_shot = FEW_SHOTS["crisis_surge"]

    else:
        instructions = '{"priority": "medium", "category": "other"}'

    # RAG knowledge base injection
    rag_kb_injection = ""
    if "knowledge_results" in obs and obs["knowledge_results"]:
        rag_kb_injection = "\n\n=== INTERNAL KNOWLEDGE BASE ===\n"
        for i, res in enumerate(obs["knowledge_results"][:2], 1):
            rag_kb_injection += f"[{i}] {res['title']}:\n{res['content_snippet']}\n\n"
        rag_kb_injection += "Use exactly these steps to ground your resolution."

    prompt = f"{few_shot}\n\n{ticket_block}{rag_kb_injection}\n\n{instructions}"
    return prompt


# ── llm call with retry ──


def get_action(client: OpenAI, obs: Dict[str, Any], step: int) -> Dict[str, Any]:
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

            # strip markdown fences if the model adds them anyway
            raw = re.sub(r"```(?:json)?", "", raw).strip()

            # find the json object
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                raw = raw[start : end + 1]

            action = json.loads(raw)

            # validate required fields exist and aren't empty
            task = obs["task"]
            if task == "ticket_classify":
                if not action.get("priority"):
                    action["priority"] = "medium"
                if not action.get("category"):
                    action["category"] = "other"
            elif task in ("ticket_route", "crisis_surge"):
                if not action.get("priority"):
                    action["priority"] = "medium"
                if not action.get("category"):
                    action["category"] = "other"
                if not action.get("team"):
                    action["team"] = "helpdesk"
            elif task == "ticket_resolve":
                if step == 1:
                    if not action.get("priority"):
                        action["priority"] = "medium"
                    if not action.get("category"):
                        action["category"] = "other"
                    if not action.get("team"):
                        action["team"] = "helpdesk"
                elif step == 2:
                    if not action.get("affected_system"):
                        action["affected_system"] = "unknown"
                    if (
                        not action.get("first_response")
                        or len(action.get("first_response", "")) < 10
                    ):
                        action["first_response"] = (
                            "Thank you for reporting this issue. We are looking into it and will update you shortly."
                        )
                elif step == 3:
                    if not action.get("resolution_steps") or not isinstance(
                        action["resolution_steps"], list
                    ):
                        action["resolution_steps"] = [
                            "Investigate the reported issue",
                            "Apply appropriate fix",
                            "Verify resolution",
                        ]
                    sla = action.get("sla_hours")
                    if not isinstance(sla, (int, float)) or sla <= 0:
                        action["sla_hours"] = 8

            return action

        except json.JSONDecodeError:
            if attempt == MAX_RETRIES:
                # give up, return safe defaults
                return _task_defaults(obs["task"], step)
        except Exception as e:
            if attempt == MAX_RETRIES:
                return _task_defaults(obs["task"], step)

    return _task_defaults(obs["task"], step)


def _task_defaults(task: str, step: int) -> Dict[str, Any]:
    """sensible per-task fallbacks so we don't just return empty stuff"""
    if task == "ticket_classify":
        return {"priority": "medium", "category": "other"}
    if task in ("ticket_route", "crisis_surge"):
        return {"priority": "medium", "category": "other", "team": "helpdesk"}
    if task == "ticket_resolve":
        if step == 1:
            return {"priority": "medium", "category": "other", "team": "helpdesk"}
        if step == 2:
            return {
                "affected_system": "unknown",
                "first_response": "Thank you for contacting IT support. We are investigating your issue and will provide an update soon.",
            }
        if step == 3:
            return {
                "resolution_steps": [
                    "Investigate the reported issue",
                    "Apply fix",
                    "Verify with user",
                ],
                "sla_hours": 8,
            }
    return {"priority": "medium", "category": "other"}


# ── main loop ──


def run_task(client: OpenAI, task: str) -> None:
    rewards: List[float] = []
    steps_taken = 0
    score = 0.01
    success = False
    session_id = ""
    error_msg = None

    log_start(task=task, env=BENCHMARK, model=MODEL_NAME)

    try:
        reset_result = env_reset(task)
        obs = reset_result["observation"]
        session_id = reset_result["session_id"]
        max_steps = obs["max_steps"]

        for step in range(1, max_steps + 1):
            # 1. OPT-IN FEATURE: Multi-agent Escalation / RAG Knowledge Search
            if task == "ticket_resolve" and step == 3:
                # Before resolution, search the knowledge base
                query = f"{obs.get('subject', '')} {obs.get('category', '')}"
                search_action = {"action_type": "search_kb", "query": query}
                try:
                    search_res = env_step(session_id, search_action)
                    obs = search_res["observation"]  # This now contains the knowledge_results
                    log_step(step=step, action=json.dumps(search_action), reward=0.01, done=False, error=None)
                except Exception as e:
                    pass

            action = get_action(client, obs, step)
            action_str = json.dumps(action, separators=(",", ":"))

            try:
                result = env_step(session_id, action)
                obs = result["observation"]
                reward = max(0.01, min(0.99, float(result["reward"])))
                done = bool(result["done"])
                error_msg = None
            except requests.exceptions.HTTPError as e:
                # try to extract a useful message
                try:
                    detail = e.response.json().get("detail", str(e))[:100]
                except Exception:
                    detail = str(e)[:100]
                reward = 0.01
                done = True
                error_msg = detail
            except Exception as e:
                reward = 0.01
                done = True
                error_msg = str(e)[:100]

            rewards.append(reward)
            steps_taken = step
            log_step(step=step, action=action_str, reward=reward, done=done, error=error_msg)

            if done:
                break

        score = max(0.01, min(0.99, sum(rewards) / max(len(rewards), 1)))
        threshold = SUCCESS_THRESHOLDS.get(task, 0.45)
        success = score >= threshold

    except Exception as e:
        error_msg = str(e)[:100]
        if not rewards:
            rewards = [0.01]
            log_step(step=1, action="{}", reward=0.01, done=True, error=error_msg)
        steps_taken = steps_taken or 1
        success = False

    log_end(success=success, steps=steps_taken, rewards=rewards)


def main():
    client = OpenAI(base_url=API_BASE_URL, api_key=HF_TOKEN)

    for task in TASKS:
        run_task(client, task)


if __name__ == "__main__":
    main()
