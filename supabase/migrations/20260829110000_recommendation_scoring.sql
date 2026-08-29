-- CropSage deterministic recommendation runs, crop results, and render validation.

create type public.recommendation_run_kind as enum (
  'baseline',
  'scenario'
);

create type public.validation_outcome as enum (
  'passed',
  'rejected'
);

create or replace function public.run_artifacts_valid(value jsonb)
returns boolean
language plpgsql
immutable
strict
parallel safe
set search_path = ''
as $$
declare
  artifact jsonb;
begin
  if pg_catalog.jsonb_typeof(value) <> 'array' then
    return false;
  end if;

  for artifact in
    select item
    from pg_catalog.jsonb_array_elements(value) as element(item)
  loop
    if pg_catalog.jsonb_typeof(artifact) <> 'object'
      or not artifact ?& array[
        'bucket_name',
        'object_path',
        'sha256',
        'content_type',
        'size_bytes',
        'schema_version'
      ]
      or artifact ->> 'bucket_name' <> 'run-artifacts'
      or artifact ->> 'object_path' !~ '^[A-Za-z0-9][A-Za-z0-9/_=.-]*$'
      or artifact ->> 'object_path' like '%..%'
      or artifact ->> 'sha256' !~ '^[0-9a-f]{64}$'
      or artifact ->> 'content_type' !~ '^[a-z0-9.+-]+/[a-z0-9.+-]+$'
      or pg_catalog.jsonb_typeof(artifact -> 'size_bytes') <> 'number'
      or artifact ->> 'size_bytes' !~ '^[0-9]+$'
      or nullif(btrim(artifact ->> 'schema_version'), '') is null
      or public.jsonb_contains_sensitive_keys(artifact)
    then
      return false;
    end if;
  end loop;

  return true;
end;
$$;

revoke all on function public.run_artifacts_valid(jsonb) from public, anon, authenticated;

