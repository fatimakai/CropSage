begin;

set local search_path = public, extensions;

select plan(33);

select has_table('public', 'provider_fetches', 'provider fetches table exists');
select has_type('public', 'provider_code', 'provider code enum exists');
select has_type('public', 'provider_attempt_kind', 'provider attempt kind enum exists');
select has_type('public', 'http_method', 'HTTP method enum exists');
select has_column('public', 'provider_fetches', 'request_group_id', 'fetches retain retry groups');
select has_column('public', 'provider_fetches', 'attempt_number', 'fetches retain attempt order');
select has_column('public', 'provider_fetches', 'cache_key', 'fetches have generated cache keys');
select has_column('public', 'provider_fetches', 'artifacts_jsonb', 'fetches retain artifact metadata');
select has_fk('public', 'provider_fetches', 'provider fetches have foreign keys');
select fk_ok(
  'public',
  'provider_fetches',
  'cache_hit_fetch_id',
  'public',
  'provider_fetches',
  'id',
  'cache reuse points to an earlier provider fetch'
);
select ok(
  (select relrowsecurity from pg_class where oid = 'public.provider_fetches'::regclass),
  'provider fetches have RLS enabled'
);
select ok(
  not has_table_privilege('anon', 'public.provider_fetches', 'SELECT'),
  'anonymous users cannot read provider fetches'
);
select ok(
  not has_table_privilege('authenticated', 'public.provider_fetches', 'INSERT'),
  'authenticated browser users cannot insert provider fetches directly'
);
select is(
  (select count(*) from storage.buckets where id = 'provider-artifacts'),
  1::bigint,
  'the provider artifacts bucket exists'
);
select is(
  (select public from storage.buckets where id = 'provider-artifacts'),
  false,
  'the provider artifacts bucket is private'
);
select is(
  (select file_size_limit from storage.buckets where id = 'provider-artifacts'),
  52428800::bigint,
  'the provider artifacts bucket has a 50 MiB object limit'
);

select lives_ok(
  $$
    insert into public.provider_fetches (
      id,
      farm_profile_id,
      request_group_id,
      attempt_number,
      provider,
      endpoint,
      http_method,
      request_parameters_jsonb,
      request_schema_version,
      sanitization_version,
      requested_variables,
      request_point,
      spatial_resolution_m,
      cache_key_material_jsonb,
      status,
      produced_evidence,
      result_mode,
      http_status_code,
      submitted_at,
      completed_at,
      fetched_at,
      expires_at,
      artifacts_jsonb
    ) values (
      '20000000-0000-4000-8000-000000000001',
      '00000000-0000-4000-8000-000000000101',
      '21000000-0000-4000-8000-000000000001',
      1,
      'nasa_power',
      '/api/temporal/climatology/point',
      'GET',
      '{"community":"AG","format":"JSON"}'::jsonb,
      'nasa-power-climatology-v1',
      '1.0.0',
      array['T2M', 'T2M_MAX', 'PRECTOTCORR'],
      extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
      50000,
      '{"provider":"nasa_power","endpoint":"climatology_point","coordinate":"34.1800,-101.7600","variables":["PRECTOTCORR","T2M","T2M_MAX"],"period":"2001-2020"}'::jsonb,
      'succeeded',
      true,
      'live',
      200,
      statement_timestamp() - interval '60 seconds',
      statement_timestamp() - interval '50 seconds',
      statement_timestamp() - interval '50 seconds',
      statement_timestamp() + interval '30 days',
      jsonb_build_array(jsonb_build_object(
        'bucket_name', 'provider-artifacts',
        'object_path', 'nasa_power/plainview/climatology-2001-2020.json',
        'sha256', repeat('a', 64),
        'content_type', 'application/json',
        'size_bytes', 1024,
        'provider_timestamp', '2026-08-28T00:00:00Z',
        'sanitization_version', '1.0.0',
        'schema_version', 'nasa-power-climatology-v1'
      ))
    )
  $$,
  'a sanitized live evidence-producing fetch can be stored'
);

