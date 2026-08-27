# Overview

## Problem

Live, unrepeatable media events (global streaming premieres, award shows, live sports simulcasts) generate traffic spikes that regularly break delivery pipelines — CDN edge overload, encoder saturation, origin latency. Today the response is manual: an engineer stares at a wall of Grafana dashboards, greps logs by hand, and pages people ad hoc. Minutes of triage translate directly into buffering fans and an incident that can never be "re-aired."

## Solution

A crew of five ADK agents (**Sentinel, Detective, Producer, Responder, Wrap**) shares one Grafana Cloud MCP connection and automates the detect → correlate → brief → remediate → document loop, with a forced human-approval gate before any state-changing action. A FastAPI backend orchestrates the crew and streams every step to a real-time "control room" web dashboard.

## Hackathon constraints this spec is designed against

| Constraint | How this design satisfies it |
|---|---|
| Must call Grafana Cloud MCP server at runtime (not just AI Observability) | Every agent holds an `McpToolset` connected to `mcp.grafana.com` (or self-hosted `mcp-grafana`) and calls it on every turn — see [`agents.md`](agents.md) |
| Must use `google-adk` / `google-genai` / `google-cloud-aiplatform` at runtime | All five agents are `google.adk.agents.Agent` instances; orchestrator imports `google.adk` directly in the FastAPI backend entry point |
| No non-Google AI frameworks or models | No LangChain, no third-party LLM SDKs anywhere in the stack |
| Must run on web, Android, or iOS | Control room is a web app (Next.js) |
| New project, built during contest period | This spec starts from zero — no reused code |

## Goals and non-goals

### Goals

- Detect a live-event SLO breach within seconds of onset, using only Grafana telemetry.
- Automatically correlate the breach across metrics, logs, and traces to a root-cause hypothesis.
- Translate that hypothesis into a plain-language brief a non-engineer (Studio Head) can read.
- Never let an agent take a production-impacting action without an explicit human approval step.
- Auto-generate a postmortem timeline from the incident's own agent-generated audit trail.
- Demonstrate deep, real runtime use of the Grafana MCP server's read *and* write surface (dashboards, alerting, incidents, OnCall) — not a single token API call.

### Non-goals (v1)

- Not a general observability platform — Grafana already is one; this is a decision-and-communication layer on top of it.
- Not a replacement for human on-call engineers — a human always confirms state-changing actions.
- Not covering non-streaming media workflows (VFX render farms, virtual-production stages) in v1. The agent-crew pattern is designed to extend there later, but out of scope for the hackathon build.
- Not building real CDN/encoder infrastructure. A lightweight synthetic pipeline stands in for a broadcast stack for demo purposes (see [`build-plan.md`](build-plan.md)).