create table public.recommendation_runs (
  id uuid primary key default extensions.gen_random_uuid(),
  external_run_id text not null unique,
  assessment_session_id uuid not null references public.assessment_sessions(id) on delete restrict,
  farm_profile_id uuid not null,
  evidence_bundle_id uuid not null,
  parent_run_id uuid,

  run_kind public.recommendation_run_kind not null default 'baseline',
  evaluation_mode public.evaluation_mode not null,
  requested_crop_id text,
  scenario_type text,
  scenario_changes_jsonb jsonb not null default '{}'::jsonb,
  scenario_assumptions text[] not null default '{}'::text[],

  farm_profile_version integer not null,
  farm_profile_hash text not null,
  evidence_bundle_hash text not null,
  catalog_version text not null,
  catalog_source_path text not null,
  catalog_manifest_jsonb jsonb not null,
  catalog_hash text generated always as (public.jsonb_sha256(catalog_manifest_jsonb)) stored,
  engine_version text not null,
  engine_git_commit text,
  scoring_policy_version text not null,
  scoring_policy_jsonb jsonb not null,
  scoring_policy_hash text generated always as (public.jsonb_sha256(scoring_policy_jsonb)) stored,
  engine_input_schema_version text not null,
  engine_output_schema_version text not null,
  engine_input_jsonb jsonb not null,
  engine_input_hash text generated always as (public.jsonb_sha256(engine_input_jsonb)) stored,
  engine_output_jsonb jsonb,
  engine_output_hash text generated always as (public.jsonb_sha256(engine_output_jsonb)) stored,
  artifacts_jsonb jsonb not null default '[]'::jsonb,

  status public.recommendation_run_status not null default 'pending',
  started_at timestamptz,
  scored_at timestamptz,
  validated_at timestamptz,
  completed_at timestamptz,
  failed_at timestamptz,
  error_code text,
  error_message text,
  created_at timestamptz not null default statement_timestamp(),
  updated_at timestamptz not null default statement_timestamp(),

  constraint recommendation_runs_external_id_format
    check (external_run_id ~ '^[a-z0-9][a-z0-9_-]{2,99}$'),
  constraint recommendation_runs_requested_crop_format
    check (requested_crop_id is null or requested_crop_id ~ '^[a-z0-9][a-z0-9_]*$'),
  constraint recommendation_runs_scenario_shape
    check (
      (
        run_kind = 'baseline'
        and parent_run_id is null
        and scenario_type is null
        and scenario_changes_jsonb = '{}'::jsonb
        and cardinality(scenario_assumptions) = 0
      )
      or (
        run_kind = 'scenario'
        and parent_run_id is not null
        and nullif(btrim(scenario_type), '') is not null
        and jsonb_typeof(scenario_changes_jsonb) = 'object'
        and scenario_changes_jsonb <> '{}'::jsonb
      )
    ),
  constraint recommendation_runs_scenario_changes_object
    check (jsonb_typeof(scenario_changes_jsonb) = 'object'),
  constraint recommendation_runs_scenario_assumptions_no_nulls
    check (array_position(scenario_assumptions, null) is null),
  constraint recommendation_runs_positive_profile_version
    check (farm_profile_version > 0),
  constraint recommendation_runs_hash_formats
    check (
      farm_profile_hash ~ '^[0-9a-f]{64}$'
      and evidence_bundle_hash ~ '^[0-9a-f]{64}$'
    ),
  constraint recommendation_runs_versions_present
    check (
      nullif(btrim(catalog_version), '') is not null
      and nullif(btrim(engine_version), '') is not null
      and nullif(btrim(scoring_policy_version), '') is not null
      and nullif(btrim(engine_input_schema_version), '') is not null
      and nullif(btrim(engine_output_schema_version), '') is not null
    ),
  constraint recommendation_runs_catalog_path_present
    check (nullif(btrim(catalog_source_path), '') is not null),
  constraint recommendation_runs_git_commit_format
    check (engine_git_commit is null or engine_git_commit ~ '^[0-9a-f]{7,40}$'),
  constraint recommendation_runs_documents_safe
    check (
      jsonb_typeof(catalog_manifest_jsonb) = 'object'
      and jsonb_typeof(scoring_policy_jsonb) = 'object'
      and jsonb_typeof(engine_input_jsonb) = 'object'
      and (engine_output_jsonb is null or jsonb_typeof(engine_output_jsonb) = 'object')
      and not public.jsonb_contains_sensitive_keys(catalog_manifest_jsonb)
      and not public.jsonb_contains_sensitive_keys(scoring_policy_jsonb)
      and not public.jsonb_contains_sensitive_keys(engine_input_jsonb)
      and (
        engine_output_jsonb is null
        or not public.jsonb_contains_sensitive_keys(engine_output_jsonb)
      )
    ),
  constraint recommendation_runs_artifacts_valid
    check (public.run_artifacts_valid(artifacts_jsonb)),
  constraint recommendation_runs_lifecycle
    check (
      (
        status = 'pending'
        and num_nonnulls(started_at, scored_at, validated_at, completed_at, failed_at) = 0
        and engine_output_jsonb is null
        and error_code is null
        and error_message is null
      )
      or (
        status = 'running'
        and started_at is not null
        and num_nonnulls(scored_at, validated_at, completed_at, failed_at) = 0
        and engine_output_jsonb is null
        and error_code is null
        and error_message is null
      )
      or (
        status = 'scored'
        and started_at is not null
        and scored_at is not null
        and scored_at >= started_at
        and num_nonnulls(validated_at, completed_at, failed_at) = 0
        and engine_output_jsonb is not null
        and error_code is null
        and error_message is null
      )
      or (
        status = 'validated'
        and started_at is not null
        and scored_at is not null
        and validated_at is not null
        and scored_at >= started_at
        and validated_at >= scored_at
        and num_nonnulls(completed_at, failed_at) = 0
        and engine_output_jsonb is not null
        and error_code is null
        and error_message is null
      )
      or (
        status = 'completed'
        and started_at is not null
        and scored_at is not null
        and validated_at is not null
        and completed_at is not null
        and scored_at >= started_at
        and validated_at >= scored_at
        and completed_at >= validated_at
        and failed_at is null
        and engine_output_jsonb is not null
        and error_code is null
        and error_message is null
      )
      or (
        status = 'failed'
        and failed_at is not null
        and completed_at is null
        and nullif(btrim(error_code), '') is not null
        and nullif(btrim(error_message), '') is not null
      )
    ),
  constraint recommendation_runs_updated_after_creation
    check (updated_at >= created_at),
  constraint recommendation_runs_session_profile_fk
    foreign key (assessment_session_id, farm_profile_id)
    references public.farm_profiles(assessment_session_id, id)
    on delete restrict,
  constraint recommendation_runs_profile_bundle_fk
    foreign key (farm_profile_id, evidence_bundle_id)
    references public.evidence_bundles(farm_profile_id, id)
    on delete restrict,
  constraint recommendation_runs_session_id_pair_unique
    unique (assessment_session_id, id),
  constraint recommendation_runs_session_parent_fk
    foreign key (assessment_session_id, parent_run_id)
    references public.recommendation_runs(assessment_session_id, id)
    on delete restrict
);

