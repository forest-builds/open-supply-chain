from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ingestion.nyc.datasets import NYC_DATASETS
from ingestion.nyc.records import NormalizedSignal

BOROUGH_ID_TO_NAME: dict[str, str] = {
    "1": "MANHATTAN",
    "2": "BRONX",
    "3": "BROOKLYN",
    "4": "QUEENS",
    "5": "STATEN ISLAND",
}

BOROUGH_CODE_TO_NAME: dict[str, str] = {
    "M": "MANHATTAN",
    "MN": "MANHATTAN",
    "MANHATTAN": "MANHATTAN",
    "X": "BRONX",
    "BX": "BRONX",
    "BRONX": "BRONX",
    "K": "BROOKLYN",
    "BK": "BROOKLYN",
    "BROOKLYN": "BROOKLYN",
    "Q": "QUEENS",
    "QN": "QUEENS",
    "QUEENS": "QUEENS",
    "R": "STATEN ISLAND",
    "SI": "STATEN ISLAND",
    "STATEN ISLAND": "STATEN ISLAND",
}

HIGH_STRESS_311_TYPES = {
    "FLOODING",
    "HEAT/HOT WATER",
    "SEWER",
    "WATER SYSTEM",
}
MEDIUM_STRESS_311_TYPES = {
    "AIR QUALITY",
    "BLOCKED DRIVEWAY",
    "CONSTRUCTION",
    "ILLEGAL PARKING",
    "NOISE",
    "NOISE - COMMERCIAL",
    "NOISE - RESIDENTIAL",
    "UNSANITARY CONDITION",
}


def normalize_311_complaint(record: dict[str, Any]) -> NormalizedSignal:
    config = NYC_DATASETS["311"]
    complaint_type = _text(record.get("complaint_type")) or "311 complaint"
    descriptor = _text(record.get("descriptor"))
    occurred_at = _parse_datetime(record.get("created_date"))
    observed_at = occurred_at or _now()
    title = complaint_type if descriptor is None else f"{complaint_type}: {descriptor}"
    severity = _severity_for_311(complaint_type)

    return NormalizedSignal(
        source_name=config.source_name,
        external_id=_required(record, "unique_key"),
        record_type=config.record_type,
        payload=record,
        signal_type="civic_complaint",
        title=title,
        summary=_text(record.get("resolution_description")),
        severity=severity,
        occurred_at=occurred_at,
        observed_at=observed_at,
        location=_base_location(
            borough=record.get("borough"),
            zip_code=record.get("incident_zip"),
            latitude=record.get("latitude"),
            longitude=record.get("longitude"),
        ),
        attributes={
            "agency": record.get("agency"),
            "complaint_type": complaint_type,
            "descriptor": descriptor,
            "status": record.get("status"),
        },
    )


def normalize_dot_street_closure(record: dict[str, Any]) -> NormalizedSignal:
    config = NYC_DATASETS["dot_street_closures"]
    occurred_at = _parse_datetime(record.get("work_start_date"))
    observed_at = occurred_at or _now()
    purpose = _text(record.get("purpose")) or _text(record.get("work_type")) or "Street closure"
    on_street = _text(record.get("onstreetname"))
    from_street = _text(record.get("fromstreetname"))
    to_street = _text(record.get("tostreetname"))

    return NormalizedSignal(
        source_name=config.source_name,
        external_id=str(
            record.get("segmentid")
            or record.get("segment_id")
            or f"{purpose}:{on_street}:{occurred_at}"
        ),
        record_type=config.record_type,
        payload=record,
        signal_type="street_closure",
        title=_join_title([purpose, on_street, from_street, to_street]),
        summary=_text(record.get("closure_reason")),
        severity=_severity_for_closure(purpose),
        occurred_at=occurred_at,
        observed_at=observed_at,
        location=_base_location(
            borough=record.get("boro") or record.get("borough_code"),
            latitude=record.get("latitude"),
            longitude=record.get("longitude"),
        ),
        attributes={
            "purpose": purpose,
            "work_type": record.get("work_type"),
            "work_end_date": record.get("work_end_date"),
            "segment_id": record.get("segmentid") or record.get("segment_id"),
        },
    )


def normalize_nyc_event(record: dict[str, Any]) -> NormalizedSignal:
    config = NYC_DATASETS["nyc_events"]
    occurred_at = _parse_datetime(record.get("start_date_time"))
    observed_at = occurred_at or _now()
    event_name = _text(record.get("event_name")) or "NYC event"
    event_type = _text(record.get("event_type"))

    return NormalizedSignal(
        source_name=config.source_name,
        external_id=str(record.get("event_id") or f"{event_name}:{occurred_at}"),
        record_type=config.record_type,
        payload=record,
        signal_type="public_event",
        title=event_name if event_type is None else f"{event_name} ({event_type})",
        summary=_text(record.get("event_location")),
        severity=_severity_for_event(event_name, event_type),
        occurred_at=occurred_at,
        observed_at=observed_at,
        location=_base_location(
            borough=record.get("event_borough"),
        ),
        attributes={
            "event_type": event_type,
            "event_location": record.get("event_location"),
            "community_board": record.get("community_board"),
            "end_date_time": record.get("end_date_time"),
        },
    )


