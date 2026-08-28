# CropMatch AI - Project Context

## Document Status and Evidence Basis

This is the primary handoff for the planned CropMatch AI hackathon project. It consolidates the latest revised agentic implementation plan (23 August 2026), the earlier implementation plan (22 August 2026), the research landscape (22 August 2026), and the local FortyGuard quickstart reference. Where the plans differ, the revised agentic plan is treated as the latest decision.

Nothing in this document should be read as implemented unless a future update explicitly says so.

## Project Overview

### Hackathon

- **Name:** FortyGuard Global AI Hackathon 2026
- **Organizer:** FortyGuard, as identified in the planning materials. `Needs verification` against the official event page.
- **Primary track:** Agentic - API + Agentic
- **Build window recorded in the latest plan:** 23-30 August 2026
- **Submission deadline recorded in the plans:** 30 August 2026 at 11:59 PM GST. `Needs verification` against the official rules.
- **Hackathon objective understood from the planning record:** Build a useful AI application in which the FortyGuard Temperature API is technically central, then demonstrate impact, technical execution, innovation, and clear communication. The exact organizer wording was not preserved. `Needs verification`.

### Problem Statement

Farmers choosing what to plant must reconcile recent heat exposure, long-term climate, soil conditions, water or irrigation access, crop calendars, and crop-specific requirements. Those signals live in different sources and are difficult to translate into a defensible shortlist. A poor pre-planting decision can waste seed, land, water, labor, input costs, and an entire growing season.

### Chosen Problem

CropMatch AI will support the **pre-planting crop comparison decision** for one farm in one US agricultural region. It will help a farmer compare a small verified set of crops under current evidence and changed conditions, rather than attempting exact yield prediction or general farm management.

### Why It Matters

- Heat risk is nonlinear, crop-specific, and sometimes growth-stage-dependent; averages can hide damaging short events.
- Farmers need a decision-oriented synthesis rather than another collection of climate layers.
- Trust depends on showing evidence, uncertainty, and factor contributions instead of presenting an opaque prediction.
- The decision happens before land, seed, water, and labor are committed.

### Target Users and Beneficiaries

1. **Primary:** Small or medium US farmer planning a new crop or changing the next season's crop mix.
2. **Secondary:** Agronomist or extension advisor needing a consistent first-pass screen.
3. **Secondary:** Buyer evaluating agricultural land with limited farm history.

### Primary Use Cases

- Rank three plausible crop options for a farm and planting period.
- Explain temperature, climate, soil, water, and timing contributions.
- Compare a baseline with a hotter/drier, no-irrigation, or delayed-planting counterfactual.
- Reuse the verified farm profile in follow-up questions.
- Surface confidence, evidence provenance, the main limitation, and the next agronomic check.
- Provide an immediate up-to-12-hour heat-risk flag where FortyGuard supports it; this is an operational alert, not a seasonal forecast.

## Proposed Solution

CropMatch AI is planned as a bounded, evidence-grounded agricultural decision agent. A single planning agent will understand the farmer's objective, identify missing information, select typed tools, gather live or cached evidence, request deterministic calculations, validate the result, and explain the approved structured output.

### Intended User Workflow

1. The farmer enters or chooses a US location and planting time. Soil, drainage, and irrigation can also be supplied; unknown values are allowed.
2. The system normalizes the farm profile, identifies missing or conflicting fields, and retains the verified profile for follow-up turns.
3. The agent requests recent/local heat evidence from FortyGuard and a long-term regional baseline from NASA POWER.
4. The system loads a versioned catalog of six manually verified crop records.
5. A deterministic decision engine applies eligibility filters, computes component scores and crop-specific heat metrics, adds risk flags, and calculates confidence inputs.
6. A validator checks numerical consistency, catalog grounding, evidence coverage, and whether the result is safe to render.
7. The interface shows the top three crops, reasons, risks, confidence, sources, and a recommended next check.
8. If the farmer changes irrigation, planting time, or a supported heat assumption, the agent reuses state, calls only necessary tools, reruns the scorer and validator, and shows the before/after ranking and causal factor changes.

### Inputs

- Required for the planned MVP: location and planting time/month.
- Optional but important: soil texture, pH, drainage, irrigation availability, and a natural-language goal.
- Scenario changes: no irrigation, delayed planting, documented demonstration heat/water deltas, or other explicitly supported variables.

### Processing

