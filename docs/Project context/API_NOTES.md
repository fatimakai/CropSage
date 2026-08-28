# CropMatch AI - API Notes

## Planned API Use

CropMatch AI is planned to use APIs only as evidence providers behind a server-side boundary. FortyGuard supplies the primary recent/local heat evidence and supported short-horizon risk; NASA POWER supplies a coarse long-term regional climate baseline. The agent chooses which approved tools to call, but deterministic code normalizes provider data, calculates scores, and validates the result.

No CropMatch API integration has been implemented. The local `temperature-api-quickstart/` directory is a reference client/notebook collection, not the application. Its bundled cached JSON proves example response shapes for selected San Jose requests, but does not prove that this project has successfully made a live call with the hackathon key.

## FortyGuard Temperature API

### Purpose

FortyGuard is the required and technically central heat-intelligence provider. The planned MVP will use it to produce recent/local heat evidence, crop-threshold exposure metrics, and an immediate up-to-12-hour event flag where supported. At least one demo crop's risk or rank must change because of a FortyGuard-derived metric; otherwise the integration would be merely decorative.

### Documentation and Resources

- Official docs: <https://docs-api.fortyguard.com/docs>
- Quickstart: <https://docs-api.fortyguard.com/docs/quickstart>
- Authentication: <https://docs-api.fortyguard.com/docs/authentication>
- Heatmap: <https://docs-api.fortyguard.com/docs/create-heatmap>
- Environmental parameters: <https://docs-api.fortyguard.com/docs/environmental-parameters>
- Status: <https://docs-api.fortyguard.com/docs/check-status>
- Heat intelligence: <https://docs-api.fortyguard.com/docs/heat-intelligence>
- Known limitations: <https://docs-api.fortyguard.com/docs/limitations>
- Release notes: <https://docs-api.fortyguard.com/docs/release-notes>
- Local reference client: `temperature-api-quickstart/fortyguard/client.py`
- Local endpoint walkthroughs: `temperature-api-quickstart/notebooks/00_setup.ipynb` through `05_heat_intelligence_report.ipynb`
- Local use-case notebooks: `temperature-api-quickstart/notebooks/use_cases/`
- Admin console/dashboard: the local quickstart says keys can be checked in the FortyGuard console, but no verified dashboard URL was preserved. `Unknown / Needs verification`.

### Base URL

```text
https://api.fortyguard.com
```

The local quickstart also records a development override:

```text
https://tos-enterprise-api.dev.app.fortyguard.com
```

Use the production URL unless FortyGuard explicitly provides development-environment access.

### Authentication

- Method: API key in the `api-key` request header; no OAuth exchange.
- Content type for JSON requests: `application/json`.
- Planned environment variables:

```env
FORTYGUARD_API_KEY=<secret>
FORTYGUARD_BASE_URL=https://api.fortyguard.com
```

The key must remain in server-side environment variables. Never place it in browser code, logs, cached responses, notebooks committed for submission, screenshots, or documentation.

### Common Asynchronous Lifecycle

Analysis submissions use a submit-then-poll pattern:

1. `POST /v1/<endpoint>` with JSON.
2. Read `data.activity_id` from the submission response.
3. Poll `GET /v1/status/{activity_id}` with the same `api-key` header.
4. Treat `Processing` as non-terminal; `Completed`/`Succeeded` as success; `Failed`/`Error` as terminal failure.
5. Stop after a bounded deadline. The local client defaults to 3-second polling and a 600-second overall wait for most analysis endpoints.
6. A 404 immediately after submission may be eventual consistency rather than permanent failure; the local client retries it until the deadline.

Typical submission envelope:

```json
{
  "error": false,
  "status_code": 200,
  "message": "Submitted Successfully",
  "data": { "activity_id": "ACTIVITY_UUID" }
}
```

Typical completed envelope:

```json
{
  "error": false,
  "status_code": 200,
  "message": "Completed",
  "data": {
    "activity_id": "ACTIVITY_UUID",
    "status": "Completed",
    "result": {}
  }
}
```