def normalize_hpd_violation(record: dict[str, Any]) -> NormalizedSignal:
    config = NYC_DATASETS["hpd_violations"]
    occurred_at = _parse_datetime(record.get("inspectiondate") or record.get("novissueddate"))
    observed_at = occurred_at or _now()
    violation_class = _text(record.get("class"))
    description = _text(record.get("novdescription")) or "HPD violation"

    return NormalizedSignal(
        source_name=config.source_name,
        external_id=_required(record, "violationid"),
        record_type=config.record_type,
        payload=record,
        signal_type="housing_violation",
        title=description,
        summary=_text(record.get("currentstatus")),
        severity=_severity_for_hpd(violation_class),
        occurred_at=occurred_at,
        observed_at=observed_at,
        location=_base_location(
            borough=record.get("boroid"),
            zip_code=record.get("zip"),
            latitude=record.get("latitude"),
            longitude=record.get("longitude"),
            nta=record.get("nta"),
        ),
        attributes={
            "class": violation_class,
            "building_id": record.get("buildingid"),
            "bbl": record.get("bbl"),
            "current_status": record.get("currentstatus"),
        },
    )


def _to_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def normalize_nypd_collision(record: dict[str, Any]) -> NormalizedSignal:
    config = NYC_DATASETS["nypd_collisions"]
    occurred_at = _parse_datetime(record.get("crash_date"))
    observed_at = occurred_at or _now()
    killed = _to_int(record.get("number_of_persons_killed"))
    injured = _to_int(record.get("number_of_persons_injured"))
    if killed > 0:
        severity = "High"
    elif injured > 0:
        severity = "Medium"
    else:
        severity = "Low"
    on_street = _text(record.get("on_street_name"))
    cross = _text(record.get("cross_street_name"))
    return NormalizedSignal(
        source_name=config.source_name,
        external_id=str(
            record.get("collision_id")
            or record.get("unique_key")
            or f"collision:{on_street}:{occurred_at}"
        ),
        record_type=config.record_type,
        payload=record,
        signal_type="civic_complaint",
        title=_join_title(["Motor vehicle collision", on_street, cross]),
        summary=_text(record.get("contributing_factor_vehicle_1")),
        severity=severity,
        occurred_at=occurred_at,
        observed_at=observed_at,
        location=_base_location(
            borough=record.get("borough"),
            zip_code=record.get("zip_code"),
            latitude=record.get("latitude"),
            longitude=record.get("longitude"),
        ),
        attributes={
            "persons_injured": injured,
            "persons_killed": killed,
            "on_street": on_street,
        },
    )


def normalize_film_permit(record: dict[str, Any]) -> NormalizedSignal:
    config = NYC_DATASETS["film_permits"]
    occurred_at = _parse_datetime(record.get("startdatetime"))
    observed_at = occurred_at or _now()
    category = _text(record.get("category")) or _text(record.get("subcategoryname"))
    event_type = _text(record.get("eventtype")) or "Film permit"
    return NormalizedSignal(
        source_name=config.source_name,
        external_id=str(record.get("eventid") or f"film:{category}:{occurred_at}"),
        record_type=config.record_type,
        payload=record,
        signal_type="public_event",
        title=event_type if category is None else f"{event_type}: {category}",
        summary=_text(record.get("parkingheld")),
        severity="Medium" if "shoot" in event_type.lower() else "Low",
        occurred_at=occurred_at,
        observed_at=observed_at,
        location=_base_location(borough=record.get("borough")),
        attributes={
            "event_type": event_type,
            "category": category,
            "parking_held": record.get("parkingheld"),
            "end_date_time": record.get("enddatetime"),
        },
    )


def normalize_hpd_complaint(record: dict[str, Any]) -> NormalizedSignal:
    config = NYC_DATASETS["hpd_complaints"]
    occurred_at = _parse_datetime(record.get("receiveddate"))
    observed_at = occurred_at or _now()
    status = _text(record.get("status")) or "Open"
    severity = "Medium" if status.upper().startswith("OPEN") else "Low"
    return NormalizedSignal(
        source_name=config.source_name,
        external_id=_required(record, "complaintid"),
        record_type=config.record_type,
        payload=record,
        signal_type="housing_violation",
        title=f"HPD complaint ({status})",
        summary=_text(record.get("majorcategory")) or _text(record.get("apartment")),
        severity=severity,
        occurred_at=occurred_at,
        observed_at=observed_at,
        location=_base_location(
            borough=record.get("borough"),
            zip_code=record.get("zip"),
        ),
        attributes={
            "status": status,
            "building_id": record.get("buildingid"),
            "apartment": record.get("apartment"),
        },
    )


