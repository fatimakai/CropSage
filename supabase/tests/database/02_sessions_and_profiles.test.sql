begin;

set local search_path = public, extensions;

select plan(29);

select has_table('public', 'assessment_sessions', 'assessment sessions table exists');
select has_table('public', 'farm_profiles', 'farm profiles table exists');
select has_column('public', 'assessment_sessions', 'active_profile_id', 'session tracks its active profile');
select has_column('public', 'farm_profiles', 'farm_point', 'profile stores an authoritative point');
select has_column('public', 'farm_profiles', 'farm_boundary', 'profile supports an optional boundary');
select has_column('public', 'farm_profiles', 'profile_snapshot', 'profile retains its exact contract document');
select has_column('public', 'farm_profiles', 'input_hash', 'profile stores a deterministic input hash');
select has_type('public', 'location_source', 'location source enum exists');

select col_type_is(
  'public',
  'farm_profiles',
  'farm_point',
  'extensions.geography(Point,4326)',
  'farm point uses PostGIS geography Point SRID 4326'
);
select col_type_is(
  'public',
  'farm_profiles',
  'farm_boundary',
  'extensions.geography(MultiPolygon,4326)',
  'farm boundary uses PostGIS geography MultiPolygon SRID 4326'
);

select has_fk('public', 'farm_profiles', 'farm profile belongs to an assessment session');
select has_fk('public', 'assessment_sessions', 'active profile is constrained to its session');

select ok(
  (select relrowsecurity from pg_class where oid = 'public.assessment_sessions'::regclass),
  'assessment sessions have RLS enabled'
);
select ok(
  (select relrowsecurity from pg_class where oid = 'public.farm_profiles'::regclass),
  'farm profiles have RLS enabled'
);
select ok(
  not has_table_privilege('anon', 'public.assessment_sessions', 'SELECT'),
  'anonymous users cannot read assessment sessions'
);
select ok(
  not has_table_privilege('authenticated', 'public.farm_profiles', 'INSERT'),
  'authenticated browser users cannot insert farm profiles directly'
);

select is(
  (select count(*) from public.farm_profiles where external_profile_id = 'plainview_aug_2026_demo'),
  1::bigint,
  'the synthetic Plainview FarmProfile fixture is seeded once'
);
select is(
  (
    select active_profile_id
    from public.assessment_sessions
    where id = '00000000-0000-4000-8000-000000000001'
  ),
  '00000000-0000-4000-8000-000000000101'::uuid,
  'the seed session points at its active profile'
);
select matches(
  (
    select input_hash
    from public.farm_profiles
    where external_profile_id = 'plainview_aug_2026_demo'
  ),
  '^[0-9a-f]{64}$',
  'the generated profile hash is lowercase SHA-256'
);
select is(
  public.jsonb_sha256('{"b":2,"a":1}'::jsonb),
  public.jsonb_sha256('{"a":1,"b":2}'::jsonb),
  'JSON object key order does not change the canonical hash'
);

insert into public.assessment_sessions (id)
values ('00000000-0000-4000-8000-000000000002');

select lives_ok(
  $$
    insert into public.farm_profiles (
      id,
      assessment_session_id,
      external_profile_id,
      profile_version,
      schema_version,
      farm_point,
      location_source,
      planned_planting_date,
      profile_snapshot
    ) values (
      '00000000-0000-4000-8000-000000000201',
      '00000000-0000-4000-8000-000000000002',
      'contract_test_profile_v1',
      1,
      '1.0.0',
      extensions.st_setsrid(extensions.st_makepoint(-97.7431, 30.2672), 4326)::extensions.geography,
      'map_pin',
      '2026-09-15',
      '{"schema_version":"1.0.0","profile_id":"contract_test_profile_v1","location":{"latitude":30.2672,"longitude":-97.7431},"planting":{"planned_date":"2026-09-15"}}'::jsonb
    )
  $$,
  'a valid date-based profile can be inserted'
);

select lives_ok(
  $$
    insert into public.farm_profiles (
      id,
      assessment_session_id,
      external_profile_id,
      profile_version,
      schema_version,
      supersedes_profile_id,
      farm_point,
      location_source,
      planned_planting_month,
      profile_snapshot
    ) values (
      '00000000-0000-4000-8000-000000000202',
      '00000000-0000-4000-8000-000000000002',
      'contract_test_profile_v2',
      2,
      '1.0.0',
      '00000000-0000-4000-8000-000000000201',
      extensions.st_setsrid(extensions.st_makepoint(-97.7431, 30.2672), 4326)::extensions.geography,
      'map_pin',
      '2026-10-01',
      '{"schema_version":"1.0.0","profile_id":"contract_test_profile_v2","location":{"latitude":30.2672,"longitude":-97.7431},"planting":{"planned_month":"2026-10"}}'::jsonb
    )
  $$,
  'a sequential successor profile can be inserted'
);

select throws_ok(
  $$
    insert into public.farm_profiles (
      assessment_session_id,
      external_profile_id,
      profile_version,
      schema_version,
      supersedes_profile_id,
      farm_point,
      location_source,
      planned_planting_month,
      profile_snapshot
    ) values (
      '00000000-0000-4000-8000-000000000002',
      'contract_test_profile_v4',
      4,
      '1.0.0',
      '00000000-0000-4000-8000-000000000202',
      extensions.st_setsrid(extensions.st_makepoint(-97.7431, 30.2672), 4326)::extensions.geography,
      'map_pin',
      '2026-11-01',
      '{"schema_version":"1.0.0"}'::jsonb
    )
  $$,
  'Farm profile versions must increase by exactly one.',
  'profile versions cannot skip a predecessor number'
);