select matches(
  (
    select cache_key
    from public.provider_fetches
    where id = '20000000-0000-4000-8000-000000000001'
  ),
  '^[0-9a-f]{64}$',
  'provider cache keys are generated as lowercase SHA-256'
);

select throws_ok(
  $$
    insert into public.provider_fetches (
      farm_profile_id,
      provider,
      endpoint,
      http_method,
      request_parameters_jsonb,
      request_schema_version,
      sanitization_version,
      requested_variables,
      request_point,
      cache_key_material_jsonb
    ) values (
      '00000000-0000-4000-8000-000000000101',
      'fortyguard',
      '/v1/heatmap',
      'POST',
      '{"api_key":"must-not-be-stored"}'::jsonb,
      'fortyguard-heatmap-v1',
      '1.0.0',
      array['tcm'],
      extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
      '{"provider":"fortyguard","analysis":"tcm"}'::jsonb
    )
  $$,
  '23514',
  'new row for relation "provider_fetches" violates check constraint "provider_fetches_request_parameters_object"',
  'request parameters containing an API key are rejected'
);

select throws_ok(
  $$
    insert into public.provider_fetches (
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
      produced_evidence,
      result_mode,
      submitted_at,
      completed_at,
      fetched_at,
      artifacts_jsonb
    ) values (
      '00000000-0000-4000-8000-000000000101',
      'fortyguard',
      '/v1/status/activity-id',
      'GET',
      'fortyguard-status-v1',
      '1.0.0',
      array['tcm'],
      extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
      '{"provider":"fortyguard","analysis":"tcm"}'::jsonb,
      'succeeded',
      true,
      'live',
      statement_timestamp() - interval '10 seconds',
      statement_timestamp() - interval '5 seconds',
      statement_timestamp() - interval '5 seconds',
      jsonb_build_array(jsonb_build_object(
        'bucket_name', 'provider-artifacts',
        'object_path', 'fortyguard/plainview/tcm.json',
        'sha256', repeat('b', 64),
        'content_type', 'application/json',
        'size_bytes', 100,
        'provider_timestamp', '2026-08-28T00:00:00Z',
        'sanitization_version', '1.0.0',
        'schema_version', 'fortyguard-status-v1',
        'signed_url', 'https://temporary.example.test/result'
      ))
    )
  $$,
  '23514',
  'new row for relation "provider_fetches" violates check constraint "provider_fetches_artifacts_valid"',
  'artifact metadata containing a temporary signed URL is rejected'
);

select throws_ok(
  $$
    insert into public.provider_fetches (
      farm_profile_id,
      provider,
      endpoint,
      http_method,
      request_schema_version,
      sanitization_version,
      requested_variables,
      request_point,
      cache_key_material_jsonb
    ) values (
      '00000000-0000-4000-8000-000000000101',
      'open_meteo',
      '/v1/forecast',
      'GET',
      'open-meteo-forecast-v1',
      '1.0.0',
      array['temperature_2m'],
      extensions.st_setsrid(extensions.st_makepoint(-95.3698, 29.7604), 4326)::extensions.geography,
      '{"provider":"open_meteo","coordinate":"29.7604,-95.3698"}'::jsonb
    )
  $$,
  'Provider request point does not match the farm profile within tolerance.',
  'provider request coordinates must match the farm profile'
);

select lives_ok(
  $$
    insert into public.provider_fetches (
      id,
      farm_profile_id,
      request_group_id,
      attempt_number,
      provider,
      endpoint,
      http_method,
      request_schema_version,
      sanitization_version,
      requested_variables,
      request_point,
      cache_key_material_jsonb,
      status,
      http_status_code,
      submitted_at,
      completed_at,
      error_code,
      error_message
    ) values (
      '20000000-0000-4000-8000-000000000010',
      '00000000-0000-4000-8000-000000000101',
      '21000000-0000-4000-8000-000000000010',
      1,
      'open_meteo',
      '/v1/forecast',
      'GET',
      'open-meteo-forecast-v1',
      '1.0.0',
      array['temperature_2m'],
      extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
      '{"provider":"open_meteo","coordinate":"34.1800,-101.7600","variables":["temperature_2m"]}'::jsonb,
      'failed',
      503,
      statement_timestamp() - interval '20 seconds',
      statement_timestamp() - interval '15 seconds',
      'provider_unavailable',
      'Provider returned a temporary service error.'
    )
  $$,
  'a failed provider attempt remains auditable'
);

