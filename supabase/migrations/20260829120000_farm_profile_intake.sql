-- Atomic server-only intake for a validated FarmProfile contract document.

create or replace function public.create_farm_profile(
  p_owner_user_id uuid,
  p_profile_snapshot jsonb,
  p_missing_fields text[] default '{}'::text[],
  p_completeness_notes text[] default '{}'::text[]
)
returns table (
  assessment_session_id uuid,
  farm_profile_id uuid,
  external_profile_id text
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_assessment_session_id uuid := extensions.gen_random_uuid();
  v_farm_profile_id uuid := extensions.gen_random_uuid();
  v_external_profile_id text := p_profile_snapshot ->> 'profile_id';
  v_location_source public.location_source;
  v_latitude double precision;
  v_longitude double precision;
begin
  if p_owner_user_id is null then
    raise exception 'A profile owner is required.';
  end if;

  if p_profile_snapshot is null or jsonb_typeof(p_profile_snapshot) <> 'object' then
    raise exception 'A FarmProfile object is required.';
  end if;

  v_latitude := (p_profile_snapshot #>> '{location,latitude}')::double precision;
  v_longitude := (p_profile_snapshot #>> '{location,longitude}')::double precision;
  v_location_source := (p_profile_snapshot #>> '{location,source}')::public.location_source;

  insert into public.assessment_sessions (
    id,
    owner_user_id,
    status,
    expires_at
  ) values (
    v_assessment_session_id,
    p_owner_user_id,
    'active',
    statement_timestamp() + interval '30 days'
  );

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
    planned_planting_date,
    planned_planting_month,
    planting_flexibility_days,
    requested_crop_id,
    irrigation_jsonb,
    soil_overrides_jsonb,
    current_soil_moisture_jsonb,
    recent_rainfall_jsonb,
    farmer_goal_jsonb,
    missing_fields,
    completeness_notes,
    profile_snapshot
  ) values (
    v_farm_profile_id,
    v_assessment_session_id,
    v_external_profile_id,
    1,
    p_profile_snapshot ->> 'schema_version',
    'ready',
    nullif(p_profile_snapshot ->> 'captured_at', '')::timestamptz,
    extensions.st_setsrid(
      extensions.st_makepoint(v_longitude, v_latitude),
      4326
    )::extensions.geography,
    nullif(p_profile_snapshot #>> '{location,farm_name}', ''),
    nullif(p_profile_snapshot #>> '{location,location_label}', ''),
    v_location_source,
    nullif(p_profile_snapshot #>> '{planting,planned_date}', '')::date,
    case
      when nullif(p_profile_snapshot #>> '{planting,planned_month}', '') is null then null
      else ((p_profile_snapshot #>> '{planting,planned_month}') || '-01')::date
    end,
    nullif(p_profile_snapshot #>> '{planting,flexibility_days}', '')::smallint,
    nullif(p_profile_snapshot ->> 'requested_crop_id', ''),
    case when p_profile_snapshot ? 'irrigation' then p_profile_snapshot -> 'irrigation' end,
    case when p_profile_snapshot ? 'soil_overrides' then p_profile_snapshot -> 'soil_overrides' end,
    case when p_profile_snapshot ? 'current_soil_moisture' then p_profile_snapshot -> 'current_soil_moisture' end,
    case when p_profile_snapshot ? 'recent_rainfall' then p_profile_snapshot -> 'recent_rainfall' end,
    case when p_profile_snapshot ? 'farmer_goal' then p_profile_snapshot -> 'farmer_goal' end,
    coalesce(p_missing_fields, '{}'::text[]),
    coalesce(p_completeness_notes, '{}'::text[]),
    p_profile_snapshot
  );

  update public.assessment_sessions
  set active_profile_id = v_farm_profile_id
  where id = v_assessment_session_id;

  return query
  select v_assessment_session_id, v_farm_profile_id, v_external_profile_id;
end;
$$;

revoke all on function public.create_farm_profile(uuid, jsonb, text[], text[])
  from public, anon, authenticated;
grant execute on function public.create_farm_profile(uuid, jsonb, text[], text[])
  to service_role;

comment on function public.create_farm_profile(uuid, jsonb, text[], text[]) is
  'Creates an owned assessment session and its initial immutable ready FarmProfile in one transaction.';
