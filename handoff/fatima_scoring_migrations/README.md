# CropSage scoring migration handoff

This folder contains the database-contract samples requested for the scoring
migrations. All JSON files use synthetic or demonstration farm data and contain
no API keys.

## Files

- `sample_engine_input.json` — farmer profile passed to the engine.
- `sample_evidence_bundle.json` — normalized four-provider evidence for the
  same location.
- `sample_scoring_config.json` — deterministic weights, mappings, caps and
  confidence settings used by the engine.
- `sample_22_crop_engine_output.json` — complete validated output containing
  all 22 crop results and 18 factor records per crop.
- `sample_validation_report.json` — sample bundle and engine-output validation
  report suitable for designing validation-run storage.
- `INELIGIBLE_CROP_RANKING_POLICY.md` — required persistence and display
  behavior for regionally unsupported crops.
- `schemas/` — JSON Schemas for the farm profile, EvidenceBundle and engine
  recommendation output.

## Engine contract

The deterministic engine receives three documents:

1. `sample_engine_input.json`
2. `sample_evidence_bundle.json`
3. `sample_scoring_config.json`

It returns `sample_22_crop_engine_output.json`.

The engine is authoritative for scores, factors, caps, recommendation bands and
rank. The LLM must not calculate or modify these fields.

