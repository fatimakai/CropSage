-- Persist one prepared deterministic recommendation as an atomic, replayable run.

create or replace function public.persist_recommendation_execution(
  p_assessment_session_id uuid,
  p_resolved_profile_snapshot jsonb,
  p_location_resolution jsonb,
  p_evidence_bundle_snapshot jsonb,
  p_scoring_policy jsonb,
  p_engine_output jsonb,
  p_validation_report jsonb,
  p_provider_artifacts jsonb
)
returns table (
  recommendation_run_id uuid,
  farm_profile_id uuid,
  evidence_bundle_id uuid,
  created boolean
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_existing_run_id uuid;
  v_source_profile public.farm_profiles%rowtype;
  v_profile_id uuid := extensions.gen_random_uuid();
  v_bundle_id uuid := extensions.gen_random_uuid();
  v_run_id uuid := extensions.gen_random_uuid();
  v_external_bundle_id text := 'eb_' || replace(v_bundle_id::text, '-', '');
  v_external_run_id text := 'run_' || replace(v_run_id::text, '-', '');
  v_latitude double precision;
  v_longitude double precision;
  v_now timestamptz := statement_timestamp();
  v_profile_hash text;
  v_bundle_hash text;
  v_engine_input_hash text;
  v_engine_output_hash text;
  v_provider public.provider_code;
  v_evidence_key text;
  v_provider_fetch_id uuid;
  v_evidence_record_id uuid;
  v_evidence_record_ids uuid[] := '{}'::uuid[];
  v_artifact jsonb;
  v_provenance jsonb;
  v_evidence_value jsonb;
  v_rank jsonb;
  v_sequence integer := 0;
  v_provider_codes public.provider_code[] := array[
    'nasa_power'::public.provider_code,
    'open_meteo'::public.provider_code,
    'ssurgo'::public.provider_code,
    'fortyguard'::public.provider_code
  ];
  v_evidence_keys text[] := array[
    'nasa_power_climate',
    'open_meteo_weather',
    'ssurgo_soil',
    'fortyguard_heat'
  ];
  v_index integer;
begin
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(p_assessment_session_id::text, 0)
  );

  select id into v_existing_run_id
  from public.recommendation_runs
  where assessment_session_id = p_assessment_session_id
    and run_kind = 'baseline'
    and status = 'completed'
  order by created_at desc
  limit 1;

  if v_existing_run_id is not null then
    return query
    select
      r.id,
      r.farm_profile_id,
      r.evidence_bundle_id,
      false
    from public.recommendation_runs r
    where r.id = v_existing_run_id;
    return;
  end if;

  if jsonb_typeof(p_resolved_profile_snapshot) <> 'object'
    or jsonb_typeof(p_location_resolution) <> 'object'
    or jsonb_typeof(p_evidence_bundle_snapshot) <> 'object'
    or jsonb_typeof(p_scoring_policy) <> 'object'
    or jsonb_typeof(p_engine_output) <> 'object'
    or jsonb_typeof(p_validation_report) <> 'object'
    or jsonb_typeof(p_provider_artifacts) <> 'object'
  then
    raise exception 'Recommendation persistence requires object contract documents.';
  end if;

  if p_validation_report ->> 'status' <> 'passed'
    or coalesce((p_validation_report ->> 'render_allowed')::boolean, false) is false
    or jsonb_array_length(coalesce(p_validation_report -> 'errors', '[]'::jsonb)) > 0
  then
    raise exception 'Only a passed, render-authorizing validation report may be persisted.';
  end if;

  select fp.* into v_source_profile
  from public.assessment_sessions s
  join public.farm_profiles fp on fp.id = s.active_profile_id
  where s.id = p_assessment_session_id
    and s.status = 'active'
  for update of s, fp;

  if not found then
    raise exception 'The assessment session has no active farm profile.';
  end if;

  v_latitude := (p_resolved_profile_snapshot #>> '{location,latitude}')::double precision;
  v_longitude := (p_resolved_profile_snapshot #>> '{location,longitude}')::double precision;

  insert into public.farm_profiles (
    id, assessment_session_id, external_profile_id, profile_version,
    schema_version, status, supersedes_profile_id, captured_at,
    farm_point, farm_name, location_label, location_source,
    resolved_region_id, region_resolution_method, region_resolution_version,
    timezone, timezone_resolution_method, timezone_resolution_version,
    location_resolution_jsonb, planned_planting_date, planned_planting_month,
    planting_flexibility_days, requested_crop_id, irrigation_jsonb,
    soil_overrides_jsonb, current_soil_moisture_jsonb, recent_rainfall_jsonb,
    farmer_goal_jsonb, field_sources_jsonb, missing_fields, completeness_notes,
    profile_snapshot
  ) values (
    v_profile_id,
    p_assessment_session_id,
    p_resolved_profile_snapshot ->> 'profile_id',
    v_source_profile.profile_version + 1,
    p_resolved_profile_snapshot ->> 'schema_version',
    'ready',
    v_source_profile.id,
    nullif(p_resolved_profile_snapshot ->> 'captured_at', '')::timestamptz,
    extensions.st_setsrid(extensions.st_makepoint(v_longitude, v_latitude), 4326)::extensions.geography,
    nullif(p_resolved_profile_snapshot #>> '{location,farm_name}', ''),
    nullif(p_resolved_profile_snapshot #>> '{location,location_label}', ''),
    (p_resolved_profile_snapshot #>> '{location,source}')::public.location_source,
    nullif(p_location_resolution ->> 'evidence_region_id', ''),
    p_location_resolution ->> 'method',
    '1.0.0',
    nullif(p_location_resolution ->> 'timezone', ''),
    'representative_site_manifest',
    '1.0.0',
    p_location_resolution,
    nullif(p_resolved_profile_snapshot #>> '{planting,planned_date}', '')::date,
    case
      when nullif(p_resolved_profile_snapshot #>> '{planting,planned_month}', '') is null then null
      else ((p_resolved_profile_snapshot #>> '{planting,planned_month}') || '-01')::date
    end,
    nullif(p_resolved_profile_snapshot #>> '{planting,flexibility_days}', '')::smallint,
    nullif(p_resolved_profile_snapshot ->> 'requested_crop_id', ''),
    case when p_resolved_profile_snapshot ? 'irrigation' then p_resolved_profile_snapshot -> 'irrigation' end,
    case when p_resolved_profile_snapshot ? 'soil_overrides' then p_resolved_profile_snapshot -> 'soil_overrides' end,
    case when p_resolved_profile_snapshot ? 'current_soil_moisture' then p_resolved_profile_snapshot -> 'current_soil_moisture' end,
    case when p_resolved_profile_snapshot ? 'recent_rainfall' then p_resolved_profile_snapshot -> 'recent_rainfall' end,
    case when p_resolved_profile_snapshot ? 'farmer_goal' then p_resolved_profile_snapshot -> 'farmer_goal' end,
    v_source_profile.field_sources_jsonb,
    v_source_profile.missing_fields,
    v_source_profile.completeness_notes,
    p_resolved_profile_snapshot
  );

  update public.farm_profiles set status = 'superseded' where id = v_source_profile.id;
  update public.assessment_sessions set active_profile_id = v_profile_id where id = p_assessment_session_id;

  for v_index in 1..array_length(v_provider_codes, 1) loop
    v_provider := v_provider_codes[v_index];
    v_evidence_key := v_evidence_keys[v_index];
    v_artifact := p_provider_artifacts -> v_provider::text;
    v_provenance := p_evidence_bundle_snapshot #> array['provenance', v_provider::text];
    v_evidence_value := p_evidence_bundle_snapshot #> array['location_evidence', v_evidence_key];

    if v_artifact is null or v_evidence_value is null or v_provenance is null then
      raise exception 'Missing persistence lineage for provider %.', v_provider;
    end if;

    v_provider_fetch_id := extensions.gen_random_uuid();
    insert into public.provider_fetches (
      id, farm_profile_id, attempt_kind, provider,
      request_parameters_jsonb, request_schema_version, sanitization_version,
      requested_variables, request_point, coordinate_tolerance_m,
      cache_key_material_jsonb, status, produced_evidence, result_mode,
      submitted_at, completed_at, fetched_at, response_metadata_jsonb,
      artifacts_jsonb
    ) values (
      v_provider_fetch_id,
      v_profile_id,
      'fallback_load',
      v_provider,
      jsonb_build_object('site_id', p_location_resolution ->> 'site_id'),
      p_evidence_bundle_snapshot ->> 'schema_version',
      '1.0.0',
      array[v_evidence_key],
      extensions.st_setsrid(extensions.st_makepoint(v_longitude, v_latitude), 4326)::extensions.geography,
      100,
      jsonb_build_object(
        'provider', v_provider,
        'site_id', p_location_resolution ->> 'site_id',
        'source_path', v_provenance ->> 'source_path',
        'bundle_id', p_evidence_bundle_snapshot ->> 'bundle_id'
      ),
      'succeeded',
      true,
      'fallback',
      v_now,
      v_now,
      v_now,
      v_provenance,
      jsonb_build_array(v_artifact)
    );

    v_evidence_record_id := extensions.gen_random_uuid();
    insert into public.evidence_records (
      id, farm_profile_id, provider_fetch_id, source_type, source_name,
      source_field, source_metadata_jsonb, canonical_variable, availability,
      freshness, value_kind, value_jsonb, fetched_at, evidence_point,
      coordinate_tolerance_m, quality_score, quality_flags, warnings,
      evidence_snapshot
    ) values (
      v_evidence_record_id,
      v_profile_id,
      v_provider_fetch_id,
      'provider',
      coalesce(v_provenance ->> 'provider', v_provider::text),
      v_evidence_key,
      v_provenance,
      'provider.' || v_provider::text,
      'available',
      case
        when v_provenance #>> '{freshness,status}' = 'fresh' then 'fresh'::public.evidence_freshness
        when v_provenance #>> '{freshness,status}' = 'stale' then 'stale'::public.evidence_freshness
        else 'unknown'::public.evidence_freshness
      end,
      'json',
      v_evidence_value,
      v_now,
      extensions.st_setsrid(extensions.st_makepoint(v_longitude, v_latitude), 4326)::extensions.geography,
      100,
      case when coalesce((v_provenance #>> '{freshness,passed}')::boolean, false) then 0.9 else 0.6 end,
      array['representative_site', 'cached_validated_artifact'],
      case
        when coalesce((v_provenance #>> '{freshness,passed}')::boolean, false) then '{}'::text[]
        else array['Provider artifact freshness was not confirmed.']
      end,
      jsonb_build_object(
        'provider', v_provider,
        'provenance', v_provenance,
        'value', v_evidence_value,
        'artifact', v_artifact
      )
    );
    v_evidence_record_ids := array_append(v_evidence_record_ids, v_evidence_record_id);
  end loop;

  insert into public.evidence_bundles (
    id, farm_profile_id, external_bundle_id, bundle_version, schema_version,
    status, catalog_version, catalog_source_path, contains_catalog_evidence,
    location_snapshot_jsonb, provider_coverage_jsonb, freshness_summary_jsonb,
    validation_summary_jsonb, completeness_percent, missing_required_variables,
    warnings, bundle_snapshot, assembled_at
  ) values (
    v_bundle_id,
    v_profile_id,
    v_external_bundle_id,
    1,
    p_evidence_bundle_snapshot ->> 'schema_version',
    'assembling',
    p_evidence_bundle_snapshot #>> '{catalog,version}',
    p_evidence_bundle_snapshot #>> '{catalog,source_path}',
    true,
    p_evidence_bundle_snapshot -> 'location',
    p_evidence_bundle_snapshot -> 'provenance',
    p_evidence_bundle_snapshot -> 'provenance',
    p_evidence_bundle_snapshot -> 'validation',
    100,
    '{}'::text[],
    array(select jsonb_array_elements_text(coalesce(p_location_resolution -> 'limitations', '[]'::jsonb))),
    p_evidence_bundle_snapshot,
    v_now
  );

  for v_index in 1..array_length(v_evidence_record_ids, 1) loop
    insert into public.evidence_bundle_records (
      evidence_bundle_id, evidence_record_id, inclusion_role, inclusion_order, inclusion_reason
    ) values (
      v_bundle_id, v_evidence_record_ids[v_index], 'required', v_index,
      'Normalized provider evidence used by the deterministic scoring engine.'
    );
  end loop;

  update public.evidence_bundles
  set status = 'validated', validated_at = v_now
  where id = v_bundle_id
  returning bundle_hash into v_bundle_hash;

  select input_hash into v_profile_hash from public.farm_profiles where id = v_profile_id;

  insert into public.recommendation_runs (
    id, external_run_id, assessment_session_id, farm_profile_id, evidence_bundle_id,
    run_kind, evaluation_mode, requested_crop_id, farm_profile_version,
    farm_profile_hash, evidence_bundle_hash, catalog_version, catalog_source_path,
    catalog_manifest_jsonb, engine_version, scoring_policy_version,
    scoring_policy_jsonb, engine_input_schema_version, engine_output_schema_version,
    engine_input_jsonb, status
  ) values (
    v_run_id,
    v_external_run_id,
    p_assessment_session_id,
    v_profile_id,
    v_bundle_id,
    'baseline',
    (p_engine_output ->> 'evaluation_mode')::public.evaluation_mode,
    nullif(p_engine_output ->> 'requested_crop_id', ''),
    v_source_profile.profile_version + 1,
    v_profile_hash,
    v_bundle_hash,
    p_evidence_bundle_snapshot #>> '{catalog,version}',
    p_evidence_bundle_snapshot #>> '{catalog,source_path}',
    p_evidence_bundle_snapshot -> 'catalog',
    p_engine_output ->> 'scoring_version',
    p_scoring_policy ->> 'scoring_version',
    p_scoring_policy,
    '1.0.0',
    p_engine_output ->> 'schema_version',
    jsonb_build_object(
      'farm_profile', p_resolved_profile_snapshot,
      'evidence_bundle', p_evidence_bundle_snapshot,
      'scoring_config', p_scoring_policy
    ),
    'pending'
  );

  update public.recommendation_runs
  set status = 'running', started_at = v_now
  where id = v_run_id;

  for v_rank in select value from jsonb_array_elements(p_engine_output -> 'rankings') loop
    insert into public.crop_score_results (
      recommendation_run_id, crop_id, crop_name, status, regionally_eligible,
      overall_rank, eligible_rank, suitability_score, recommendation,
      confidence_score, confidence_band, evidence_coverage_percent, factors_jsonb,
      applied_caps_jsonb, applied_gates_jsonb, key_strengths_jsonb,
      key_risks_jsonb, warnings, reason_codes, evidence_record_ids, result_snapshot
    ) values (
      v_run_id,
      v_rank ->> 'crop_id',
      v_rank ->> 'crop_name',
      (v_rank ->> 'status')::public.crop_result_status,
      (v_rank ->> 'regionally_eligible')::boolean,
      (v_rank ->> 'overall_rank')::smallint,
      nullif(v_rank ->> 'eligible_rank', '')::smallint,
      nullif(v_rank ->> 'suitability_score', '')::numeric,
      (v_rank ->> 'recommendation')::public.recommendation_class,
      nullif(v_rank ->> 'confidence_score', '')::numeric,
      nullif(v_rank ->> 'confidence_band', '')::public.confidence_band,
      nullif(v_rank ->> 'evidence_coverage_percent', '')::numeric,
      v_rank -> 'factors',
      coalesce(v_rank -> 'applied_caps', '[]'::jsonb),
      coalesce(v_rank -> 'applied_gates', '[]'::jsonb),
      coalesce(v_rank -> 'key_strengths', '[]'::jsonb),
      coalesce(v_rank -> 'key_risks', '[]'::jsonb),
      array(select jsonb_array_elements_text(coalesce(v_rank -> 'warnings', '[]'::jsonb))),
      array(
        select distinct code from (
          select gate ->> 'gate' as code
          from jsonb_array_elements(coalesce(v_rank -> 'applied_gates', '[]'::jsonb)) gate
          union all
          select risk ->> 'factor_id' as code
          from jsonb_array_elements(coalesce(v_rank -> 'key_risks', '[]'::jsonb)) risk
        ) reasons where code is not null
      ),
      v_evidence_record_ids,
      v_rank
    );
  end loop;

  update public.recommendation_runs
  set status = 'scored', scored_at = v_now, engine_output_jsonb = p_engine_output
  where id = v_run_id
  returning engine_input_hash, engine_output_hash into v_engine_input_hash, v_engine_output_hash;

  insert into public.validation_reports (
    recommendation_run_id, validator_version, report_schema_version, outcome,
    render_allowed, checked_engine_input_hash, checked_engine_output_hash,
    checked_evidence_bundle_hash, checks_jsonb, reconciliation_jsonb,
    grounding_jsonb, evidence_coverage_jsonb, errors, warnings,
    report_snapshot, validated_at
  ) values (
    v_run_id,
    p_validation_report ->> 'validator_version',
    p_validation_report ->> 'report_schema_version',
    'passed',
    true,
    v_engine_input_hash,
    v_engine_output_hash,
    v_bundle_hash,
    p_validation_report -> 'checks',
    p_validation_report -> 'engine_output_validation',
    p_validation_report -> 'evidence_bundle_validation',
    jsonb_build_object(
      'ranking_count', p_validation_report #> '{engine_output_validation,ranking_count}',
      'eligible_crop_count', p_validation_report #> '{engine_output_validation,eligible_crop_count}'
    ),
    '{}'::text[],
    array(select jsonb_array_elements_text(coalesce(p_validation_report -> 'warnings', '[]'::jsonb))),
    p_validation_report,
    v_now
  );

  update public.recommendation_runs
  set status = 'validated', validated_at = v_now
  where id = v_run_id;
  update public.recommendation_runs
  set status = 'completed', completed_at = v_now
  where id = v_run_id;

  for v_index in 1..array_length(v_provider_codes, 1) loop
    v_sequence := v_sequence + 1;
    insert into public.run_events (
      recommendation_run_id, sequence_number, event_kind, event_name, status,
      tool_name, evidence_bundle_id, cache_state, safe_summary,
      started_at, finished_at, occurred_at, event_snapshot
    ) values (
      v_run_id, v_sequence, 'provider', 'provider.' || v_provider_codes[v_index]::text || '.completed',
      'succeeded', v_provider_codes[v_index]::text, v_bundle_id, 'fallback',
      initcap(replace(v_provider_codes[v_index]::text, '_', ' ')) || ' evidence is ready.',
      v_now, v_now, v_now,
      jsonb_build_object('provider', v_provider_codes[v_index], 'status', 'succeeded', 'mode', 'fallback')
    );
  end loop;

  insert into public.run_events (
    recommendation_run_id, sequence_number, event_kind, event_name, status,
    evidence_bundle_id, safe_summary, started_at, finished_at, occurred_at, event_snapshot
  ) values
    (v_run_id, 5, 'evidence', 'evidence.bundle.completed', 'succeeded', v_bundle_id,
      'The validated location evidence bundle is ready.', v_now, v_now, v_now,
      jsonb_build_object('status', 'succeeded', 'bundle_id', v_bundle_id)),
    (v_run_id, 6, 'scoring', 'scoring.deterministic.completed', 'succeeded', v_bundle_id,
      'All 22 catalog crops were scored and ranked.', v_now, v_now, v_now,
      jsonb_build_object('status', 'succeeded', 'crop_count', 22)),
    (v_run_id, 7, 'validation', 'validation.results.completed', 'succeeded', v_bundle_id,
      'The ranking contract passed and results are authorized for display.', v_now, v_now, v_now,
      jsonb_build_object('status', 'succeeded', 'render_allowed', true)),
    (v_run_id, 8, 'system', 'system.analysis.completed', 'succeeded', v_bundle_id,
      'Farm evidence analysis is complete.', v_now, v_now, v_now,
      jsonb_build_object('status', 'completed', 'run_id', v_run_id));

  return query select v_run_id, v_profile_id, v_bundle_id, true;
end;
$$;

revoke all on function public.persist_recommendation_execution(
  uuid, jsonb, jsonb, jsonb, jsonb, jsonb, jsonb, jsonb
) from public, anon, authenticated;
grant execute on function public.persist_recommendation_execution(
  uuid, jsonb, jsonb, jsonb, jsonb, jsonb, jsonb, jsonb
) to service_role;

comment on function public.persist_recommendation_execution(
  uuid, jsonb, jsonb, jsonb, jsonb, jsonb, jsonb, jsonb
) is 'Atomically versions the scoring profile and persists provider lineage, evidence, all 22 crop scores, validation, and progress events.';
