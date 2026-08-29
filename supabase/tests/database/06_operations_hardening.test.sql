begin;

set local search_path = public, extensions;

select plan(40);

select has_type('public', 'run_event_kind', 'run event kind enum exists');
select has_type('public', 'run_event_status', 'run event status enum exists');
select has_table('public', 'run_events', 'run events table exists');
select has_column('public', 'run_events', 'sequence_number', 'run events have deterministic sequence numbers');
select has_column('public', 'run_events', 'arguments_summary_jsonb', 'run events retain sanitized argument summaries');
select has_column('public', 'run_events', 'safe_summary', 'run events retain user-safe summaries');
select has_column('public', 'run_events', 'event_hash', 'run event snapshots receive deterministic hashes');
select hasnt_table('public', 'chat_messages', 'chat remains transient application state for the MVP');

select is(
  (
    select count(*)
    from pg_catalog.pg_class
    join pg_catalog.pg_namespace on pg_namespace.oid = pg_class.relnamespace
    where pg_namespace.nspname = 'public'
      and pg_class.relkind = 'r'
      and pg_class.relname = any (array[
        'assessment_sessions',
        'farm_profiles',
        'provider_fetches',
        'evidence_records',
        'evidence_bundles',
        'evidence_bundle_records',
        'recommendation_runs',
        'crop_score_results',
        'validation_reports',
        'run_events'
      ])
  ),
  10::bigint,
  'the finalized application persistence boundary contains ten tables'
);

select is(
  (
    select count(*)
    from pg_catalog.pg_class
    join pg_catalog.pg_namespace on pg_namespace.oid = pg_class.relnamespace
    where pg_namespace.nspname = 'public'
      and pg_class.relname = any (array[
        'assessment_sessions',
        'farm_profiles',
        'provider_fetches',
        'evidence_records',
        'evidence_bundles',
        'evidence_bundle_records',
        'recommendation_runs',
        'crop_score_results',
        'validation_reports',
        'run_events'
      ])
      and pg_class.relrowsecurity
  ),
  10::bigint,
  'RLS is enabled on all ten application tables'
);

select ok(
  not exists (
    select 1
    from unnest(array[
      'assessment_sessions', 'farm_profiles', 'provider_fetches', 'evidence_records',
      'evidence_bundles', 'evidence_bundle_records', 'recommendation_runs',
      'crop_score_results', 'validation_reports', 'run_events'
    ]) as tables(table_name)
    cross join unnest(array['INSERT', 'UPDATE', 'DELETE']) as privileges(privilege_name)
    where has_table_privilege('anon', 'public.' || table_name, privilege_name)
  ),
  'anonymous browser clients have no direct application-table writes'
);

select ok(
  not exists (
    select 1
    from unnest(array[
      'assessment_sessions', 'farm_profiles', 'provider_fetches', 'evidence_records',
      'evidence_bundles', 'evidence_bundle_records', 'recommendation_runs',
      'crop_score_results', 'validation_reports', 'run_events'
    ]) as tables(table_name)
    cross join unnest(array['INSERT', 'UPDATE', 'DELETE']) as privileges(privilege_name)
    where has_table_privilege('authenticated', 'public.' || table_name, privilege_name)
  ),
  'authenticated browser clients have no direct application-table writes'
);

set local role anon;

select throws_ok(
  $$insert into storage.objects (bucket_id, name) values ('run-artifacts', 'forbidden/test.json')$$,
  '42501',
  'new row violates row-level security policy for table "objects"',
  'anonymous browser writes to the private artifact bucket are blocked by RLS'
);

reset role;

select is(
  (select count(*) from storage.buckets where id in ('provider-artifacts', 'run-artifacts') and not public),
  2::bigint,
  'provider and run artifact buckets are both private'
);

select is(
  (
    select count(*)
    from pg_catalog.pg_policies
    where schemaname = 'storage'
      and tablename in ('objects', 'buckets')
      and roles && array['anon', 'authenticated']::name[]
  ),
  0::bigint,
  'no browser Storage policy bypasses the server-only artifact boundary'
);

select is(
  public.jsonb_contains_sensitive_keys('{"hidden_reasoning":"do not persist"}'::jsonb),
  true,
  'hidden reasoning keys are rejected by shared JSON safety checks'
);

select is(
  public.jsonb_contains_sensitive_keys('{"reason_code":"SOIL_PH_OUTSIDE_RANGE"}'::jsonb),
  false,
  'ordinary deterministic reason codes remain valid metadata'
);

