"""Expanded NYC Open Data coverage. No DB required.

Mock-record -> expected NormalizedSignal for each new dataset, plus the
registry/protocol invariants. Mirrors the contributor test structure in
packages/ingestion/CONTRIBUTING.md.
"""

from __future__ import annotations

from ingestion import NormalizedSignal, NormalizerProtocol
from ingestion.nyc import (
    NYC_DATASETS,
    normalize_dob_permit,
    normalize_film_permit,
    normalize_hpd_complaint,
    normalize_nypd_collision,
    normalize_record,
    nyc_normalizer,
)

SCORED_TYPES = {
    "civic_complaint",
    "public_event",
    "housing_violation",
    "street_closure",
}


def test_all_new_datasets_registered_and_route():
    for name in (
        "nypd_collisions",
        "film_permits",
        "hpd_complaints",
        "dob_permits",
    ):
        assert name in NYC_DATASETS
    assert isinstance(nyc_normalizer, NormalizerProtocol)


def test_collision_severity_scales_with_harm():
    fatal = normalize_record(
        "nypd_collisions",
        {
            "collision_id": "C1",
            "crash_date": "2026-05-12T10:00:00.000",
            "borough": "BROOKLYN",
            "number_of_persons_killed": "1",
            "number_of_persons_injured": "0",
            "on_street_name": "ATLANTIC AVE",
        },
    )
    injured = normalize_record(
        "nypd_collisions",
        {
            "collision_id": "C2",
            "crash_date": "2026-05-12T10:00:00.000",
            "number_of_persons_killed": "0",
            "number_of_persons_injured": "3",
        },
    )
    clean = normalize_record(
        "nypd_collisions",
        {"collision_id": "C3", "crash_date": "2026-05-12T10:00:00.000"},
    )
    assert isinstance(fatal, NormalizedSignal)
    assert fatal.signal_type == "civic_complaint"
    assert (fatal.severity, injured.severity, clean.severity) == (
        "High",
        "Medium",
        "Low",
    )
    assert fatal.location["borough"] == "BROOKLYN"
    assert fatal.external_id == "C1"


def test_film_permit_is_public_event():
    sig = normalize_film_permit(
        {
            "eventid": "F9",
            "eventtype": "Shooting Permit",
            "category": "Television",
            "startdatetime": "2026-05-12T06:00:00.000",
            "borough": "Manhattan",
            "parkingheld": "5th Ave between 1st and 2nd",
        }
    )
    assert sig.signal_type == "public_event"
    assert sig.severity == "Medium"
    assert sig.external_id == "F9"
    assert "Shooting Permit" in sig.title


def test_hpd_complaint_open_vs_closed():
    op = normalize_hpd_complaint(
        {
            "complaintid": "H1",
            "status": "OPEN",
            "receiveddate": "2026-05-10T00:00:00.000",
            "borough": "BRONX",
        }
    )
    closed = normalize_hpd_complaint(
        {
            "complaintid": "H2",
            "status": "CLOSE",
            "receiveddate": "2026-05-10T00:00:00.000",
        }
    )
    assert op.signal_type == "housing_violation"
    assert (op.severity, closed.severity) == ("Medium", "Low")


def test_dob_permit_is_street_closure():
    sig = normalize_dob_permit(
        {
            "job__": "J42",
            "work_type": "Construction Equipment",
            "issuance_date": "2026-05-11T00:00:00.000",
            "borough": "QUEENS",
            "street_name": "NORTHERN BLVD",
        }
    )
    assert sig.signal_type == "street_closure"
    assert sig.external_id == "J42"
    assert sig.severity in {"Low", "Medium", "High"}


def test_every_new_normalizer_emits_a_scored_type():
    for fn, rec in (
        (normalize_nypd_collision, {"collision_id": "x", "crash_date": None}),
        (normalize_film_permit, {"eventid": "x", "startdatetime": None}),
        (normalize_hpd_complaint, {"complaintid": "x", "receiveddate": None}),
        (normalize_dob_permit, {"job__": "x", "issuance_date": None}),
    ):
        assert fn(rec).signal_type in SCORED_TYPES