create table public.crop_score_results (
  id uuid primary key default extensions.gen_random_uuid(),
  recommendation_run_id uuid not null references public.recommendation_runs(id) on delete restrict,
  crop_id text not null,
  crop_name text not null,
  status public.crop_result_status not null,
  regionally_eligible boolean not null,
  overall_rank smallint not null,
  eligible_rank smallint,
  suitability_score numeric(5, 2),
  recommendation public.recommendation_class not null,
  confidence_score numeric(5, 2),
  confidence_band public.confidence_band,
  evidence_coverage_percent numeric(5, 2),
  factors_jsonb jsonb not null,
  applied_caps_jsonb jsonb not null default '[]'::jsonb,
  applied_gates_jsonb jsonb not null default '[]'::jsonb,
  key_strengths_jsonb jsonb not null default '[]'::jsonb,
  key_risks_jsonb jsonb not null default '[]'::jsonb,
  warnings text[] not null default '{}'::text[],
  reason_codes text[] not null default '{}'::text[],
  evidence_record_ids uuid[] not null,
  baseline_suitability_score numeric(5, 2),
  suitability_delta numeric(6, 2),
  baseline_overall_rank smallint,
  overall_rank_delta smallint,
  result_snapshot jsonb not null,
  result_hash text generated always as (public.jsonb_sha256(result_snapshot)) stored,
  created_at timestamptz not null default statement_timestamp(),

  constraint crop_score_results_crop_id_format
    check (crop_id ~ '^[a-z0-9][a-z0-9_]*$'),
  constraint crop_score_results_crop_name_present
    check (nullif(btrim(crop_name), '') is not null and char_length(crop_name) <= 160),
  constraint crop_score_results_rank_ranges
    check (
      overall_rank between 1 and 22
      and (eligible_rank is null or eligible_rank between 1 and 22)
      and (baseline_overall_rank is null or baseline_overall_rank between 1 and 22)
    ),
  constraint crop_score_results_eligibility_shape
    check (
      (regionally_eligible and eligible_rank is not null)
      or (not regionally_eligible and eligible_rank is null)
    ),
  constraint crop_score_results_score_ranges
    check (
      (suitability_score is null or suitability_score between 0 and 100)
      and (confidence_score is null or confidence_score between 0 and 100)
      and (evidence_coverage_percent is null or evidence_coverage_percent between 0 and 100)
      and (baseline_suitability_score is null or baseline_suitability_score between 0 and 100)
    ),
  constraint crop_score_results_status_shape
    check (
      (
        status = 'scored'
        and suitability_score is not null
        and confidence_score is not null
        and confidence_band is not null
        and evidence_coverage_percent is not null
        and recommendation <> 'insufficient_evidence'
      )
      or (
        status = 'insufficient_evidence'
        and suitability_score is null
        and recommendation = 'insufficient_evidence'
      )
    ),
  constraint crop_score_results_ineligible_policy
    check (
      status <> 'scored'
      or regionally_eligible
      or (
        recommendation = 'not_recommended'
        and suitability_score is not null
        and suitability_score <= 54
      )
    ),
  constraint crop_score_results_documents
    check (
      jsonb_typeof(factors_jsonb) = 'array'
      and jsonb_typeof(applied_caps_jsonb) = 'array'
      and jsonb_typeof(applied_gates_jsonb) = 'array'
      and jsonb_typeof(key_strengths_jsonb) = 'array'
      and jsonb_typeof(key_risks_jsonb) = 'array'
      and jsonb_typeof(result_snapshot) = 'object'
      and not public.jsonb_contains_sensitive_keys(factors_jsonb)
      and not public.jsonb_contains_sensitive_keys(applied_caps_jsonb)
      and not public.jsonb_contains_sensitive_keys(applied_gates_jsonb)
      and not public.jsonb_contains_sensitive_keys(key_strengths_jsonb)
      and not public.jsonb_contains_sensitive_keys(key_risks_jsonb)
      and not public.jsonb_contains_sensitive_keys(result_snapshot)
    ),
  constraint crop_score_results_arrays_no_nulls
    check (
      array_position(warnings, null) is null
      and array_position(reason_codes, null) is null
      and cardinality(evidence_record_ids) > 0
      and array_position(evidence_record_ids, null) is null
    ),
  constraint crop_score_results_run_crop_unique
    unique (recommendation_run_id, crop_id),
  constraint crop_score_results_run_overall_rank_unique
    unique (recommendation_run_id, overall_rank)
);