### Common Errors

| Error/status | Meaning and planned handling |
|---|---|
| `400` / `422` | Invalid input or schema validation. Show a useful field error; do not retry unchanged input. |
| `401` | Missing/invalid API key, or possibly a key/tier issue according to the quickstart. Stop and verify credentials. |
| `403` | Insufficient plan access/authorization. Do not retry as a transient failure. |
| `404` immediately after submit | Activity may not yet be visible. Retry only within the bounded poll deadline. |
| `404` later | Activity not found. Stop and record the `activity_id`. |
| `429` | Rate limit exceeded. Numerical rate limit is `Unknown / Needs verification`; use bounded backoff and cached evidence. |
| `500` | Server-side error. Use a bounded retry/fallback policy, never infinite polling. |
| `Processing` | Continue bounded polling. |
| `Completed` / `Succeeded` | Retrieve and normalize endpoint-specific result. Credits are charged only on completion according to the docs. |
| `Failed` / `Error` | Terminal failure. Stop; failed tasks are documented as not consuming credits. |

### Common Limits and Constraints

- Regional coverage: United States only on documented Basic, Premium, and Startup plans.
- Coordinates: latitude `[-90, 90]`, longitude `[-180, 180]`, and currently within the US.
- GeoJSON coordinates: `[longitude, latitude]`.
- Polygon: valid GeoJSON `FeatureCollection` with a closed `Polygon` ring.
- Date format: `YYYY-MM-DD`; time: `HH:MM` in 24-hour format.
- Heatmap granularity: 60, 80, or 100 metres.
- Credits: documented plan allocations are 1,000,000/month for Basic, 5,000,000/month for Premium, and 1,000,000 for the Startup six-month window. The actual hackathon key's plan and balance are `Unknown / Needs verification`.
- Failed/invalid tasks are documented as free; credits are deducted at `Completed`.
- Numerical request-rate limits are not documented in the material reviewed. `Unknown / Needs verification`.

### Documentation Conflicts Requiring Live Verification

1. **Historical/forecast window:** Current official heatmap and limitation pages say `2019-01-01` through now, with heatmap forecasting up to 12 hours. The local quickstart says `2021-01-01` through today and says future dates fail. Use the current official rule provisionally, but test the hackathon key.
2. **Range-of-days filter:** The current heatmap page documents `filter_type=4` with a range no longer than about one month. The current general limitations page lists only filter types 1-3. The local client implements type 4. `Needs verification`.
3. **Heat-intelligence retrieval:** The endpoint page and current client describe JSON with a temporary `result.download_link`; the status page also contains older streamed-PDF guidance. The client supports both. `Needs verification`.
4. **Heatmap units:** Current official docs, local README, and cached values identify TCM temperatures as Celsius. A stale `client.py` docstring says Fahrenheit. Treat Celsius as authoritative and verify `stats_data`/sample values.
5. **Environmental arrays:** Official schema examples show arrays; bundled cached JSON stores several parameter series as space-delimited strings. The adapter must normalize both until live behavior is confirmed.
6. **Endpoint count:** Official quickstart/release material mentions six POST endpoints and Temperature Property access, while the local client exposes five analysis methods plus usage endpoints. Temperature Property is not part of the CropMatch plan. `Needs verification` before claiming the local client wraps every current endpoint.

## `POST /v1/heatmap`

### Purpose and Status

- **Confirmed from official docs and local client.**
- **Likely to be used in implementation.**
- Local cached quickstart results exist for `tcm`, `exceedance`, and `persistence`; these are reference data, not a CropMatch live test.

This endpoint generates a tile-based GeoJSON thermal layer over a polygon. It is the planned source for recent/local temperature fit, threshold-exceedance duration, persistence, time of peak, and supported 12-hour operational risk.

### Request

Required or conditionally required fields:

