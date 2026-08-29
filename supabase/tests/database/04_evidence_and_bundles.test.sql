begin;

set local search_path = public, extensions;

select plan(49);

select has_table('public', 'evidence_records', 'evidence records table exists');
select has_table('public', 'evidence_bundles', 'evidence bundles table exists');
select has_table('public', 'evidence_bundle_records', 'evidence bundle membership table exists');
select has_type('public', 'evidence_availability', 'evidence availability enum exists');
select has_type('public', 'evidence_freshness', 'evidence freshness enum exists');
select has_type('public', 'evidence_value_kind', 'evidence value kind enum exists');
select has_type('public', 'bundle_record_role', 'bundle membership role enum exists');
select has_fk('public', 'evidence_records', 'evidence records retain provenance foreign keys');
select has_fk('public', 'evidence_bundles', 'evidence bundles belong to farm profiles');
select has_fk('public', 'evidence_bundle_records', 'bundle membership links bundles and records');
select has_column('public', 'evidence_records', 'record_hash', 'evidence records retain generated hashes');
select has_column('public', 'evidence_bundles', 'bundle_hash', 'evidence bundles retain generated hashes');
select ok(
  (select relrowsecurity from pg_class where oid = 'public.evidence_records'::regclass),
  'evidence records have RLS enabled'
);
select ok(
  (select relrowsecurity from pg_class where oid = 'public.evidence_bundles'::regclass),
  'evidence bundles have RLS enabled'
);
select ok(
  (select relrowsecurity from pg_class where oid = 'public.evidence_bundle_records'::regclass),
  'bundle membership has RLS enabled'
);
select ok(
  not has_table_privilege('anon', 'public.evidence_records', 'SELECT'),
  'anonymous users cannot read evidence records'
);
select ok(
  not has_table_privilege('authenticated', 'public.evidence_bundles', 'INSERT'),
  'authenticated browser users cannot insert evidence bundles directly'
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
  '40000000-0000-4000-8000-000000000001',
  '00000000-0000-4000-8000-000000000101',
  'nasa_power',
  '/api/temporal/climatology/point',
  'GET',
  'nasa-power-climatology-v1',
  '1.0.0',
  array['T2M', 'PRECTOTCORR'],
  extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
  '{"provider":"nasa_power","coordinate":"34.1800,-101.7600","variables":["PRECTOTCORR","T2M"]}'::jsonb,
  'succeeded',
  true,
  'live',
  statement_timestamp() - interval '1 minute',
  statement_timestamp() - interval '50 seconds',
  statement_timestamp() - interval '50 seconds',
  statement_timestamp() + interval '30 days',
  jsonb_build_array(jsonb_build_object(
    'bucket_name', 'provider-artifacts',
    'object_path', 'nasa_power/plainview/evidence-source.json',
    'sha256', repeat('e', 64),
    'content_type', 'application/json',
    'size_bytes', 2048,
    'provider_timestamp', '2026-08-28T00:00:00Z',
    'sanitization_version', '1.0.0',
    'schema_version', 'nasa-power-climatology-v1'
  ))
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
  submitted_at,
  completed_at,
  error_code,
  error_message
) values (
  '40000000-0000-4000-8000-000000000002',
  '00000000-0000-4000-8000-000000000101',
  'open_meteo',
  '/v1/forecast',
  'GET',
  'open-meteo-forecast-v1',
  '1.0.0',
  array['temperature_2m'],
  extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
  '{"provider":"open_meteo","coordinate":"34.1800,-101.7600"}'::jsonb,
  'failed',
  statement_timestamp() - interval '30 seconds',
  statement_timestamp() - interval '20 seconds',
  'provider_unavailable',
  'Synthetic provider failure.'
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
) values
  (
    '40000000-0000-4000-8000-000000000003',
    '00000000-0000-4000-8000-000000000101',
    'fortyguard',
    '/v1/status/activity-id',
    'GET',
    'fortyguard-status-v1.2',
    '1.0.0',
    array[
      'minimum_tile_average_temperature_c',
      'maximum_tile_average_temperature_c',
      'period_minimum_temperature_c',
      'period_maximum_temperature_c'
    ],
    extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
    '{"provider":"fortyguard","coordinate":"34.1800,-101.7600","analysis":"tcm","schema_version":"1.2.0"}'::jsonb,
    'succeeded',
    true,
    'live',
    statement_timestamp() - interval '1 minute',
    statement_timestamp() - interval '50 seconds',
    statement_timestamp() - interval '50 seconds',
    statement_timestamp() + interval '1 day',
    jsonb_build_array(jsonb_build_object(
      'bucket_name', 'provider-artifacts',
      'object_path', 'fortyguard/plainview/temperature-summary-v1.2.json',
      'sha256', repeat('f', 64),
      'content_type', 'application/json',
      'size_bytes', 1024,
      'provider_timestamp', '2026-08-28T00:00:00Z',
      'sanitization_version', '1.0.0',
      'schema_version', 'fortyguard-status-v1.2'
    ))
  ),
  (
    '40000000-0000-4000-8000-000000000004',
    '00000000-0000-4000-8000-000000000101',
    'ssurgo',
    '/Tabular/post.rest',
    'POST',
    'ssurgo-sda-v1',
    '1.0.0',
    array['texture_name'],
    extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
    '{"provider":"ssurgo","coordinate":"34.1800,-101.7600","attributes":["texture_name"]}'::jsonb,
    'succeeded',
    true,
    'live',
    statement_timestamp() - interval '1 minute',
    statement_timestamp() - interval '50 seconds',
    statement_timestamp() - interval '50 seconds',
    statement_timestamp() + interval '30 days',
    jsonb_build_array(jsonb_build_object(
      'bucket_name', 'provider-artifacts',
      'object_path', 'ssurgo/plainview/texture-summary.json',
      'sha256', repeat('a', 64),
      'content_type', 'application/json',
      'size_bytes', 1024,
      'provider_timestamp', '2026-08-28T00:00:00Z',
      'sanitization_version', '1.0.0',
      'schema_version', 'ssurgo-sda-v1'
    ))
  );