- Normalize and version the farm profile.
- Retrieve live or disclosed cached provider evidence.
- Derive crop-specific heat metrics such as preferred-range share, threshold-exceedance hours, degree-hours above a sourced threshold, recent anomaly, sensitive-stage overlap where supported, and a 12-hour event flag.
- Apply hard eligibility filters separately from weighted suitability.
- Score eligible crops on a documented 0-100 scale.
- Calculate risk and confidence separately from suitability.
- Validate all scores, crop IDs, thresholds, provenance, and explanation inputs.

The latest proposed default weights are:

| Component | Weight |
|---|---:|
| FortyGuard recent/local heat fit | 40% |
| NASA POWER long-term climate fit | 20% |
| Soil compatibility | 20% |
| Water and irrigation fit | 10% |
| Optional local evidence | 10% |

These are documented MVP defaults, not agronomically validated universal weights. `Needs verification` through testing and expert review.

### Outputs

- Top-three crop shortlist from the supported catalog.
- Suitability score and component scores.
- Separate heat-risk flags and scenario sensitivity.
- Confidence level and the evidence gaps that reduced it.
- Plain-language positive and negative reasons.
- Before/after scenario comparison.
- Source provider, timestamp, spatial resolution, cache/live status, catalog source, and assumptions.
- A next verification action such as a soil test or local extension review.

### Definitely Decided MVP Features

- One US region, one polished demonstration farm, and one reliable end-to-end scenario conversation.
- A single bounded planning agent with typed tool use, retained structured state, and validation.
- A small versioned crop catalog targeting six verified candidate crops.
- FortyGuard as the primary recent/local heat signal and source of an up-to-12-hour operational risk where supported.
- NASA POWER as the long-term regional climate baseline.
- Deterministic filters, scoring, scenarios, and risk calculations; the language model must not invent scores or thresholds.
- Baseline plus at least four tested scenarios: baseline, hot-dry, no irrigation, and delayed planting.
- Top-three recommendations with reasons, risks, confidence, evidence provenance, and next checks.
- Disclosed cached fallback for provider failure.
- Public end-to-end demonstration as the intended submission outcome.

### Optional Features, Only After the Core Works

- A static USDA NASS county summary as a regional prevalence sanity check.
- A manually verified USDA soil profile for the demo farm and later automated SSURGO integration.
- Polygon drawing; a fixed map pin is an accepted fallback.
- Export/shareable report after the main flow is stable.
- Saved accounts or assessments, if time remains.

### Explored or Deferred Ideas

- Cool-wet scenario from the earlier plan: no longer listed among the latest required four scenarios. `Status: Undecided`.
- Leaflet with OpenStreetMap: proposed in the earlier plan, not reaffirmed in the revised plan. `Status: Undecided`.
- Field-level ML or an exact yield model: deferred until post-hackathon data and agronomic validation exist.
- Automated nationwide soil integration, satellite NDVI, IoT sensors, disease diagnosis, irrigation scheduling, commodity prices, and multi-agent design: excluded from the MVP.

### Intended User Experience

The product should feel like a guided farmer decision assistant, not a raw climate dashboard. It should have a short input flow, visible user-safe tool activity, no hidden indefinite loading, progressive evidence details, clear units and timestamps, and accessible text labels in addition to color. It should say **preliminary suitability** and **consider**, never imply a guarantee or instruction to plant.

## Hackathon Requirements and Constraints

The following items are captured from the planning artifacts. Items presented as organizer requirements must still be checked against the official rules.

### Recorded Requirements

- Use the FortyGuard Temperature API centrally; the demo should show at least one crop's rank or risk changing because a FortyGuard-derived heat metric crosses a sourced crop threshold.
- Target the Agentic - API + Agentic track.
- Intended submission artifacts: public repository, live demo URL, architecture/tool/scoring documentation, three-minute video, AI-use disclosure, limitations, and the organizer-specified FortyGuard collaborator.
- Recorded judging weights: Impact and Relevance 40%, Technical Execution 35%, Innovation 15%, Communication 10%. `Needs verification`.
- Secrets must stay server-side and must not appear in the repository, browser, logs, screenshots, or demo data.

### Time and Team Constraints

- One-week build window.
- Two-person team context is implied by the handoff request, but no finalized work split is recorded.
- Scope lock: one agent, six verified crops, one demo farm, one US region, one reliable scenario conversation.

### API and Data Constraints