select lives_ok(
  $$
    insert into public.provider_fetches (
      farm_profile_id,
      request_group_id,
      attempt_number,
      provider,
      endpoint,
      http_method,
      request_schema_version,
      sanitization_version,
      requested_variables,
      request_point,
      cache_key_material_jsonb
    ) values (
      '00000000-0000-4000-8000-000000000101',
      '21000000-0000-4000-8000-000000000010',
      2,
      'open_meteo',
      '/v1/forecast',
      'GET',
      'open-meteo-forecast-v1',
      '1.0.0',
      array['temperature_2m'],
      extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
      '{"provider":"open_meteo","coordinate":"34.1800,-101.7600","variables":["temperature_2m"]}'::jsonb
    )
  $$,
  'a retry can follow a failed attempt in the same request group'
);

select is(
  (
    select count(*)
    from public.provider_fetches
    where request_group_id = '21000000-0000-4000-8000-000000000010'
  ),
  2::bigint,
  'failed and retry attempts remain distinct rows'
);

select throws_ok(
  $$
    insert into public.provider_fetches (
      farm_profile_id,
      request_group_id,
      attempt_number,
      provider,
      endpoint,
      http_method,
      request_schema_version,
      sanitization_version,
      requested_variables,
      request_point,
      cache_key_material_jsonb
    ) values (
      '00000000-0000-4000-8000-000000000101',
      '21000000-0000-4000-8000-000000000010',
      2,
      'open_meteo',
      '/v1/forecast',
      'GET',
      'open-meteo-forecast-v1',
      '1.0.0',
      array['temperature_2m'],
      extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
      '{"provider":"open_meteo"}'::jsonb
    )
  $$,
  '23505',
  'duplicate key value violates unique constraint "provider_fetches_group_attempt_unique"',
  'the same attempt number cannot be reused within a request group'
);

select lives_ok(
  $$
    insert into public.provider_fetches (
      id,
      farm_profile_id,
      request_group_id,
      attempt_number,
      attempt_kind,
      provider,
      request_schema_version,
      sanitization_version,
      requested_variables,
      request_point,
      cache_key_material_jsonb,
      cache_hit_fetch_id,
      status,
      produced_evidence,
      result_mode,
      submitted_at,
      completed_at,
      fetched_at,
      expires_at,
      artifacts_jsonb
    ) values (
      '20000000-0000-4000-8000-000000000002',
      '00000000-0000-4000-8000-000000000101',
      '21000000-0000-4000-8000-000000000002',
      1,
      'cache_lookup',
      'nasa_power',
      'nasa-power-climatology-v1',
      '1.0.0',
      array['T2M', 'T2M_MAX', 'PRECTOTCORR'],
      extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
      '{"provider":"nasa_power","endpoint":"climatology_point","coordinate":"34.1800,-101.7600","variables":["PRECTOTCORR","T2M","T2M_MAX"],"period":"2001-2020"}'::jsonb,
      '20000000-0000-4000-8000-000000000001',
      'succeeded',
      true,
      'cache',
      statement_timestamp(),
      statement_timestamp(),
      statement_timestamp(),
      statement_timestamp() + interval '30 days',
      jsonb_build_array(jsonb_build_object(
        'bucket_name', 'provider-artifacts',
        'object_path', 'nasa_power/plainview/climatology-2001-2020.json',
        'sha256', repeat('a', 64),
        'content_type', 'application/json',
        'size_bytes', 1024,
        'provider_timestamp', '2026-08-28T00:00:00Z',
        'sanitization_version', '1.0.0',
        'schema_version', 'nasa-power-climatology-v1'
      ))
    )
  $$,
  'a fresh matching evidence fetch can be reused from cache'
);