select lives_ok(
  $$
    insert into public.evidence_records (
      id,
      farm_profile_id,
      provider_fetch_id,
      source_type,
      source_name,
      source_field,
      canonical_variable,
      availability,
      freshness,
      value_kind,
      value_numeric,
      unit,
      fetched_at,
      expires_at,
      evidence_point,
      spatial_resolution_m,
      quality_score,
      evidence_snapshot
    ) values (
      '41000000-0000-4000-8000-000000000001',
      '00000000-0000-4000-8000-000000000101',
      '40000000-0000-4000-8000-000000000001',
      'provider',
      'NASA POWER',
      'T2M',
      'air_temperature.mean_c',
      'available',
      'fresh',
      'numeric',
      28.016129,
      'degC',
      statement_timestamp() - interval '50 seconds',
      statement_timestamp() + interval '30 days',
      extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
      50000,
      0.90,
      '{"provider":"nasa_power","field":"T2M","value":28.016129,"unit":"degC","period":"Aug"}'::jsonb
    )
  $$,
  'a normalized fact from a successful provider fetch can be stored'
);

select matches(
  (
    select record_hash
    from public.evidence_records
    where id = '41000000-0000-4000-8000-000000000001'
  ),
  '^[0-9a-f]{64}$',
  'evidence records receive canonical SHA-256 hashes'
);

select lives_ok(
  $$
    insert into public.evidence_records (
      id,
      farm_profile_id,
      source_type,
      source_name,
      canonical_variable,
      availability,
      freshness,
      evidence_point,
      warnings,
      evidence_snapshot
    ) values (
      '41000000-0000-4000-8000-000000000002',
      '00000000-0000-4000-8000-000000000101',
      'farmer',
      'Farm profile',
      'farm.current_soil_moisture',
      'missing',
      'not_applicable',
      extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
      array['No farmer observation or sensor reading was supplied.'],
      '{"source":"farmer","variable":"current_soil_moisture","availability":"missing"}'::jsonb
    )
  $$,
  'missing farm evidence remains explicit without inventing a value'
);

