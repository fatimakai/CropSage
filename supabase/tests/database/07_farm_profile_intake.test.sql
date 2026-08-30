begin;

set local search_path = public, extensions;

select plan(14);

select has_function(
  'public',
  'create_farm_profile',
  array['uuid', 'jsonb', 'text[]', 'text[]', 'jsonb'],
  'server farm profile intake function exists'
);

select ok(
  not has_function_privilege(
    'anon',
    'public.create_farm_profile(uuid,jsonb,text[],text[],jsonb)',
    'EXECUTE'
  ),
  'anonymous database clients cannot call farm profile intake'
);

select ok(
  not has_function_privilege(
    'authenticated',
    'public.create_farm_profile(uuid,jsonb,text[],text[],jsonb)',
    'EXECUTE'
  ),
  'authenticated browser clients cannot call farm profile intake'
);

select ok(
  has_function_privilege(
    'service_role',
    'public.create_farm_profile(uuid,jsonb,text[],text[],jsonb)',
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
  array['Optional field evidence was not supplied.'],
  '{}'::jsonb
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

create temporary table boundary_intake_result as
select *
from public.create_farm_profile(
  '10000000-0000-4000-8000-000000000007',
  '{
    "schema_version":"1.0.0",
    "profile_id":"frontend_boundary_intake_test",
    "captured_at":"2026-08-30T12:00:00Z",
    "location":{
      "latitude":34.18,
      "longitude":-101.76,
      "source":"map_pin"
    },
    "planting":{"planned_month":"2026-10"},
    "farm_boundary":{
      "type":"Polygon",
      "coordinates":[[
        [-101.77,34.17],
        [-101.75,34.17],
        [-101.75,34.19],
        [-101.77,34.19],
        [-101.77,34.17]
      ]]
    }
  }'::jsonb,
  array['soil_overrides', 'current_soil_moisture'],
  array['Optional field evidence was not supplied.'],
  '{
    "farm_boundary":{
      "source":"usda_csb",
      "source_id":"481825000000001",
      "dataset_name":"usda_nass_crop_sequence_boundaries",
      "dataset_version":"2018-2025-rev23",
      "farmer_confirmed":true,
      "confirmed_at":"2026-08-30T12:00:00Z"
    }
  }'::jsonb
);

select is(
  (
    select extensions.st_geometrytype(farm_boundary::extensions.geometry)
    from public.farm_profiles
    where id = (select farm_profile_id from boundary_intake_result)
  ),
  'ST_MultiPolygon',
  'a GeoJSON Polygon is normalized to the database MultiPolygon contract'
);

select is(
  (
    select profile_snapshot #>> '{farm_boundary,type}'
    from public.farm_profiles
    where id = (select farm_profile_id from boundary_intake_result)
  ),
  'Polygon',
  'the immutable engine snapshot retains the submitted GeoJSON geometry type'
);

select is(
  (
    select field_sources_jsonb #>> '{farm_boundary,source}'
    from public.farm_profiles
    where id = (select farm_profile_id from boundary_intake_result)
  ),
  'usda_csb',
  'boundary provenance is stored outside the engine snapshot'
);

select is(
  (
    select field_sources_jsonb #>> '{farm_boundary,source_id}'
    from public.farm_profiles
    where id = (select farm_profile_id from boundary_intake_result)
  ),
  '481825000000001',
  'the selected USDA CSB identifier is retained'
);

select ok(
  (
    select (field_sources_jsonb #>> '{farm_boundary,area_square_meters}')::numeric > 0
    from public.farm_profiles
    where id = (select farm_profile_id from boundary_intake_result)
  ),
  'the database calculates and stores a positive authoritative field area'
);

select * from finish();

rollback;
