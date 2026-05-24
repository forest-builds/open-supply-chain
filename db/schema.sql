CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS sources (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL UNIQUE,
  api_url TEXT,
  auth_required BOOLEAN NOT NULL DEFAULT FALSE,
  refresh_rate TEXT,
  license TEXT,
  attribution TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw_ingestions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id UUID NOT NULL REFERENCES sources(id),
  source_name TEXT NOT NULL,
  ingestion_key TEXT NOT NULL,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  request JSONB NOT NULL DEFAULT '{}'::jsonb,
  payload JSONB NOT NULL,
  payload_hash TEXT NOT NULL,
  UNIQUE (source_name, ingestion_key, payload_hash)
);

CREATE TABLE IF NOT EXISTS areas_of_interest (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  geometry geometry(MultiPolygon, 4326) NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS geo_entities (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_type TEXT NOT NULL CHECK (entity_type IN ('port', 'facility', 'route', 'location', 'aoi')),
  subtype TEXT,
  name TEXT,
  description TEXT,
  geometry geometry(Geometry, 4326) NOT NULL,
  source_id UUID REFERENCES sources(id),
  source_name TEXT NOT NULL,
  source_entity_id TEXT NOT NULL,
  source_tags JSONB NOT NULL DEFAULT '{}'::jsonb,
  confidence NUMERIC(4, 3) NOT NULL DEFAULT 0.500,
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source_name, source_entity_id, entity_type)
);

CREATE INDEX IF NOT EXISTS geo_entities_geometry_idx
  ON geo_entities USING GIST (geometry);

CREATE INDEX IF NOT EXISTS geo_entities_type_idx
  ON geo_entities (entity_type);

CREATE INDEX IF NOT EXISTS geo_entities_type_subtype_idx
  ON geo_entities (entity_type, subtype);

CREATE INDEX IF NOT EXISTS geo_entities_source_idx
  ON geo_entities (source_name, source_entity_id);

CREATE TABLE IF NOT EXISTS risk_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type TEXT NOT NULL,
  severity TEXT,
  certainty TEXT,
  urgency TEXT,
  headline TEXT,
  description TEXT,
  instruction TEXT,
  area_desc TEXT,
  effective_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ,
  geometry geometry(Geometry, 4326),
  source_id UUID REFERENCES sources(id),
  source_name TEXT NOT NULL,
  source_event_id TEXT NOT NULL,
  source_tags JSONB NOT NULL DEFAULT '{}'::jsonb,
  confidence NUMERIC(4, 3) NOT NULL DEFAULT 0.900,
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source_name, source_event_id)
);

CREATE INDEX IF NOT EXISTS risk_events_geometry_idx
  ON risk_events USING GIST (geometry);

CREATE INDEX IF NOT EXISTS risk_events_type_idx
  ON risk_events (event_type);

CREATE INDEX IF NOT EXISTS risk_events_source_idx
  ON risk_events (source_name, source_event_id);

CREATE TABLE IF NOT EXISTS risk_impacts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  risk_event_id UUID NOT NULL REFERENCES risk_events(id) ON DELETE CASCADE,
  impacted_entity_id UUID NOT NULL REFERENCES geo_entities(id) ON DELETE CASCADE,
  relationship_type TEXT NOT NULL DEFAULT 'IMPACTS',
  impact_method TEXT NOT NULL CHECK (impact_method IN ('intersects', 'near')),
  distance_m NUMERIC(12, 3),
  source_id UUID REFERENCES sources(id),
  confidence NUMERIC(4, 3) NOT NULL DEFAULT 0.700,
  evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (risk_event_id, impacted_entity_id, relationship_type)
);

CREATE INDEX IF NOT EXISTS risk_impacts_event_idx
  ON risk_impacts (risk_event_id);

CREATE INDEX IF NOT EXISTS risk_impacts_entity_idx
  ON risk_impacts (impacted_entity_id);

CREATE INDEX IF NOT EXISTS risk_impacts_method_idx
  ON risk_impacts (impact_method);

CREATE TABLE IF NOT EXISTS entity_relationships (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  subject_entity_id UUID NOT NULL REFERENCES geo_entities(id),
  relationship_type TEXT NOT NULL,
  object_entity_id UUID NOT NULL REFERENCES geo_entities(id),
  source_id UUID REFERENCES sources(id),
  confidence NUMERIC(4, 3) NOT NULL DEFAULT 0.500,
  evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
  valid_from TIMESTAMPTZ,
  valid_to TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (subject_entity_id, relationship_type, object_entity_id, source_id)
);
