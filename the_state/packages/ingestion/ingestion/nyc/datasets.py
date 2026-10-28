from __future__ import annotations

from ingestion.nyc.records import NycDatasetConfig, NycDatasetName

NYC_DATASETS: dict[NycDatasetName, NycDatasetConfig] = {
    "311": NycDatasetConfig(
        name="311",
        source_name="nyc-311",
        dataset_id="erm2-nwe9",
        record_type="nyc_311_complaint",
        date_field="created_date",
        default_order="created_date DESC",
    ),
    "dot_street_closures": NycDatasetConfig(
        name="dot_street_closures",
        source_name="nyc-dot-street-closures",
        dataset_id="i6b5-j7bu",
        record_type="nyc_dot_street_closure",
        date_field="work_start_date",
        default_order="work_start_date DESC",
    ),
    "nyc_events": NycDatasetConfig(
        name="nyc_events",
        source_name="nyc-events",
        dataset_id="tvpp-9vvx",
        record_type="nyc_permitted_event",
        date_field="start_date_time",
        default_order="start_date_time ASC",
    ),
    "hpd_violations": NycDatasetConfig(
        name="hpd_violations",
        source_name="nyc-hpd-violations",
        dataset_id="wvxf-dwi5",
        record_type="nyc_hpd_violation",
        date_field="inspectiondate",
        default_order="inspectiondate DESC",
    ),
    "nypd_collisions": NycDatasetConfig(
        name="nypd_collisions",
        source_name="nyc-nypd-collisions",
        dataset_id="h9gi-nx95",
        record_type="nyc_mv_collision",
        date_field="crash_date",
        default_order="crash_date DESC",
    ),
    "film_permits": NycDatasetConfig(
        name="film_permits",
        source_name="nyc-film-permits",
        dataset_id="tg4x-b46p",
        record_type="nyc_film_permit",
        date_field="startdatetime",
        default_order="startdatetime DESC",
    ),
    "hpd_complaints": NycDatasetConfig(
        name="hpd_complaints",
        source_name="nyc-hpd-complaints",
        dataset_id="uwyv-629c",
        record_type="nyc_hpd_complaint",
        date_field="receiveddate",
        default_order="receiveddate DESC",
    ),
    "dob_permits": NycDatasetConfig(
        name="dob_permits",
        source_name="nyc-dob-permits",
        dataset_id="ipu4-2q9a",
        record_type="nyc_dob_permit",
        date_field="issuance_date",
        default_order="issuance_date DESC",
    ),
}
