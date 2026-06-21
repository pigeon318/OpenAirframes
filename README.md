# OpenAirframes
 
> A free, open, community aircraft database — aggregated from authoritative sources, with explicit provenance on every field.
 
OpenAirframes is a free public API for aircraft registry data. It aggregates data from authoritative sources (currently the FAA Releasable Aircraft Database, with UK CAA G-INFO, Mictronics, and others planned) into a single normalised schema, with every row tagged by its source.
 
**Live API:** [`https://api.pigeite.com`](https://api.pigeite.com)
**Status:** v0.1.0 — basic API live, more data sources coming. Not yet recommended for production use.
 
---
 
## Why this exists
 
> *This section is a placeholder — please rewrite in your own voice. The story below is a rough sketch based on what you've told me; replace it with your own words. Your authentic motivation is the single most important thing in this README.*
 
I started this project because, when I went looking for a free aircraft database, every option I found was broken in some way. Most had blank rows, malformed data, or no information about where the data actually came from. Some were behind paywalls. Some were scrapes of scrapes, years out of date, with no clear ownership. None of them were what I wanted.
 
OpenAirframes is the database I wished existed: aggregated directly from authoritative sources, with explicit attribution on every field, no removal requests honoured, AGPLv3-licensed so it can't be quietly sold off and closed.
 
---
 
## Try it
 
A working request you can run right now:
 
```bash
curl https://api.pigeite.com/aircraft/ac0cab
```
 
```json
{
  "icao_hex": "ac0cab",
  "registration": "N876AL",
  "manufacturer": "BOEING",
  "model": "787-8",
  "type_aircraft": "fixed_wing_multi_engine",
  "year_manufactured": 2022,
  "type_engine": "turbo_fan",
  "engine_count": 2,
  "seats": 260,
  "owner_name": "WILMINGTON TRUST CO TRUSTEE",
  "owner_city": "WILMINGTON",
  "owner_state": "DE",
  "owner_country": "US",
  "status": "valid",
  "source": "FAA"
}
```
 
For full detail (35 fields including raw source codes and audit timestamps), pass `?detail=full`:
 
```bash
curl "https://api.pigeite.com/aircraft/ac0cab?detail=full"
```
 
Interactive API documentation: [`https://api.pigeite.com/docs`](https://api.pigeite.com/docs)
 
---
 
## Design principles
 
These shape every decision in the project.
 
**Authoritative sources only.** No scrapes-of-scrapes. No copied CSVs of unknown provenance. Each piece of data comes from the registry or community database that owns it, and we say so in the response.
 
**Source attribution on every row.** The `source` field tells you which dataset supplied the data. When sources disagree, the highest-trust source wins (FAA > UK CAA > Mictronics > OpenSky > user-contributed), and the loser's raw value is preserved separately for inspection.
 
**No removal requests.** OpenAirframes displays aircraft data as published by authoritative sources. We do not honour requests to hide specific aircraft, registrations, or operators. ADS-B is a public broadcast protocol; aircraft registry data is published by national civil aviation authorities. We are mirrors of public information, not arbiters of who deserves privacy.
 
**Anti-vandalism, not anti-edit.** When community submissions are added (planned), they will go through review. Edits will be tracked. Authoritative sources will always outrank user submissions. The goal is correctness, not gatekeeping.
 
**Free, open, community-owned.** AGPLv3 for code, ODbL for data. The project cannot be quietly sold and closed. Anyone can run their own instance. Improvements made by anyone running a public instance must be shared back.
 
---
 
## API
 
### `GET /aircraft/{icao_hex}`
 
Look up a single aircraft by its 24-bit ICAO hex address (lowercase, 6 characters).
 
**Path parameters**
 
| Name | Type | Description |
|---|---|---|
| `icao_hex` | string | 6 lowercase hex characters, e.g. `ac0cab` |
 
**Query parameters**
 
| Name | Type | Default | Description |
|---|---|---|---|
| `detail` | `standard` \| `full` | `standard` | Response detail level. `standard` returns ~19 commonly useful fields; `full` returns all 35 fields including raw source codes and audit timestamps. |
 
**Responses**
 
- `200 OK` — JSON object with aircraft fields
- `400 Bad Request` — `icao_hex` is not 6 lowercase hex characters
- `404 Not Found` — no aircraft in database with that hex
### `GET /health`
 
Service health check. Returns `{"status": "Running OpenAirframes ..."}`.
 
### `GET /version`
 
Database connectivity check. Returns the running PostgreSQL version string.
 
### `GET /docs`
 
FastAPI's interactive Swagger UI for exploring the API.
 
### Planned endpoints
 
- `GET /aircraft` — search and filter by registration, manufacturer, model, owner; with pagination
- `GET /stats` — aggregate counts and database freshness
---
 
## Data sources
 
### Current
 
- **FAA Releasable Aircraft Database** (US, ~314,000 aircraft). Public domain. Updated monthly.
### Planned
 
- **Mictronics** (global community database, ~450,000 entries, includes military). Adds operator data and ICAO type codes that FAA lacks.
- **UK CAA G-INFO** (~21,000 UK aircraft). On-demand scraping with caching, as bulk download is not provided.
- **Other European registries** (France, Italy, Sweden) — on-demand scraping where bulk data is unavailable.
### Not planned
 
- **Germany (LBA)** — not legally accessible to the public for redistribution.
- **Commercial sources** (FlightAware, FR24, ADSBExchange) — paywalled or restricted.
---
 
## Roadmap
 
**Phase 1 — Database + API** *(in progress)*
**Phase 2 — Webpage**
- Public web UI for searching the databasee
**Phase 3 — Live ADS-B tracking**
- Integration with personal ADS-B feeder via ultrafeeder / BEAST
- Live map of aircraft enriched with database details
- Open to community feeders
---
 
## Self-hosting
 
OpenAirframes is designed to be runnable by anyone. Requirements:
 
- Python 3.12+
- PostgreSQL 17+
- A copy of the FAA Releasable Aircraft Database (free download)
Setup instructions will be added once the schema and ingestor are considered stable. For now, the project is best read as source.
 
---
 
## Contributing
 
Pull requests welcome. Issues for bugs, feature requests, or data-quality reports are appreciated.
 
This is a solo project at present, so review and merge times will be slow. Patience appreciated.
 
---
 
## License
 
- **Code:** [GNU Affero General Public License v3.0 (AGPLv3)](https://www.gnu.org/licenses/agpl-3.0.en.html)
- **Data:** [Open Database License (ODbL)](https://opendatacommons.org/licenses/odbl/)
The AGPL covers the source code. The ODbL covers the aggregated database content. Together they ensure that OpenAirframes remains a community resource — forks, modifications, and derivative works are encouraged, but they must stay open under the same terms. The project cannot be taken closed-source or quietly sold off.
 
The data ingested from third-party sources retains its original licensing terms. FAA data is US Government public domain.
 
---
 
## Acknowledgements
 
- The **FAA** for publishing aircraft registration data as open public-domain data
- The **Mictronics** project for maintaining a free community aircraft database
- The wider **ADS-B feeder community** for keeping aviation data accessible
---
 
## Contact
 
GitHub: [@pigeon318](https://github.com/pigeon318)
Issues: file via the GitHub issue tracker.

Germany (LBA) — not legally accessible to the public for redistribution.
Commercial sources (FlightAware, FR24, ADSBExchange) — paywalled or restricted.