select throws_ok(
  $$
    insert into public.evidence_records (
      farm_profile_id,
      source_type,
      source_name,
      canonical_variable,
      availability,
      freshness,
      value_kind,
      value_numeric,
      unit,
      evidence_point,
      evidence_snapshot
    ) values (
      '00000000-0000-4000-8000-000000000101',
      'farmer',
      'Farm profile',
      'farm.recent_rainfall_mm',
      'missing',
      'not_applicable',
      'numeric',
      0,
      'mm',
      extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
      '{"variable":"recent_rainfall","availability":"missing","value":0}'::jsonb
    )
  $$,
  '23514',
  'new row for relation "evidence_records" violates check constraint "evidence_records_value_shape"',
  'missing evidence cannot be represented as zero'
);

select throws_ok(
  $$
    insert into public.evidence_records (
      farm_profile_id,
      source_type,
      source_name,
      canonical_variable,
      value_kind,
      value_numeric,
      evidence_point,
      evidence_snapshot
    ) values (
      '00000000-0000-4000-8000-000000000101',
      'farmer',
      'Farm profile',
      'farm.recent_rainfall_mm',
      'numeric',
      12.5,
      extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
      '{"variable":"recent_rainfall","value":12.5}'::jsonb
    )
  $$,
  '23514',
  'new row for relation "evidence_records" violates check constraint "evidence_records_numeric_unit_present"',
  'numeric evidence must declare a normalized unit'
);

select throws_ok(
  $$
    insert into public.evidence_records (
      farm_profile_id,
      provider_fetch_id,
      source_type,
      source_name,
      canonical_variable,
      value_kind,
      value_numeric,
      unit,
      evidence_point,
      evidence_snapshot
    ) values (
      '00000000-0000-4000-8000-000000000101',
      '40000000-0000-4000-8000-000000000002',
      'provider',
      'Open-Meteo',
      'air_temperature.current_c',
      'numeric',
      27.1,
      'degC',
      extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
      '{"provider":"open_meteo","value":27.1}'::jsonb
    )
  $$,
  'A failed or non-evidence provider attempt cannot become evidence.',
  'a failed provider request cannot masquerade as evidence'
);

select throws_ok(
  $$
    insert into public.evidence_records (
      farm_profile_id,
      source_type,
      source_name,
      canonical_variable,
      value_kind,
      value_numeric,
      unit,
      evidence_point,
      evidence_snapshot
    ) values (
      '00000000-0000-4000-8000-000000000101',
      'farmer',
      'Farm profile',
      'farm.recent_rainfall_mm',
      'numeric',
      12.5,
      'mm',
      extensions.st_setsrid(extensions.st_makepoint(-95.3698, 29.7604), 4326)::extensions.geography,
      '{"variable":"recent_rainfall","value":12.5,"unit":"mm"}'::jsonb
    )
  $$,
  'Evidence point does not match the farm profile within tolerance.',
  'evidence coordinates must match the farm profile'
);

select lives_ok(
  $$
    insert into public.evidence_records (
      id,
      farm_profile_id,
      source_type,
      source_name,
      source_field,
      canonical_variable,
      availability,
      freshness,
      value_kind,
      value_numeric,
      unit,
      observed_start_at,
      observed_end_at,
      evidence_point,
      quality_score,
      evidence_snapshot
    ) values (
      '41000000-0000-4000-8000-000000000003',
      '00000000-0000-4000-8000-000000000101',
      'laboratory',
      'Synthetic soil laboratory report',
      'pH',
      'soil.ph',
      'available',
      'not_applicable',
      'numeric',
      7.5,
      'dimensionless',
      '2026-08-20T00:00:00Z',
      '2026-08-20T00:00:00Z',
      extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
      0.95,
      '{"source":"laboratory","field":"pH","value":7.5,"unit":"dimensionless"}'::jsonb
    )
  $$,
  'laboratory evidence remains distinguishable from mapped provider evidence'
);

select lives_ok(
  $$
    insert into public.evidence_records (
      id,
      farm_profile_id,
      source_type,
      source_name,
      canonical_variable,
      availability,
      freshness,
      value_kind,
      value_numeric,
      unit,
      evidence_point,
      quality_score,
      derivation_name,
      derivation_version,
      derivation_input_ids,
      derivation_jsonb,
      evidence_snapshot
    ) values (
      '41000000-0000-4000-8000-000000000004',
      '00000000-0000-4000-8000-000000000101',
      'derived',
      'CropSage normalizer',
      'derived.demo_index',
      'available',
      'fresh',
      'numeric',
      0.82,
      'dimensionless',
      extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
      0.85,
      'demo_index',
      '1.0.0',
      array[
        '41000000-0000-4000-8000-000000000001'::uuid,
        '41000000-0000-4000-8000-000000000003'::uuid
      ],
      '{"calculation":"synthetic test derivation","method":"deterministic"}'::jsonb,
      '{"source":"derived","variable":"demo_index","value":0.82,"inputs":["41000000-0000-4000-8000-000000000001","41000000-0000-4000-8000-000000000003"]}'::jsonb
    )
  $$,
  'derived evidence retains named and versioned lineage'
);

