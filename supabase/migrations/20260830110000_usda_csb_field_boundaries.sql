-- Server-only USDA NASS Crop Sequence Boundary reference data and viewport queries.

create table public.usda_csb_fields (
  dataset_version text not null,
  field_id text not null,
  state_fips text not null,
  county_fips text,
  county_name text,
  area_acres numeric(14, 4) not null,
  boundary extensions.geometry(MultiPolygon, 4326) not null,
  representative_point extensions.geometry(Point, 4326) not null,
  source_url text not null default
    'https://www.nass.usda.gov/Research_and_Science/Crop-Sequence-Boundaries/',
  imported_at timestamptz not null default statement_timestamp(),

  constraint usda_csb_fields_primary_key
    primary key (dataset_version, field_id),
  constraint usda_csb_fields_dataset_version_format
    check (dataset_version ~ '^[0-9]{4}-[0-9]{4}-rev[0-9]+$'),
  constraint usda_csb_fields_field_id_format
    check (field_id ~ '^48[0-9]{13}$'),
  constraint usda_csb_fields_texas_only
    check (state_fips = '48'),
  constraint usda_csb_fields_county_fips_format
    check (county_fips is null or county_fips ~ '^[0-9]{3}$'),
  constraint usda_csb_fields_county_name_length
    check (county_name is null or char_length(btrim(county_name)) between 1 and 120),
  constraint usda_csb_fields_area_positive
    check (area_acres > 0),
  constraint usda_csb_fields_boundary_valid
    check (
      not extensions.st_isempty(boundary)
      and extensions.st_isvalid(boundary)
      and extensions.st_srid(boundary) = 4326
    ),
  constraint usda_csb_fields_point_covered
    check (extensions.st_covers(boundary, representative_point)),
  constraint usda_csb_fields_source_https
    check (source_url ~ '^https://')
);

create index usda_csb_fields_boundary_gist_idx
  on public.usda_csb_fields using gist (boundary);

create index usda_csb_fields_version_county_idx
  on public.usda_csb_fields(dataset_version, county_fips);

alter table public.usda_csb_fields enable row level security;

revoke all on table public.usda_csb_fields from public, anon, authenticated;
grant select on table public.usda_csb_fields to service_role;

create function public.import_usda_csb_fields(
  p_dataset_version text,
  p_features jsonb
)
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_feature jsonb;
  v_properties jsonb;
  v_geometry extensions.geometry;
  v_field_id text;
  v_state_fips text;
  v_area_acres numeric;
  v_imported_count integer := 0;
begin
  if p_dataset_version is null
    or p_dataset_version !~ '^[0-9]{4}-[0-9]{4}-rev[0-9]+$'
  then
    raise exception 'A valid CSB dataset version is required.';
  end if;

  if p_features is null
    or pg_catalog.jsonb_typeof(p_features) <> 'array'
    or pg_catalog.jsonb_array_length(p_features) not between 1 and 250
  then
    raise exception 'CSB imports require an array containing 1 to 250 features.';
  end if;

  for v_feature in
    select value
    from pg_catalog.jsonb_array_elements(p_features)
  loop
    if v_feature ->> 'type' <> 'Feature'
      or pg_catalog.jsonb_typeof(v_feature -> 'geometry') <> 'object'
      or pg_catalog.jsonb_typeof(v_feature -> 'properties') <> 'object'
    then
      raise exception 'Every CSB import item must be a GeoJSON Feature.';
    end if;

    v_properties := v_feature -> 'properties';
    v_field_id := nullif(btrim(v_properties ->> 'CSBID'), '');
    v_state_fips := nullif(btrim(v_properties ->> 'STATEFIPS'), '');

    if v_field_id is null or v_field_id !~ '^48[0-9]{13}$' then
      raise exception 'A Texas CSBID is required for every imported feature.';
    end if;

    if v_state_fips is distinct from '48' then
      raise exception 'Only Texas USDA CSB features can be imported.';
    end if;

    begin
      v_area_acres := (v_properties ->> 'CSBACRES')::numeric;
    exception when invalid_text_representation then
      raise exception 'CSBACRES must be numeric for field %.', v_field_id;
    end;

    if v_area_acres is null or v_area_acres <= 0 then
      raise exception 'CSBACRES must be positive for field %.', v_field_id;
    end if;

    begin
      v_geometry := extensions.st_setsrid(
        extensions.st_geomfromgeojson((v_feature -> 'geometry')::text),
        4326
      );
    exception when others then
      raise exception 'Field % contains invalid GeoJSON geometry.', v_field_id;
    end;

    if extensions.st_geometrytype(v_geometry) not in ('ST_Polygon', 'ST_MultiPolygon')
      or extensions.st_isempty(v_geometry)
      or not extensions.st_isvalid(v_geometry)
    then
      raise exception 'Field % must contain a valid Polygon or MultiPolygon.', v_field_id;
    end if;

    v_geometry := extensions.st_multi(v_geometry);

    if not extensions.st_intersects(
      v_geometry,
      extensions.st_makeenvelope(-106.7, 25.8, -93.4, 36.6, 4326)
    ) then
      raise exception 'Field % does not intersect the supported Texas extent.', v_field_id;
    end if;

    insert into public.usda_csb_fields (
      dataset_version,
      field_id,
      state_fips,
      county_fips,
      county_name,
      area_acres,
      boundary,
      representative_point,
      imported_at
    ) values (
      p_dataset_version,
      v_field_id,
      v_state_fips,
      nullif(btrim(v_properties ->> 'CNTYFIPS'), ''),
      nullif(btrim(v_properties ->> 'CNTY'), ''),
      v_area_acres,
      v_geometry,
      extensions.st_pointonsurface(v_geometry),
      statement_timestamp()
    )
    on conflict (dataset_version, field_id) do update
    set
      state_fips = excluded.state_fips,
      county_fips = excluded.county_fips,
      county_name = excluded.county_name,
      area_acres = excluded.area_acres,
      boundary = excluded.boundary,
      representative_point = excluded.representative_point,
      imported_at = excluded.imported_at;

    v_imported_count := v_imported_count + 1;
  end loop;

  return v_imported_count;