select has_index('public', 'run_events', 'run_events_run_occurred_idx', 'run events have a run/time retrieval index');
select has_index('public', 'run_events', 'run_events_provider_fetch_idx', 'run events have a provider-fetch index');
select has_index('public', 'run_events', 'run_events_evidence_bundle_idx', 'run events have an evidence-bundle index');
select has_index('public', 'recommendation_runs', 'recommendation_runs_evidence_bundle_idx', 'recommendation runs have an evidence-bundle foreign-key index');

select throws_ok(
  $$
    update public.farm_profiles
    set farm_name = 'Changed after ready'
    where id = '00000000-0000-4000-8000-000000000101'
  $$,
  'Ready farm profiles are immutable; create a successor profile version.',
  'ready farm profiles cannot be edited in place'
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
  '71000000-0000-4000-8000-000000000001',
  '00000000-0000-4000-8000-000000000101',
  'farmer',
  'Farm profile',
  'farm.irrigation_available',
  'boolean',
  true,
  extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
  '{"variable":"irrigation_available","value":true}'::jsonb
);

select throws_ok(
  $$
    update public.evidence_records
    set warnings = array['late correction']
    where id = '71000000-0000-4000-8000-000000000001'
  $$,
  'Evidence records are append-only; create a new record for corrections.',
  'normalized evidence cannot be rewritten'
);

select throws_ok(
  $$delete from public.evidence_records where id = '71000000-0000-4000-8000-000000000001'$$,
  'Evidence records are append-only; create a new record for corrections.',
  'normalized evidence cannot be deleted'
);

insert into public.evidence_bundles (
  id,
  farm_profile_id,
  external_bundle_id,
  bundle_version,
  schema_version,
  catalog_version,
  catalog_source_path,
  location_snapshot_jsonb
) values (
  '72000000-0000-4000-8000-000000000001',
  '00000000-0000-4000-8000-000000000101',
  'operations_test_bundle',
  1,
  '1.2.0',
  '1.1.0',
  'data/crop-catalog/catalog.json',
  '{"latitude":34.18,"longitude":-101.76,"texas_region_id":"plains"}'::jsonb
);

insert into public.evidence_bundle_records (
  evidence_bundle_id,
  evidence_record_id,
  inclusion_role,
  inclusion_order
) values (
  '72000000-0000-4000-8000-000000000001',
  '71000000-0000-4000-8000-000000000001',
  'required',
  1
);

update public.evidence_bundles
set status = 'validated',
    completeness_percent = 100,
    assembled_at = statement_timestamp() - interval '1 second',
    validated_at = statement_timestamp(),
    bundle_snapshot = '{"schema_version":"1.2.0","bundle_id":"operations_test_bundle","status":"validated","record_ids":["71000000-0000-4000-8000-000000000001"]}'::jsonb
where id = '72000000-0000-4000-8000-000000000001';

select throws_ok(
  $$
    update public.evidence_bundles
    set warnings = array['late change']
    where id = '72000000-0000-4000-8000-000000000001'
  $$,
  'Validated or failed evidence bundles are immutable.',
  'validated evidence bundles cannot be rewritten'
);

insert into public.provider_fetches (
  id,
  farm_profile_id,
  provider,
  endpoint,
  http_method,
  request_schema_version,
  sanitization_version,
  requested_variables,
  request_point,
  cache_key_material_jsonb,
  status,
  completed_at,
  error_code,
  error_message
) values (
  '74000000-0000-4000-8000-000000000001',
  '00000000-0000-4000-8000-000000000101',
  'open_meteo',
  'https://api.open-meteo.com/v1/forecast',
  'GET',
  '1.0.0',
  '1.0.0',
  array['temperature_2m'],
  extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
  '{"provider":"open_meteo","point":{"latitude":34.18,"longitude":-101.76},"variables":["temperature_2m"]}'::jsonb,
  'failed',
  statement_timestamp(),
  'UPSTREAM_TIMEOUT',
  'Provider request timed out.'
);