select is(
  (
    select cardinality(derivation_input_ids)
    from public.evidence_records
    where id = '41000000-0000-4000-8000-000000000004'
  ),
  2,
  'derived evidence retains every input evidence-record ID'
);

select lives_ok(
  $$
    insert into public.evidence_records (
      id, farm_profile_id, provider_fetch_id, source_type, source_name, source_field,
      canonical_variable, availability, freshness, value_kind, value_text, value_jsonb,
      fetched_at, expires_at, evidence_point, evidence_snapshot
    ) values
      (
        '41000000-0000-4000-8000-000000000006',
        '00000000-0000-4000-8000-000000000101',
        '40000000-0000-4000-8000-000000000003',
        'provider',
        'FortyGuard',
        'temperature_summary',
        'air_temperature.fortyguard_extrema_c',
        'available',
        'fresh',
        'json',
        null,
        '{"minimum_tile_average_temperature_c":11.2,"maximum_tile_average_temperature_c":34.8,"period_minimum_temperature_c":8.1,"period_maximum_temperature_c":38.4}'::jsonb,
        statement_timestamp() - interval '50 seconds',
        statement_timestamp() + interval '1 day',
        extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
        '{"provider":"fortyguard","field":"temperature_summary","minimum_tile_average_temperature_c":11.2,"maximum_tile_average_temperature_c":34.8,"period_minimum_temperature_c":8.1,"period_maximum_temperature_c":38.4}'::jsonb
      ),
      (
        '41000000-0000-4000-8000-000000000007',
        '00000000-0000-4000-8000-000000000101',
        '40000000-0000-4000-8000-000000000004',
        'provider',
        'USDA SSURGO',
        'texture_name',
        'soil.texture_class',
        'available',
        'fresh',
        'text',
        'fine sandy loam',
        null,
        statement_timestamp() - interval '50 seconds',
        statement_timestamp() + interval '30 days',
        extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
        '{"provider":"ssurgo","field":"texture_name","value":"fine sandy loam"}'::jsonb
      ),
      (
        '41000000-0000-4000-8000-000000000008',
        '00000000-0000-4000-8000-000000000101',
        '40000000-0000-4000-8000-000000000004',
        'provider',
        'USDA SSURGO',
        'texture_name',
        'soil.texture_class',
        'available',
        'fresh',
        'text',
        'loamy fine sand',
        null,
        statement_timestamp() - interval '50 seconds',
        statement_timestamp() + interval '30 days',
        extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
        '{"provider":"ssurgo","field":"texture_name","value":"loamy fine sand"}'::jsonb
      )
  $$,
  'corrected FortyGuard temperature fields and expanded SSURGO textures can be stored'
);

select results_eq(
  $$
    select key
    from public.evidence_records,
      lateral jsonb_object_keys(value_jsonb) as key
    where id = '41000000-0000-4000-8000-000000000006'
    order by key
  $$,
  $$ values
    ('maximum_tile_average_temperature_c'::text),
    ('minimum_tile_average_temperature_c'::text),
    ('period_maximum_temperature_c'::text),
    ('period_minimum_temperature_c'::text)
  $$,
  'FortyGuard evidence preserves every corrected temperature field name'
);

select results_eq(
  $$
    select value_text as texture_name
    from public.evidence_records
    where id in (
      '41000000-0000-4000-8000-000000000007',
      '41000000-0000-4000-8000-000000000008'
    )
    order by texture_name
  $$,
  $$ values
    ('fine sandy loam'::text),
    ('loamy fine sand'::text)
  $$,
  'SSURGO evidence accepts expanded multi-word texture names'
);