end;
$$;

create function public.get_usda_csb_viewport(
  p_dataset_version text,
  p_west double precision,
  p_south double precision,
  p_east double precision,
  p_north double precision,
  p_limit integer default 350
)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_envelope extensions.geometry;
  v_available boolean;
  v_candidate_count integer;
  v_features jsonb;
begin
  if p_dataset_version is null
    or p_dataset_version !~ '^[0-9]{4}-[0-9]{4}-rev[0-9]+$'
  then
    raise exception 'A valid CSB dataset version is required.';
  end if;

  if p_west is null or p_south is null or p_east is null or p_north is null
    or p_west >= p_east or p_south >= p_north
  then
    raise exception 'A valid west,south,east,north viewport is required.';
  end if;

  if p_west < -106.7 or p_east > -93.4 or p_south < 25.8 or p_north > 36.6 then
    raise exception 'The CSB viewport must remain within the supported Texas extent.';
  end if;

  if (p_east - p_west) > 1.5 or (p_north - p_south) > 1.5 then
    raise exception 'The CSB viewport is too large; zoom in before requesting fields.';
  end if;

  if p_limit is null or p_limit not between 1 and 500 then
    raise exception 'The CSB viewport limit must be between 1 and 500.';
  end if;

  v_envelope := extensions.st_makeenvelope(p_west, p_south, p_east, p_north, 4326);

  select exists (
    select 1
    from public.usda_csb_fields
    where dataset_version = p_dataset_version
  ) into v_available;

  with candidates as materialized (
    select
      field_id,
      area_acres,
      boundary,
      representative_point,
      pg_catalog.row_number() over (order by field_id) as row_number
    from public.usda_csb_fields
    where dataset_version = p_dataset_version
      and boundary operator(extensions.&&) v_envelope
      and extensions.st_intersects(boundary, v_envelope)
    order by field_id
    limit p_limit + 1
  )
  select
    pg_catalog.count(*)::integer,
    coalesce(
      pg_catalog.jsonb_agg(
        pg_catalog.jsonb_build_object(
          'type', 'Feature',
          'geometry', extensions.st_asgeojson(boundary, 6, 0)::jsonb,
          'properties', pg_catalog.jsonb_build_object(
            'field_id', field_id,
            'source', 'usda_csb',
            'area_acres', area_acres::double precision,
            'representative_latitude', extensions.st_y(representative_point),
            'representative_longitude', extensions.st_x(representative_point)
          )
        ) order by field_id
      ) filter (where row_number <= p_limit),
      '[]'::jsonb
    )
  into v_candidate_count, v_features
  from candidates;

  return pg_catalog.jsonb_build_object(
    'available', v_available,
    'truncated', v_candidate_count > p_limit,
    'features', v_features
  );
end;
$$;

revoke all on function public.import_usda_csb_fields(text, jsonb)
  from public, anon, authenticated;
revoke all on function public.get_usda_csb_viewport(
  text,
  double precision,
  double precision,
  double precision,
  double precision,
  integer
) from public, anon, authenticated;

grant execute on function public.import_usda_csb_fields(text, jsonb) to service_role;
grant execute on function public.get_usda_csb_viewport(
  text,
  double precision,
  double precision,
  double precision,
  double precision,
  integer
) to service_role;

comment on table public.usda_csb_fields is
  'Server-only USDA NASS synthetic crop-field boundaries used for optional map selection; these are not property or ownership parcels.';
comment on function public.import_usda_csb_fields(text, jsonb) is
  'Validates and upserts bounded batches of official Texas USDA CSB GeoJSON features.';
comment on function public.get_usda_csb_viewport(
  text,
  double precision,
  double precision,
  double precision,
  double precision,
  integer
) is
  'Returns a bounded, deterministic GeoJSON viewport response for server-side map delivery.';