select throws_ok(
  $$
    update public.provider_fetches
    set error_message = 'Changed after failure.'
    where id = '74000000-0000-4000-8000-000000000001'
  $$,
  'Succeeded or failed provider fetches are immutable.',
  'terminal provider attempts cannot be rewritten'
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
      '73000000-0000-4000-8000-000000000001', 'operations_event_test',
      farm_profiles.assessment_session_id, farm_profiles.id, evidence_bundles.id,
      'planning', farm_profiles.profile_version, farm_profiles.input_hash, evidence_bundles.bundle_hash,
      '1.1.0', 'data/crop-catalog/catalog.json', '{"version":"1.1.0","crop_count":22}',
      '1.0.0-provisional', '1.0.0-provisional', '{"ranking_policy":"eligibility_first"}',
      '1.0.0', '1.1.0', '{"profile_id":"plainview_aug_2026_demo","mode":"planning"}'
    from public.farm_profiles
    join public.evidence_bundles on evidence_bundles.farm_profile_id = farm_profiles.id
    where farm_profiles.id = '00000000-0000-4000-8000-000000000101'
      and evidence_bundles.id = '72000000-0000-4000-8000-000000000001'
  $$,
  'a recommendation run can be prepared for append-only event tracing'
);

select lives_ok(
  $$
    insert into public.run_events (
      id, recommendation_run_id, sequence_number, event_kind, event_name, status,
      evidence_bundle_id, arguments_summary_jsonb, safe_summary, event_snapshot
    ) values (
      '75000000-0000-4000-8000-000000000001',
      '73000000-0000-4000-8000-000000000001',
      1,
      'evidence',
      'evidence.bundle.ready',
      'info',
      '72000000-0000-4000-8000-000000000001',
      '{"bundle_status":"validated"}',
      'Location evidence is ready for scoring.',
      '{"sequence":1,"event":"evidence.bundle.ready","status":"info"}'
    )
  $$,
  'a user-safe informational run event can be stored'
);

select is(
  (select event_hash from public.run_events where id = '75000000-0000-4000-8000-000000000001'),
  public.jsonb_sha256('{"sequence":1,"event":"evidence.bundle.ready","status":"info"}'::jsonb),
  'run event hash is generated from the exact event snapshot'
);

select throws_ok(
  $$
    insert into public.run_events (
      recommendation_run_id, sequence_number, event_kind, event_name, status,
      arguments_summary_jsonb, safe_summary, event_snapshot
    ) values (
      '73000000-0000-4000-8000-000000000001', 3, 'system', 'system.out_of_order', 'info',
      '{}', 'This event is deliberately out of order.', '{"sequence":3}'
    )
  $$,
  'Run event sequence must be the next contiguous number: expected 2.',
  'run event sequences cannot contain gaps'
);

select throws_ok(
  $$
    insert into public.run_events (
      recommendation_run_id, sequence_number, event_kind, event_name, status,
      arguments_summary_jsonb, safe_summary, event_snapshot
    ) values (
      '73000000-0000-4000-8000-000000000001', 2, 'system', 'system.unsafe', 'info',
      '{"chain_of_thought":"private"}', 'Unsafe event.', '{"sequence":2}'
    )
  $$,
  '23514',
  'new row for relation "run_events" violates check constraint "run_events_arguments_safe"',
  'run events reject hidden reasoning in argument summaries'
);

select lives_ok(
  $$
    insert into public.run_events (
      id, recommendation_run_id, sequence_number, event_kind, event_name, status,
      tool_name, arguments_summary_jsonb, safe_summary, started_at, occurred_at,
      event_snapshot
    ) values (
      '75000000-0000-4000-8000-000000000002',
      '73000000-0000-4000-8000-000000000001',
      2,
      'scoring',
      'scoring.engine.started',
      'started',
      'deterministic_scorer',
      '{"crop_count":22,"evaluation_mode":"planning"}',
      'Crop suitability scoring has started.',
      statement_timestamp(),
      statement_timestamp(),
      '{"sequence":2,"event":"scoring.engine.started","status":"started"}'
    )
  $$,
  'a started progress event records safe tool and timing metadata'
);

select lives_ok(
  $$
    insert into public.run_events (
      id, recommendation_run_id, sequence_number, event_kind, event_name, status,
      tool_name, arguments_summary_jsonb, safe_summary, started_at, finished_at,
      occurred_at, event_snapshot
    ) values (
      '75000000-0000-4000-8000-000000000003',
      '73000000-0000-4000-8000-000000000001',
      3,
      'scoring',
      'scoring.engine.succeeded',
      'succeeded',
      'deterministic_scorer',
      '{"crop_count":22}',
      'Crop suitability scoring completed.',
      statement_timestamp() - interval '1 second',
      statement_timestamp(),
      statement_timestamp(),
      '{"sequence":3,"event":"scoring.engine.succeeded","status":"succeeded"}'
    )
  $$,
  'a completed event records bounded start and finish times'
);