- FortyGuard is currently documented as US-only.
- Current official documentation describes a 2019-to-present catalog and heatmap forecasting up to 12 hours; the local quickstart says 2021-to-today and future dates unsupported. `Needs verification` with the hackathon key and live endpoint.
- FortyGuard heatmap granularity is 60, 80, or 100 metres; rural coverage and plausibility must be tested on Day 1.
- NASA POWER is a coarse regional baseline, approximately 0.5 x 0.625 degrees for meteorology and 1 x 1 degree for solar products, not field-level evidence.
- Crop requirements vary by variety, region, and management; every threshold used for a hard filter or high-risk warning needs a source.
- External providers are asynchronous or can be slow; bounded polling, timeouts, caching, and explicit fallback labels are required.

## Technology Plan

| Technology or approach | Status | Intended role and reasoning |
|---|---|---|
| TypeScript/JavaScript web stack | Proposed | Supports a fast web UI and a single deployable application if Next.js is chosen. |
| Next.js or React | Undecided | Proposed for farm setup, conversation, tool activity, maps, and result comparison. The revised plan did not choose between them. |
| Next.js server routes | Alternative | Keeps secrets and provider adapters with a Next.js deployment. |
| Python + FastAPI | Alternative | Fits data processing and the existing FortyGuard Python client but may require a separate backend deployment. |
| Python/Jupyter | Proposed for research/prototyping | The local FortyGuard quickstart and notebooks are useful for testing endpoints and producing cached evidence; they are not the application implementation. |
| One structured tool-calling agent loop | Selected architecture | Makes planning, tool selection, state reuse, scenario adaptation, and grounding visible and testable. |
| Pure deterministic scoring functions | Selected architecture | Reproducible and easier to validate than a rushed black-box model. |
| LLM for orchestration and explanation | Selected architecture, provider undecided | The model may plan and explain validated values but may not calculate or edit final scores in free text. |
| Typed schemas/contracts | Selected approach | Bounds tool inputs/outputs and protects the final rendering from invented values. |
| JSON crop catalog | Selected approach | A small, versioned, auditable six-record catalog is feasible within one week. |
| SQLite or simple Postgres | Undecided | Proposed for state, cache, evidence, and traces; local JSON may be sufficient for the demo. |
| Leaflet + OpenStreetMap | Alternative | Earlier low-overhead mapping proposal; not reaffirmed in the latest plan. |
| Vercel or equivalent public host | Proposed | Fast public URL and server-side environment variables; exact deployment is not finalized. |
| Conventional ML classifier | Rejected for MVP | Generic training data and accuracy would not establish US agronomic validity. |
| Multi-agent system | Rejected for MVP | Adds delivery and evaluation risk without improving the central one-week decision loop. |

## Major Project Components

### Farm Profile Resolver

Normalizes location, planting time, soil, drainage, irrigation, and provenance; detects missing/conflicting fields; versions the profile; and supplies structured state for follow-ups.

### Planning Agent

Interprets the request, selects only necessary tools, constructs supported scenarios, reuses verified state, requests validation, and explains only approved structured output.

### FortyGuard Adapter

Submits and polls the relevant Temperature API jobs, normalizes recent/local heat evidence, adds timestamps and resolution metadata, caches responses, and exposes live/cached status. See [API_NOTES.md](./API_NOTES.md).

### NASA POWER Adapter

Retrieves and caches long-term regional temperature, precipitation, humidity-related, and solar baselines by rounded coordinate and variable set.

### Versioned Crop Catalog

Stores six manually curated crop records with thermal, stage, soil, water, calendar, variety/region, source, review, and confidence fields. The actual six crops are not yet selected.

### Scenario and Recommendation Engine

Applies eligibility filters, computes factor scores and crop-specific heat metrics, creates scenario deltas, ranks crops, and returns immutable structured calculations.

### Validator

Checks schema validity, numerical reconciliation, crop/catalog grounding, evidence freshness and coverage, confidence inputs, and whether the result may be rendered.

### Storage and Cache

Stores or references farm profile versions, provider responses, normalized evidence, catalog version, scenario assumptions, recommendation bundles, validation reports, and user-safe agent traces. Exact technology is undecided.

### Web Experience

Collects farm input, presents user-safe agent activity, displays top-three comparison cards and scenario deltas, and provides an expandable evidence drawer.

## Data Flow Summary