select throws_ok(
  $$
    insert into public.evidence_records (
      farm_profile_id,
      source_type,
      source_name,
      canonical_variable,
      value_kind,
      value_numeric,
      unit,
      evidence_point,
      derivation_name,
      derivation_version,
      derivation_input_ids,
      derivation_jsonb,
      evidence_snapshot
    ) values (
      '00000000-0000-4000-8000-000000000101',
      'derived',
      'CropSage normalizer',
      'derived.invalid_index',
      'numeric',
      0.5,
      'dimensionless',
      extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
      'invalid_index',
      '1.0.0',
      array['49999999-9999-4999-8999-999999999999'::uuid],
      '{"method":"deterministic"}'::jsonb,
      '{"source":"derived","variable":"invalid_index"}'::jsonb
    )
  $$,
  'Derived evidence input does not exist.',
  'derived evidence cannot cite nonexistent inputs'
);

select throws_ok(
  $$
    insert into public.evidence_records (
      farm_profile_id,
      provider_fetch_id,
      source_type,
      source_name,
      source_field,
      canonical_variable,
      value_kind,
      value_numeric,
      unit,
      evidence_point,
      evidence_snapshot
    ) values (
      '00000000-0000-4000-8000-000000000101',
      '40000000-0000-4000-8000-000000000001',
      'provider',
      'NASA POWER',
      'T2M',
      'air_temperature.duplicate_c',
      'numeric',
      28.016129,
      'degC',
      extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
      '{"provider":"nasa_power","field":"T2M","value":28.016129,"unit":"degC","period":"Aug"}'::jsonb
    )
  $$,
  '23505',
  'duplicate key value violates unique constraint "evidence_records_profile_hash_unique"',
  'identical evidence snapshots are deduplicated within a farm profile'
);

select lives_ok(
  $$
    insert into public.evidence_records (
      id,
      farm_profile_id,
      provider_fetch_id,
      source_type,
      source_name,
      source_field,
      canonical_variable,
      availability,
      freshness,
      value_kind,
      value_numeric,
      unit,
      fetched_at,
      expires_at,
      evidence_point,
      evidence_snapshot
    ) values (
      '41000000-0000-4000-8000-000000000005',
      '00000000-0000-4000-8000-000000000101',
      '40000000-0000-4000-8000-000000000001',
      'provider',
      'NASA POWER',
      'PRECTOTCORR',
      'precipitation.climatology_mm',
      'available',
      'stale',
      'numeric',
      52.4,
      'mm',
      statement_timestamp() - interval '40 days',
      statement_timestamp() - interval '10 days',
      extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
      '{"provider":"nasa_power","field":"PRECTOTCORR","value":52.4,"unit":"mm","freshness":"stale"}'::jsonb
    )
  $$,
  'stale evidence retains its value while remaining explicitly stale'
);

select throws_ok(
  $$
    insert into public.evidence_records (
      farm_profile_id,
      provider_fetch_id,
      source_type,
      source_name,
      canonical_variable,
      availability,
      freshness,
      value_kind,
      value_numeric,
      unit,
      fetched_at,
      expires_at,
      evidence_point,
      evidence_snapshot
    ) values (
      '00000000-0000-4000-8000-000000000101',
      '40000000-0000-4000-8000-000000000001',
      'provider',
      'NASA POWER',
      'precipitation.invalid_fresh_mm',
      'available',
      'fresh',
      'numeric',
      52.4,
      'mm',
      statement_timestamp() - interval '40 days',
      statement_timestamp() - interval '10 days',
      extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
      '{"provider":"nasa_power","field":"PRECTOTCORR","freshness":"incorrectly_fresh"}'::jsonb
    )
  $$,
  '23514',
  'new row for relation "evidence_records" violates check constraint "evidence_records_freshness_state"',
  'expired evidence cannot be labeled fresh'
);

insert into auth.users (id, aud, role, email, created_at, updated_at)
values
  (
    '50000000-0000-4000-8000-000000000001',
    'authenticated',
    'authenticated',
    'evidence-owner-one@example.test',
    statement_timestamp(),
    statement_timestamp()
  ),
  (
    '50000000-0000-4000-8000-000000000002',
    'authenticated',
    'authenticated',
    'evidence-owner-two@example.test',
    statement_timestamp(),
    statement_timestamp()
  );

