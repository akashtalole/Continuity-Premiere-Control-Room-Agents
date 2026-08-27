"""Remediation playbook table, keyed by the SLO metric that breached.

The spec's Responder instruction (instructions.py) always names the same
four playbook actions -- scale encoder capacity, purge CDN cache, fail a
region over to backup CDN, roll back a bad deploy -- but the original
implementation only ever executed the CDN failover, and always at high
risk. This table gives each anomaly type its own action and risk tier, so
low-risk actions (e.g. scaling encoder capacity) auto-execute the way
docs/low-level-design.md's state machine describes (Briefed -> Remediating
directly, no AwaitingApproval hop), while high-risk actions still gate on
request_human_approval.

Both the orchestrator (to decide whether to show the approval UI before
calling the Responder) and the mock crew (to decide whether to actually
call request_human_approval) consult this same table, so the two stay in
sync. The real Responder agent's instruction also documents this table so
Gemini's own action/risk choice matches it by default, though -- being an
LLM -- it remains free to deviate given a genuinely novel finding.
"""

from typing import Literal, TypedDict


class Playbook(TypedDict):
    action_type: str
    risk_level: Literal["low", "high"]
    description: str


PLAYBOOKS: dict[str, Playbook] = {
    "rebuffer_ratio": {
        "action_type": "cdn_regional_failover",
        "risk_level": "high",
        "description": "Fail affected-region edge traffic over to the backup CDN pool.",
    },
    "origin_error_rate": {
        "action_type": "purge_cdn_cache",
        "risk_level": "high",
        "description": "Purge the CDN cache for the affected region to clear stale or poisoned edge responses.",
    },
    "playback_failure_rate": {
        "action_type": "rollback_bad_deploy",
        "risk_level": "high",
        "description": "Roll back the most recent player/edge deploy in the affected region.",
    },
    "encoder_queue_depth": {
        "action_type": "scale_encoder_capacity",
        "risk_level": "low",
        "description": "Scale encoder capacity up in the affected region to drain the backlog.",
    },
    "cache_hit_ratio": {
        "action_type": "purge_cdn_cache",
        "risk_level": "low",
        "description": "Purge and rewarm the CDN cache for the affected region.",
    },
}

DEFAULT_PLAYBOOK: Playbook = PLAYBOOKS["rebuffer_ratio"]


def select_playbook(metric_name: str | None) -> Playbook:
    if metric_name is None:
        return DEFAULT_PLAYBOOK
    return PLAYBOOKS.get(metric_name, DEFAULT_PLAYBOOK)