| Field | Type | Notes |
|---|---|---|
| `polygon_aoi` | GeoJSON `FeatureCollection` | Closed Polygon, coordinates `[lon, lat]`. |
| `date_time.start_date` | string | `YYYY-MM-DD`. Current official range begins 2019; `Needs verification` against key. |
| `date_time.filter_type` | integer | `1` single hour; `2` same-day hour range; `3` full day; `4` day range is documented on the endpoint page but conflicts with general limitations. |
| `date_time.start_time` | string | Required for types 1 and 2. |
| `date_time.end_time` | string | Required for type 2; same-day range, documented maximum 23 hours. |
| `date_time.end_date` | string | Required for type 4 if supported; documented cap about one month. |
| `granularity` | integer | `60`, `80`, or `100` metres. |
| `analytic_type` | string | Optional, default `tcm`; also `time_of_measure`, `exceedance`, `persistence`. |
| `threshold` | number | Celsius; required by local client for `exceedance`/`persistence`; API default is documented as 30 C. |
| `direction` | string | `above` or `below`; relevant to `exceedance`/`persistence`. |

Sanitized example:

```http
POST https://api.fortyguard.com/v1/heatmap
api-key: ${FORTYGUARD_API_KEY}
Content-Type: application/json
```

```json
{
  "polygon_aoi": {
    "type": "FeatureCollection",
    "features": [{
      "type": "Feature",
      "properties": {},
      "geometry": {
        "type": "Polygon",
        "coordinates": [[
          [-121.9010, 37.3295],
          [-121.8990, 37.3295],
          [-121.8990, 37.3310],
          [-121.9010, 37.3310],
          [-121.9010, 37.3295]
        ]]
      }
    }]
  },
  "date_time": {
    "start_date": "2024-07-15",
    "end_date": "2024-07-21",
    "filter_type": 4
  },
  "granularity": 100,
  "analytic_type": "exceedance",
  "threshold": 35.0,
  "direction": "above"
}
```

Use filter type 4 only after live verification.

### Response Structure

For `tcm`:

- `result.map_data`: GeoJSON `FeatureCollection` of tile polygons.
- Tile `properties`: `tile_id`, `average_temperature`, `min_temperature`, `max_temperature` in Celsius according to current official docs/README.
- `result.stats_data`: aggregate temperature statistics and distribution/frequency fields.

For `time_of_measure`, `exceedance`, and `persistence`:

- Tile `properties.value` instead of the TCM temperature fields.
- `stats_data.analytic_type`, `units`, `n_cells`, `min`, `max`, and `mean`.
- `time_of_measure`: UTC hour of peak, 0-23.
- `exceedance`: count of hours past the threshold, not degree-hours.
- `persistence`: longest continuous run of hours past the threshold.

### Plan Limits

- Basic/Startup: heatmap area up to 10 square miles.
- Premium: heatmap area up to 50 square miles.
- Full map statistics are documented for both.
- Current rural response quality and agricultural coverage remain `Needs verification`.

### Planned Usage

Use a small farm polygon or representative point buffer. Prefer `exceedance` and `persistence` for crop-specific exposure duration; use TCM for temperature context. Convert native provider values only at the display boundary. Cache by polygon/coordinate, time range, analysis type, threshold, direction, granularity, and `activity_id`. The demo must disclose whether evidence is live or cached.

### Outstanding Questions

- Does the chosen farm return plausible values at the required granularity?
- Is range-of-days (`filter_type=4`) accepted for the hackathon key?
- What exact timestamps/time zones apply to requested hours and returned values?
- How should farm-wide values be aggregated across intersecting tiles?
- Which sourced crop thresholds and windows should be requested?
- Can a future request up to 12 hours be made reliably, and how should it be labeled?

## `POST /v1/env_params`

### Purpose and Status

- **Confirmed from official docs and local client.**
- **Considered, not required for the core ranking.** `Status: Undecided`.
- Local cached quickstart responses exist, but no CropMatch live test is recorded.

The endpoint returns time-aligned environmental and thermal-stress parameters for a point. It may supply heat index, apparent temperature, wet-bulb temperature, humidity, precipitation, cloud cover, air-quality indicators, gases, elevation, and solar irradiance.