create unique index crop_score_results_run_eligible_rank_idx
  on public.crop_score_results(recommendation_run_id, eligible_rank)
  where regionally_eligible;

create table public.validation_reports (
  id uuid primary key default extensions.gen_random_uuid(),
  recommendation_run_id uuid not null unique references public.recommendation_runs(id) on delete restrict,
  validator_version text not null,
  report_schema_version text not null,
  outcome public.validation_outcome not null,
  render_allowed boolean not null default false,
  checked_engine_input_hash text not null,
  checked_engine_output_hash text not null,
  checked_evidence_bundle_hash text not null,
  checks_jsonb jsonb not null default '[]'::jsonb,
  reconciliation_jsonb jsonb not null default '{}'::jsonb,
  grounding_jsonb jsonb not null default '{}'::jsonb,
  evidence_coverage_jsonb jsonb not null default '{}'::jsonb,
  errors text[] not null default '{}'::text[],
  warnings text[] not null default '{}'::text[],
  report_snapshot jsonb not null,
  report_hash text generated always as (public.jsonb_sha256(report_snapshot)) stored,
  validated_at timestamptz not null,
  created_at timestamptz not null default statement_timestamp(),

  constraint validation_reports_versions_present
    check (
      nullif(btrim(validator_version), '') is not null
      and nullif(btrim(report_schema_version), '') is not null
    ),
  constraint validation_reports_hash_formats
    check (
      checked_engine_input_hash ~ '^[0-9a-f]{64}$'
      and checked_engine_output_hash ~ '^[0-9a-f]{64}$'
      and checked_evidence_bundle_hash ~ '^[0-9a-f]{64}$'
    ),
  constraint validation_reports_outcome_shape
    check (
      (
        outcome = 'passed'
        and render_allowed
        and cardinality(errors) = 0
      )
      or (
        outcome = 'rejected'
        and not render_allowed
        and cardinality(errors) > 0
      )
    ),
  constraint validation_reports_documents
    check (
      jsonb_typeof(checks_jsonb) = 'array'
      and jsonb_typeof(reconciliation_jsonb) = 'object'
      and jsonb_typeof(grounding_jsonb) = 'object'
      and jsonb_typeof(evidence_coverage_jsonb) = 'object'
      and jsonb_typeof(report_snapshot) = 'object'
      and not public.jsonb_contains_sensitive_keys(checks_jsonb)
      and not public.jsonb_contains_sensitive_keys(reconciliation_jsonb)
      and not public.jsonb_contains_sensitive_keys(grounding_jsonb)
      and not public.jsonb_contains_sensitive_keys(evidence_coverage_jsonb)
      and not public.jsonb_contains_sensitive_keys(report_snapshot)
    ),
  constraint validation_reports_arrays_no_nulls
    check (array_position(errors, null) is null and array_position(warnings, null) is null),
  constraint validation_reports_time_order
    check (validated_at >= created_at)
);