```text
Farmer location, planting time, soil, drainage, irrigation, and goal
  -> normalized/versioned FarmProfile
  -> planning agent selects bounded tools
  -> FortyGuard live/cached heat evidence + NASA POWER baseline
  -> versioned six-crop catalog
  -> deterministic filters, heat metrics, factor scores, risks, and scenarios
  -> validation and confidence checks
  -> top-three crops, reasons, risks, uncertainty, provenance, and next action
  -> follow-up changes reuse structured state and rerun only necessary tools
```

## Important Decisions

| Decision | Why | Alternatives considered and disposition |
|---|---|---|
| Position CropMatch as a heat-aware pre-planting decision agent, not a generic crop recommender | A direct competitor already performs location-based crop suitability; the narrower agentic changed-condition workflow is more defensible. | Generic recommender rejected as insufficiently differentiated. |
| Use one bounded agent | Shows planning, tool use, state, and adaptation while remaining testable in one week. | Multi-agent design rejected for MVP. |
| Keep scoring deterministic and transparent | Identical inputs must produce identical results; source and factor contributions must be auditable. | Rushed black-box classifier rejected. |
| Make FortyGuard materially change a result | Proves the required API is central rather than decorative. | Weather-dashboard treatment rejected. |
| Use NASA POWER only as a long-term regional baseline | Adds climate context without claiming farm resolution. | Treating coarse data as field truth rejected. |
| Limit the catalog to six verified crops | Credibility and source quality matter more than breadth; catalog curation is a delivery risk. | Automatically scraped or nationwide catalog rejected. |
| Separate suitability, risk, and confidence | A crop can fit overall while carrying a sensitive-stage heat risk; missing evidence should lower confidence rather than masquerade as a match. | Single opaque score rejected. |
| Use scenarios for seasonal change | FortyGuard's short forecast horizon does not justify an exact seasonal prediction. | Exact seasonal forecast claims rejected. |
| Preserve structured state, not free-text model output | Prevents hallucinated or altered facts from becoming trusted state. | Treating previous prose as authoritative state rejected. |
| Ship a disclosed cached fallback | Protects the public demo from provider latency/failure without pretending cached data is live. | Silent fallback rejected. |

## Rejected / Deferred Ideas

- Exact field yield, profit, commodity-price, precise irrigation-volume, pest, or disease prediction.
- Universal/nationwide calibration and a large automatically scraped crop database.
- Generic Kaggle crop classifier or unvalidated deep-learning model.
- Nationwide automated SSURGO workflow during the MVP.
- Satellite NDVI/vegetation pipeline, sensors, edge hardware, and IoT integration.
- Multi-agent or autonomous internet-research workflow.
- User accounts, exports, polygon drawing, and NASS evidence before the core decision loop is stable.
- Copying crop databases without confirmed licensing and attribution.
- Presenting a 12-hour operational forecast as a seasonal crop forecast.

## Assumptions

- A rural or peri-urban US demo location will return plausible FortyGuard data. `Needs verification`.
- One agricultural region and one demonstration farm will be selected early. `Status: Undecided`.
- Six plausible alternative crops can be sourced and reviewed within the sprint. `Needs verification`; the crop list is undecided.
- At least one FortyGuard heat metric can cross a crop-specific threshold and visibly change a ranking or risk. `Needs verification`.
- The hackathon API key has sufficient plan access and credits for the chosen endpoints. `Needs verification`.
- NASA POWER variables and time periods can be normalized into the intended regional baseline. `Needs verification`.
- Farmer-provided soil/drainage/irrigation data may be incomplete; the system will label their origin and reduce confidence.
- Cached demonstration responses may be included without credentials and with permitted redistribution. `Needs verification`.

## Known Risks and Open Questions

- Which US region, farm coordinate/polygon, and six crops will be used?
- Does the provided FortyGuard key support the required endpoints, area, credits, and 12-hour forecast?
- Which FortyGuard date/filter constraints are authoritative where the current docs and local quickstart disagree?
- Are rural outputs available and agronomically plausible for the selected location?
- How will crop-sensitive growth stages be estimated from planting time: calendar windows, growing degree days, or both?
- What is the exact policy for missing weighted components and score renormalization?
- What threshold evidence is strong enough to trigger a hard filter versus only a warning?
- Which LLM/provider and structured-output mechanism will be used?
- Will the application use Next.js server routes or a FastAPI service?
- Is JSON sufficient, or is SQLite/Postgres needed for the demo?
- What map component, if any, survives the cut order?
- Can an agronomist or mentor review the six crop records before the pitch?
- Are the recorded submission requirements, collaborator instruction, judging weights, and deadline current?

