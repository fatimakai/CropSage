# CropSage Catalog Evidence Usage Policy

## Status

- Applies to crop catalog version `1.1.0`.
- Clarifies the existing contract without adding, removing, or renaming fields.
- Does not replace the versioned deterministic calculation policy.

## Required Presence and Required Values

Every property listed in the crop schema is structurally required. This keeps the
contract stable for validators, adapters, and the deterministic engine.

A structurally required property is not necessarily required to contain a numeric
value. When the schema permits `null`, the property contains optional numeric
evidence. A null value means that no sufficiently transferable number was
established from the selected sources.

## Core Comparable Evidence

The following evidence is populated consistently across the catalog and may support
the common MVP suitability calculation:

| Evidence | Catalog field |
|---|---|
| Regional support | `supported_texas_regions`, `regional_suitability` |
| Planting timing | `planting_windows_by_region` |
| Season length | `days_to_maturity` |
| Temperature fit | `optimal_temperature_range` |
| Soil texture | `preferred_soil_textures` |
| Soil pH | `ph_tolerable_range` |
| Soil depth and storage context | `effective_root_zone_depth_cm` |
| Drainage | `drainage_requirement` |
| Categorical water demand | `water_demand.class` |
| Drought response | `drought_tolerance` |
| Irrigation dependency | `irrigation_requirement` |

The calculation policy remains responsible for defining the exact comparison,
weight, eligibility rule, and treatment of unavailable runtime location evidence.

## Nullable Supplementary Evidence

| Evidence | Nullable property | MVP treatment |
|---|---|---|
| Numeric heat threshold | `heat_stress_threshold.value_c`, `operator` | Supplementary heat-risk or explanatory evidence |
| Heat exposure duration | `heat_exposure_duration.hours`, `consecutive_days` | Informational observation only unless a transferable duration is later sourced |
| Seasonal crop-water range | `water_demand.seasonal_range_mm` | Informational water context; categorical demand remains the comparable field |
| Representative root depth | `effective_root_zone_depth_cm.reference` | Optional convenience value; use the sourced min-max range when null |

Missing supplementary evidence must not invalidate an otherwise valid crop record.
It must also not make that crop rank higher than a crop with stronger evidence.

## Null Semantics

Runtime code and documentation must follow these rules:

1. Null means `not numerically established`; it never means zero.
2. Null is not favorable evidence, compatibility, safety, or heat tolerance.
3. Null must not trigger a hard filter, numeric penalty, or numeric bonus.
4. Runtime provider observations must not be copied into catalog requirement fields.
5. The upper boundary of an optimal range must not be substituted for an injury threshold.
6. A provider's observed exceedance or persistence must not be converted into a biological duration limit.
7. Missing supplementary evidence must be disclosed in the recommendation evidence notes.

## Heat Evidence

`optimal_temperature_range` is the common temperature-fit requirement across all
22 crops. FortyGuard, NASA POWER, and Open-Meteo evidence may be normalized and
compared with that range under the calculation policy.

A numeric `heat_stress_threshold` may support a sourced heat-risk flag. For catalog
version `1.1.0`, threshold coverage is incomplete, so the calculation policy may
conservatively keep threshold exceedance outside the common suitability score.

`heat_exposure_duration` remains informational when its numeric values are null.
Provider persistence hours may be displayed as an observation, but they are not a
crop requirement and do not establish injury by themselves.

`heat_sensitive_stages` supports explanation. It must not trigger stage-specific
MVP scoring unless a separately validated crop-stage resolver is introduced.

## Water Evidence

`water_demand.class`, `drought_tolerance`, and `irrigation_requirement` are the
comparable MVP crop requirements. A nullable `seasonal_range_mm` is supplementary
context and must not be interpreted as zero water demand.

SSURGO available-water capacity, modeled current soil moisture, rainfall, ET0, and
farmer irrigation evidence are runtime location evidence. They do not belong in the
crop catalog and must not be treated as interchangeable quantities.

## Evidence Status and Review

- `direct`: directly applicable evidence, still subject to field-level usage rules.
- `regional_transfer`: relevant evidence transferred from another suitable region or context.
- `generalized`: broad guidance suitable for context or conservative soft use.
- `not_numerically_established`: no transferable numeric requirement; informational only.

`scoring_use` describes the maximum use supported by the catalog evidence. The
versioned calculation policy may always choose a more conservative treatment.

All current crop records are `provisional` until reviewed by a Texas agronomist or
Extension specialist.
