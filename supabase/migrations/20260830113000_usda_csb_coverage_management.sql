-- Track bounded CSB data packs so absent coverage is never reported as absent farmland.

create table public.usda_csb_coverage (
  dataset_version text not null,
  coverage_id text not null,
  coverage_label text not null,
  coverage_status text not null,
  state_fips text not null default '48',
  county_fips text,
  county_name text,
  coverage_area extensions.geometry(MultiPolygon, 4326) not null,
  field_count integer not null,
  table_storage_bytes_at_import bigint not null,
  imported_at timestamptz not null default statement_timestamp(),

  constraint usda_csb_coverage_primary_key
    primary key (dataset_version, coverage_id),
  constraint usda_csb_coverage_dataset_version_format
    check (dataset_version ~ '^[0-9]{4}-[0-9]{4}-rev[0-9]+$'),
  constraint usda_csb_coverage_id_format
    check (coverage_id ~ '^[a-z0-9]+(?:[a-z0-9-]{0,78}[a-z0-9])?$'),
  constraint usda_csb_coverage_label_length
    check (char_length(btrim(coverage_label)) between 1 and 120),
  constraint usda_csb_coverage_status_value
    check (coverage_status in ('partial', 'ready')),
  constraint usda_csb_coverage_texas_only
    check (state_fips = '48'),
  constraint usda_csb_coverage_county_fips_format
    check (county_fips is null or county_fips ~ '^[0-9]{3}$'),
  constraint usda_csb_coverage_county_name_length
    check (county_name is null or char_length(btrim(county_name)) between 1 and 120),
  constraint usda_csb_coverage_field_count_nonnegative
    check (field_count >= 0),
  constraint usda_csb_coverage_storage_positive
    check (table_storage_bytes_at_import > 0),
  constraint usda_csb_coverage_area_valid
    check (
      not extensions.st_isempty(coverage_area)
      and extensions.st_isvalid(coverage_area)
      and extensions.st_srid(coverage_area) = 4326
    )
);

create index usda_csb_coverage_area_gist_idx
  on public.usda_csb_coverage using gist (coverage_area);

create index usda_csb_coverage_lookup_idx
  on public.usda_csb_coverage(dataset_version, coverage_status);

alter table public.usda_csb_coverage enable row level security;

revoke all on table public.usda_csb_coverage from public, anon, authenticated;
grant select on table public.usda_csb_coverage to service_role;

create function public.get_usda_csb_storage_usage(
  p_dataset_version text default null
)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select pg_catalog.jsonb_build_object(
    'dataset_version', p_dataset_version,
    'field_count', (
      select pg_catalog.count(*)
      from public.usda_csb_fields
      where p_dataset_version is null or dataset_version = p_dataset_version
    ),
    'table_storage_bytes', pg_catalog.pg_total_relation_size(
      'public.usda_csb_fields'::pg_catalog.regclass
    )
  );
$$;