select throws_ok(
  $$
    insert into public.farm_profiles (
      assessment_session_id,
      external_profile_id,
      profile_version,
      schema_version,
      farm_point,
      location_source,
      planned_planting_date,
      planned_planting_month,
      profile_snapshot
    ) values (
      '00000000-0000-4000-8000-000000000002',
      'contract_test_invalid_planting',
      3,
      '1.0.0',
      extensions.st_setsrid(extensions.st_makepoint(-97.7431, 30.2672), 4326)::extensions.geography,
      'map_pin',
      '2026-11-15',
      '2026-11-01',
      '{"schema_version":"1.0.0"}'::jsonb
    )
  $$,
  '23514',
  'new row for relation "farm_profiles" violates check constraint "farm_profiles_planting_time_exactly_one"',
  'a profile cannot provide both planting date and planting month'
);

select throws_ok(
  $$
    insert into public.farm_profiles (
      assessment_session_id,
      external_profile_id,
      profile_version,
      schema_version,
      supersedes_profile_id,
      farm_point,
      farm_boundary,
      location_source,
      planned_planting_month,
      profile_snapshot
    ) values (
      '00000000-0000-4000-8000-000000000002',
      'contract_test_outside_boundary',
      3,
      '1.0.0',
      '00000000-0000-4000-8000-000000000202',
      extensions.st_setsrid(extensions.st_makepoint(-97.7431, 30.2672), 4326)::extensions.geography,
      extensions.st_multi(extensions.st_geomfromtext('POLYGON((-101 34,-101 35,-100 35,-100 34,-101 34))', 4326))::extensions.geography,
      'map_pin',
      '2026-11-01',
      '{"schema_version":"1.0.0"}'::jsonb
    )
  $$,
  '23514',
  'new row for relation "farm_profiles" violates check constraint "farm_profiles_point_within_boundary"',
  'a farm point must fall inside its optional boundary'
);

select lives_ok(
  $$
    update public.assessment_sessions
    set active_profile_id = '00000000-0000-4000-8000-000000000202'
    where id = '00000000-0000-4000-8000-000000000002'
  $$,
  'a session can select a profile that belongs to it'
);

select throws_ok(
  $$
    update public.assessment_sessions
    set active_profile_id = '00000000-0000-4000-8000-000000000101'
    where id = '00000000-0000-4000-8000-000000000002'
  $$,
  '23503',
  'insert or update on table "assessment_sessions" violates foreign key constraint "assessment_sessions_active_profile_fk"',
  'a session cannot select a profile owned by another session'
);

insert into auth.users (id, aud, role, email, created_at, updated_at)
values
  (
    '10000000-0000-4000-8000-000000000001',
    'authenticated',
    'authenticated',
    'owner-one@example.test',
    statement_timestamp(),
    statement_timestamp()
  ),
  (
    '10000000-0000-4000-8000-000000000002',
    'authenticated',
    'authenticated',
    'owner-two@example.test',
    statement_timestamp(),
    statement_timestamp()
  );

insert into public.assessment_sessions (id, owner_user_id)
values
  ('00000000-0000-4000-8000-000000000003', '10000000-0000-4000-8000-000000000001'),
  ('00000000-0000-4000-8000-000000000004', '10000000-0000-4000-8000-000000000002');

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
    '00000000-0000-4000-8000-000000000301',
    '00000000-0000-4000-8000-000000000003',
    'owner_one_profile',
    1,
    '1.0.0',
    extensions.st_setsrid(extensions.st_makepoint(-96.7970, 32.7767), 4326)::extensions.geography,
    'map_pin',
    '2026-09-01',
    '{"schema_version":"1.0.0","profile_id":"owner_one_profile"}'::jsonb
  ),
  (
    '00000000-0000-4000-8000-000000000401',
    '00000000-0000-4000-8000-000000000004',
    'owner_two_profile',
    1,
    '1.0.0',
    extensions.st_setsrid(extensions.st_makepoint(-95.3698, 29.7604), 4326)::extensions.geography,
    'map_pin',
    '2026-09-01',
    '{"schema_version":"1.0.0","profile_id":"owner_two_profile"}'::jsonb
  );

do $$
begin
  perform set_config(
    'request.jwt.claim.sub',
    '10000000-0000-4000-8000-000000000001',
    true
  );
  perform set_config(
    'request.jwt.claims',
    '{"sub":"10000000-0000-4000-8000-000000000001","role":"authenticated"}',
    true
  );
end;
$$;
set local role authenticated;

select is(
  (
    select count(*)
    from public.assessment_sessions
    where id in (
      '00000000-0000-4000-8000-000000000003',
      '00000000-0000-4000-8000-000000000004'
    )
  ),
  1::bigint,
  'an authenticated user sees only their own assessment session'
);
select is(
  (
    select count(*)
    from public.farm_profiles
    where assessment_session_id in (
      '00000000-0000-4000-8000-000000000003',
      '00000000-0000-4000-8000-000000000004'
    )
  ),
  1::bigint,
  'an authenticated user sees only profiles in their own session'
);

reset role;

select * from finish();

rollback;
