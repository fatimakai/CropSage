import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const handoffDir = resolve(root, "handoff", "fatima_scoring_migrations");
const outputPath = resolve(
  root,
  "supabase",
  "tests",
  "database",
  "08_handoff_fixture_integration.test.sql",
);

const files = {
  engine_input: "sample_engine_input.json",
  evidence_bundle: "sample_evidence_bundle.json",
  scoring_config: "sample_scoring_config.json",
  engine_output: "sample_22_crop_engine_output.json",
  validation_report: "sample_validation_report.json",
};

const documents = Object.fromEntries(
  Object.entries(files).map(([name, file]) => [
    name,
    JSON.parse(readFileSync(resolve(handoffDir, file), "utf8")),
  ]),
);

const evidenceSchema = JSON.parse(
  readFileSync(resolve(handoffDir, "schemas", "evidence_bundle.schema.json"), "utf8"),
);
const recommendationSchema = JSON.parse(
  readFileSync(resolve(handoffDir, "schemas", "recommendation.schema.json"), "utf8"),
);

function assert(condition, message) {
  if (!condition) {
    throw new Error(`Handoff fixture contract failed: ${message}`);
  }
}

const {
  engine_input: engineInput,
  evidence_bundle: evidenceBundle,
  engine_output: engineOutput,
  validation_report: validationReport,
} = documents;

assert(evidenceBundle.schema_version === "1.2.0", "EvidenceBundle must use schema 1.2.0");
assert(
  evidenceSchema.properties?.schema_version?.const === "1.2.0",
  "EvidenceBundle schema must require version 1.2.0",
);
assert(
  recommendationSchema.$defs?.cropResult?.required?.includes("regionally_eligible") &&
    recommendationSchema.$defs?.cropResult?.required?.includes("overall_rank") &&
    recommendationSchema.$defs?.cropResult?.required?.includes("eligible_rank") &&
    recommendationSchema.$defs?.cropResult?.required?.includes("applied_gates"),
  "recommendation schema must require eligibility-aware ranking fields",
);

const heatWindows = evidenceBundle.location_evidence?.fortyguard_heat?.windows ?? [];
const correctedHeatFields = [
  "minimum_tile_average_temperature_c",
  "maximum_tile_average_temperature_c",
  "period_minimum_temperature_c",
  "period_maximum_temperature_c",
];
assert(heatWindows.length === 4, "EvidenceBundle must contain four FortyGuard windows");
assert(
  heatWindows.every((window) => correctedHeatFields.every((field) => Number.isFinite(window[field]))),
  "every FortyGuard window must contain the four corrected numeric temperature fields",
);

const rankings = engineOutput.rankings ?? [];
const eligible = rankings.filter((crop) => crop.regionally_eligible === true);
const ineligible = rankings.filter((crop) => crop.regionally_eligible === false);
const sortedOverallRanks = rankings.map((crop) => crop.overall_rank).sort((a, b) => a - b);
const sortedEligibleRanks = eligible.map((crop) => crop.eligible_rank).sort((a, b) => a - b);
const expectedCropIds = [...(evidenceBundle.catalog?.crop_ids ?? [])].sort();
const actualCropIds = rankings.map((crop) => crop.crop_id).sort();

assert(rankings.length === 22, "engine output must contain 22 crop results");
assert(new Set(actualCropIds).size === 22, "engine output crop IDs must be unique");
assert(
  sortedOverallRanks.every((rank, index) => rank === index + 1),
  "overall ranks must be the contiguous sequence 1-22",
);
assert(
  sortedEligibleRanks.every((rank, index) => rank === index + 1),
  "eligible ranks must be contiguous",
);
assert(
  ineligible.every(
    (crop) =>
      crop.eligible_rank === null &&
      crop.suitability_score <= 54 &&
      crop.recommendation === "not_recommended" &&
      crop.applied_gates.some((gate) => gate.gate === "unsupported_region"),
  ),
  "every ineligible crop must retain the unsupported_region gate and policy cap",
);
assert(
  rankings.every((crop) => Array.isArray(crop.factors) && crop.factors.length === 18),
  "every crop result must contain 18 factors",
);
assert(
  JSON.stringify(actualCropIds) === JSON.stringify(expectedCropIds),
  "engine output crop IDs must match the EvidenceBundle catalog",
);
assert(engineOutput.profile_id === engineInput.profile_id, "engine input and output profile IDs must match");
assert(
  engineOutput.evidence_bundle_id === evidenceBundle.bundle_id,
  "engine output must reference the supplied EvidenceBundle",
);
assert(
  validationReport.profile_id === engineInput.profile_id &&
    validationReport.evidence_bundle_id === evidenceBundle.bundle_id,
  "validation report must reference the supplied profile and EvidenceBundle",
);
assert(
  validationReport.evidence_bundle_validation?.all_passed === true &&
    validationReport.engine_output_validation?.eligibility_ranking_policy_passed === true,
  "validation report must pass evidence and eligibility-ranking validation",
);
assert(
  validationReport.engine_output_validation?.eligible_crop_count === eligible.length &&
    validationReport.engine_output_validation?.ineligible_crop_count === ineligible.length,
  "validation report eligibility counts must match the engine output",
);