create or replace function public.validate_recommendation_run_contract()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  actual_profile_version integer;
  actual_profile_hash text;
  actual_bundle_hash text;
  actual_bundle_status public.evidence_bundle_status;
  parent_status public.recommendation_run_status;
begin
  if new.status <> 'pending' then
    raise exception 'Recommendation runs must be created in pending state.';
  end if;

  select profile_version, input_hash
    into actual_profile_version, actual_profile_hash
  from public.farm_profiles
  where id = new.farm_profile_id
    and assessment_session_id = new.assessment_session_id;

  if not found
    or new.farm_profile_version <> actual_profile_version
    or new.farm_profile_hash <> actual_profile_hash
  then
    raise exception 'Recommendation run profile version and hash must match the referenced farm profile.';
  end if;

  select bundle_hash, status
    into actual_bundle_hash, actual_bundle_status
  from public.evidence_bundles
  where id = new.evidence_bundle_id
    and farm_profile_id = new.farm_profile_id;

  if not found
    or actual_bundle_status <> 'validated'
    or actual_bundle_hash is null
    or new.evidence_bundle_hash <> actual_bundle_hash
  then
    raise exception 'Recommendation run must use the exact hash of a validated evidence bundle.';
  end if;

  if new.run_kind = 'scenario' then
    select status
      into parent_status
    from public.recommendation_runs
    where id = new.parent_run_id
      and assessment_session_id = new.assessment_session_id;

    if not found or parent_status <> 'completed' then
      raise exception 'A scenario run must reference a completed run in the same assessment session.';
    end if;
  end if;

  return new;
end;
$$;

create or replace function public.validate_crop_score_result_write()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  run_status public.recommendation_run_status;
  run_bundle_id uuid;
  evidence_id uuid;
begin
  select status, evidence_bundle_id
    into run_status, run_bundle_id
  from public.recommendation_runs
  where id = coalesce(new.recommendation_run_id, old.recommendation_run_id);

  if run_status <> 'running' then
    raise exception 'Crop score results may only be written while the recommendation run is running.';
  end if;

  if tg_op <> 'DELETE' then
    foreach evidence_id in array new.evidence_record_ids
    loop
      if not exists (
        select 1
        from public.evidence_bundle_records
        where evidence_bundle_id = run_bundle_id
          and evidence_record_id = evidence_id
      ) then
        raise exception 'Crop score evidence references must belong to the run evidence bundle.';
      end if;
    end loop;
  end if;

  if tg_op = 'DELETE' then
    return old;
  end if;

  return new;
end;
$$;

create or replace function public.validate_recommendation_run_results(run_id uuid)
returns void
language plpgsql
security invoker
set search_path = ''
as $$
declare
  result_count integer;
  wrong_overall_order_count integer;
  wrong_eligible_order_count integer;
begin
  select count(*)
    into result_count
  from public.crop_score_results
  where recommendation_run_id = run_id;

  if result_count <> 22 then
    raise exception 'A scored recommendation run must contain exactly 22 crop results.';
  end if;

  select count(*)
    into wrong_overall_order_count
  from (
    select
      overall_rank,
      row_number() over (
        order by
          regionally_eligible desc,
          suitability_score desc nulls last,
          confidence_score desc nulls last,
          crop_id asc
      ) as expected_rank
    from public.crop_score_results
    where recommendation_run_id = run_id
  ) ranked
  where overall_rank <> expected_rank;

  if wrong_overall_order_count > 0 then
    raise exception 'Crop overall ranks do not match the eligibility-first deterministic ordering policy.';
  end if;

  select count(*)
    into wrong_eligible_order_count
  from (
    select
      eligible_rank,
      row_number() over (
        order by suitability_score desc nulls last, confidence_score desc nulls last, crop_id asc
      ) as expected_rank
    from public.crop_score_results
    where recommendation_run_id = run_id
      and regionally_eligible
  ) ranked
  where eligible_rank <> expected_rank;

  if wrong_eligible_order_count > 0 then
    raise exception 'Eligible crop ranks must be contiguous and follow deterministic score ordering.';
  end if;
end;
$$;

