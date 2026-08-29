begin;

set local search_path = public, extensions;

select plan(52);

select has_type('public', 'recommendation_run_kind', 'recommendation run kind enum exists');
select has_type('public', 'validation_outcome', 'validation outcome enum exists');
select has_table('public', 'recommendation_runs', 'recommendation runs table exists');
select has_table('public', 'crop_score_results', 'crop score results table exists');
select has_table('public', 'validation_reports', 'validation reports table exists');
select has_column('public', 'crop_score_results', 'regionally_eligible', 'crop results store regional eligibility');
select has_column('public', 'crop_score_results', 'overall_rank', 'crop results store an overall rank');
select has_column('public', 'crop_score_results', 'eligible_rank', 'crop results store a nullable eligible rank');
select has_column('public', 'recommendation_runs', 'engine_input_hash', 'runs hash the exact engine input');
select has_column('public', 'recommendation_runs', 'engine_output_hash', 'runs hash the exact engine output');
select has_column('public', 'validation_reports', 'render_allowed', 'validation explicitly controls rendering');

select is(
  (select public from storage.buckets where id = 'run-artifacts'),
  false,
  'run artifacts use a private Storage bucket'
);

select ok(
  public.run_artifacts_valid(
    '[{"bucket_name":"run-artifacts","object_path":"runs/demo/output.json","sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","content_type":"application/json","size_bytes":120,"schema_version":"1.0.0"}]'::jsonb
  ),
  'stable sanitized run artifact metadata is accepted'
);

select is(
  public.run_artifacts_valid(
    '[{"bucket_name":"run-artifacts","object_path":"runs/demo/output.json","sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","content_type":"application/json","size_bytes":120,"schema_version":"1.0.0","signed_url":"https://example.test/private"}]'::jsonb
  ),
  false,
  'temporary signed artifact URLs are rejected'
);

insert into public.evidence_records (
  id,
  farm_profile_id,
  source_type,
  source_name,
  canonical_variable,
  value_kind,
  value_boolean,
  evidence_point,
  evidence_snapshot
) values (
  '61000000-0000-4000-8000-000000000001',
  '00000000-0000-4000-8000-000000000101',
  'farmer',
  'Farm profile',
  'farm.irrigation_available',
  'boolean',
  true,
  extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
  '{"variable":"irrigation_available","value":true}'::jsonb
);

insert into public.evidence_bundles (
  id,
  farm_profile_id,
  external_bundle_id,
  bundle_version,
  schema_version,
  catalog_version,
  catalog_hash,
  catalog_source_path,
  location_snapshot_jsonb
) values (
  '62000000-0000-4000-8000-000000000001',
  '00000000-0000-4000-8000-000000000101',
  'scoring_test_bundle',
  1,
  '1.2.0',
  '1.1.0',
  repeat('b', 64),
  'data/crop-catalog/catalog.json',
  '{"latitude":34.18,"longitude":-101.76,"texas_region_id":"plains","timezone":"America/Chicago"}'::jsonb
);

insert into public.evidence_bundle_records (
  evidence_bundle_id,
  evidence_record_id,
  inclusion_role,
  inclusion_order
) values (
  '62000000-0000-4000-8000-000000000001',
  '61000000-0000-4000-8000-000000000001',
  'required',
  1
);

update public.evidence_bundles
set status = 'validated',
    completeness_percent = 100,
    assembled_at = statement_timestamp() - interval '1 second',
    validated_at = statement_timestamp(),
    validation_summary_jsonb = '{"all_passed":true}'::jsonb,
    bundle_snapshot = '{"schema_version":"1.2.0","bundle_id":"scoring_test_bundle","status":"validated","record_ids":["61000000-0000-4000-8000-000000000001"]}'::jsonb
where id = '62000000-0000-4000-8000-000000000001';

