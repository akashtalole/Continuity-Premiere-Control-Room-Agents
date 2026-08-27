import uuid

from app.services import agent_status


def test_set_state_tracks_per_incident_not_a_single_current_incident():
    incident_a = uuid.uuid4()
    incident_b = uuid.uuid4()

    agent_status.set_state("detective", incident_a, "running")
    agent_status.set_state("detective", incident_b, "running")

    active = agent_status.snapshot()["detective"]["active_incidents"]
    assert str(incident_a) in active
    assert str(incident_b) in active

    agent_status.clear_incident(incident_a)
    agent_status.clear_incident(incident_b)


def test_blocked_wins_over_running_in_overall_state():
    incident_a = uuid.uuid4()
    incident_b = uuid.uuid4()

    agent_status.set_state("responder", incident_a, "running")
    agent_status.set_state("responder", incident_b, "blocked")

    assert agent_status.snapshot()["responder"]["state"] == "blocked"

    agent_status.clear_incident(incident_a)
    agent_status.clear_incident(incident_b)
    assert agent_status.snapshot()["responder"]["state"] == "idle"


def test_idle_removes_the_incident_from_the_active_set():
    incident = uuid.uuid4()
    agent_status.set_state("wrap", incident, "running")
    assert str(incident) in agent_status.snapshot()["wrap"]["active_incidents"]

    agent_status.set_state("wrap", incident, "idle")
    assert str(incident) not in agent_status.snapshot()["wrap"]["active_incidents"]


def test_clear_incident_removes_it_from_every_agent():
    incident = uuid.uuid4()
    for agent in agent_status.AGENT_NAMES:
        agent_status.set_state(agent, incident, "running")

    agent_status.clear_incident(incident)

    for agent in agent_status.AGENT_NAMES:
        assert str(incident) not in agent_status.snapshot()[agent]["active_incidents"]
