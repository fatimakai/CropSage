begin;

set local search_path = public, extensions;

select plan(9);

select has_function(
  'public',
  'create_farm_profile',
  array['uuid', 'jsonb', 'text[]', 'text[]'],
  'server farm profile intake function exists'
);

select ok(
  not has_function_privilege(
    'anon',
    'public.create_farm_profile(uuid,jsonb,text[],text[])',
    'EXECUTE'
  ),
  'anonymous database clients cannot call farm profile intake'
);

select ok(
  not has_function_privilege(
    'authenticated',
    'public.create_farm_profile(uuid,jsonb,text[],text[])',
    'EXECUTE'
  ),
  'authenticated browser clients cannot call farm profile intake'
);

select ok(
  has_function_privilege(
    'service_role',
    'public.create_farm_profile(uuid,jsonb,text[],text[])',
    'EXECUTE'
  ),
  'the server service role can call farm profile intake'
);

insert into auth.users (id, aud, role, created_at, updated_at)
values (
  '10000000-0000-4000-8000-000000000007',
  'authenticated',
  'authenticated',
  statement_timestamp(),
  statement_timestamp()
);

create temporary table intake_result as
select *
from public.create_farm_profile(
  '10000000-0000-4000-8000-000000000007',
  '{
    "schema_version":"1.0.0",
    "profile_id":"frontend_intake_test",
    "captured_at":"2026-08-29T12:00:00Z",
    "location":{
      "latitude":34.18,
      "longitude":-101.76,
      "farm_name":"Test farm",
      "location_label":"Plainview, Texas",
      "source":"demo_farm"
    },
    "planting":{"planned_month":"2026-10","flexibility_days":14},
    "requested_crop_id":null,
    "irrigation":{"availability":"unknown","reliability":"unknown"}
  }'::jsonb,
  array['soil_overrides', 'current_soil_moisture'],
  array['Optional field evidence was not supplied.']
);

select is(
  (
    select owner_user_id
    from public.assessment_sessions
    where id = (select assessment_session_id from intake_result)
  ),
  '10000000-0000-4000-8000-000000000007'::uuid,
  'the assessment session belongs to the supplied authenticated user'
);

select is(
  (
    select active_profile_id
    from public.assessment_sessions
    where id = (select assessment_session_id from intake_result)
  ),
  (select farm_profile_id from intake_result),
  'the new profile is active for its assessment session'
);

select is(
  (
    select status::text
    from public.farm_profiles
    where id = (select farm_profile_id from intake_result)
  ),
  'ready',
  'the validated intake profile is ready'
);

select is(
  (
    select planned_planting_month
    from public.farm_profiles
    where id = (select farm_profile_id from intake_result)
  ),
  '2026-10-01'::date,
  'the planting month is normalized to the first day'
);

select is(
  (
    select profile_snapshot ->> 'profile_id'
    from public.farm_profiles
    where id = (select farm_profile_id from intake_result)
  ),
  'frontend_intake_test',
  'the exact validated profile snapshot is retained'
);

select * from finish();

rollback;