select is(
  (
    select cache_hit_fetch_id
    from public.provider_fetches
    where id = '20000000-0000-4000-8000-000000000002'
  ),
  '20000000-0000-4000-8000-000000000001'::uuid,
  'cache reuse retains its source fetch'
);

select throws_ok(
  $$
    insert into public.provider_fetches (
      farm_profile_id,
      attempt_kind,
      provider,
      request_schema_version,
      sanitization_version,
      requested_variables,
      request_point,
      cache_key_material_jsonb,
      cache_hit_fetch_id,
      status,
      produced_evidence,
      result_mode,
      submitted_at,
      completed_at,
      fetched_at,
      artifacts_jsonb
    ) values (
      '00000000-0000-4000-8000-000000000101',
      'cache_lookup',
      'nasa_power',
      'nasa-power-climatology-v1',
      '1.0.0',
      array['T2M'],
      extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
      '{"provider":"nasa_power","variables":["T2M"],"period":"different"}'::jsonb,
      '20000000-0000-4000-8000-000000000001',
      'succeeded',
      true,
      'cache',
      statement_timestamp(),
      statement_timestamp(),
      statement_timestamp(),
      jsonb_build_array(jsonb_build_object(
        'bucket_name', 'provider-artifacts',
        'object_path', 'nasa_power/plainview/climatology-2001-2020.json',
        'sha256', repeat('a', 64),
        'content_type', 'application/json',
        'size_bytes', 1024,
        'provider_timestamp', '2026-08-28T00:00:00Z',
        'sanitization_version', '1.0.0',
        'schema_version', 'nasa-power-climatology-v1'
      ))
    )
  $$,
  'Cache source key does not match the requested evidence.',
  'a cache source cannot be reused for different request material'
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
  produced_evidence,
  result_mode,
  submitted_at,
  completed_at,
  fetched_at,
  expires_at,
  artifacts_jsonb
) values (
  '20000000-0000-4000-8000-000000000003',
  '00000000-0000-4000-8000-000000000101',
  'ssurgo',
  '/Tabular/post.rest',
  'POST',
  'ssurgo-sda-v1',
  '1.0.0',
  array['awc_r', 'ph1to1h2o_r'],
  extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
  '{"provider":"ssurgo","coordinate":"34.1800,-101.7600","attributes":["awc_r","ph1to1h2o_r"]}'::jsonb,
  'succeeded',
  true,
  'live',
  statement_timestamp() - interval '2 days',
  statement_timestamp() - interval '2 days' + interval '5 seconds',
  statement_timestamp() - interval '2 days' + interval '5 seconds',
  statement_timestamp() - interval '1 day',
  jsonb_build_array(jsonb_build_object(
    'bucket_name', 'provider-artifacts',
    'object_path', 'ssurgo/plainview/soil-summary.json',
    'sha256', repeat('c', 64),
    'content_type', 'application/json',
    'size_bytes', 2048,
    'provider_timestamp', '2026-08-27T00:00:00Z',
    'sanitization_version', '1.0.0',
    'schema_version', 'ssurgo-sda-v1'
  )));

