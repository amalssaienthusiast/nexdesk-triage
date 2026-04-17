# Synopsis

**NexDesk Ticket Triage** is an innovative simulation-based AI agent environment built natively for the OpenEnv benchmark framework.

Diverging from established, simplistic categorization challenges, NexDesk places Large Language Models squarely inside an immersive enterprise IT helpdesk simulation. The agents must read, parse, and handle employee IT tickets in a system where actions have consequences. Agents are graded deterministically on their ability to:
- Correctly classify priority and sort categories.
- Provide technically valid, empathetic first-response interactions.
- Provide tangible, exact multi-step resolution advice.

**Core Unique Selling Points (USPs):**
- **Non-Static Evaluation:** Actions taken affect the state.
- **Time/Stress Vectors:** Failing to act rapidly incurs SLA point penalties mathematically drawn against a simulated clock and queue depth depth.
- **Confidence Calibration:** Agents must understand their own limitations. Predicting high confidence on a wrong answer severely penalizes the final output score.
- **The "Crisis Surge":** A specific 10-step testing task that simulates a major IT production outage, flooding the agent to evaluate its batch-triage prioritization logic.

By deploying as a highly encapsulated FastAPI REST server tracking internal state memory and strict numeric bound validation natively, NexDesk proves the ROI and literal economic utility (in USD) of AI integrations on real-world incident management teams.