insert into public.assessment_sessions (id, owner_user_id)
values
  ('51000000-0000-4000-8000-000000000001', '50000000-0000-4000-8000-000000000001'),
  ('51000000-0000-4000-8000-000000000002', '50000000-0000-4000-8000-000000000002');

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
    '52000000-0000-4000-8000-000000000001',
    '51000000-0000-4000-8000-000000000001',
    'evidence_owner_one_profile',
    1,
    '1.0.0',
    extensions.st_setsrid(extensions.st_makepoint(-96.7970, 32.7767), 4326)::extensions.geography,
    'map_pin',
    '2026-09-01',
    '{"schema_version":"1.0.0","profile_id":"evidence_owner_one_profile"}'::jsonb
  ),
  (
    '52000000-0000-4000-8000-000000000002',
    '51000000-0000-4000-8000-000000000002',
    'evidence_owner_two_profile',
    1,
    '1.0.0',
    extensions.st_setsrid(extensions.st_makepoint(-95.3698, 29.7604), 4326)::extensions.geography,
    'map_pin',
    '2026-09-01',
    '{"schema_version":"1.0.0","profile_id":"evidence_owner_two_profile"}'::jsonb
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
) values
  (
    '53000000-0000-4000-8000-000000000001',
    '52000000-0000-4000-8000-000000000001',
    'farmer',
    'Farm profile',
    'farm.irrigation_available',
    'boolean',
    true,
    extensions.st_setsrid(extensions.st_makepoint(-96.7970, 32.7767), 4326)::extensions.geography,
    '{"variable":"irrigation_available","value":true,"owner":1}'::jsonb
  ),
  (
    '53000000-0000-4000-8000-000000000002',
    '52000000-0000-4000-8000-000000000002',
    'farmer',
    'Farm profile',
    'farm.irrigation_available',
    'boolean',
    false,
    extensions.st_setsrid(extensions.st_makepoint(-95.3698, 29.7604), 4326)::extensions.geography,
    '{"variable":"irrigation_available","value":false,"owner":2}'::jsonb
  );

insert into public.evidence_bundles (
  id,
  farm_profile_id,
  external_bundle_id,
  bundle_version,
  schema_version,
  catalog_version,
  location_snapshot_jsonb
) values
  (
    '54000000-0000-4000-8000-000000000001',
    '52000000-0000-4000-8000-000000000001',
    'evidence_owner_one_bundle',
    1,
    '1.2.0',
    '1.1.0',
    '{"latitude":32.7767,"longitude":-96.7970}'::jsonb
  ),
  (
    '54000000-0000-4000-8000-000000000002',
    '52000000-0000-4000-8000-000000000002',
    'evidence_owner_two_bundle',
    1,
    '1.2.0',
    '1.1.0',
    '{"latitude":29.7604,"longitude":-95.3698}'::jsonb
  );

insert into public.evidence_bundle_records (
  evidence_bundle_id,
  evidence_record_id,
  inclusion_role,
  inclusion_order
) values
  (
    '54000000-0000-4000-8000-000000000001',
    '53000000-0000-4000-8000-000000000001',
    'required',
    1
  ),
  (
    '54000000-0000-4000-8000-000000000002',
    '53000000-0000-4000-8000-000000000002',
    'required',
    1
  );

select lives_ok(
  $$
    insert into public.evidence_bundles (
      id,
      farm_profile_id,
      external_bundle_id,
      bundle_version,
      schema_version,
      catalog_version,
      catalog_source_path,
      location_snapshot_jsonb,
      provider_coverage_jsonb,
      freshness_summary_jsonb
    ) values (
      '42000000-0000-4000-8000-000000000001',
      '00000000-0000-4000-8000-000000000101',
      'plainview_test_bundle',
      1,
      '1.2.0',
      '1.1.0',
      'data/crop-catalog/catalog.json',
      '{"latitude":34.18,"longitude":-101.76,"texas_region_id":"plains","timezone":"America/Chicago"}'::jsonb,
      '{"nasa_power":"available","fortyguard":"available","ssurgo":"available","farmer":"partial","laboratory":"available"}'::jsonb,
      '{"fresh":5,"not_applicable":2}'::jsonb
    )
  $$,
  'an evidence bundle begins in assembling state'
);