function jsonDollarQuote(name, document) {
  const tag = `$${name}$`;
  const json = JSON.stringify(document);
  assert(!json.includes(tag), `${name} contains the generated SQL dollar-quote tag`);
  return `${tag}${json}${tag}::jsonb`;
}

const documentValues = Object.entries(documents)
  .map(([name, document]) => `  ('${name}', ${jsonDollarQuote(name, document)})`)
  .join(",\n");

const sql = `-- Generated by scripts/generate-handoff-db-test.mjs. Do not edit manually.
-- The checked-in handoff JSON remains the source of truth for this acceptance test.

begin;

set local search_path = public, extensions;

select plan(21);

create temporary table handoff_fixture_documents (
  name text primary key,
  document jsonb not null
) on commit drop;

insert into handoff_fixture_documents (name, document) values
${documentValues};

select is(
  (select document ->> 'schema_version' from handoff_fixture_documents where name = 'evidence_bundle'),
  '1.2.0',
  'the checked-in EvidenceBundle fixture uses schema 1.2.0'
);

select is(
  (
    select jsonb_array_length(document #> '{location_evidence,fortyguard_heat,windows}')
    from handoff_fixture_documents
    where name = 'evidence_bundle'
  ),
  4,
  'the EvidenceBundle retains all four FortyGuard windows'
);

select ok(
  (
    select bool_and(
      heat_window ?& array[
        'minimum_tile_average_temperature_c',
        'maximum_tile_average_temperature_c',
        'period_minimum_temperature_c',
        'period_maximum_temperature_c'
      ]
    )
    from handoff_fixture_documents,
      lateral jsonb_array_elements(
        document #> '{location_evidence,fortyguard_heat,windows}'
      ) as windows(heat_window)
    where name = 'evidence_bundle'
  ),
  'every FortyGuard window preserves the corrected temperature fields'
);

insert into public.evidence_records (
  id,
  farm_profile_id,
  source_type,
  source_name,
  source_metadata_jsonb,
  canonical_variable,
  freshness,
  value_kind,
  value_boolean,
  evidence_point,
  evidence_snapshot
)
select
  '81000000-0000-4000-8000-000000000001',
  '00000000-0000-4000-8000-000000000101',
  'farmer',
  'FarmProfile handoff fixture',
  jsonb_build_object('profile_id', document ->> 'profile_id'),
  'farm.irrigation_available',
  'not_applicable',
  'boolean',
  (document #>> '{irrigation,availability}') = 'yes',
  extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
  jsonb_build_object(
    'source', 'farm_profile_handoff',
    'profile_id', document ->> 'profile_id',
    'variable', 'irrigation_available',
    'value', (document #>> '{irrigation,availability}') = 'yes'
  )
from handoff_fixture_documents
where name = 'engine_input';

insert into public.evidence_bundles (
  id,
  farm_profile_id,
  external_bundle_id,
  bundle_version,
  schema_version,
  catalog_version,
  catalog_hash,
  catalog_source_path,
  location_snapshot_jsonb,
  provider_coverage_jsonb,
  freshness_summary_jsonb
)
select
  '82000000-0000-4000-8000-000000000001',
  '00000000-0000-4000-8000-000000000101',
  document ->> 'bundle_id',
  1,
  document ->> 'schema_version',
  document #>> '{catalog,version}',
  public.jsonb_sha256(document -> 'catalog'),
  document #>> '{catalog,source_path}',
  document -> 'location',
  jsonb_build_object(
    'fortyguard', 'available',
    'nasa_power', 'available',
    'open_meteo', 'available',
    'ssurgo', 'available'
  ),
  '{"fresh":4}'::jsonb
from handoff_fixture_documents
where name = 'evidence_bundle';

insert into public.evidence_bundle_records (
  evidence_bundle_id,
  evidence_record_id,
  inclusion_role,
  inclusion_order,
  inclusion_reason
) values (
  '82000000-0000-4000-8000-000000000001',
  '81000000-0000-4000-8000-000000000001',
  'required',
  1,
  'Required farmer irrigation input retained by the handoff contract'
);

update public.evidence_bundles
set status = 'validated',
    completeness_percent = 100,
    assembled_at = statement_timestamp() - interval '1 second',
    validated_at = statement_timestamp(),
    validation_summary_jsonb = fixture.document -> 'validation',
    bundle_snapshot = fixture.document
from handoff_fixture_documents as fixture
where evidence_bundles.id = '82000000-0000-4000-8000-000000000001'
  and fixture.name = 'evidence_bundle';

select is(
  (select schema_version from public.evidence_bundles where id = '82000000-0000-4000-8000-000000000001'),
  '1.2.0',
  'the database stores the fixture EvidenceBundle schema version'
);

select is(
  (select bundle_hash from public.evidence_bundles where id = '82000000-0000-4000-8000-000000000001'),
  (
    select public.jsonb_sha256(document)
    from handoff_fixture_documents
    where name = 'evidence_bundle'
  ),
  'the persisted EvidenceBundle hash matches the exact handoff document'
);

select is(
  (select bundle_snapshot from public.evidence_bundles where id = '82000000-0000-4000-8000-000000000001'),
  (select document from handoff_fixture_documents where name = 'evidence_bundle'),
  'the EvidenceBundle 1.2.0 fixture round-trips without structural loss'
);

insert into public.recommendation_runs (
  id,
  external_run_id,
  assessment_session_id,
  farm_profile_id,
  evidence_bundle_id,
  evaluation_mode,
  requested_crop_id,
  farm_profile_version,
  farm_profile_hash,
  evidence_bundle_hash,
  catalog_version,
  catalog_source_path,
  catalog_manifest_jsonb,
  engine_version,
  engine_git_commit,
  scoring_policy_version,
  scoring_policy_jsonb,
  engine_input_schema_version,
  engine_output_schema_version,
  engine_input_jsonb
)
select
  '83000000-0000-4000-8000-000000000001',
  'plainview_handoff_acceptance',
  profile.assessment_session_id,
  profile.id,
  bundle.id,
  (output.document ->> 'evaluation_mode')::public.evaluation_mode,
  output.document ->> 'requested_crop_id',
  profile.profile_version,
  profile.input_hash,
  bundle.bundle_hash,
  evidence.document #>> '{catalog,version}',
  evidence.document #>> '{catalog,source_path}',
  evidence.document -> 'catalog',
  output.document ->> 'scoring_version',
  'd4a4a13',
  config.document ->> 'scoring_version',
  config.document,
  input.document ->> 'schema_version',
  output.document ->> 'schema_version',
  input.document
from public.farm_profiles as profile
join public.evidence_bundles as bundle
  on bundle.farm_profile_id = profile.id
cross join handoff_fixture_documents as input
cross join handoff_fixture_documents as evidence
cross join handoff_fixture_documents as config
cross join handoff_fixture_documents as output
where profile.id = '00000000-0000-4000-8000-000000000101'
  and bundle.id = '82000000-0000-4000-8000-000000000001'
  and input.name = 'engine_input'
  and evidence.name = 'evidence_bundle'
  and config.name = 'scoring_config'
  and output.name = 'engine_output';

update public.recommendation_runs
set status = 'running',
    started_at = statement_timestamp()
where id = '83000000-0000-4000-8000-000000000001';

insert into public.crop_score_results (
  recommendation_run_id,
  crop_id,
  crop_name,
  status,
  regionally_eligible,
  overall_rank,
  eligible_rank,
  suitability_score,
  recommendation,
  confidence_score,
  confidence_band,
  evidence_coverage_percent,
  factors_jsonb,
  applied_caps_jsonb,
  applied_gates_jsonb,
  key_strengths_jsonb,
  key_risks_jsonb,
  warnings,
  evidence_record_ids,
  result_snapshot
)
select
  '83000000-0000-4000-8000-000000000001',
  crop ->> 'crop_id',
  crop ->> 'crop_name',
  (crop ->> 'status')::public.crop_result_status,
  (crop ->> 'regionally_eligible')::boolean,
  (crop ->> 'overall_rank')::smallint,
  (crop ->> 'eligible_rank')::smallint,
  (crop ->> 'suitability_score')::numeric,
  (crop ->> 'recommendation')::public.recommendation_class,
  (crop ->> 'confidence_score')::numeric,
  (crop ->> 'confidence_band')::public.confidence_band,
  (crop ->> 'evidence_coverage_percent')::numeric,
  crop -> 'factors',
  crop -> 'applied_caps',
  crop -> 'applied_gates',
  crop -> 'key_strengths',
  crop -> 'key_risks',
  array(select jsonb_array_elements_text(crop -> 'warnings')),
  array['81000000-0000-4000-8000-000000000001'::uuid],
  crop
from handoff_fixture_documents,
  lateral jsonb_array_elements(document -> 'rankings') as ranking(crop)
where name = 'engine_output';

update public.recommendation_runs
set status = 'scored',
    scored_at = statement_timestamp(),
    engine_output_jsonb = fixture.document
from handoff_fixture_documents as fixture
where recommendation_runs.id = '83000000-0000-4000-8000-000000000001'
  and fixture.name = 'engine_output';

select is(
  (select engine_input_hash from public.recommendation_runs where id = '83000000-0000-4000-8000-000000000001'),
  (select public.jsonb_sha256(document) from handoff_fixture_documents where name = 'engine_input'),
  'the run hashes the exact handoff engine input'
);

select is(
  (select scoring_policy_hash from public.recommendation_runs where id = '83000000-0000-4000-8000-000000000001'),
  (select public.jsonb_sha256(document) from handoff_fixture_documents where name = 'scoring_config'),
  'the run hashes the exact handoff scoring policy'
);

select is(
  (select engine_output_hash from public.recommendation_runs where id = '83000000-0000-4000-8000-000000000001'),
  (select public.jsonb_sha256(document) from handoff_fixture_documents where name = 'engine_output'),
  'the run hashes the exact corrected engine output'
);

select is(
  (select count(*) from public.crop_score_results where recommendation_run_id = '83000000-0000-4000-8000-000000000001'),
  22::bigint,
  'the corrected handoff persists all 22 crop results'
);

select is(
  (select count(distinct crop_id) from public.crop_score_results where recommendation_run_id = '83000000-0000-4000-8000-000000000001'),
  22::bigint,
  'the corrected handoff persists 22 unique crop IDs'
);

select is(
  (
    select array_agg(overall_rank order by overall_rank)
    from public.crop_score_results
    where recommendation_run_id = '83000000-0000-4000-8000-000000000001'
  ),
  array[1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22]::smallint[],
  'overall ranks remain the contiguous sequence 1-22'
);

select is(
  (
    select count(*)
    from public.crop_score_results
    where recommendation_run_id = '83000000-0000-4000-8000-000000000001'
      and regionally_eligible
  ),
  (
    select (document #>> '{engine_output_validation,eligible_crop_count}')::bigint
    from handoff_fixture_documents
    where name = 'validation_report'
  ),
  'eligible crop count matches the handoff validation report'
);

select is(
  (
    select count(*)
    from public.crop_score_results
    where recommendation_run_id = '83000000-0000-4000-8000-000000000001'
      and not regionally_eligible
  ),
  (
    select (document #>> '{engine_output_validation,ineligible_crop_count}')::bigint
    from handoff_fixture_documents
    where name = 'validation_report'
  ),
  'ineligible crop count matches the handoff validation report'
);

select is(
  (
    select count(*)
    from public.crop_score_results
    where recommendation_run_id = '83000000-0000-4000-8000-000000000001'
      and not regionally_eligible
      and eligible_rank is null
      and suitability_score <= 54
      and recommendation = 'not_recommended'
      and public.applied_gates_include(applied_gates_jsonb, 'unsupported_region')
  ),
  (
    select (document #>> '{engine_output_validation,ineligible_crop_count}')::bigint
    from handoff_fixture_documents
    where name = 'validation_report'
  ),
  'every ineligible fixture crop satisfies the persisted unsupported-region policy'
);

select is(
  (
    select count(*)
    from public.crop_score_results
    where recommendation_run_id = '83000000-0000-4000-8000-000000000001'
      and jsonb_array_length(factors_jsonb) = 18
  ),
  22::bigint,
  'all persisted fixture crops retain their 18 deterministic factors'
);

select is(
  (
    select count(*)
    from public.crop_score_results as result
    where result.recommendation_run_id = '83000000-0000-4000-8000-000000000001'
      and exists (
        select 1
        from handoff_fixture_documents,
          lateral jsonb_array_elements(document -> 'rankings') as ranking(crop)
        where name = 'engine_output'
          and crop = result.result_snapshot
      )
  ),
  22::bigint,
  'every crop result snapshot matches the exact handoff crop document'
);

insert into public.validation_reports (
  recommendation_run_id,
  validator_version,
  report_schema_version,
  outcome,
  render_allowed,
  checked_engine_input_hash,
  checked_engine_output_hash,
  checked_evidence_bundle_hash,
  checks_jsonb,
  reconciliation_jsonb,
  grounding_jsonb,
  evidence_coverage_jsonb,
  report_snapshot,
  validated_at
)
select
  run.id,
  'handoff-validator-' || (report.document ->> 'report_version'),
  report.document ->> 'report_version',
  'passed',
  true,
  run.engine_input_hash,
  run.engine_output_hash,
  run.evidence_bundle_hash,
  (report.document #> '{evidence_bundle_validation,checks}') || jsonb_build_array(
    jsonb_build_object(
      'name', 'engine_output_validation',
      'passed', report.document #> '{engine_output_validation,passed}'
    )
  ),
  report.document -> 'engine_output_validation',
  jsonb_build_object(
    'profile_id', report.document ->> 'profile_id',
    'evidence_bundle_id', report.document ->> 'evidence_bundle_id'
  ),
  jsonb_build_object(
    'eligible_crop_count', report.document #> '{engine_output_validation,eligible_crop_count}',
    'ineligible_crop_count', report.document #> '{engine_output_validation,ineligible_crop_count}'
  ),
  report.document,
  statement_timestamp()
from public.recommendation_runs as run
cross join handoff_fixture_documents as report
where run.id = '83000000-0000-4000-8000-000000000001'
  and report.name = 'validation_report';

select is(
  (
    select report_hash
    from public.validation_reports
    where recommendation_run_id = '83000000-0000-4000-8000-000000000001'
  ),
  (select public.jsonb_sha256(document) from handoff_fixture_documents where name = 'validation_report'),
  'the validation report hash matches the exact handoff report'
);

select ok(
  (
    select render_allowed
    from public.validation_reports
    where recommendation_run_id = '83000000-0000-4000-8000-000000000001'
  ),
  'the passed handoff validation report authorizes rendering'
);

update public.recommendation_runs
set status = 'validated',
    validated_at = statement_timestamp()
where id = '83000000-0000-4000-8000-000000000001';

update public.recommendation_runs
set status = 'completed',
    completed_at = statement_timestamp()
where id = '83000000-0000-4000-8000-000000000001';

select is(
  (select status from public.recommendation_runs where id = '83000000-0000-4000-8000-000000000001'),
  'completed'::public.recommendation_run_status,
  'the exact handoff fixture reaches completed recommendation state'
);

select throws_ok(
  $$
    update public.recommendation_runs
    set error_message = 'late mutation'
    where id = '83000000-0000-4000-8000-000000000001'
  $$,
  'Completed or failed recommendation runs are immutable.',
  'the completed handoff recommendation remains append-only'
);

select * from finish();

rollback;
`;

writeFileSync(outputPath, sql, "utf8");
console.log(`Generated ${outputPath}`);
