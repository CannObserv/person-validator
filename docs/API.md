# API Reference

## Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | None | Public health check |
| GET | `/versions` | None | List supported API versions and deprecation status |
| GET | `/v1/health` | API key | Authenticated health check |
| POST | `/v1/find` | API key | Find persons by name query |
| GET | `/v1/read/{id}` | API key | Full person record by ID |

Auth: `X-API-Key` header. Keys stored in `keys_apikey` (hashed).

### POST /v1/find

Request: `{"name": "..."}`. Runs the 5-stage normalization pipeline.

Responses:
- **422** — `InputClassification` rejected input as non-person name. Shape: `{"detail": [...]}`  (Pydantic-compatible)
- **200** — matches found
- **404** — no matches

Response body always includes:
- `query`: `{original, normalized, variants: [{name, weight}]}`
- `messages`: list of transformation notes

Certainty scoring: base × variant weight
- Base: primary exact = 1.0, other exact = 0.9, primary partial = 0.8, other partial = 0.7
- Variant weights: `resolved` = 1.0, nickname variants = 0.85, title-stripped variants = 0.70

### GET /v1/read/{id}

Returns `PersonReadResponse`:
```json
{
  "id": "...",
  "name": "...", "given_name": "...", "middle_name": "...", "surname": "...",
  "created_at": "...", "updated_at": "...",
  "names": [...],
  "attributes": [...]
}
```

404: `{"message": "Person not found"}`

---

## Versioning Strategy

**Scheme:** URL prefix only (`/v1/`, `/v2/`, …). No header-based negotiation. Stable versions only.

**Breaking changes** (require new major version):
- Removing or renaming an endpoint, request field, or response field
- Changing a field's type or format
- Tightening validation (previously-accepted value now rejected)
- Changing field semantics in a way that silently alters client behavior

**Non-breaking changes** (allowed within current version):
- Adding optional request or response fields
- Adding new endpoints
- Relaxing validation
- Bug fixes restoring documented behavior

**Deprecation timeline:** 1-month sunset window after successor ships.

**Deprecation signaling (three channels, applied during sunset window):**
1. `Deprecation: true` + `Sunset: <RFC 1123 date>` response headers (RFC 8594)
2. `deprecation_warning` field in every response body pointing to new version
3. FastAPI router and endpoints marked `deprecated=True` (visible in `/docs` + `/redoc`)

**Version discovery:** `GET /versions` returns all versions with `status` (`"stable"` | `"deprecated"`) and `sunset_date` (ISO 8601). Registry: `src/api/routes/health.py` → `_API_VERSIONS`.