def normalize_dob_permit(record: dict[str, Any]) -> NormalizedSignal:
    config = NYC_DATASETS["dob_permits"]
    occurred_at = _parse_datetime(record.get("issuance_date") or record.get("job_start_date"))
    observed_at = occurred_at or _now()
    work_type = (
        _text(record.get("work_type")) or _text(record.get("permit_type")) or "Construction permit"
    )
    return NormalizedSignal(
        source_name=config.source_name,
        external_id=str(
            record.get("job__")
            or record.get("job_filing_number")
            or f"dob:{work_type}:{occurred_at}"
        ),
        record_type=config.record_type,
        payload=record,
        signal_type="street_closure",
        title=_join_title([work_type, _text(record.get("street_name"))]),
        summary=_text(record.get("job_type")),
        severity=_severity_for_closure(work_type),
        occurred_at=occurred_at,
        observed_at=observed_at,
        location=_base_location(
            borough=record.get("borough"),
            zip_code=record.get("zip_code"),
        ),
        attributes={
            "work_type": work_type,
            "permit_status": record.get("permit_status"),
            "job_type": record.get("job_type"),
        },
    )


NORMALIZERS = {
    "311": normalize_311_complaint,
    "dot_street_closures": normalize_dot_street_closure,
    "nyc_events": normalize_nyc_event,
    "hpd_violations": normalize_hpd_violation,
    "nypd_collisions": normalize_nypd_collision,
    "film_permits": normalize_film_permit,
    "hpd_complaints": normalize_hpd_complaint,
    "dob_permits": normalize_dob_permit,
}


def normalize_record(dataset_name: str, record: dict[str, Any]) -> NormalizedSignal:
    normalizer = NORMALIZERS[dataset_name]
    return normalizer(record)


class NycNormalizer:
    """Reference implementation of ``NormalizerProtocol``.

    Pure delegation to the existing registry — it adds the formal interface
    a new city's normalizer should mirror, with no behavioral change.
    """

    def normalize_record(self, dataset_name: str, record: dict[str, Any]) -> NormalizedSignal:
        return normalize_record(dataset_name, record)


nyc_normalizer = NycNormalizer()


def _base_location(
    *,
    borough: Any = None,
    zip_code: Any = None,
    latitude: Any = None,
    longitude: Any = None,
    nta: Any = None,
) -> dict[str, Any]:
    location: dict[str, Any] = {
        "state": "NY",
        "city": "New York",
    }
    normalized_borough = _normalize_borough(borough)
    if normalized_borough:
        location["borough"] = normalized_borough
    if zip_code:
        location["zip"] = str(zip_code)
    if nta:
        location["nta"] = str(nta)
    lat = _float_or_none(latitude)
    lon = _float_or_none(longitude)
    if lat is not None:
        location["latitude"] = lat
    if lon is not None:
        location["longitude"] = lon
    return location


def _normalize_borough(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    return BOROUGH_ID_TO_NAME.get(text) or BOROUGH_CODE_TO_NAME.get(text) or text


def _severity_for_311(complaint_type: str) -> str:
    normalized = complaint_type.upper()
    if normalized in HIGH_STRESS_311_TYPES:
        return "High"
    if normalized in MEDIUM_STRESS_311_TYPES or normalized.startswith("NOISE"):
        return "Medium"
    return "Low"


def _severity_for_closure(purpose: str) -> str:
    normalized = purpose.upper()
    if any(term in normalized for term in ("EMERGENCY", "FULL CLOSURE", "WATER MAIN")):
        return "High"
    if any(term in normalized for term in ("CONSTRUCTION", "UTILITY", "STREET")):
        return "Medium"
    return "Low"


def _severity_for_event(event_name: str, event_type: str | None) -> str:
    normalized = f"{event_name} {event_type or ''}".upper()
    if any(term in normalized for term in ("MARATHON", "PARADE", "FESTIVAL", "RALLY")):
        return "Medium"
    return "Low"


def _severity_for_hpd(violation_class: str | None) -> str:
    normalized = (violation_class or "").upper()
    if normalized == "C":
        return "High"
    if normalized == "B":
        return "Medium"
    return "Low"


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _required(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    if value in (None, ""):
        raise ValueError(f"NYC Open Data record is missing required field '{key}'")
    return str(value)


def _text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _join_title(parts: list[str | None]) -> str:
    return " - ".join(part for part in parts if part) or "NYC operational signal"


def _now() -> datetime:
    return datetime.now(timezone.utc)
