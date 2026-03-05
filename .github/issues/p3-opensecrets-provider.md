## Context

OpenSecrets (opensecrets.org, operated by the Center for Responsive Politics) is the authoritative source for US federal campaign finance data. It covers contributions to and expenditures by federal candidates, PACs, parties, and outside groups, sourced from FEC filings.

The Wikidata property **P4386** stores the OpenSecrets CRP ID for US political figures. This provider reads that ID and queries the OpenSecrets API for campaign finance summaries.

## Domain knowledge: OpenSecrets

**What OpenSecrets covers:**
- All US federal candidates (House, Senate, President) since the 1990s
- PAC contributors and recipients
- Industry and sector breakdown of contributions
- "Revolving door" — former government officials who became lobbyists
- Outside spending (Super PACs, 501c4s)

**What it does NOT cover:**
- State/local campaign finance (these are in separate state databases)
- International political finance
- Persons who have never been federal candidates or major donors

**The CRP ID (P4386):** OpenSecrets assigns a unique alphanumeric ID to each tracked politician, e.g. `N00007360` for Nancy Pelosi. This is the primary lookup key.

## API access

OpenSecrets has a REST API documented at `https://www.opensecrets.org/api/`.

**Authentication:** Free API key required. Register at `https://www.opensecrets.org/api/admin/`. The key is stored in the `env` file as `OPENSECRETS_API_KEY` and read via environment variable.

**Base URL:** `https://www.opensecrets.org/api/`

### Relevant endpoints

**`getLegislators`** — Basic info + finance summary for a legislator:
```
GET https://www.opensecrets.org/api/?method=getLegislators&id={crp_id}&output=json&apikey={key}
```

Response includes: `@cid` (CRP ID), `@firstlast` (name), `@party`, `@office`, `@gender`, `@first_elected`, `@exit_code`, `@comments`, `@phone`, `@fax`, `@website`, `@webform`, `@congress_office`, `@bioguide_id`, `@votesmart_id`, `@feccandid`, `@twitter_id`, `@youtube_url`, `@facebook_id`, `@birthdate`.

**`candSummary`** — Fundraising summary for a candidate:
```
GET https://www.opensecrets.org/api/?method=candSummary&cid={crp_id}&cycle=YYYY&output=json&apikey={key}
```
`cycle` is a 4-digit election year (even years only, or `0` for most recent). Returns: total raised, total spent, cash on hand, debt, industry breakdown.

**`candContrib`** — Top contributors:
```
GET https://www.opensecrets.org/api/?method=candContrib&cid={crp_id}&cycle=YYYY&output=json&apikey={key}
```

### Rate limits

The free tier allows ~200 API calls per day. The provider must:
1. Check the `X-RateLimit-Remaining` response header if present
2. Log a warning (not raise an exception) when near the limit

## What the provider extracts

| key | value_type | value | notes |
|---|---|---|---|
| `opensecrets_url` | `platform_url` | `"https://www.opensecrets.org/members-of-congress/summary?cid=N00007360"` | platform=`opensecrets` |
| `party` | `text` | `"Democrat"` | Skip if already present |
| `first_elected` | `date` | `"1987-01-01"` | Year only; store as Jan 1 of that year |
| `gender` | `text` | `"F"` | Raw OpenSecrets value |
| `fec_candidate_id` | `text` | `"H8CA05036"` | FEC candidate ID — useful for future FEC provider |
| `bioguide_id` | `text` | `"P000197"` | Congressional Bioguide ID |
| `votesmart_id` | `text` | `"26732"` | Vote Smart ID |

Campaign finance summary data (raised, spent) is intentionally **not** stored as `PersonAttribute` records — this data is highly time-dependent and point-in-time snapshots would be misleading. Include it only if a `financial_summary` attribute type and refresh strategy are designed separately.

## Input: where to find the P4386 value

The CRP ID is extracted from `person.existing_attributes` where `key = "opensecrets-crp-id"` — written by `WikidataProvider` when it extracts the P4386 claim.

```python
dependencies = [
    Dependency("wikidata_qid", skip_if_absent=True),
    Dependency("opensecrets-crp-id", skip_if_absent=True),
]
```

## Secrets management

```python
import os
API_KEY = os.environ.get("OPENSECRETS_API_KEY", "")
```

If `OPENSECRETS_API_KEY` is empty, the provider raises `ImproperlyConfigured` at instantiation time (not at run time, so misconfiguration is surfaced early).

Add to `env` file (not committed): `OPENSECRETS_API_KEY=your_key_here`
Add to `deploy/person-validator-api.service` and `deploy/person-validator-web.service` EnvironmentFile stanza.

## Acceptance criteria

- [ ] `OpenSecretsProvider` in `src/core/enrichment/providers/opensecrets.py`
- [ ] API key read from environment; `ImproperlyConfigured` raised if missing
- [ ] Reads `opensecrets-crp-id` from `person.existing_attributes`
- [ ] Calls `getLegislators` endpoint and extracts fields listed above
- [ ] Skips attributes already present at higher confidence
- [ ] Rate limit warning logged when near limit
- [ ] Returns `no_match` on 404 or empty response
- [ ] Both dependencies declared correctly
- [ ] Tests use mocked HTTP with fixture JSON
- [ ] `OPENSECRETS_API_KEY` documented in README and `.env.example`
- [ ] Integration test (marked `@pytest.mark.integration`, skipped if key absent)