### Request

| Field | Type | Notes |
|---|---|---|
| `latitude` | number | US point. |
| `longitude` | number | US point. |
| `temperature` | number | Celsius anchor supplied by the caller. |
| `date_time.start_date` | string | `YYYY-MM-DD`. |
| `date_time.filter_type` | integer | Official endpoint page lists 1 single hour, 2 range of hours, 3 full day. |
| `date_time.start_time` / `end_time` | string | Conditional on filter type. |
| `analysis` | array of strings | Optional subset in the local client; Basic is documented as up to three parameters per request, Premium all. |

Local-client accepted analysis names include:

```text
heat_index_celsius
apparent_temperature_celsius
wet_bulb_temperature_celsius
relative_humidity_percent
precipitation_mm
cloud_cover_octas
air_quality:idx
air_quality_no2:idx
air_quality_o3:idx
air_quality_pm2p5:idx
air_quality_pm10:idx
air_quality_so2:idx
aqi_us_co
methane_ppb
co2_ppm
elevation
solar_irradiance
```

Sanitized example:

```json
{
  "latitude": 37.3305,
  "longitude": -121.9000,
  "temperature": 32.5,
  "date_time": {
    "start_date": "2024-07-15",
    "filter_type": 3
  },
  "analysis": [
    "apparent_temperature_celsius",
    "relative_humidity_percent",
    "wet_bulb_temperature_celsius"
  ]
}
```

### Response Structure

- `result.metadata`: timezone, offset, exact time range, interval, count, timestamps.
- `result.locations[]`: `lat`, `lon`, elevation, caller-supplied temperature, `parameters`, and `solar_irradiance`.
- `parameters`: time-aligned series; live shape may be arrays or space-delimited strings. Normalize and validate count against timestamps.
- `solar_irradiance.clear_sky`: GHI, DNI, and DHI plus a description.

### Important Interpretation Limitation

The local quickstart reports that `heat_index_celsius` applies the single submitted temperature anchor across the whole time series while humidity varies. It is therefore a humidity-sensitivity curve at a fixed temperature, **not a diurnal temperature forecast**. For the MVP, do not count its duration as crop exposure. Use heatmap `exceedance` for duration and, if used at all, interpret heat index only near the time when actual/apparent temperature is close to the anchor. `Needs verification` against live behavior.

The quickstart also found identical environmental arrays for nearby parcels, indicating a coarser weather grid than field separation. Do not use this endpoint to distinguish adjacent farms without validation.

### Planned Usage

Optional contextual evidence only. The core scoring should not depend on it until the fixed-anchor behavior, spatial resolution, parameter shape, and hackathon plan access are verified.

## `GET /v1/status/{activity_id}`

### Purpose and Status

- **Confirmed and required** for all asynchronous FortyGuard submissions.

### Request

- Path parameter: provider-issued `activity_id`.
- Header: `api-key: ${FORTYGUARD_API_KEY}`.
- No request body.

### Response

- `data.status`: commonly `Processing`, `Completed`, or `Failed`; local client also accepts case-insensitive `Succeeded` and `Error`.
- `data.result`: endpoint-specific result on completion.
- Heat Intelligence may return a temporary `result.download_link` or legacy streamed content; see the documented conflict above.

### Planned Usage

Use bounded polling with a timeout, retry short-lived post-submit 404s, stop on terminal states, record `activity_id`, and never retry indefinitely.

## `POST /v1/satellite`

### Purpose and Status

- **Confirmed from official docs/local client.**
- **Premium only.**
- **Researched but rejected/deferred for the CropMatch MVP.**

It segments a satellite tile into land-cover classes and returns Base64 imagery plus coverage metrics. It could eventually help explain local heat through vegetation/building/road composition, but it is not needed for the crop-selection decision loop.

### Request Fields

- `sat.latitude`, `sat.longitude`.
- `date_time` with `start_date`, `filter_type`, and conditional time fields.
- `granularity`: 60, 80, or 100 metres.
- Official search material records a date up to about five hours in the future and recommends matching the heatmap time. `Needs verification`.