select lives_ok(
  $$
    insert into public.evidence_bundle_records (
      evidence_bundle_id,
      evidence_record_id,
      inclusion_role,
      inclusion_order,
      inclusion_reason
    ) values
      ('42000000-0000-4000-8000-000000000001', '41000000-0000-4000-8000-000000000001', 'required', 1, 'Climate baseline'),
      ('42000000-0000-4000-8000-000000000001', '41000000-0000-4000-8000-000000000002', 'required', 2, 'Explicit missing farmer input'),
      ('42000000-0000-4000-8000-000000000001', '41000000-0000-4000-8000-000000000003', 'supplementary', 3, 'Laboratory override'),
      ('42000000-0000-4000-8000-000000000001', '41000000-0000-4000-8000-000000000004', 'contextual', 4, 'Derived normalized metric'),
      ('42000000-0000-4000-8000-000000000001', '41000000-0000-4000-8000-000000000006', 'required', 5, 'FortyGuard temperature extrema'),
      ('42000000-0000-4000-8000-000000000001', '41000000-0000-4000-8000-000000000007', 'supplementary', 6, 'SSURGO component texture'),
      ('42000000-0000-4000-8000-000000000001', '41000000-0000-4000-8000-000000000008', 'supplementary', 7, 'SSURGO component texture')
  $$,
  'ordered evidence records can be assembled into a bundle'
);

select is(
  (
    select record_count
    from public.evidence_bundles
    where id = '42000000-0000-4000-8000-000000000001'
  ),
  7,
  'bundle record_count follows membership automatically'
);

select throws_ok(
  $$
    insert into public.evidence_bundle_records (
      evidence_bundle_id,
      evidence_record_id,
      inclusion_role,
      inclusion_order
    ) values (
      '42000000-0000-4000-8000-000000000001',
      '53000000-0000-4000-8000-000000000002',
      'supplementary',
      5
    )
  $$,
  'Bundle and evidence record must use the same farm profile.',
  'bundle membership cannot cross farm profiles'
);

select lives_ok(
  $$
    update public.evidence_bundles
    set status = 'validated',
        completeness_percent = 92.50,
        assembled_at = statement_timestamp() - interval '2 seconds',
        validated_at = statement_timestamp(),
        validation_summary_jsonb = '{"all_passed":true,"checks":["schema","location","freshness"]}'::jsonb,
        bundle_snapshot = '{"schema_version":"1.2.0","bundle_id":"plainview_test_bundle","status":"validated","location":{"latitude":34.18,"longitude":-101.76,"texas_region_id":"plains","timezone":"America/Chicago"},"catalog":{"version":"1.1.0"},"record_ids":["41000000-0000-4000-8000-000000000001","41000000-0000-4000-8000-000000000002","41000000-0000-4000-8000-000000000003","41000000-0000-4000-8000-000000000004","41000000-0000-4000-8000-000000000006","41000000-0000-4000-8000-000000000007","41000000-0000-4000-8000-000000000008"]}'::jsonb
    where id = '42000000-0000-4000-8000-000000000001'
  $$,
  'a non-empty assembled bundle can transition to validated'
);

select is(
  (
    select bundle_hash
    from public.evidence_bundles
    where id = '42000000-0000-4000-8000-000000000001'
  ),
  (
    select public.jsonb_sha256(bundle_snapshot)
    from public.evidence_bundles
    where id = '42000000-0000-4000-8000-000000000001'
  ),
  'bundle hash is generated from the exact stored snapshot'
);

select is(
  (
    select bundle_snapshot
    from public.evidence_bundles
    where id = '42000000-0000-4000-8000-000000000001'
  ),
  '{"schema_version":"1.2.0","bundle_id":"plainview_test_bundle","status":"validated","location":{"latitude":34.18,"longitude":-101.76,"texas_region_id":"plains","timezone":"America/Chicago"},"catalog":{"version":"1.1.0"},"record_ids":["41000000-0000-4000-8000-000000000001","41000000-0000-4000-8000-000000000002","41000000-0000-4000-8000-000000000003","41000000-0000-4000-8000-000000000004","41000000-0000-4000-8000-000000000006","41000000-0000-4000-8000-000000000007","41000000-0000-4000-8000-000000000008"]}'::jsonb,
  'an EvidenceBundle snapshot round-trips without structural loss'
);

