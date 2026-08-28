# CropMatch AI - Dataset Research and Data Plan

## Overview

External data is needed because FortyGuard alone does not answer the full crop-selection question. FortyGuard provides the primary recent/local heat signal and supported short-horizon risk, but the recommendation also needs long-term regional climate context, crop-specific thermal/soil/water/calendar requirements, and farm constraints. Optional soil and historical-production sources can improve confidence or sanity-check results, but should not expand the one-week MVP beyond a defensible decision loop.

The planned minimum data stack is:

1. FortyGuard live or disclosed cached heat evidence.
2. NASA POWER long-term regional baseline.
3. A hand-curated, versioned six-crop catalog with citations.
4. Farmer-provided farm/soil/irrigation fields plus one manually verified demo profile.

No CropMatch dataset pipeline has been implemented. Bundled JSON under `temperature-api-quickstart/data/` belongs to the reference quickstart and must not be mistaken for the chosen farm, model training data, or validated agricultural evidence.

## FortyGuard Temperature Data

### Source

- **Provider:** FortyGuard
- **Documentation:** <https://docs-api.fortyguard.com/docs>
- **API base:** <https://api.fortyguard.com>

### Description

Dynamic tile-based temperature and heat-analysis data returned by the FortyGuard Temperature API. The most relevant heatmap modes are temperature snapshot (`tcm`), time of peak, threshold exceedance hours, and persistence. Environmental parameters are available but optional and require careful interpretation.

### Relevant Variables / Fields

- Tile geometry and `tile_id`.
- `average_temperature`, `min_temperature`, `max_temperature` for TCM.
- `value`, `analytic_type`, and `units` for time-of-measure/exceedance/persistence.
- Aggregate min/max/mean and distribution/frequency statistics.
- Activity ID, request time window, threshold, direction, granularity, and completion timestamp.
- Optional environmental parameters: apparent temperature, wet-bulb temperature, humidity, precipitation, and solar irradiance.

### Geographic Coverage

- Current official scope: United States only.
- Polygon heatmaps at 60, 80, or 100 metre tile granularity.
- Basic/Startup documented area cap: 10 square miles; Premium: 50 square miles.
- Rural agricultural plausibility: `Needs verification`.

### Temporal Coverage

- Current official docs: 2019-01-01 to present, with heatmap forecast up to 12 hours.
- Local quickstart: 2021-01-01 to today, future unsupported.
- `Needs verification` with the actual hackathon key because the sources conflict.
- Single hour, same-day range, full day, and possibly up-to-one-month day range; filter type 4 is inconsistently documented.

### Format

- Asynchronous REST API.
- JSON submission/status envelopes.
- GeoJSON `FeatureCollection` tile layer and JSON statistics.
- Heat Intelligence returns a PDF via a temporary signed link or legacy stream; not selected for MVP.

### Dataset Size

Request-dependent. Tile counts grow with polygon area and granularity. No fixed dataset download is planned.

### Licensing / Usage Restrictions

Official plan material documents a commercial license on Basic/Premium/Startup, but hackathon reuse and redistribution rules for cached responses were not captured. `Needs verification` before publishing provider data.

### Why We Considered It

It is the required API and the intended source of the project's differentiating recent/local heat signal.

### Strengths

- Localized, high-resolution heat tiles relative to regional climate products.
- Threshold-exposure and persistence analyses are directly useful for crop-specific heat risk.
- Short-horizon forecasting can support an operational event flag.
- Clear async task/result pattern and cacheable responses.

### Limitations

- US-only and rural performance unverified.
- Short forecast horizon cannot support seasonal predictions.
- Asynchronous latency and plan/credit limits can affect the demo.
- Documentation conflicts require live testing.
- Environmental parameters may be coarser than a farm and fixed-temperature heat index is not a diurnal forecast.

### Decision

`Selected`

### Reason for Decision

Required by the hackathon and central to the heat-aware differentiation.

### Planned Usage

Request a selected farm polygon/representative point, derive crop-specific preferred-range and threshold-exposure metrics, record full provenance, and cache one complete demo response. A disclosed cache may be used only when live data is unavailable. At least one rank or risk must visibly change because of this evidence.

## NASA POWER

### Source

