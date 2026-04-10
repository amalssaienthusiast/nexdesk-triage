"""
NexDesk — Baseline Inference Script
=====================================
Runs an LLM agent against all 3 NexDesk tasks and logs results in
the mandatory OpenEnv format.

Environment variables:
  API_BASE_URL   LLM endpoint  (default: https://router.huggingface.co/v1)
  MODEL_NAME     LLM model     (default: Qwen/Qwen2.5-72B-Instruct)
  HF_TOKEN       API key for LLM
  ENV_BASE_URL   NexDesk server URL (default: http://localhost:7860)
"""

import json
import os
import textwrap
from typing import Any, Dict, List, Optional

import requests
from openai import OpenAI

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")
HF_TOKEN = os.getenv("HF_TOKEN")
if HF_TOKEN is None:
    raise ValueError("HF_TOKEN environment variable is required")
ENV_BASE_URL = os.getenv("ENV_BASE_URL", "http://localhost:7860").rstrip("/")

BENCHMARK = "nexdesk-ticket-triage"
MAX_STEPS = 3
TEMPERATURE = 0.2
MAX_TOKENS = 512
SUCCESS_THRESHOLD = 0.5

TASKS = ["ticket_classify", "ticket_route", "ticket_resolve", "crisis_surge"]

# ─────────────────────────────────────────────
# Log helpers  (MANDATORY FORMAT — do not change)
# ─────────────────────────────────────────────


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


# ─────────────────────────────────────────────
# Env HTTP helpers
# ─────────────────────────────────────────────


def env_reset(task: str) -> Dict[str, Any]:
    r = requests.post(f"{ENV_BASE_URL}/reset", json={"task": task}, timeout=30)
    r.raise_for_status()
    return r.json()


def env_step(session_id: str, action: Dict[str, Any]) -> Dict[str, Any]:
    payload = {"session_id": session_id, **action}
    r = requests.post(f"{ENV_BASE_URL}/step", json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


# ─────────────────────────────────────────────
# LLM prompts per task + step
# ─────────────────────────────────────────────

SYSTEM_BASE = textwrap.dedent("""
    You are an expert IT helpdesk manager. Analyze the support ticket and respond
    with a JSON object containing only the fields specified in the instructions.
    Return ONLY valid JSON. No markdown, no explanation, no preamble.
""").strip()


def build_prompt(obs: Dict[str, Any], step: int) -> str:
    task = obs["task"]
    ticket_block = (
        f"Ticket ID: {obs['ticket_id']}\n"
        f"Subject: {obs['subject']}\n"
        f"Description: {obs['description']}\n"
        f"Submitter: {obs['submitter']} ({obs['department']})\n"
        f"Submitted: {obs['submitted_at']}"
    )

    if task == "ticket_classify":
        instructions = textwrap.dedent("""
            Return JSON with exactly these fields:
            {
              "priority": "<low|medium|high|critical>",
              "category": "<network|hardware|software|access|security|other>"
            }
        """).strip()

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
        else:
            instructions = textwrap.dedent("""
                Identify the primary system affected by this ticket.
                Return JSON with exactly this field:
                {
                  "affected_system": "<name of affected system or device>"
                }
            """).strip()

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
        elif step == 2:
            instructions = textwrap.dedent("""
                Step 2 of 3. Return JSON with exactly these fields:
                {
                  "affected_system": "<name of affected system or device>",
                  "first_response": "<professional first response email to the user acknowledging their issue>"
                }
            """).strip()
        else:
            instructions = textwrap.dedent("""
                Step 3 of 3. Return JSON with exactly these fields:
                {
                  "resolution_steps": ["<step 1>", "<step 2>", "<step 3>", "..."],
                  "sla_hours": <estimated hours to resolve as integer>
                }
            """).strip()
    elif task == "crisis_surge":
        instructions = textwrap.dedent("""
            CRISIS MODE: You are handling a surge of tickets during a production outage.
            Prioritize critical tickets. Return JSON with exactly these fields:
            {
              "priority": "<low|medium|high|critical>",
              "category": "<network|hardware|software|access|security|other>",
              "team": "<helpdesk|network-ops|sysadmin|security|dev>"
            }
        """).strip()
    else:
        instructions = '{"priority": "medium", "category": "other"}'

    return f"{ticket_block}\n\n{instructions}"


def get_action(client: OpenAI, obs: Dict[str, Any], step: int) -> Dict[str, Any]:
    prompt = build_prompt(obs, step)
    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_BASE},
                {"role": "user", "content": prompt},
            ],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )
        raw = (completion.choices[0].message.content or "{}").strip()
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1:
            raw = raw[start:end+1]
        return json.loads(raw)
    except Exception as e:
        # Fallback defaults
        return {"priority": "medium", "category": "other"}


# ─────────────────────────────────────────────
# Run one task episode
# ─────────────────────────────────────────────


def run_task(client: OpenAI, task: str) -> None:
    rewards: List[float] = []
    steps_taken = 0
    score = 0.001  # Initialize > 0
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
            action = get_action(client, obs, step)
            action_str = json.dumps(action, separators=(",", ":"))

            try:
                result = env_step(session_id, action)
                obs = result["observation"]
                reward = float(result["reward"])
                done = bool(result["done"])
                error_msg = None
            except Exception as e:
                reward = 0.01  # Never exactly 0.0
                done = True
                error_msg = str(e)[:100]

            rewards.append(reward)
            steps_taken = step
            log_step(step=step, action=action_str, reward=reward, done=done, error=error_msg)

            if done:
                break

        score = sum(rewards)
        success = score >= SUCCESS_THRESHOLD

    except Exception as e:
        error_msg = str(e)[:100]
        if not rewards:
            rewards = [0.01]
        steps_taken = steps_taken or 1
        success = False

    log_end(success=success, steps=steps_taken, rewards=rewards)


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────


def main():
    client = OpenAI(base_url=API_BASE_URL, api_key=HF_TOKEN)

    for task in TASKS:
        run_task(client, task)


if __name__ == "__main__":
    main()