### Response Fields

The documented result includes imagery year and a segmentation object with image dimensions, mode, processing time, request ID, per-class segments, legend, and Base64 `image_content`. Add a `data:image/png;base64,` prefix when necessary for browser rendering.

## `POST /v1/streetview`

### Purpose and Status

- **Confirmed from official docs/local client.**
- **Premium only.**
- **Researched but rejected/deferred for the CropMatch MVP.**

It segments ground-level imagery into features such as buildings, vegetation, and road surfaces. It is relevant to urban/site heat work in the quickstart, not to the chosen one-week crop comparison core.

### Request Fields

- `latitude`, `longitude`.
- `vertical_angle` in degrees.
- `horizontal_angle` in degrees (0-360 documented).
- `back_view` boolean.

### Response Fields

Documented results include analyzed coordinates, front view and optional back view, original/segmented Base64 imagery, and class coverage/legend metadata. Exact full schema is not needed for CropMatch and must be rechecked if added later.

## `POST /v1/heat_intelligence`

### Purpose and Status

- **Confirmed from official docs/local client.**
- **Premium only.**
- **Researched but rejected/deferred for the CropMatch MVP.**

It generates a multi-dimensional PDF report for an urban location using one or more analysis categories. A PDF report is not required for the core pre-planting agent.

### Request Fields

- `latitude`, `longitude`.
- `temperature` in Celsius.
- `date` in `YYYY-MM-DD`, intended to match the heatmap reading.
- `analysis`: subset of `geographic`, `environmental`, `urban`, `events`, `anthropogenic`.

### Result

Current endpoint docs and the local client expect `data.result.download_link` on completion. The signed link is temporary, should be used immediately, and must not be logged or shared. The local client retains legacy support for a PDF streamed directly from the status endpoint. Live behavior `Needs verification`.

## Usage Endpoints

### `POST /v1/system/fetch-api-key-usage`

- **Purpose:** Current billing-cycle/credit summary.
- **Status:** Confirmed in the local client and release notes; useful during setup, not part of farmer workflow.
- **Authentication:** The local client sends the API key header and an `api_key` body field. Do not log the request body.
- **Response:** Plan, usage/remaining credits, and cycle information are expected; exact schema `Needs verification`.

### `POST /v1/system/fetch-api-key-custom-usage`

- **Purpose:** Usage over a requested range.
- **Inputs:** `api_key`, ISO `start_date`, ISO `end_date`; the local client expands date-only strings to UTC day boundaries.
- **Status:** Confirmed in the local client and release notes; development/monitoring only.
- **Response:** Exact schema `Needs verification`.

## Temperature Property API

Official introductory/release material mentions a Temperature Property API and six POST endpoints, but the local quickstart client has no corresponding method and the planning record never selected it for CropMatch.

`Status: Undecided / Not planned for MVP`

Do not add it merely to increase endpoint count. If FortyGuard requires it for the hackathon, obtain the current endpoint documentation first.

## Jupyter and Local Development Notes

The local quickstart provides the preserved testing workflow:

1. Use Python 3.10 or newer.
2. Install `temperature-api-quickstart/requirements.txt` in a virtual environment.
3. Create a local `.env` from the example and set `FORTYGUARD_API_KEY` and optionally `FORTYGUARD_BASE_URL`.
4. Launch Jupyter from the quickstart repository root so the `fortyguard` package imports correctly.
5. Run `notebooks/00_setup.ipynb` top-to-bottom; its final check should display plan and remaining credits.
6. Use `01_create_heatmap.ipynb` and `02_environmental_parameters.ipynb` first for the CropMatch-relevant endpoints.
7. Pass `wait=False` to inspect submit/poll behavior manually, or use client methods for bounded polling.
8. Save only sanitized provider responses and preserve original timestamps, request parameters, and `activity_id`.

The quickstart's parcel notebooks include cached San Jose responses that can run offline. They should be treated as schema/UX examples, not as CropMatch's selected farm or agricultural validation.