select is(
  (
    select array_agg(evidence_record_id order by inclusion_order)
    from public.evidence_bundle_records
    where evidence_bundle_id = '42000000-0000-4000-8000-000000000001'
  ),
  array[
    '41000000-0000-4000-8000-000000000001'::uuid,
    '41000000-0000-4000-8000-000000000002'::uuid,
    '41000000-0000-4000-8000-000000000003'::uuid,
    '41000000-0000-4000-8000-000000000004'::uuid,
    '41000000-0000-4000-8000-000000000006'::uuid,
    '41000000-0000-4000-8000-000000000007'::uuid,
    '41000000-0000-4000-8000-000000000008'::uuid
  ],
  'bundle membership preserves deterministic inclusion order'
);

select throws_ok(
  $$
    insert into public.evidence_bundle_records (
      evidence_bundle_id,
      evidence_record_id,
      inclusion_role,
      inclusion_order
    ) values (
      '42000000-0000-4000-8000-000000000001',
      '41000000-0000-4000-8000-000000000005',
      'supplementary',
      5
    )
  $$,
  'Terminal evidence bundle membership cannot be changed.',
  'validated bundle membership cannot be changed'
);

select lives_ok(
  $$
    insert into public.evidence_bundles (
      id,
      farm_profile_id,
      external_bundle_id,
      bundle_version,
      supersedes_bundle_id,
      schema_version,
      catalog_version,
      location_snapshot_jsonb
    ) values (
      '42000000-0000-4000-8000-000000000002',
      '00000000-0000-4000-8000-000000000101',
      'plainview_test_bundle_v2',
      2,
      '42000000-0000-4000-8000-000000000001',
      '1.2.0',
      '1.1.0',
      '{"latitude":34.18,"longitude":-101.76,"texas_region_id":"plains"}'::jsonb
    )
  $$,
  'a sequential successor evidence bundle can be created'
);

select throws_ok(
  $$
    update public.evidence_bundles
    set status = 'validated',
        completeness_percent = 100,
        assembled_at = statement_timestamp() - interval '1 second',
        validated_at = statement_timestamp(),
        bundle_snapshot = '{"schema_version":"1.2.0","bundle_id":"plainview_test_bundle_v2","status":"validated"}'::jsonb
    where id = '42000000-0000-4000-8000-000000000002'
  $$,
  'Validated bundle record_count must match non-empty bundle membership.',
  'an empty bundle cannot be validated'
);

select throws_ok(
  $$
    insert into public.evidence_bundles (
      farm_profile_id,
      external_bundle_id,
      bundle_version,
      supersedes_bundle_id,
      schema_version,
      catalog_version,
      location_snapshot_jsonb
    ) values (
      '00000000-0000-4000-8000-000000000101',
      'plainview_test_bundle_v4',
      4,
      '42000000-0000-4000-8000-000000000002',
      '1.2.0',
      '1.1.0',
      '{"latitude":34.18,"longitude":-101.76}'::jsonb
    )
  $$,
  'Evidence bundle versions must increase by exactly one.',
  'evidence bundle versions cannot skip a predecessor number'
);

do $$
begin
  perform set_config(
    'request.jwt.claim.sub',
    '50000000-0000-4000-8000-000000000001',
    true
  );
  perform set_config(
    'request.jwt.claims',
    '{"sub":"50000000-0000-4000-8000-000000000001","role":"authenticated"}',
    true
  );
end;
$$;
set local role authenticated;

select is(
  (
    select count(*)
    from public.evidence_records
    where farm_profile_id in (
      '52000000-0000-4000-8000-000000000001',
      '52000000-0000-4000-8000-000000000002'
    )
  ),
  1::bigint,
  'an authenticated user sees evidence records only for their own profile'
);
select is(
  (
    select count(*)
    from public.evidence_bundles
    where farm_profile_id in (
      '52000000-0000-4000-8000-000000000001',
      '52000000-0000-4000-8000-000000000002'
    )
  ),
  1::bigint,
  'an authenticated user sees evidence bundles only for their own profile'
);
select is(
  (
    select count(*)
    from public.evidence_bundle_records
    where evidence_bundle_id in (
      '54000000-0000-4000-8000-000000000001',
      '54000000-0000-4000-8000-000000000002'
    )
  ),
  1::bigint,
  'an authenticated user sees bundle membership only for their own profile'
);

reset role;

select * from finish();

rollback;