- **Provider:** NASA Langley Research Center POWER project
- **Data-request docs:** <https://power.larc.nasa.gov/docs/tutorials/service-data-request/api/>
- **Climatology docs:** <https://power.larc.nasa.gov/docs/services/api/temporal/climatology/>
- **Parameter dictionary:** <https://power.larc.nasa.gov/parameters/>

### Description

Global meteorological and solar products exposed through hourly, daily, monthly, annual, and climatology services. CropMatch plans to use point climatology or summarized daily history as a long-term regional climate baseline.

### Relevant Variables / Fields

The exact set is `Status: Undecided`. Discussed families include:

- Temperature and temperature maxima/minima.
- Precipitation.
- Humidity-related variables.
- Solar radiation/irradiance.
- Coordinate, time period, units, product metadata, and missing-value sentinels.

`T2M` and `T2M_MAX` appear in official climatology examples, but no final CropMatch parameter list has been selected.

### Geographic Coverage

- Global point and regional services.
- Documented approximate resolution: 0.5 x 0.625 degrees for meteorology and 1 x 1 degree for solar products.
- Must be labeled a **regional baseline**, never field-level truth.

### Temporal Coverage

- Long-term climatology and hourly/daily/monthly products.
- Exact available date range and chosen baseline years were not fixed in the planning record. `Needs verification`.
- NASA notes that improved climate-quality meteorological products can replace near-real-time values after two to three months.

### Format

REST API returning JSON, CSV, ASCII, or NetCDF depending on endpoint/request.

### Dataset Size

Small for a single point and selected parameters. The planned cache is one normalized response per rounded coordinate, variable set, and baseline period.

### Licensing / Usage Restrictions

Described by NASA as free and globally available. Exact attribution/terms for the submission were not recorded. `Needs verification` before distribution.

### Why We Considered It

FortyGuard's catalog/forecast horizon cannot provide the long-term climate context needed to compare crops or express recent anomaly.

### Strengths

- Authoritative, free, global data.
- Agriculture community option and documented climatology endpoint.
- Stable, slowly changing baseline suitable for caching.

### Limitations

- Coarse grid relative to a farm.
- Synchronous service should not be called excessively.
- Exact parameter mapping, units, sentinel handling, and baseline period are undecided.
- Cannot validate within-field differences.

### Decision

`Selected`

### Reason for Decision

It provides the smallest credible long-term baseline without building a large climate pipeline.

### Planned Usage

Fetch a point climatology or summarized daily series for the representative farm coordinate; cache by rounded coordinate/variables/period; normalize units; align relevant months with the planned planting/season window; use for a 20% climate-fit component and recent-versus-normal context. `Needs verification` after a sample request.

## Verified Six-Crop Catalog

### Source

- **Provider:** A CropMatch-maintained derived dataset, manually curated from USDA, US university extension, peer-reviewed crop-stage heat studies, and secondary FAO plausibility references.
- **Dataset URL:** None; it has not been created.

### Description

A small, versioned JSON catalog containing the only crops the MVP is allowed to recommend. It is intentionally limited to six auditable records.

### Relevant Variables / Fields

| Group | Planned fields |
|---|---|
| Identity | `crop_id`, `common_name`, `scientific_name`, `supported_region`, `variety_scope` |
| Thermal | `preferred_temp_min/max`, `extreme_heat_threshold`, `heat_exposure_duration`, `base_temp`, `upper_temp` |
| Growth stage | `sensitive_stage`, `stage_window_or_GDD`, `threshold_source` |
| Soil | `accepted_textures`, `pH_min/max`, `drainage_requirement`, `root_depth_note` |
| Water | `water_demand_class`, `irrigation_dependency`, `drought_tolerance_class` |
| Calendar | `planting_months`, `season_length_days_or_GDD`, `harvest_window_note` |
| Evidence | `source_urls`, `source_type`, `region`, `reviewed_at`, `reviewer_note`, `confidence` |

### Geographic Coverage

One selected US agricultural region. The region is `Status: Undecided`.

### Temporal Coverage

Requirements are reviewed records rather than a time series. Every record needs a review date and catalog version.

### Format

Planned local JSON; database storage may follow later.

### Dataset Size

Six crop records, potentially reduced to four only if evidence verification threatens the core build.

### Licensing / Usage Restrictions

Each threshold/rule must retain a source URL and allowable attribution. Copying a third-party crop database without verified licensing is prohibited. Exact source licenses are `Needs verification` during curation.

### Why We Considered It

