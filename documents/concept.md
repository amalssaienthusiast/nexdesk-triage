# NexDesk Ticket Triage - Main Concept Idea

## Overview

NexDesk Ticket Triage is a production-grade **OpenEnv environment** designed specifically for training and evaluating Large Language Models (LLMs) and AI agents on real-world IT helpdesk ticket triage operations. 

While most environments focus on simplified, static classification tasks, NexDesk mirrors the chaotic reality of an IT operations floor. The fundamental premise of NexDesk is that **the business value of an IT support agent is not simply measured by pure correct classification, but by the speed, accuracy, empathy, and judgment applied in high-stakes environments.** 

## Core Problem Statement

In enterprise IT, misrouted or poorly diagnosed tickets result in extensive delays, breached Service Level Agreements (SLAs), and severe revenue drops. A "simple" issue like a forgotten password can bounce between queues for 6 hours, while a critical server outage might sit unattended in a software support queue. LLMs must be trained not just to understand *what* an issue is, but *how urgent* it is and *who* needs to address it immediately.

## Conceptual Innovations

NexDesk introduces several novel mechanisms to reflect the realities of helpdesk operations:

1. **Time Pressure System (SLA Mechanics):** 
   Tickets are given SLA deadlines (e.g., 60 minutes for low priority, 5 minutes for a crisis). If an agent does not resolve or route the ticket within the allowed SLA period, severe point penalties are enforced mathematically on the reward. The environment calculates the penalty dynamically as the elapsed time approaches and surpasses the deadline.

2. **Confidence Calibration:** 
   NexDesk heavily penalizes overconfident models making erroneous decisions and rewards models that accurately estimate their own uncertainty. Agents can report a `confidence` rating (0.01 - 0.99) alongside their action. Calibration metrics compare this confidence level against the actual accuracy of their action:
   - **Good Calibration:** Confidence roughly matches action accuracy. Bonus rewarded.
   - **Overconfident:** Confidence heavily exceeds action accuracy. Model blindly assumes accuracy. High penalty applied.
   - **Underconfident:** Accuracy exceeds confidence. Marginal penalty applied to encourage proper self-assessment.

3. **Crisis Surge Mode:**
   To test model perseverance under pressure, NexDesk employs a "Crisis Surge" task mode (`crisis_surge`). In this sequence, agents are hit with 10 tickets in rapid succession representing a large-scale outage (e.g., "PRODUCTION SERVER DOWN"). Tickets are arriving continuously depending on a randomized queue depth simulation, creating a stress multiplier where the agent must successfully triage critical faults first while ignoring or deprioritizing low-impact complaints.

4. **Multi-Dimensional Quality Scoring:**
   Rewards are not binary (1 for right, 0 for wrong). Points are distributed across multi-step pipelines. For instance, in the `ticket_resolve` task, the model must (a) correctly route, (b) identify the affected system, (c) draft an empathetic first response to the user, and (d) lay down technical resolution steps. The Graders systematically grant partial credit using heuristic evaluation of required semantic components.

5. **Business Metrics Mapping:**
   NexDesk calculates the direct financial ROI mapping. It calculates metrics like monthly savings in USD, automation rates, and SLA compliance percentages to help project managers visualize how an LLM saves or costs money in production settings.

## Summary

The main conceptual idea is to shift AI evaluation in IT tools from a sterile text classification paradigm to a **dynamic, time-pressured, and stateful simulation game** where agents are evaluated on operational competence, triage prioritization, and communication empathy.