create or replace function public.enforce_recommendation_run_lifecycle()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if old.status in ('completed', 'failed') then
    raise exception 'Completed or failed recommendation runs are immutable.';
  end if;

  if row(
    new.external_run_id,
    new.assessment_session_id,
    new.farm_profile_id,
    new.evidence_bundle_id,
    new.parent_run_id,
    new.run_kind,
    new.evaluation_mode,
    new.requested_crop_id,
    new.scenario_type,
    new.scenario_changes_jsonb,
    new.scenario_assumptions,
    new.farm_profile_version,
    new.farm_profile_hash,
    new.evidence_bundle_hash,
    new.catalog_version,
    new.catalog_source_path,
    new.catalog_manifest_jsonb,
    new.engine_version,
    new.engine_git_commit,
    new.scoring_policy_version,
    new.scoring_policy_jsonb,
    new.engine_input_schema_version,
    new.engine_output_schema_version,
    new.engine_input_jsonb
  ) is distinct from row(
    old.external_run_id,
    old.assessment_session_id,
    old.farm_profile_id,
    old.evidence_bundle_id,
    old.parent_run_id,
    old.run_kind,
    old.evaluation_mode,
    old.requested_crop_id,
    old.scenario_type,
    old.scenario_changes_jsonb,
    old.scenario_assumptions,
    old.farm_profile_version,
    old.farm_profile_hash,
    old.evidence_bundle_hash,
    old.catalog_version,
    old.catalog_source_path,
    old.catalog_manifest_jsonb,
    old.engine_version,
    old.engine_git_commit,
    old.scoring_policy_version,
    old.scoring_policy_jsonb,
    old.engine_input_schema_version,
    old.engine_output_schema_version,
    old.engine_input_jsonb
  ) then
    raise exception 'Recommendation run contract inputs and version references are immutable.';
  end if;

  if new.engine_output_jsonb is distinct from old.engine_output_jsonb
    and not (old.status = 'running' and new.status = 'scored')
  then
    raise exception 'Engine output may only be attached when a running recommendation run becomes scored.';
  end if;

  if new.artifacts_jsonb is distinct from old.artifacts_jsonb
    and not (old.status = 'running' and new.status = 'scored')
  then
    raise exception 'Run artifacts may only be attached when a running recommendation run becomes scored.';
  end if;

  if not (
    (old.status = 'pending' and new.status in ('running', 'failed'))
    or (old.status = 'running' and new.status in ('scored', 'failed'))
    or (old.status = 'scored' and new.status in ('validated', 'failed'))
    or (old.status = 'validated' and new.status in ('completed', 'failed'))
  ) then
    raise exception 'Invalid recommendation run status transition from % to %.', old.status, new.status;
  end if;

  if new.status = 'scored' then
    perform public.validate_recommendation_run_results(new.id);
  elsif new.status = 'validated' then
    if not exists (
      select 1
      from public.validation_reports
      where recommendation_run_id = new.id
        and outcome = 'passed'
        and render_allowed
    ) then
      raise exception 'A run requires a passed render-authorizing validation report before validation.';
    end if;
  end if;

  new.updated_at := statement_timestamp();
  return new;
end;
$$;

create or replace function public.validate_validation_report()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  run_status public.recommendation_run_status;
  run_input_hash text;
  run_output_hash text;
  run_bundle_hash text;
begin
  select status, engine_input_hash, engine_output_hash, evidence_bundle_hash
    into run_status, run_input_hash, run_output_hash, run_bundle_hash
  from public.recommendation_runs
  where id = new.recommendation_run_id;

  if run_status <> 'scored' then
    raise exception 'Validation reports may only be created for scored recommendation runs.';
  end if;

  if new.checked_engine_input_hash <> run_input_hash
    or new.checked_engine_output_hash <> run_output_hash
    or new.checked_evidence_bundle_hash <> run_bundle_hash
  then
    raise exception 'Validation report hashes must match the exact run input, output, and evidence bundle.';
  end if;

  return new;
end;
$$;

create or replace function public.reject_validation_report_mutation()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  raise exception 'Validation reports are immutable; create a new recommendation run for corrections.';
end;
$$;