The language model and scorer need a bounded, reproducible source of crop IDs and agronomic screening rules.

### Strengths

- Auditable and feasible within one week.
- Prevents invented crops/thresholds.
- Supports build-time validation and versioned calculations.

### Limitations

- Six crops cannot represent general US agriculture.
- Requirements vary by variety, region, management, and evidence quality.
- The actual region and crop list have not been selected.

### Decision

`Selected`

### Reason for Decision

A small verified catalog is more defensible than a large unreviewed or scraped database.

### Planned Usage

Curate six plausible alternatives in the same region with meaningful heat/water tradeoffs. Reject inverted ranges at build time. A threshold without a source may be displayed as unverified but may not trigger a hard filter. Save catalog version with every recommendation.

## Farmer Input and Demonstration Soil Profile

### Source

- **Provider:** Farmer/user input; one demo profile manually checked against official soil information.
- **Reference:** <https://www.nrcs.usda.gov/resources/data-and-reports/web-soil-survey>

### Description

Farm constraints that are not reliably supplied by the heat/climate APIs: soil texture, pH, drainage, irrigation availability, planting time, and location.

### Relevant Variables / Fields

- Location/coordinate or small polygon.
- Planting month/date.
- Soil texture and pH, including unknown.
- Drainage.
- Irrigation availability.
- Source label (`farmer`, `demo`, `soil survey`, etc.) and profile version.

### Geographic Coverage

One US demonstration farm for the MVP; user-entered US locations if the final demo supports them.

### Temporal Coverage

Current self-reported/profile state. No historical farm record is planned.

### Format

Web form normalized into `FarmProfile`; one static demo record.

### Dataset Size

One demo farm plus current session input.

### Licensing / Usage Restrictions

Farmer-provided data should be minimized and not retained unnecessarily. Privacy policy is not finalized. `Needs verification` before any real-user storage.

### Why We Considered It

Soil, water, and planting constraints materially affect the shortlist and are not provided at farm resolution by the selected APIs.

### Strengths

- Very low integration overhead.
- Allows explicit unknown values.
- Preserves the user's actual constraints.

### Limitations

- May be incomplete or inaccurate.
- Self-reported values are not laboratory/field validation.

### Decision

`Selected`

### Planned Usage

Only location and planting time are mandatory. Unknown soil fields do not become matches; they reduce confidence and generate a next-check recommendation. The demo farm should have one manually verified profile.

## USDA Web Soil Survey / SSURGO

### Source

- **Provider:** USDA Natural Resources Conservation Service
- **Web Soil Survey:** <https://www.nrcs.usda.gov/resources/data-and-reports/web-soil-survey>
- **SSURGO overview:** <https://www.nrcs.usda.gov/resources/data-and-reports/soil-survey-geographic-database-ssurgo>

### Description

Official US soil maps, properties, interpretations, and downloadable spatial/tabular survey data.

### Relevant Variables / Fields

Soil map unit, texture-related properties, pH-related properties, drainage, available water/root-zone context, spatial geometry, and survey metadata. Exact fields were not selected. `Needs verification`.

### Geographic Coverage

United States; polygon/map-unit based. Coverage detail varies by survey area.

### Temporal Coverage

Survey/database releases rather than live time series. Release/version handling was not discussed.

### Format

Web application plus downloadable spatial and tabular data; a runtime API/data-service contract was not selected.

### Dataset Size

Large/complex for nationwide automation; one manual demo lookup is small.

### Licensing / Usage Restrictions

Not established in the planning record. `Needs verification`.

### Why We Considered It

To prepare and verify the demonstration farm's soil profile and support deeper post-hackathon automation.

### Strengths

- Official US source.
- More credible than inventing a demo soil profile.

### Limitations

- Complex data model and spatial joins.
- Nationwide integration could consume the one-week build.
- Survey resolution/interpretation must not be overstated as a current field test.

### Decision

`Likely Selected` for manual demo verification; `Rejected` for automated MVP integration.

### Planned Usage

Manually look up one selected farm after the region is locked, record the relevant values and source metadata, and keep the application form-based. Automated SSURGO ingestion is post-hackathon.

## USDA NASS Data

### Source

- **Provider:** USDA National Agricultural Statistics Service
- **Developer resources:** <https://www.nass.usda.gov/developer/>

### Description

Quick Stats and geospatial/crop-condition resources describing historical agricultural production and prevalence.