select throws_ok(
  $$
    insert into public.provider_fetches (
      farm_profile_id,
      attempt_kind,
      provider,
      request_schema_version,
      sanitization_version,
      requested_variables,
      request_point,
      cache_key_material_jsonb,
      cache_hit_fetch_id,
      status,
      produced_evidence,
      result_mode,
      submitted_at,
      completed_at,
      fetched_at,
      artifacts_jsonb
    ) values (
      '00000000-0000-4000-8000-000000000101',
      'cache_lookup',
      'ssurgo',
      'ssurgo-sda-v1',
      '1.0.0',
      array['awc_r', 'ph1to1h2o_r'],
      extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
      '{"provider":"ssurgo","coordinate":"34.1800,-101.7600","attributes":["awc_r","ph1to1h2o_r"]}'::jsonb,
      '20000000-0000-4000-8000-000000000003',
      'succeeded',
      true,
      'cache',
      statement_timestamp(),
      statement_timestamp(),
      statement_timestamp(),
      jsonb_build_array(jsonb_build_object(
        'bucket_name', 'provider-artifacts',
        'object_path', 'ssurgo/plainview/soil-summary.json',
        'sha256', repeat('c', 64),
        'content_type', 'application/json',
        'size_bytes', 2048,
        'provider_timestamp', '2026-08-27T00:00:00Z',
        'sanitization_version', '1.0.0',
        'schema_version', 'ssurgo-sda-v1'
      ))
    )
  $$,
  'Cache source was expired at reuse time.',
  'stale provider evidence cannot be labeled as reusable cache'
);

select throws_ok(
  $$
    insert into public.provider_fetches (
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
      produced_evidence,
      result_mode,
      submitted_at,
      completed_at,
      fetched_at
    ) values (
      '00000000-0000-4000-8000-000000000101',
      'open_meteo',
      '/v1/forecast',
      'GET',
      'open-meteo-forecast-v1',
      '1.0.0',
      array['temperature_2m'],
      extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
      '{"provider":"open_meteo"}'::jsonb,
      'succeeded',
      true,
      'live',
      statement_timestamp(),
      statement_timestamp(),
      statement_timestamp()
    )
  $$,
  '23514',
  'new row for relation "provider_fetches" violates check constraint "provider_fetches_lifecycle"',
  'an evidence-producing success must retain at least one artifact'
);

select lives_ok(
  $$
    insert into public.provider_fetches (
      farm_profile_id,
      attempt_kind,
      provider,
      request_schema_version,
      sanitization_version,
      requested_variables,
      request_point,
      cache_key_material_jsonb,
      status,
      produced_evidence,
      result_mode,
      submitted_at,
      completed_at,
      fetched_at,
      artifacts_jsonb
    ) values (
      '00000000-0000-4000-8000-000000000101',
      'fallback_load',
      'ssurgo',
      'ssurgo-sda-v1',
      '1.0.0',
      array['awc_r'],
      extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
      '{"provider":"ssurgo","fallback_version":"2026-08-28"}'::jsonb,
      'succeeded',
      true,
      'fallback',
      statement_timestamp(),
      statement_timestamp(),
      statement_timestamp(),
      jsonb_build_array(jsonb_build_object(
        'bucket_name', 'provider-artifacts',
        'object_path', 'ssurgo/plainview/fallback.json',
        'sha256', repeat('d', 64),
        'content_type', 'application/json',
        'size_bytes', 512,
        'provider_timestamp', null,
        'sanitization_version', '1.0.0',
        'schema_version', 'ssurgo-sda-v1'
      ))
    )
  $$,
  'a sanitized fallback artifact is stored without pretending an HTTP call occurred'
);

select lives_ok(
  $$
    insert into public.provider_fetches (
      farm_profile_id,
      provider,
      endpoint,
      http_method,
      request_schema_version,
      sanitization_version,
      requested_variables,
      request_area,
      cache_key_material_jsonb,
      status,
      provider_activity_id,
      provider_status,
      http_status_code,
      submitted_at,
      completed_at
    ) values (
      '00000000-0000-4000-8000-000000000101',
      'fortyguard',
      '/v1/heatmap',
      'POST',
      'fortyguard-heatmap-v1',
      '1.0.0',
      array['tcm'],
      extensions.st_multi(extensions.st_geomfromtext('POLYGON((-101.77 34.17,-101.77 34.19,-101.75 34.19,-101.75 34.17,-101.77 34.17))', 4326))::extensions.geography,
      '{"provider":"fortyguard","endpoint":"heatmap","analysis":"tcm","granularity_m":100}'::jsonb,
      'succeeded',
      'activity-test-001',
      'Processing',
      202,
      statement_timestamp() - interval '5 seconds',
      statement_timestamp()
    )
  $$,
  'an asynchronous submission response can succeed before producing evidence'
);