No Postman workflow was found in the preserved planning materials. `Status: Undecided` whether a Postman collection is worth creating; Jupyter/client testing is already documented.

## NASA POWER API

### Purpose

NASA POWER is the planned long-term **regional** climate baseline for temperature, precipitation, humidity-related, and solar context. It complements FortyGuard's recent/local heat signal; it must never be described as field-resolution data.

### Documentation

- Data-request tutorial: <https://power.larc.nasa.gov/docs/tutorials/service-data-request/api/>
- API services: <https://power.larc.nasa.gov/docs/services/api/>
- Climatology API: <https://power.larc.nasa.gov/docs/services/api/temporal/climatology/>
- Parameter dictionary: <https://power.larc.nasa.gov/parameters/>

### Base URL and Authentication

```text
https://power.larc.nasa.gov/api
```

No API key/authentication was discussed or shown in the official examples. Planned environment variable: none.

### Likely Endpoint

```http
GET /api/temporal/climatology/point
```

Current official example:

```text
https://power.larc.nasa.gov/api/temporal/climatology/point?parameters=T2M,T2M_MAX&community=AG&longitude=-121.9000&latitude=37.3305&format=JSON
```

Potential request parameters:

| Parameter | Purpose |
|---|---|
| `parameters` | Comma-separated POWER variable codes. Exact CropMatch set `Status: Undecided`. |
| `community` | Use `AG` for agroclimatology unless testing shows another product is required. |
| `longitude`, `latitude` | Farm representative point. |
| `format` | JSON planned; CSV/ASCII/NetCDF are also documented. |
| `start`, `end` | Optional years for custom climatology. Baseline period `Status: Undecided`. |

Daily history is an alternative if climatology cannot support the required derived feature:

```http
GET /api/temporal/daily/point
```

### Response Structure

Expected JSON contains metadata/header information and parameter time series keyed by the requested variable codes and climatology periods/months. Exact normalized contract must be fixed after a sample call. `Needs verification`.

### Limits and Constraints

- Free, globally available data according to NASA documentation.
- Maximum 20 parameters in one single-point climatology request; regional requests are limited to one parameter.
- Current documented resolution is approximately 0.5 x 0.625 degrees for meteorology and 1 x 1 degree for solar products.
- Do not request points more densely than the product resolution; repeated coordinates may return the same grid cell.
- NASA warns not to submit excessive synchronous requests; an official example says no more than five concurrent requests.
- Near-real-time meteorological values may be replaced by improved climate-quality products two to three months later.
- Numerical quota/rate limit: `Unknown / Needs verification`.

### Planned Usage

Make one point request per rounded farm coordinate and variable/baseline set; cache normalized JSON because climatology changes slowly. Label it as a regional baseline and record product resolution and climatology period. Use it for climate fit and recent anomaly context, not for within-field differences.

### Outstanding Questions

- Which parameters best support the six selected crops?
- Which climatology years should define the baseline?
- Should the MVP use the climatology endpoint or cached summarized daily history?
- What missing-value sentinels and units apply to each selected parameter?
- How should seasonal months align with planting and estimated sensitive stages?

## USDA NASS Developer Resources

### Purpose and Status

USDA NASS was considered only as optional local evidence: a pre-cached county summary could show whether a recommended crop is historically prevalent in the region.

`Status: Optional / not selected for the core MVP`

Documentation: <https://www.nass.usda.gov/developer/>

No specific endpoint, authentication flow, request schema, or response contract was finalized in the planning record. `Unknown / Needs verification`.

If used, NASS must remain a sanity/validation signal. Historical prevalence is not future suitability and must not dominate the score.

## APIs Not Selected

- USDA Web Soil Survey/SSURGO was researched as a data source, but no runtime API integration was chosen. The MVP should accept farmer input and manually verify one demo profile.
- NOAA was mentioned in the earlier plan only as a manually entered seasonal category, not an API integration.
- FAO Ecocrop and GAEZ were investigated as references/benchmarks, not selected runtime APIs.