### Relevant Variables / Fields

County/region, crop/commodity, year/period, area/production/yield measures, and source metadata. No exact query or fields were finalized.

### Geographic Coverage

United States, with national/state/county and other product-specific levels.

### Temporal Coverage

Historical and periodically updated agricultural statistics. Exact years/frequency `Needs verification`.

### Format

API/download/geospatial products depending on source. Proposed MVP form: one pre-cached county summary.

### Dataset Size

Small if limited to one county summary; potentially large otherwise.

### Licensing / Usage Restrictions

Not established in the planning record. API access requirements and attribution `Needs verification`.

### Why We Considered It

Optional sanity check that candidate crops are historically present in the chosen region.

### Strengths

- Official US agricultural statistics.
- Useful external reasonableness check.

### Limitations

- Historical prevalence is not future suitability.
- It could bias toward incumbent crops and suppress viable alternatives.
- Not necessary for the core heat-aware decision.

### Decision

`Alternative` / optional only if core work is complete.

### Planned Usage

Pre-cache one county-level summary and use at most as the optional 10% local-evidence component or a non-scoring validation note. Cut first if behind schedule.

## FAO Ecocrop

### Source

- **Provider:** Food and Agriculture Organization of the United Nations
- **URL:** <https://ecocrop.apps.fao.org/ecocrop/srv/en/home>

### Description

A crop-requirements reference/matching system using climate and soil conditions such as temperature, rainfall, light, texture, depth, pH, salinity, and fertility.

### Relevant Variables / Fields

Temperature, rainfall, light, soil texture/depth/pH/salinity/fertility, and plant/crop identity. Exact downloadable schema was not investigated.

### Geographic Coverage

General/global reference; applicability still depends on region and variety.

### Temporal Coverage

Reference requirements, not a live time series.

### Format

Web application/reference. A downloadable/API format was not selected.

### Dataset Size

Unknown.

### Licensing / Usage Restrictions

The research record explicitly warns to confirm licensing before extracting or redistributing records. `Needs verification`.

### Why We Considered It

Useful for designing the crop catalog schema and checking whether manually curated ranges are plausible.

### Strengths

- Direct crop/environment requirements reference.
- Broad set of suitability dimensions.

### Limitations

- Not a live farm-specific heat agent.
- Licensing and attribution for extraction are unresolved.
- Requirements may be too general for variety-specific hard filters.

### Decision

`Alternative` as a secondary plausibility check, not a runtime dataset.

### Planned Usage

Consult manually during catalog curation only after source/licensing review; do not copy unattributed records.

## FAO Global Agro-Ecological Zones (GAEZ) v5

### Source

- **Provider:** FAO
- **URL:** <https://www.fao.org/gaez/en/>

### Description

Global agro-ecological suitability/attainable-production platform using crop requirements, climate, soil, terrain, water supply, and management assumptions.

### Relevant Variables / Fields

Suitability, attainable production, crop requirements, climate, soil, terrain, water supply, and management scenario. Exact layers were not selected.

### Geographic Coverage

Global, gridded/regional planning scale.

### Temporal Coverage

Present/future or scenario-dependent products; exact releases and periods `Needs verification`.

### Format

Large geospatial platform/downloads. No MVP ingestion method was chosen.

### Dataset Size

Large; unsuitable for full one-week integration.

### Licensing / Usage Restrictions

Not established in the planning record. `Needs verification`.

### Why We Considered It

Scientific benchmark for multi-factor suitability and scenario concepts.

### Strengths

- Authoritative and comprehensive.
- Useful conceptual validation for crop profiles and scenarios.

### Limitations

- Analyst/institutional scale, not a minimal farmer conversation.
- Integration complexity and scale exceed the MVP.

### Decision

`Alternative` benchmark; rejected as an MVP runtime dataset.

## Global Crop Suitability Datasets for 17 Crops

### Source

- **Provider/publication:** Scientific Data (2026)
- **Article:** <https://www.nature.com/articles/s41597-026-06688-4>
- **DOI:** <https://doi.org/10.1038/s41597-026-06688-4>

### Description

Continuous suitability probabilities for 17 crops based on soil, climate, and topographic predictors under present and future climate scenarios.

### Relevant Variables / Fields

Crop, continuous suitability probability, soil/climate/topographic predictors, present/future scenario dimensions, and grid coordinates. Exact repository/schema/variables were not extracted during planning.