insert into auth.users (id, aud, role, email, created_at, updated_at)
values
  (
    '30000000-0000-4000-8000-000000000001',
    'authenticated',
    'authenticated',
    'provider-owner-one@example.test',
    statement_timestamp(),
    statement_timestamp()
  ),
  (
    '30000000-0000-4000-8000-000000000002',
    'authenticated',
    'authenticated',
    'provider-owner-two@example.test',
    statement_timestamp(),
    statement_timestamp()
  );

insert into public.assessment_sessions (id, owner_user_id)
values
  ('31000000-0000-4000-8000-000000000001', '30000000-0000-4000-8000-000000000001'),
  ('31000000-0000-4000-8000-000000000002', '30000000-0000-4000-8000-000000000002');

insert into public.farm_profiles (
  id,
  assessment_session_id,
  external_profile_id,
  profile_version,
  schema_version,
  farm_point,
  location_source,
  planned_planting_month,
  profile_snapshot
) values
  (
    '32000000-0000-4000-8000-000000000001',
    '31000000-0000-4000-8000-000000000001',
    'provider_owner_one_profile',
    1,
    '1.0.0',
    extensions.st_setsrid(extensions.st_makepoint(-96.7970, 32.7767), 4326)::extensions.geography,
    'map_pin',
    '2026-09-01',
    '{"schema_version":"1.0.0","profile_id":"provider_owner_one_profile"}'::jsonb
  ),
  (
    '32000000-0000-4000-8000-000000000002',
    '31000000-0000-4000-8000-000000000002',
    'provider_owner_two_profile',
    1,
    '1.0.0',
    extensions.st_setsrid(extensions.st_makepoint(-95.3698, 29.7604), 4326)::extensions.geography,
    'map_pin',
    '2026-09-01',
    '{"schema_version":"1.0.0","profile_id":"provider_owner_two_profile"}'::jsonb
  );

insert into public.provider_fetches (
  farm_profile_id,
  provider,
  endpoint,
  http_method,
  request_schema_version,
  sanitization_version,
  requested_variables,
  request_point,
  cache_key_material_jsonb
) values
  (
    '32000000-0000-4000-8000-000000000001',
    'open_meteo',
    '/v1/forecast',
    'GET',
    'open-meteo-forecast-v1',
    '1.0.0',
    array['temperature_2m'],
    extensions.st_setsrid(extensions.st_makepoint(-96.7970, 32.7767), 4326)::extensions.geography,
    '{"provider":"open_meteo","owner":1}'::jsonb
  ),
  (
    '32000000-0000-4000-8000-000000000002',
    'open_meteo',
    '/v1/forecast',
    'GET',
    'open-meteo-forecast-v1',
    '1.0.0',
    array['temperature_2m'],
    extensions.st_setsrid(extensions.st_makepoint(-95.3698, 29.7604), 4326)::extensions.geography,
    '{"provider":"open_meteo","owner":2}'::jsonb
  );

do $$
begin
  perform set_config(
    'request.jwt.claim.sub',
    '30000000-0000-4000-8000-000000000001',
    true
  );
  perform set_config(
    'request.jwt.claims',
    '{"sub":"30000000-0000-4000-8000-000000000001","role":"authenticated"}',
    true
  );
end;
$$;
set local role authenticated;

select is(
  (
    select count(*)
    from public.provider_fetches
    where farm_profile_id in (
      '32000000-0000-4000-8000-000000000001',
      '32000000-0000-4000-8000-000000000002'
    )
  ),
  1::bigint,
  'an authenticated user sees provider attempts only for their own profile'
);

reset role;

select * from finish();

rollback;
