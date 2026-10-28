import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "packages", "state_engine"))

import pytest
from state_engine.engine import EntityStatus, IncidentStatus, StateEngine


def test_upsert_and_get():
    engine = StateEngine()
    state = engine.upsert("DR-4800-CA", entity_type="incident", title="Test Incident")
    assert state.entity_id == "DR-4800-CA"
    assert state.status == EntityStatus.OPEN
    assert engine.get("DR-4800-CA") is state


def test_transition():
    engine = StateEngine()
    engine.upsert("DR-4800-CA")
    state = engine.transition("DR-4800-CA", EntityStatus.ACTIVE)
    assert state.status == EntityStatus.ACTIVE


def test_transition_unknown_raises():
    engine = StateEngine()
    with pytest.raises(KeyError):
        engine.transition("nonexistent", EntityStatus.CLOSED)


def test_incident_status_alias():
    # IncidentStatus is an alias for EntityStatus — backwards compat
    assert IncidentStatus.OPEN == EntityStatus.OPEN