### Geographic Coverage

Global/regional gridded data; not direct field-level proof.

### Temporal Coverage

Present and multiple future climate scenarios. Exact periods `Needs verification`.

### Format

Large research dataset associated with the paper. Exact download formats and size were not captured. `Needs verification`.

### Dataset Size

Described as large; full integration is outside the one-week MVP.

### Licensing / Usage Restrictions

Not captured. `Needs verification` from the article/data repository.

### Why We Considered It

Supports continuous 0-100 suitability and scenario comparison, and may provide a post-hackathon validation benchmark.

### Strengths

- Recent peer-reviewed dataset.
- Continuous rather than categorical suitability.
- Future-scenario framing aligns with the product.

### Limitations

- Large and regional/global in scale.
- Not a substitute for local crop-stage thresholds or field validation.

### Decision

`Alternative` / post-hackathon validation; rejected for MVP integration.

## USDA Plant Hardiness Zone Map

### Source

- **Provider:** USDA Agricultural Research Service
- **URL:** <https://planthardiness.ars.usda.gov/>

### Description

Plant hardiness zones based on extreme minimum temperature, primarily useful for perennial survival context.

### Relevant Variables / Fields

Hardiness zone and extreme-minimum-temperature bands. Exact data layers were not selected.

### Geographic Coverage

United States.

### Temporal Coverage

2023 map was cited in the earlier implementation plan; update cadence not discussed.

### Format / Size / License

Not captured in the planning record. `Needs verification`.

### Why We Considered It

Possible context for perennial crops and hard frost constraints.

### Strengths

- Authoritative US reference.

### Limitations

- Narrow focus on extreme minimum temperature.
- Less relevant if the chosen six crops are annuals.

### Decision

`Undecided` reference only; not in the selected minimum data stack.

## NOAA Seasonal Category (Manual)

### Source

An earlier plan mentioned a manually entered NOAA seasonal category for the demo region. No product, URL, variable, or acquisition method was specified.

### Description / Coverage / Format

`Unknown / Needs verification`

### Why We Considered It

Optional scenario context without building a national GIS integration.

### Decision

`Rejected` from the latest core plan / `Status: Undecided` as an optional later enhancement.

### Reason for Decision

The revised agentic plan uses explicit evidence-based baseline and clearly labeled illustrative/farmer counterfactual scenarios. An unspecified manual category would add ambiguity.

## Generic Kaggle Crop-Recommendation Dataset

### Source

The research review discussed a Kaggle dataset associated with an Indian crop-recommendation study:

- Paper: <https://doi.org/10.1016/j.heliyon.2024.e25112>
- Exact Kaggle dataset URL/name: not preserved. `Needs verification`.

### Description

Conventional crop-recommendation variables including nitrogen, phosphorus, potassium, pH, temperature, rainfall, and humidity, used to compare machine-learning models.

### Geographic Coverage

Associated with Indian crops/data; not shown to validate US farms or unseen varieties.

### Temporal Coverage / Format / Size / License

Not captured. `Unknown / Needs verification`.

### Why We Considered It

As a conventional ML baseline and example of common feature families.

### Strengths

- Convenient for model experiments.
- Demonstrates common recommendation variables.

### Limitations

- Dataset accuracy does not establish US agronomic validity.
- Likely region/crop distribution mismatch.
- Encourages an opaque classifier without local threshold provenance.

### Decision

`Rejected`

### Reason for Decision

The MVP requires transparent, source-grounded US screening and scenario recomputation, not a high test score on a generic out-of-region dataset.

## Dataset Comparison

### Core Climate and Heat Sources

| Source | Coverage/resolution | Time role | Access | MVP suitability | Decision |
|---|---|---|---|---|---|
| FortyGuard | US; 60/80/100 m heatmap tiles; rural fit unverified | Recent/historical plus supported 12-hour heatmap forecast | Authenticated async API, plan/credit limits | Essential local heat evidence | **Selected** |
| NASA POWER | Global; ~0.5 x 0.625 deg meteorology, 1 x 1 deg solar | Long-term climatology/history | Free synchronous API | Strong regional baseline, not field truth | **Selected** |
| NOAA manual category | Product/resolution unspecified | Seasonal category | Manual/unspecified | Ambiguous and not in latest core | Rejected/Undecided |
| Global 17-crop suitability dataset | Global/regional grid | Present/future scenarios | Large research dataset | Useful later benchmark, too large for MVP | Alternative |

