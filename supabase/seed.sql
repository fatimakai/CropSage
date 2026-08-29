-- Synthetic Plainview fixture used by local development and contract tests.

insert into public.assessment_sessions (
  id,
  status,
  created_at,
  updated_at
) values (
  '00000000-0000-4000-8000-000000000001',
  'active',
  '2026-08-28T02:00:00Z',
  '2026-08-28T02:00:00Z'
) on conflict (id) do nothing;

insert into public.farm_profiles (
  id,
  assessment_session_id,
  external_profile_id,
  profile_version,
  schema_version,
  status,
  captured_at,
  farm_point,
  farm_name,
  location_label,
  location_source,
  resolved_region_id,
  region_resolution_method,
  region_resolution_version,
  timezone,
  timezone_resolution_method,
  timezone_resolution_version,
  location_resolution_jsonb,
  planned_planting_month,
  planting_flexibility_days,
  irrigation_jsonb,
  missing_fields,
  completeness_notes,
  profile_snapshot,
  created_at,
  updated_at
) values (
  '00000000-0000-4000-8000-000000000101',
  '00000000-0000-4000-8000-000000000001',
  'plainview_aug_2026_demo',
  1,
  '1.0.0',
  'ready',
  '2026-08-28T02:00:00Z',
  extensions.st_setsrid(extensions.st_makepoint(-101.76, 34.18), 4326)::extensions.geography,
  'Plainview demonstration farm',
  'Plainview, Texas',
  'demo_farm',
  'plains',
  'handoff_fixture',
  '1.1.0',
  'America/Chicago',
  'handoff_fixture',
  '1.1.0',
  '{"region_source":"sample_evidence_bundle","timezone_source":"sample_evidence_bundle"}'::jsonb,
  '2026-08-01',
  30,
  '{"availability":"yes","reliability":"reliable","method":"center_pivot","water_source":"well","notes":"Hackathon demonstration assumption, not a measured fact about a real farm."}'::jsonb,
  array['farm_boundary', 'soil_overrides', 'current_soil_moisture', 'recent_rainfall', 'farmer_goal'],
  array['Synthetic handoff fixture; not a real farm record.'],
  '{"schema_version":"1.0.0","profile_id":"plainview_aug_2026_demo","captured_at":"2026-08-28T02:00:00Z","location":{"latitude":34.18,"longitude":-101.76,"farm_name":"Plainview demonstration farm","location_label":"Plainview, Texas","source":"demo_farm"},"planting":{"planned_month":"2026-08","flexibility_days":30},"requested_crop_id":null,"irrigation":{"availability":"yes","reliability":"reliable","method":"center_pivot","water_source":"well","notes":"Hackathon demonstration assumption, not a measured fact about a real farm."}}'::jsonb,
  '2026-08-28T02:00:00Z',
  '2026-08-28T02:00:00Z'
) on conflict (id) do nothing;

update public.assessment_sessions
set active_profile_id = '00000000-0000-4000-8000-000000000101'
where id = '00000000-0000-4000-8000-000000000001'
  and active_profile_id is null;
