from app.adk_agents.playbooks import DEFAULT_PLAYBOOK, PLAYBOOKS, select_playbook


def test_known_metrics_map_to_expected_risk_tier():
    assert select_playbook("encoder_queue_depth")["risk_level"] == "low"
    assert select_playbook("cache_hit_ratio")["risk_level"] == "low"
    assert select_playbook("rebuffer_ratio")["risk_level"] == "high"
    assert select_playbook("origin_error_rate")["risk_level"] == "high"
    assert select_playbook("playback_failure_rate")["risk_level"] == "high"


def test_unknown_metric_falls_back_to_default():
    assert select_playbook("totally_unknown_metric") == DEFAULT_PLAYBOOK


def test_none_metric_falls_back_to_default():
    assert select_playbook(None) == DEFAULT_PLAYBOOK


def test_every_playbook_entry_has_required_fields():
    for metric, playbook in PLAYBOOKS.items():
        assert playbook["risk_level"] in ("low", "high"), metric
        assert playbook["action_type"], metric
        assert playbook["description"], metric


def test_low_risk_metrics_are_a_strict_subset():
    low_risk = {m for m, p in PLAYBOOKS.items() if p["risk_level"] == "low"}
    assert low_risk == {"encoder_queue_depth", "cache_hit_ratio"}