### Soil and Local Evidence

| Source | Coverage | Variables | Integration effort | Main limitation | Decision |
|---|---|---|---|---|---|
| Farmer/demo profile | One farm / user input | Soil, pH, drainage, irrigation, planting time | Low | Incomplete/self-reported | **Selected** |
| USDA Web Soil Survey / SSURGO | US soil survey map units | Soil properties and interpretations | High for automation; low for one manual lookup | Spatial/data-model complexity | **Likely Selected** manually; automation deferred |
| USDA NASS | US county/state/national statistics | Historical crop prevalence/production | Moderate, small if pre-cached | Prevalence is not suitability | Optional Alternative |

### Crop Requirement / Suitability Sources

| Source | Intended role | Breadth | Evidence concern | Decision |
|---|---|---|---|---|
| Manually verified six-crop catalog | Runtime source of truth | Narrow | Curation and variety specificity | **Selected** |
| FAO Ecocrop | Schema/plausibility reference | Broad | Licensing and generalization | Alternative reference |
| FAO GAEZ | Scientific benchmark | Broad/global | Scale and integration complexity | Alternative benchmark |
| Global 17-crop dataset | Post-hackathon validation | 17 crops | Not field-level proof | Alternative |
| Generic Kaggle crop dataset | ML baseline | Dataset-specific | US validity and provenance | Rejected |

## Data Integration Plan

### Intended Join and Alignment

1. Use the normalized farm coordinate or polygon as the primary spatial key.
2. Request FortyGuard for the polygon/time window and NASA POWER for a representative/rounded point.
3. Preserve both spatial resolutions; never imply the NASA grid is farm-scale.
4. Align timestamps/time zones and the selected planting/season window before deriving features.
5. Load the region-appropriate crop catalog version and compare each crop's thermal/calendar requirements with normalized evidence.
6. Combine farmer soil/drainage/irrigation fields with catalog requirements; preserve the farmer/source label.
7. Optionally attach a manually verified USDA soil record or NASS county note; do not silently overwrite farmer input.

### Preprocessing

- Validate coordinate order and US bounds.
- Validate date formats, time zones, and provider window constraints.
- Normalize all temperature calculations to Celsius internally.
- Normalize NASA units and provider missing-value sentinels. Exact mappings `Needs verification`.
- Convert FortyGuard tile output into polygon-level summaries using a documented aggregation policy. Area-weighted intersection is a researched quickstart approach, but the CropMatch farm aggregation method is `Status: Undecided`.
- For each crop, calculate preferred-range share, hours and degree-hours above a sourced threshold, recent anomaly, sensitive-stage overlap where supported, and short-horizon event flags.
- Record provider, original field, normalized value/unit, coordinate/area, time range, spatial resolution, fetch time, cache status, and raw-response reference.

### Missing Data

- Do not impute a perfect match.
- Continue with available components only under a documented scoring policy.
- Reduce confidence according to the importance of missing evidence.
- Display which value is missing and the next verification action.
- The exact score renormalization policy is `Status: Undecided`.

### Provenance and Versioning

- Save the crop catalog version and calculation version with each recommendation.
- Save provider timestamps, request parameters, resolution, and live/cached status.
- Preserve sanitized raw-response references for debugging.
- Do not store credentials or temporary signed download URLs.
- Cached demo data must show its original timestamp and a clear badge.

## Open Dataset Questions

- Which US region, farm, and six crops will be selected?
- Which crop sources are authoritative enough for every filter and high-risk threshold?
- What crop variety scope and sensitive-stage model will be used?
- Which NASA POWER variables and climatology period will be requested?
- Can the FortyGuard hackathon key retrieve plausible rural results, range-of-days analyses, and 12-hour forecasts?
- What is the authoritative FortyGuard historical start date for this key?
- How will tile values be aggregated to the farm polygon?
- Which time zone governs user planting/time inputs and provider hours?
- Can cached FortyGuard responses be redistributed in a public hackathon repository?
- Which USDA soil fields should be manually recorded for the demo?
- Will optional NASS evidence improve the demo enough to justify integration?
- What exact missing-data and score-renormalization policy will be implemented?
- What licenses/attribution are required for every crop-catalog source and benchmark dataset?