revoke all on function public.validate_recommendation_run_contract() from public, anon, authenticated;
revoke all on function public.validate_crop_score_result_write() from public, anon, authenticated;
revoke all on function public.validate_recommendation_run_results(uuid) from public, anon, authenticated;
revoke all on function public.enforce_recommendation_run_lifecycle() from public, anon, authenticated;
revoke all on function public.validate_validation_report() from public, anon, authenticated;
revoke all on function public.reject_validation_report_mutation() from public, anon, authenticated;

create trigger recommendation_runs_validate_contract
before insert on public.recommendation_runs
for each row execute function public.validate_recommendation_run_contract();

create trigger recommendation_runs_enforce_lifecycle
before update on public.recommendation_runs
for each row execute function public.enforce_recommendation_run_lifecycle();

create trigger crop_score_results_validate_write
before insert or update or delete on public.crop_score_results
for each row execute function public.validate_crop_score_result_write();

create trigger validation_reports_validate_insert
before insert on public.validation_reports
for each row execute function public.validate_validation_report();

create trigger validation_reports_reject_mutation
before update or delete on public.validation_reports
for each row execute function public.reject_validation_report_mutation();

create index recommendation_runs_session_created_idx
  on public.recommendation_runs(assessment_session_id, created_at desc);

create index recommendation_runs_profile_status_idx
  on public.recommendation_runs(farm_profile_id, status, created_at desc);

create index recommendation_runs_parent_idx
  on public.recommendation_runs(parent_run_id)
  where parent_run_id is not null;

create index crop_score_results_run_ranking_idx
  on public.crop_score_results(recommendation_run_id, overall_rank);

create index crop_score_results_evidence_ids_gin
  on public.crop_score_results using gin(evidence_record_ids);

alter table public.recommendation_runs enable row level security;
alter table public.crop_score_results enable row level security;
alter table public.validation_reports enable row level security;

revoke all on table public.recommendation_runs from anon, authenticated;
revoke all on table public.crop_score_results from anon, authenticated;
revoke all on table public.validation_reports from anon, authenticated;
grant select on table public.recommendation_runs to authenticated;
grant select on table public.crop_score_results to authenticated;
grant select on table public.validation_reports to authenticated;

create policy recommendation_runs_select_own_session
on public.recommendation_runs
for select
to authenticated
using (
  exists (
    select 1
    from public.assessment_sessions
    where assessment_sessions.id = recommendation_runs.assessment_session_id
      and assessment_sessions.owner_user_id = (select auth.uid())
  )
);

create policy crop_score_results_select_own_run
on public.crop_score_results
for select
to authenticated
using (
  exists (
    select 1
    from public.recommendation_runs
    join public.assessment_sessions
      on assessment_sessions.id = recommendation_runs.assessment_session_id
    where recommendation_runs.id = crop_score_results.recommendation_run_id
      and assessment_sessions.owner_user_id = (select auth.uid())
  )
);

create policy validation_reports_select_own_run
on public.validation_reports
for select
to authenticated
using (
  exists (
    select 1
    from public.recommendation_runs
    join public.assessment_sessions
      on assessment_sessions.id = recommendation_runs.assessment_session_id
    where recommendation_runs.id = validation_reports.recommendation_run_id
      and assessment_sessions.owner_user_id = (select auth.uid())
  )
);

insert into storage.buckets (
  id,
  name,
  public,
  file_size_limit,
  allowed_mime_types
) values (
  'run-artifacts',
  'run-artifacts',
  false,
  52428800,
  array[
    'application/json',
    'application/octet-stream',
    'text/csv'
  ]
) on conflict (id) do update
set public = excluded.public,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

comment on table public.recommendation_runs is
  'Immutable deterministic engine contracts and exact input/output snapshots for baseline and scenario runs.';
comment on table public.crop_score_results is
  'All 22 normalized crop outcomes with eligibility-first deterministic ranking and evidence links.';
comment on table public.validation_reports is
  'Immutable validator output; only a passed report may authorize a recommendation run for rendering.';
comment on column public.recommendation_runs.engine_output_jsonb is
  'Exact engine output document. Queryable crop fields are normalized in crop_score_results.';
comment on column public.crop_score_results.eligible_rank is
  'Contiguous rank among regionally eligible crops; always null for ineligible crops.';