create function public.register_usda_csb_coverage(
  p_dataset_version text,
  p_coverage_id text,
  p_coverage_label text,
  p_coverage_status text,
  p_west double precision,
  p_south double precision,
  p_east double precision,
  p_north double precision,
  p_county_fips text default null,
  p_county_name text default null
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_area extensions.geometry;
  v_field_count integer;
  v_storage_bytes bigint;
begin
  if p_dataset_version is null
    or p_dataset_version !~ '^[0-9]{4}-[0-9]{4}-rev[0-9]+$'
  then
    raise exception 'A valid CSB dataset version is required.';
  end if;

  if p_coverage_id is null
    or p_coverage_id !~ '^[a-z0-9]+(?:[a-z0-9-]{0,78}[a-z0-9])?$'
  then
    raise exception 'A lowercase coverage identifier is required.';
  end if;

  if p_coverage_label is null
    or char_length(btrim(p_coverage_label)) not between 1 and 120
  then
    raise exception 'A coverage label between 1 and 120 characters is required.';
  end if;

  if p_coverage_status not in ('partial', 'ready') then
    raise exception 'Coverage status must be partial or ready.';
  end if;

  if p_west is null or p_south is null or p_east is null or p_north is null
    or p_west >= p_east or p_south >= p_north
    or p_west < -106.7 or p_east > -93.4 or p_south < 25.8 or p_north > 36.6
  then
    raise exception 'Coverage bounds must be a valid west,south,east,north Texas extent.';
  end if;

  if p_county_fips is not null and p_county_fips !~ '^[0-9]{3}$' then
    raise exception 'County FIPS must contain three digits.';
  end if;

  v_area := extensions.st_multi(
    extensions.st_makeenvelope(p_west, p_south, p_east, p_north, 4326)
  );

  select pg_catalog.count(*)::integer
  into v_field_count
  from public.usda_csb_fields
  where dataset_version = p_dataset_version
    and boundary operator(extensions.&&) v_area
    and extensions.st_intersects(boundary, v_area);

  v_storage_bytes := pg_catalog.pg_total_relation_size(
    'public.usda_csb_fields'::pg_catalog.regclass
  );

  insert into public.usda_csb_coverage (
    dataset_version,
    coverage_id,
    coverage_label,
    coverage_status,
    county_fips,
    county_name,
    coverage_area,
    field_count,
    table_storage_bytes_at_import,
    imported_at
  ) values (
    p_dataset_version,
    p_coverage_id,
    btrim(p_coverage_label),
    p_coverage_status,
    p_county_fips,
    nullif(btrim(p_county_name), ''),
    v_area,
    v_field_count,
    v_storage_bytes,
    statement_timestamp()
  )
  on conflict (dataset_version, coverage_id) do update
  set
    coverage_label = excluded.coverage_label,
    coverage_status = excluded.coverage_status,
    county_fips = excluded.county_fips,
    county_name = excluded.county_name,
    coverage_area = excluded.coverage_area,
    field_count = excluded.field_count,
    table_storage_bytes_at_import = excluded.table_storage_bytes_at_import,
    imported_at = excluded.imported_at;

  return pg_catalog.jsonb_build_object(
    'coverage_id', p_coverage_id,
    'coverage_status', p_coverage_status,
    'field_count', v_field_count,
    'table_storage_bytes', v_storage_bytes
  );
end;
$$;

create or replace function public.get_usda_csb_viewport(
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
  v_candidate_count integer;
  v_features jsonb;
  v_coverage_status text;
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

  if exists (
    select 1
    from public.usda_csb_coverage
    where dataset_version = p_dataset_version
      and coverage_status = 'ready'
      and extensions.st_covers(coverage_area, v_envelope)
  ) then
    v_coverage_status := 'covered';
  elsif v_candidate_count > 0 or exists (
    select 1
    from public.usda_csb_coverage
    where dataset_version = p_dataset_version
      and coverage_area operator(extensions.&&) v_envelope
      and extensions.st_intersects(coverage_area, v_envelope)
  ) then
    v_coverage_status := 'partial';
  else
    v_coverage_status := 'not_loaded';
  end if;

  return pg_catalog.jsonb_build_object(
    'available', v_coverage_status <> 'not_loaded',
    'coverage_status', v_coverage_status,
    'truncated', v_candidate_count > p_limit,
    'features', v_features
  );
end;
$$;

revoke all on function public.get_usda_csb_storage_usage(text)
  from public, anon, authenticated;
revoke all on function public.register_usda_csb_coverage(
  text,
  text,
  text,
  text,
  double precision,
  double precision,
  double precision,
  double precision,
  text,
  text
) from public, anon, authenticated;

grant execute on function public.get_usda_csb_storage_usage(text) to service_role;
grant execute on function public.register_usda_csb_coverage(
  text,
  text,
  text,
  text,
  double precision,
  double precision,
  double precision,
  double precision,
  text,
  text
) to service_role;

comment on table public.usda_csb_coverage is
  'Imported USDA CSB data-pack extents and completeness; ready means the full declared area was loaded, while partial marks samples or incomplete packs.';
comment on function public.get_usda_csb_storage_usage(text) is
  'Returns server-only field count and total CSB table-plus-index storage for importer budget enforcement.';
comment on function public.register_usda_csb_coverage(
  text,
  text,
  text,
  text,
  double precision,
  double precision,
  double precision,
  double precision,
  text,
  text
) is
  'Registers the exact area and completeness of an imported USDA CSB data pack.';