select lives_ok(
  $$
    insert into public.recommendation_runs (
      id,
      external_run_id,
      assessment_session_id,
      farm_profile_id,
      evidence_bundle_id,
      evaluation_mode,
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
      '63000000-0000-4000-8000-000000000001',
      'plainview_baseline_test',
      farm_profiles.assessment_session_id,
      farm_profiles.id,
      evidence_bundles.id,
      'planting_readiness',
      farm_profiles.profile_version,
      farm_profiles.input_hash,
      evidence_bundles.bundle_hash,
      '1.1.0',
      'data/crop-catalog/catalog.json',
      '{"version":"1.1.0","crop_count":22}'::jsonb,
      '1.0.0-provisional',
      'abcdef1',
      '1.0.0-provisional',
      '{"scoring_version":"1.0.0-provisional","ranking_policy":"eligibility_first"}'::jsonb,
      '1.0.0',
      '1.1.0',
      '{"schema_version":"1.0.0","profile_id":"plainview_aug_2026_demo","evidence_bundle_id":"scoring_test_bundle"}'::jsonb
    from public.farm_profiles
    join public.evidence_bundles
      on evidence_bundles.farm_profile_id = farm_profiles.id
    where farm_profiles.id = '00000000-0000-4000-8000-000000000101'
      and evidence_bundles.id = '62000000-0000-4000-8000-000000000001'
  $$,
  'a baseline run captures exact profile, evidence, catalog, policy, and engine contracts'
);

select is(
  (select engine_input_hash from public.recommendation_runs where id = '63000000-0000-4000-8000-000000000001'),
  (select public.jsonb_sha256(engine_input_jsonb) from public.recommendation_runs where id = '63000000-0000-4000-8000-000000000001'),
  'engine input hash is generated from the exact input document'
);

select is(
  (select catalog_hash from public.recommendation_runs where id = '63000000-0000-4000-8000-000000000001'),
  public.jsonb_sha256('{"version":"1.1.0","crop_count":22}'::jsonb),
  'catalog hash is generated from the exact catalog manifest'
);

select is(
  (select evidence_bundle_hash from public.recommendation_runs where id = '63000000-0000-4000-8000-000000000001'),
  (select bundle_hash from public.evidence_bundles where id = '62000000-0000-4000-8000-000000000001'),
  'run stores the exact validated evidence bundle hash'
);

select throws_ok(
  $$
    insert into public.recommendation_runs (
      external_run_id, assessment_session_id, farm_profile_id, evidence_bundle_id,
      evaluation_mode, farm_profile_version, farm_profile_hash, evidence_bundle_hash,
      catalog_version, catalog_source_path, catalog_manifest_jsonb, engine_version,
      scoring_policy_version, scoring_policy_jsonb, engine_input_schema_version,
      engine_output_schema_version, engine_input_jsonb, status, started_at
    )
    select
      'invalid_initial_state', farm_profiles.assessment_session_id, farm_profiles.id, evidence_bundles.id,
      'planning', farm_profiles.profile_version, farm_profiles.input_hash, evidence_bundles.bundle_hash,
      '1.1.0', 'catalog.json', '{"crop_count":22}', '1.0.0',
      '1.0.0', '{"policy":"test"}', '1.0.0', '1.0.0', '{"input":"test"}',
      'running', statement_timestamp()
    from public.farm_profiles
    join public.evidence_bundles on evidence_bundles.farm_profile_id = farm_profiles.id
    where farm_profiles.id = '00000000-0000-4000-8000-000000000101'
      and evidence_bundles.id = '62000000-0000-4000-8000-000000000001'
  $$,
  'Recommendation runs must be created in pending state.',
  'a run cannot skip its pending state'
);

select throws_ok(
  $$
    insert into public.recommendation_runs (
      external_run_id, assessment_session_id, farm_profile_id, evidence_bundle_id,
      evaluation_mode, farm_profile_version, farm_profile_hash, evidence_bundle_hash,
      catalog_version, catalog_source_path, catalog_manifest_jsonb, engine_version,
      scoring_policy_version, scoring_policy_jsonb, engine_input_schema_version,
      engine_output_schema_version, engine_input_jsonb
    )
    select
      'invalid_profile_hash', farm_profiles.assessment_session_id, farm_profiles.id, evidence_bundles.id,
      'planning', farm_profiles.profile_version, repeat('0', 64), evidence_bundles.bundle_hash,
      '1.1.0', 'catalog.json', '{"crop_count":22}', '1.0.0',
      '1.0.0', '{"policy":"test"}', '1.0.0', '1.0.0', '{"input":"test"}'
    from public.farm_profiles
    join public.evidence_bundles on evidence_bundles.farm_profile_id = farm_profiles.id
    where farm_profiles.id = '00000000-0000-4000-8000-000000000101'
      and evidence_bundles.id = '62000000-0000-4000-8000-000000000001'
  $$,
  'Recommendation run profile version and hash must match the referenced farm profile.',
  'a run cannot claim a different farm profile snapshot'
);

select throws_ok(
  $$
    insert into public.recommendation_runs (
      external_run_id, assessment_session_id, farm_profile_id, evidence_bundle_id,
      parent_run_id, run_kind, evaluation_mode, scenario_type, scenario_changes_jsonb,
      farm_profile_version, farm_profile_hash, evidence_bundle_hash, catalog_version,
      catalog_source_path, catalog_manifest_jsonb, engine_version, scoring_policy_version,
      scoring_policy_jsonb, engine_input_schema_version, engine_output_schema_version,
      engine_input_jsonb
    )
    select
      'scenario_before_parent_complete', farm_profiles.assessment_session_id, farm_profiles.id,
      evidence_bundles.id, '63000000-0000-4000-8000-000000000001', 'scenario', 'planning',
      'planting_month_change', '{"planned_planting_month":"2026-09"}',
      farm_profiles.profile_version, farm_profiles.input_hash, evidence_bundles.bundle_hash,
      '1.1.0', 'catalog.json', '{"crop_count":22}', '1.0.0', '1.0.0',
      '{"policy":"test"}', '1.0.0', '1.0.0', '{"input":"scenario"}'
    from public.farm_profiles
    join public.evidence_bundles on evidence_bundles.farm_profile_id = farm_profiles.id
    where farm_profiles.id = '00000000-0000-4000-8000-000000000101'
      and evidence_bundles.id = '62000000-0000-4000-8000-000000000001'
  $$,
  'A scenario run must reference a completed run in the same assessment session.',
  'a scenario cannot branch from an unfinished parent run'
);

select lives_ok(
  $$
    update public.recommendation_runs
    set status = 'running', started_at = statement_timestamp()
    where id = '63000000-0000-4000-8000-000000000001'
  $$,
  'a pending run can begin deterministic scoring'
);

select throws_ok(
  $$
    insert into public.crop_score_results (
      recommendation_run_id, crop_id, crop_name, status, regionally_eligible,
      overall_rank, eligible_rank, suitability_score, recommendation,
      confidence_score, confidence_band, evidence_coverage_percent, factors_jsonb,
      evidence_record_ids, result_snapshot
    ) values (
      '63000000-0000-4000-8000-000000000001', 'invalid_crop', 'Invalid crop', 'scored', false,
      1, null, 70, 'recommended', 80, 'high', 100, '[{"factor_id":"test"}]',
      array['61000000-0000-4000-8000-000000000001'::uuid], '{"crop_id":"invalid_crop"}'
    )
  $$,
  '23514',
  'new row for relation "crop_score_results" violates check constraint "crop_score_results_ineligible_policy"',
  'an ineligible crop cannot receive an uncapped favorable recommendation'
);

select throws_ok(
  $$
    insert into public.crop_score_results (
      recommendation_run_id, crop_id, crop_name, status, regionally_eligible,
      overall_rank, eligible_rank, suitability_score, recommendation,
      confidence_score, confidence_band, evidence_coverage_percent, factors_jsonb,
      evidence_record_ids, result_snapshot
    ) values (
      '63000000-0000-4000-8000-000000000001', 'missing_region_gate',
      'Missing region gate', 'scored', false, 1, null, 54, 'not_recommended',
      80, 'high', 100, '[{"factor_id":"test"}]',
      array['61000000-0000-4000-8000-000000000001'::uuid],
      '{"crop_id":"missing_region_gate","regionally_eligible":false,"overall_rank":1,"eligible_rank":null,"applied_gates":[]}'
    )
  $$,
  '23514',
  'new row for relation "crop_score_results" violates check constraint "crop_score_results_ineligible_policy"',
  'an ineligible crop cannot omit the unsupported_region gate'
);

select lives_ok(
  $$
    insert into public.crop_score_results (
      recommendation_run_id, crop_id, crop_name, status, regionally_eligible,
      overall_rank, eligible_rank, suitability_score, recommendation,
      confidence_score, confidence_band, evidence_coverage_percent, factors_jsonb,
      applied_caps_jsonb, applied_gates_jsonb, key_strengths_jsonb, key_risks_jsonb,
      warnings, reason_codes, evidence_record_ids, result_snapshot
    )
    select
      '63000000-0000-4000-8000-000000000001',
      'crop_' || lpad(n::text, 2, '0'),
      'Test crop ' || n,
      'scored',
      n <= 18,
      n,
      case when n <= 18 then n else null end,
      case when n <= 18 then 90 - n else 73 - n end,
      case when n <= 18 then 'recommended' else 'not_recommended' end::public.recommendation_class,
      85 - n,
      case when n <= 5 then 'high' when n <= 15 then 'medium' else 'low' end::public.confidence_band,
      100,
      jsonb_build_array(jsonb_build_object('factor_id', 'deterministic_test', 'score', 90 - n)),
      case
        when n <= 18 then '[]'::jsonb
        else '[{"gate":"unsupported_region","cap":54,"reason":"Catalog marks this crop unsupported in the selected Texas region."}]'::jsonb
      end,
      case
        when n <= 18 then '[]'::jsonb
        else '[{"gate":"unsupported_region","cap":54,"reason":"Catalog marks this crop unsupported in the selected Texas region."}]'::jsonb
      end,
      '[]'::jsonb,
      '[]'::jsonb,
      '{}'::text[],
      array['TEST_RESULT'],
      array['61000000-0000-4000-8000-000000000001'::uuid],
      jsonb_build_object(
        'crop_id', 'crop_' || lpad(n::text, 2, '0'),
        'regionally_eligible', n <= 18,
        'overall_rank', n,
        'eligible_rank', case when n <= 18 then n else null end,
        'applied_gates', case
          when n <= 18 then '[]'::jsonb
          else '[{"gate":"unsupported_region","cap":54,"reason":"Catalog marks this crop unsupported in the selected Texas region."}]'::jsonb
        end
      )
    from generate_series(1, 22) as series(n)
  $$,
  'all 22 crop results can be persisted before run finalization'
);

select is(
  (select count(*) from public.crop_score_results where recommendation_run_id = '63000000-0000-4000-8000-000000000001'),
  22::bigint,
  'the run persists exactly 22 crop rows'
);

select is(
  (select count(*) from public.crop_score_results where recommendation_run_id = '63000000-0000-4000-8000-000000000001' and regionally_eligible),
  18::bigint,
  'regional eligibility remains independent from score and confidence'
);

select is(
  (select count(*) from public.crop_score_results where recommendation_run_id = '63000000-0000-4000-8000-000000000001' and not regionally_eligible and eligible_rank is null),
  4::bigint,
  'ineligible crops retain overall rank and no eligible rank'
);

select is(
  (
    select count(*)
    from public.crop_score_results
    where recommendation_run_id = '63000000-0000-4000-8000-000000000001'
      and not regionally_eligible
      and public.applied_gates_include(applied_gates_jsonb, 'unsupported_region')
  ),
  4::bigint,
  'every regionally ineligible crop retains the unsupported_region gate'
);

select is(
  (
    select count(*)
    from public.crop_score_results
    where recommendation_run_id = '63000000-0000-4000-8000-000000000001'
      and result_snapshot ?& array[
        'crop_id',
        'regionally_eligible',
        'overall_rank',
        'eligible_rank',
        'applied_gates'
      ]
  ),
  22::bigint,
  'result snapshots use the eligibility-aware ranking contract'
);

select lives_ok(
  $$
    update public.recommendation_runs
    set status = 'scored',
        scored_at = statement_timestamp(),
        engine_output_jsonb = '{"schema_version":"1.1.0","status":"scored","ranking_policy":"eligibility_first","ranking_count":22}'::jsonb,
        artifacts_jsonb = '[{"bucket_name":"run-artifacts","object_path":"runs/plainview_baseline_test/output.json","sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","content_type":"application/json","size_bytes":1024,"schema_version":"1.1.0"}]'::jsonb
    where id = '63000000-0000-4000-8000-000000000001'
  $$,
  'a correctly ordered 22-crop result set can finalize as scored'
);

select is(
  (select engine_output_hash from public.recommendation_runs where id = '63000000-0000-4000-8000-000000000001'),
  (select public.jsonb_sha256(engine_output_jsonb) from public.recommendation_runs where id = '63000000-0000-4000-8000-000000000001'),
  'engine output hash is generated from the exact output document'
);

select throws_ok(
  $$
    update public.crop_score_results
    set suitability_score = suitability_score - 1
    where recommendation_run_id = '63000000-0000-4000-8000-000000000001'
      and overall_rank = 1
  $$,
  'Crop score results may only be written while the recommendation run is running.',
  'crop results are immutable after scoring finalizes'
);

select throws_ok(
  $$
    insert into public.validation_reports (
      recommendation_run_id, validator_version, report_schema_version, outcome,
      render_allowed, checked_engine_input_hash, checked_engine_output_hash,
      checked_evidence_bundle_hash, checks_jsonb, report_snapshot, validated_at
    )
    select
      id, '1.0.0', '1.0.0', 'passed', true, repeat('0', 64), engine_output_hash,
      evidence_bundle_hash, '[{"name":"schema","passed":true}]',
      '{"status":"passed","render_allowed":true}', statement_timestamp()
    from public.recommendation_runs
    where id = '63000000-0000-4000-8000-000000000001'
  $$,
  'Validation report hashes must match the exact run input, output, and evidence bundle.',
  'a validator cannot authorize a different engine input'
);

select lives_ok(
  $$
    insert into public.validation_reports (
      id, recommendation_run_id, validator_version, report_schema_version, outcome,
      render_allowed, checked_engine_input_hash, checked_engine_output_hash,
      checked_evidence_bundle_hash, checks_jsonb, reconciliation_jsonb,
      grounding_jsonb, evidence_coverage_jsonb, report_snapshot, validated_at
    )
    select
      '64000000-0000-4000-8000-000000000001', id, '1.0.0', '1.0.0', 'passed', true,
      engine_input_hash, engine_output_hash, evidence_bundle_hash,
      '[{"name":"schema","passed":true},{"name":"ranking","passed":true}]',
      '{"crop_count":22,"rank_sequence_valid":true}',
      '{"evidence_links_valid":true}',
      '{"coverage_percent":100}',
      '{"report_version":"1.0.0","status":"passed","render_allowed":true}',
      statement_timestamp()
    from public.recommendation_runs
    where id = '63000000-0000-4000-8000-000000000001'
  $$,
  'a matching validator report can authorize rendering'
);

select lives_ok(
  $$
    update public.recommendation_runs
    set status = 'validated', validated_at = statement_timestamp()
    where id = '63000000-0000-4000-8000-000000000001'
  $$,
  'a passed render-authorizing report can validate the run'
);

select lives_ok(
  $$
    update public.recommendation_runs
    set status = 'completed', completed_at = statement_timestamp()
    where id = '63000000-0000-4000-8000-000000000001'
  $$,
  'a validated run can complete'
);

select throws_ok(
  $$
    update public.recommendation_runs
    set error_message = 'late mutation'
    where id = '63000000-0000-4000-8000-000000000001'
  $$,
  'Completed or failed recommendation runs are immutable.',
  'completed runs cannot be rewritten'
);

select throws_ok(
  $$
    update public.validation_reports
    set warnings = array['changed']
    where id = '64000000-0000-4000-8000-000000000001'
  $$,
  'Validation reports are immutable; create a new recommendation run for corrections.',
  'validation reports cannot be rewritten'
);

select lives_ok(
  $$
    insert into public.recommendation_runs (
      id, external_run_id, assessment_session_id, farm_profile_id, evidence_bundle_id,
      parent_run_id, run_kind, evaluation_mode, scenario_type, scenario_changes_jsonb,
      scenario_assumptions, farm_profile_version, farm_profile_hash, evidence_bundle_hash,
      catalog_version, catalog_source_path, catalog_manifest_jsonb, engine_version,
      scoring_policy_version, scoring_policy_jsonb, engine_input_schema_version,
      engine_output_schema_version, engine_input_jsonb
    )
    select
      '63000000-0000-4000-8000-000000000002', 'plainview_scenario_test',
      farm_profiles.assessment_session_id, farm_profiles.id, evidence_bundles.id,
      '63000000-0000-4000-8000-000000000001', 'scenario', 'planning',
      'planting_month_change', '{"planned_planting_month":"2026-09"}',
      array['All evidence except planting month is held constant.'],
      farm_profiles.profile_version, farm_profiles.input_hash, evidence_bundles.bundle_hash,
      '1.1.0', 'data/crop-catalog/catalog.json', '{"version":"1.1.0","crop_count":22}',
      '1.0.0-provisional', '1.0.0-provisional', '{"ranking_policy":"eligibility_first"}',
      '1.0.0', '1.1.0', '{"scenario_type":"planting_month_change"}'
    from public.farm_profiles
    join public.evidence_bundles on evidence_bundles.farm_profile_id = farm_profiles.id
    where farm_profiles.id = '00000000-0000-4000-8000-000000000101'
      and evidence_bundles.id = '62000000-0000-4000-8000-000000000001'
  $$,
  'a scenario can branch from a completed run without a separate scenario table'
);

select is(
  (select parent_run_id from public.recommendation_runs where id = '63000000-0000-4000-8000-000000000002'),
  '63000000-0000-4000-8000-000000000001'::uuid,
  'scenario ancestry is explicit and queryable'
);

select lives_ok(
  $$
    insert into public.recommendation_runs (
      id, external_run_id, assessment_session_id, farm_profile_id, evidence_bundle_id,
      evaluation_mode, farm_profile_version, farm_profile_hash, evidence_bundle_hash,
      catalog_version, catalog_source_path, catalog_manifest_jsonb, engine_version,
      scoring_policy_version, scoring_policy_jsonb, engine_input_schema_version,
      engine_output_schema_version, engine_input_jsonb
    )
    select
      '63000000-0000-4000-8000-000000000003', 'short_result_test',
      farm_profiles.assessment_session_id, farm_profiles.id, evidence_bundles.id,
      'planning', farm_profiles.profile_version, farm_profiles.input_hash, evidence_bundles.bundle_hash,
      '1.1.0', 'catalog.json', '{"crop_count":22}', '1.0.0', '1.0.0',
      '{"ranking_policy":"eligibility_first"}', '1.0.0', '1.0.0', '{"test":"short"}'
    from public.farm_profiles
    join public.evidence_bundles on evidence_bundles.farm_profile_id = farm_profiles.id
    where farm_profiles.id = '00000000-0000-4000-8000-000000000101'
      and evidence_bundles.id = '62000000-0000-4000-8000-000000000001'
  $$,
  'a second baseline run can be prepared for count validation'
);

select lives_ok(
  $$update public.recommendation_runs set status = 'running', started_at = statement_timestamp() where id = '63000000-0000-4000-8000-000000000003'$$,
  'the count-validation run can start'
);

select lives_ok(
  $$
    insert into public.crop_score_results (
      recommendation_run_id, crop_id, crop_name, status, regionally_eligible,
      overall_rank, eligible_rank, suitability_score, recommendation, confidence_score,
      confidence_band, evidence_coverage_percent, factors_jsonb, evidence_record_ids,
      result_snapshot
    )
    select
      '63000000-0000-4000-8000-000000000003', 'short_' || lpad(n::text, 2, '0'),
      'Short crop ' || n, 'scored', true, n, n, 90 - n, 'recommended', 80 - n,
      'medium', 100, '[{"factor_id":"test"}]',
      array['61000000-0000-4000-8000-000000000001'::uuid],
      jsonb_build_object('crop_id', 'short_' || lpad(n::text, 2, '0'))
    from generate_series(1, 21) as series(n)
  $$,
  'an incomplete running result set can be staged before finalization'
);

select throws_ok(
  $$
    update public.recommendation_runs
    set status = 'scored', scored_at = statement_timestamp(), engine_output_jsonb = '{"ranking_count":21}'
    where id = '63000000-0000-4000-8000-000000000003'
  $$,
  'A scored recommendation run must contain exactly 22 crop results.',
  'a run with only 21 crop results cannot finalize'
);

select lives_ok(
  $$
    insert into public.recommendation_runs (
      id, external_run_id, assessment_session_id, farm_profile_id, evidence_bundle_id,
      evaluation_mode, farm_profile_version, farm_profile_hash, evidence_bundle_hash,
      catalog_version, catalog_source_path, catalog_manifest_jsonb, engine_version,
      scoring_policy_version, scoring_policy_jsonb, engine_input_schema_version,
      engine_output_schema_version, engine_input_jsonb
    )
    select
      '63000000-0000-4000-8000-000000000004', 'wrong_order_test',
      farm_profiles.assessment_session_id, farm_profiles.id, evidence_bundles.id,
      'planning', farm_profiles.profile_version, farm_profiles.input_hash, evidence_bundles.bundle_hash,
      '1.1.0', 'catalog.json', '{"crop_count":22}', '1.0.0', '1.0.0',
      '{"ranking_policy":"eligibility_first"}', '1.0.0', '1.0.0', '{"test":"wrong_order"}'
    from public.farm_profiles
    join public.evidence_bundles on evidence_bundles.farm_profile_id = farm_profiles.id
    where farm_profiles.id = '00000000-0000-4000-8000-000000000101'
      and evidence_bundles.id = '62000000-0000-4000-8000-000000000001'
  $$,
  'a third baseline run can be prepared for ordering validation'
);

select lives_ok(
  $$update public.recommendation_runs set status = 'running', started_at = statement_timestamp() where id = '63000000-0000-4000-8000-000000000004'$$,
  'the ordering-validation run can start'
);

select lives_ok(
  $$
    insert into public.crop_score_results (
      recommendation_run_id, crop_id, crop_name, status, regionally_eligible,
      overall_rank, eligible_rank, suitability_score, recommendation, confidence_score,
      confidence_band, evidence_coverage_percent, factors_jsonb, evidence_record_ids,
      result_snapshot
    )
    select
      '63000000-0000-4000-8000-000000000004', 'order_' || lpad(n::text, 2, '0'),
      'Order crop ' || n, 'scored', true, n, n, 20 + n, 'conditional', 60,
      'medium', 100, '[{"factor_id":"test"}]',
      array['61000000-0000-4000-8000-000000000001'::uuid],
      jsonb_build_object('crop_id', 'order_' || lpad(n::text, 2, '0'))
    from generate_series(1, 22) as series(n)
  $$,
  'a deliberately misordered 22-row result set can be staged'
);

select throws_ok(
  $$
    update public.recommendation_runs
    set status = 'scored', scored_at = statement_timestamp(), engine_output_jsonb = '{"ranking_count":22}'
    where id = '63000000-0000-4000-8000-000000000004'
  $$,
  'Crop overall ranks do not match the eligibility-first deterministic ordering policy.',
  'a complete but incorrectly ordered result set cannot finalize'
);

insert into auth.users (id, aud, role, email, created_at, updated_at)
values
  ('65000000-0000-4000-8000-000000000001', 'authenticated', 'authenticated', 'run-owner@example.test', statement_timestamp(), statement_timestamp()),
  ('65000000-0000-4000-8000-000000000002', 'authenticated', 'authenticated', 'run-outsider@example.test', statement_timestamp(), statement_timestamp());

update public.assessment_sessions
set owner_user_id = '65000000-0000-4000-8000-000000000001'
where id = '00000000-0000-4000-8000-000000000001';

do $$
begin
  perform set_config('request.jwt.claim.sub', '65000000-0000-4000-8000-000000000002', true);
  perform set_config(
    'request.jwt.claims',
    '{"sub":"65000000-0000-4000-8000-000000000002","role":"authenticated"}',
    true
  );
end;
$$;
set local role authenticated;

select is((select count(*) from public.recommendation_runs), 0::bigint, 'RLS hides another user''s recommendation runs');
select is((select count(*) from public.crop_score_results), 0::bigint, 'RLS hides another user''s crop results');
select is((select count(*) from public.validation_reports), 0::bigint, 'RLS hides another user''s validation reports');

reset role;

select * from finish();

rollback;