select lives_ok(
  $$
    insert into public.run_events (
      id, recommendation_run_id, sequence_number, event_kind, event_name, status,
      provider_fetch_id, arguments_summary_jsonb, safe_summary, event_snapshot
    ) values (
      '75000000-0000-4000-8000-000000000004',
      '73000000-0000-4000-8000-000000000001',
      4,
      'provider',
      'provider.open_meteo.failed',
      'info',
      '74000000-0000-4000-8000-000000000001',
      '{"provider":"open_meteo","result":"failed"}',
      'A provider attempt failed and remains available for audit.',
      '{"sequence":4,"event":"provider.open_meteo.failed","status":"info"}'
    )
  $$,
  'an event may reference a same-profile provider attempt'
);

select is(
  (
    select array_agg(sequence_number order by sequence_number)
    from public.run_events
    where recommendation_run_id = '73000000-0000-4000-8000-000000000001'
  ),
  array[1, 2, 3, 4],
  'stored run event order is contiguous and deterministic'
);

insert into public.evidence_bundles (
  id, farm_profile_id, external_bundle_id, bundle_version, supersedes_bundle_id,
  schema_version, catalog_version, location_snapshot_jsonb
) values (
  '72000000-0000-4000-8000-000000000002',
  '00000000-0000-4000-8000-000000000101',
  'operations_test_bundle_v2',
  2,
  '72000000-0000-4000-8000-000000000001',
  '1.2.0',
  '1.1.0',
  '{"latitude":34.18,"longitude":-101.76}'
);

select throws_ok(
  $$
    insert into public.run_events (
      recommendation_run_id, sequence_number, event_kind, event_name, status,
      evidence_bundle_id, safe_summary, event_snapshot
    ) values (
      '73000000-0000-4000-8000-000000000001', 5, 'evidence', 'evidence.bundle.mismatch', 'info',
      '72000000-0000-4000-8000-000000000002', 'Mismatched bundle.', '{"sequence":5}'
    )
  $$,
  'Run event evidence bundle must match the recommendation run bundle.',
  'run events cannot cite a different evidence bundle'
);

select throws_ok(
  $$
    insert into public.run_events (
      recommendation_run_id, sequence_number, event_kind, event_name, status,
      safe_summary, started_at, finished_at, event_snapshot
    ) values (
      '73000000-0000-4000-8000-000000000001', 5, 'system', 'system.failed', 'failed',
      'Failure without safe error metadata.', statement_timestamp(), statement_timestamp(), '{"sequence":5}'
    )
  $$,
  '23514',
  'new row for relation "run_events" violates check constraint "run_events_status_shape"',
  'failed run events require safe error code and message fields'
);

select throws_ok(
  $$
    update public.run_events
    set safe_summary = 'Changed later.'
    where id = '75000000-0000-4000-8000-000000000001'
  $$,
  'Run events are append-only and cannot be updated or deleted.',
  'stored run events cannot be rewritten'
);

select throws_ok(
  $$delete from public.run_events where id = '75000000-0000-4000-8000-000000000001'$$,
  'Run events are append-only and cannot be updated or deleted.',
  'stored run events cannot be deleted'
);

insert into auth.users (id, aud, role, email, created_at, updated_at)
values
  ('76000000-0000-4000-8000-000000000001', 'authenticated', 'authenticated', 'event-owner@example.test', statement_timestamp(), statement_timestamp()),
  ('76000000-0000-4000-8000-000000000002', 'authenticated', 'authenticated', 'event-outsider@example.test', statement_timestamp(), statement_timestamp());

update public.assessment_sessions
set owner_user_id = '76000000-0000-4000-8000-000000000001'
where id = '00000000-0000-4000-8000-000000000001';

do $$
begin
  perform set_config('request.jwt.claim.sub', '76000000-0000-4000-8000-000000000002', true);
  perform set_config(
    'request.jwt.claims',
    '{"sub":"76000000-0000-4000-8000-000000000002","role":"authenticated"}',
    true
  );
end;
$$;
set local role authenticated;

select is((select count(*) from public.run_events), 0::bigint, 'RLS hides another user''s run events');

reset role;

select * from finish();

rollback;
