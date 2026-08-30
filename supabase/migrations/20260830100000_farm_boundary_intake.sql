-- Persist validated GeoJSON farm boundaries without changing the engine contract document.

drop function public.create_farm_profile(uuid, jsonb, text[], text[]);

create function public.create_farm_profile(
  p_owner_user_id uuid,
  p_profile_snapshot jsonb,
  p_missing_fields text[] default '{}'::text[],
  p_completeness_notes text[] default '{}'::text[],
  p_field_sources jsonb default '{}'::jsonb
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
  v_farm_point extensions.geography(Point, 4326);
  v_boundary_geometry extensions.geometry;
  v_farm_boundary extensions.geography(MultiPolygon, 4326);
  v_boundary_source jsonb;
  v_field_sources jsonb := coalesce(p_field_sources, '{}'::jsonb);
begin
  if p_owner_user_id is null then
    raise exception 'A profile owner is required.';
  end if;

  if p_profile_snapshot is null or jsonb_typeof(p_profile_snapshot) <> 'object' then
    raise exception 'A FarmProfile object is required.';
  end if;

  if jsonb_typeof(v_field_sources) <> 'object' then
    raise exception 'Field sources must be a JSON object.';
  end if;

  v_latitude := (p_profile_snapshot #>> '{location,latitude}')::double precision;
  v_longitude := (p_profile_snapshot #>> '{location,longitude}')::double precision;
  v_location_source := (p_profile_snapshot #>> '{location,source}')::public.location_source;
  v_farm_point := extensions.st_setsrid(
    extensions.st_makepoint(v_longitude, v_latitude),
    4326
  )::extensions.geography;

  if p_profile_snapshot ? 'farm_boundary' then
    if not (v_field_sources ? 'farm_boundary') then
      raise exception 'Farm boundary source metadata is required.';
    end if;

    v_boundary_source := v_field_sources -> 'farm_boundary';
    if jsonb_typeof(v_boundary_source) <> 'object' then
      raise exception 'Farm boundary source metadata must be a JSON object.';
    end if;

    if coalesce((v_boundary_source ->> 'farmer_confirmed')::boolean, false) is not true then
      raise exception 'A farm boundary must be confirmed before it is stored.';
    end if;

    v_boundary_geometry := extensions.st_setsrid(
      extensions.st_geomfromgeojson((p_profile_snapshot -> 'farm_boundary')::text),
      4326
    );

    if extensions.st_geometrytype(v_boundary_geometry) not in ('ST_Polygon', 'ST_MultiPolygon') then
      raise exception 'Farm boundary must be a Polygon or MultiPolygon.';
    end if;

    v_farm_boundary := extensions.st_multi(v_boundary_geometry)::extensions.geography;

    if extensions.st_isempty(v_boundary_geometry) or not extensions.st_isvalid(v_boundary_geometry) then
      raise exception 'Farm boundary must be non-empty and valid.';
    end if;

    if not extensions.st_covers(v_boundary_geometry, v_farm_point::extensions.geometry) then
      raise exception 'The farm point must fall inside the farm boundary.';
    end if;

    v_boundary_source := v_boundary_source || pg_catalog.jsonb_build_object(
      'area_square_meters',
      round(extensions.st_area(v_farm_boundary)::numeric, 2)
    );
    v_field_sources := v_field_sources || pg_catalog.jsonb_build_object(
      'farm_boundary',
      v_boundary_source
    );
  elsif v_field_sources ? 'farm_boundary' then
    raise exception 'Farm boundary source metadata cannot be stored without a boundary.';
  end if;

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
    farm_boundary,
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
    field_sources_jsonb,
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
    v_farm_point,
    v_farm_boundary,
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
    v_field_sources,
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

revoke all on function public.create_farm_profile(uuid, jsonb, text[], text[], jsonb)
  from public, anon, authenticated;
grant execute on function public.create_farm_profile(uuid, jsonb, text[], text[], jsonb)
  to service_role;

comment on function public.create_farm_profile(uuid, jsonb, text[], text[], jsonb) is
  'Creates an owned assessment session and initial immutable FarmProfile, including an optional confirmed farm boundary.';
