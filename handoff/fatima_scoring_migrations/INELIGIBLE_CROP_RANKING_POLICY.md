# Ineligible crop ranking policy

## Required behavior

1. Persist results for all 22 crops for transparency, debugging and audit.
2. A crop whose catalog regional rating is `not_supported` is regionally
   ineligible.
3. Apply the `unsupported_region` gate and cap suitability at `54`.
4. The recommendation must be `not_recommended`, regardless of its uncapped
   factor score.
5. Exclude ineligible crops from farmer-facing Recommended and Conditional
   groups.
6. Display them in a separate **Not suitable for this Texas region** group.
7. In visible ranking order, every regionally eligible crop precedes every
   ineligible crop. Sort within each group by suitability descending, then
   confidence descending, then `crop_id` ascending for deterministic ties.

## Storage fields

Store at least:

- `regionally_eligible` — boolean
- `overall_rank` — integer from 1 through 22 after eligibility grouping
- `eligible_rank` — nullable integer; null for ineligible crops
- `suitability_score`
- `recommendation`
- `applied_gates` or normalized gate rows

The current sample engine output represents scoring version
`1.0.0-provisional`. The migration should not infer eligibility only from a
score because other hard gates can also cap a result at 54.