## Team Responsibility Context

`Status: Undecided`

The planning materials define work areas (API/region de-risking, evidence/catalog, scoring/scenarios, agent/state, product flow, evaluation/fallback, and submission) but do not assign them to either team member.

## Relevant Resources

### Project and API

- [FortyGuard API documentation](https://docs-api.fortyguard.com/docs) - official Temperature API documentation.
- [FortyGuard authentication](https://docs-api.fortyguard.com/docs/authentication) - `api-key` header requirements.
- [FortyGuard limitations](https://docs-api.fortyguard.com/docs/limitations) - current coverage, plans, credits, and input constraints.
- [NASA POWER API data requests](https://power.larc.nasa.gov/docs/tutorials/service-data-request/api/) - official data-access tutorial.
- [NASA POWER climatology API](https://power.larc.nasa.gov/docs/services/api/temporal/climatology/) - proposed long-term baseline endpoint.
- [USDA Web Soil Survey](https://www.nrcs.usda.gov/resources/data-and-reports/web-soil-survey) - demo profile verification and post-MVP soil integration.
- [USDA NASS developer resources](https://www.nass.usda.gov/developer/) - optional county/region prevalence evidence.
- [USDA Plant Hardiness Zone Map](https://planthardiness.ars.usda.gov/) - perennial survival context only.

### Research and Benchmarks

- [Integrated AI Framework for Crop Recommendation](https://doi.org/10.3390/horticulturae12040416) - multi-factor suitability precedent.
- [Global crop suitability datasets for 17 crops](https://doi.org/10.1038/s41597-026-06688-4) - continuous suitability and future-scenario benchmark.
- [Climate change impacts across temperature thresholds](https://doi.org/10.1038/s41598-025-07405-8) - nonlinear and climate-zone-specific heat effects.
- [Local explanations for crop recommendations](https://doi.org/10.1016/j.procs.2025.04.450) - factor-level explanation reference.
- [Acceptance of intelligent decision-making in agriculture](https://doi.org/10.1016/j.aei.2024.102387) - trust and ease-of-use evidence.
- [Pre- and post-flowering wheat heatwave impacts](https://doi.org/10.1016/j.fcr.2024.109489) - exposure duration and sensitive-stage evidence.
- [US Corn Belt heat-stress projections](https://doi.org/10.1016/j.agsy.2023.103746) - US-focused problem evidence.

### Comparable Solutions

- [What Grows Here?](https://apps.apple.com/us/app/what-grows-here/id6503260984) - closest direct competitor.
- [FAO Ecocrop](https://ecocrop.apps.fao.org/ecocrop/srv/en/home) - crop-requirements reference and plausibility check.
- [FAO GAEZ](https://www.fao.org/gaez/en/) - multi-factor suitability benchmark.
- [USDA Future Crop Suitability Tool](https://climatetoolbox.org/tool/Future-Crop-Suitability) - future-scenario comparison benchmark.
- [CalAgroClimate](https://www.climatehubs.usda.gov/hubs/california/tools/calagroclimate) - crop-specific heat and phenology decision-support benchmark.
- [Iowa State FACTS](https://facts.extension.iastate.edu/) - decision-oriented soil/weather analytics benchmark.
- [EOSDA Crop Monitoring](https://eos.com/products/crop-monitoring/weather-data-for-agriculture/) - historical versus forecast and heat-alert UX reference.
- [Plantix](https://plantix.net/en/) - farmer-facing task-oriented UX reference.

See [API_NOTES.md](./API_NOTES.md) and [DATASETS.md](./DATASETS.md) for detailed records.

## Current Project State

The project is currently in the planning/research stage. No implementation repository or production code has been created yet.

Planning/research completed so far includes:

- Problem framing, user personas, competitive positioning, and the one-week scope boundary.
- A latest single-agent architecture, typed tool set, structured data contracts, deterministic scoring policy, validation policy, and scenario behavior.
- Research into FortyGuard, NASA POWER, USDA soil/agricultural sources, crop-suitability literature, and comparable products.
- A risk register, fallback strategy, test/evaluation outline, pitch structure, and post-hackathon roadmap.
- A local copy of the FortyGuard quickstart and cached example responses for reference. These are research/reference materials, not CropMatch implementation.

No farm region, demo location, final crop list, application stack, storage technology, model provider, implementation repository, deployed application, tests, or submission has been completed.
