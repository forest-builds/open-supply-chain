# Data Contracts

Every source should declare how raw data enters the system, which canonical
entities it can create, and how confident we are in those mappings.

Required fields:

```yaml
source_name:
api_url:
auth_required:
refresh_rate:
raw_schema:
canonical_entities_created:
cleaning_rules:
join_keys:
geo_fields:
confidence_score:
license:
attribution:
```

Pipeline shape:

```text
fetch -> raw_ingestions -> normalize -> canonical tables -> API -> app/MCP
```

Rules:

- Never discard raw source payloads.
- Keep source-specific fields in `JSONB`.
- Normalize only the fields needed by canonical entities.
- Store confidence and provenance on every normalized record.
- Do not let UI or MCP tools query raw source tables directly.
