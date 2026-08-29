-- CropSage provider request lifecycle, retry/cache provenance, and artifact storage.

create type public.provider_code as enum (
  'fortyguard',
  'nasa_power',
  'open_meteo',
  'ssurgo'
);

create type public.provider_attempt_kind as enum (
  'http_request',
  'cache_lookup',
  'fallback_load'
);

create type public.http_method as enum (
  'GET',
  'POST'
);

create or replace function public.jsonb_contains_sensitive_keys(value jsonb)
returns boolean
language plpgsql
immutable
strict
parallel safe
set search_path = ''
as $$
declare
  object_key text;
  child_value jsonb;
begin
  if pg_catalog.jsonb_typeof(value) = 'object' then
    for object_key, child_value in
      select key, child
      from pg_catalog.jsonb_each(value) as item(key, child)
    loop
      if pg_catalog.lower(object_key) = any (
        array[
          'api_key',
          'apikey',
          'authorization',
          'password',
          'secret',
          'token',
          'signed_url',
          'download_link'
        ]
      ) then
        return true;
      end if;

      if public.jsonb_contains_sensitive_keys(child_value) then
        return true;
      end if;
    end loop;
  elsif pg_catalog.jsonb_typeof(value) = 'array' then
    for child_value in
      select item
      from pg_catalog.jsonb_array_elements(value) as element(item)
    loop
      if public.jsonb_contains_sensitive_keys(child_value) then
        return true;
      end if;
    end loop;
  end if;

  return false;
end;
$$;

create or replace function public.provider_artifacts_valid(value jsonb)
returns boolean
language plpgsql
immutable
strict
parallel safe
set search_path = ''
as $$
declare
  artifact jsonb;
begin
  if pg_catalog.jsonb_typeof(value) <> 'array' then
    return false;
  end if;

  for artifact in
    select item
    from pg_catalog.jsonb_array_elements(value) as element(item)
  loop
    if pg_catalog.jsonb_typeof(artifact) <> 'object' then
      return false;
    end if;

    if not artifact ?& array[
      'bucket_name',
      'object_path',
      'sha256',
      'content_type',
      'size_bytes',
      'provider_timestamp',
      'sanitization_version',
      'schema_version'
    ] then
      return false;
    end if;

    if artifact ->> 'bucket_name' <> 'provider-artifacts'
      or artifact ->> 'object_path' !~ '^[A-Za-z0-9][A-Za-z0-9/_=.-]*$'
      or artifact ->> 'object_path' like '%..%'
      or artifact ->> 'sha256' !~ '^[0-9a-f]{64}$'
      or artifact ->> 'content_type' !~ '^[a-z0-9.+-]+/[a-z0-9.+-]+$'
      or pg_catalog.jsonb_typeof(artifact -> 'size_bytes') <> 'number'
      or artifact ->> 'size_bytes' !~ '^[0-9]+$'
      or pg_catalog.jsonb_typeof(artifact -> 'provider_timestamp') not in ('string', 'null')
      or artifact ->> 'sanitization_version' is null
      or artifact ->> 'schema_version' is null
      or public.jsonb_contains_sensitive_keys(artifact)
    then
      return false;
    end if;
  end loop;

  return true;
end;
$$;

revoke all on function public.jsonb_contains_sensitive_keys(jsonb) from public, anon, authenticated;
revoke all on function public.provider_artifacts_valid(jsonb) from public, anon, authenticated;

create table public.provider_fetches (
  id uuid primary key default extensions.gen_random_uuid(),
  farm_profile_id uuid not null references public.farm_profiles(id) on delete restrict,
  request_group_id uuid not null default extensions.gen_random_uuid(),
  attempt_number smallint not null default 1,
  attempt_kind public.provider_attempt_kind not null default 'http_request',

  provider public.provider_code not null,
  endpoint text,
  http_method public.http_method,
  request_parameters_jsonb jsonb not null default '{}'::jsonb,
  request_schema_version text not null,
  sanitization_version text not null,
  requested_variables text[] not null,
  requested_start_at timestamptz,
  requested_end_at timestamptz,
  request_point extensions.geography(Point, 4326),
  request_area extensions.geography(MultiPolygon, 4326),
  coordinate_tolerance_m numeric(10, 2) not null default 100,
  spatial_resolution_m numeric(12, 2),
  cache_key_material_jsonb jsonb not null,
  cache_key text generated always as (public.jsonb_sha256(cache_key_material_jsonb)) stored,
  cache_hit_fetch_id uuid references public.provider_fetches(id) on delete restrict,

  status public.provider_fetch_status not null default 'pending',
  produced_evidence boolean not null default false,
  result_mode public.provider_fetch_mode,
  provider_activity_id text,
  provider_status text,
  poll_count integer not null default 0,
  poll_deadline_at timestamptz,
  http_status_code smallint,
  submitted_at timestamptz,
  completed_at timestamptz,
  fetched_at timestamptz,
  expires_at timestamptz,

  response_metadata_jsonb jsonb not null default '{}'::jsonb,
  artifacts_jsonb jsonb not null default '[]'::jsonb,
  error_code text,
  error_message text,
  error_details_jsonb jsonb,
  created_at timestamptz not null default statement_timestamp(),
  updated_at timestamptz not null default statement_timestamp(),

  constraint provider_fetches_attempt_positive
    check (attempt_number > 0),
  constraint provider_fetches_group_attempt_unique
    unique (request_group_id, attempt_number),
  constraint provider_fetches_http_shape
    check (
      (attempt_kind = 'http_request' and endpoint is not null and http_method is not null)
      or (attempt_kind <> 'http_request' and endpoint is null and http_method is null)
    ),
  constraint provider_fetches_endpoint_length
    check (endpoint is null or char_length(endpoint) between 1 and 500),
  constraint provider_fetches_request_parameters_object
    check (
      jsonb_typeof(request_parameters_jsonb) = 'object'
      and not public.jsonb_contains_sensitive_keys(request_parameters_jsonb)
    ),
  constraint provider_fetches_request_schema_version_present
    check (btrim(request_schema_version) <> ''),
  constraint provider_fetches_sanitization_version_present
    check (btrim(sanitization_version) <> ''),
  constraint provider_fetches_requested_variables_present
    check (
      cardinality(requested_variables) > 0
      and array_position(requested_variables, null) is null
    ),
  constraint provider_fetches_requested_window_order
    check (
      num_nonnulls(requested_start_at, requested_end_at) in (0, 2)
      and (requested_start_at is null or requested_end_at >= requested_start_at)
    ),
  constraint provider_fetches_request_location_present
    check (num_nonnulls(request_point, request_area) > 0),
  constraint provider_fetches_request_area_valid
    check (
      request_area is null
      or (
        not extensions.st_isempty(request_area::extensions.geometry)
        and extensions.st_isvalid(request_area::extensions.geometry)
      )
    ),
  constraint provider_fetches_coordinate_tolerance_range
    check (coordinate_tolerance_m between 0 and 10000),
  constraint provider_fetches_spatial_resolution_positive
    check (spatial_resolution_m is null or spatial_resolution_m > 0),
  constraint provider_fetches_cache_material_object
    check (
      jsonb_typeof(cache_key_material_jsonb) = 'object'
      and not public.jsonb_contains_sensitive_keys(cache_key_material_jsonb)
    ),
  constraint provider_fetches_attempt_mode
    check (
      result_mode is null
      or (result_mode = 'live' and attempt_kind = 'http_request')
      or (result_mode = 'cache' and attempt_kind = 'cache_lookup')
      or (result_mode = 'fallback' and attempt_kind = 'fallback_load')
    ),
  constraint provider_fetches_cache_reference_shape
    check (
      (result_mode = 'cache' and cache_hit_fetch_id is not null)
      or (result_mode is distinct from 'cache' and cache_hit_fetch_id is null)
    ),
  constraint provider_fetches_poll_count_nonnegative
    check (poll_count >= 0),
  constraint provider_fetches_http_status_range
    check (http_status_code is null or http_status_code between 100 and 599),
  constraint provider_fetches_timing_order
    check (
      (completed_at is null or submitted_at is null or completed_at >= submitted_at)
      and (fetched_at is null or completed_at is null or fetched_at >= completed_at)
      and (expires_at is null or fetched_at is null or expires_at > fetched_at)
      and (poll_deadline_at is null or submitted_at is null or poll_deadline_at >= submitted_at)
    ),
  constraint provider_fetches_response_metadata_object
    check (
      jsonb_typeof(response_metadata_jsonb) = 'object'
      and not public.jsonb_contains_sensitive_keys(response_metadata_jsonb)
    ),
  constraint provider_fetches_artifacts_valid
    check (public.provider_artifacts_valid(artifacts_jsonb)),
  constraint provider_fetches_error_details_object
    check (
      error_details_jsonb is null
      or (
        jsonb_typeof(error_details_jsonb) = 'object'
        and not public.jsonb_contains_sensitive_keys(error_details_jsonb)
      )
    ),
  constraint provider_fetches_error_lengths
    check (
      (error_code is null or char_length(error_code) <= 100)
      and (error_message is null or char_length(error_message) <= 2000)
    ),
  constraint provider_fetches_lifecycle
    check (
      (
        status = 'pending'
        and submitted_at is null
        and completed_at is null
        and fetched_at is null
        and produced_evidence = false
        and result_mode is null
        and error_code is null
        and error_message is null
        and artifacts_jsonb = '[]'::jsonb
      )
      or (
        status = 'running'
        and submitted_at is not null
        and completed_at is null
        and fetched_at is null
        and produced_evidence = false
        and result_mode is null
        and error_code is null
        and error_message is null
        and artifacts_jsonb = '[]'::jsonb
      )
      or (
        status = 'succeeded'
        and submitted_at is not null
        and completed_at is not null
        and error_code is null
        and error_message is null
        and (
          (
            produced_evidence = false
            and result_mode is null
            and fetched_at is null
            and artifacts_jsonb = '[]'::jsonb
          )
          or (
            produced_evidence = true
            and result_mode is not null
            and fetched_at is not null
            and jsonb_array_length(artifacts_jsonb) > 0
          )
        )
      )
      or (
        status = 'failed'
        and completed_at is not null
        and fetched_at is null
        and produced_evidence = false
        and result_mode is null
        and num_nonnulls(error_code, error_message) > 0
        and artifacts_jsonb = '[]'::jsonb
      )
    ),
  constraint provider_fetches_updated_after_creation
    check (updated_at >= created_at)
);

create or replace function public.validate_provider_fetch_location()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  profile_point extensions.geography(Point, 4326);
begin
  select farm_point
    into profile_point
  from public.farm_profiles
  where id = new.farm_profile_id;

  if profile_point is null then
    raise exception 'Provider fetch must reference an existing farm profile.';
  end if;

  if new.request_point is not null
    and not extensions.st_dwithin(
      profile_point,
      new.request_point,
      new.coordinate_tolerance_m::double precision
    )
  then
    raise exception 'Provider request point does not match the farm profile within tolerance.';
  end if;

  if new.request_area is not null
    and not extensions.st_covers(
      new.request_area::extensions.geometry,
      profile_point::extensions.geometry
    )
  then
    raise exception 'Provider request area does not cover the farm profile point.';
  end if;

  return new;
end;
$$;

create or replace function public.validate_provider_cache_source()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  source_status public.provider_fetch_status;
  source_produced_evidence boolean;
  source_cache_key text;
  source_expires_at timestamptz;
  expected_cache_key text;
  reuse_time timestamptz;
begin
  if new.result_mode is distinct from 'cache' then
    return new;
  end if;

  if new.cache_hit_fetch_id = new.id then
    raise exception 'A provider fetch cannot reuse itself as a cache source.';
  end if;

  select status, produced_evidence, cache_key, expires_at
    into source_status, source_produced_evidence, source_cache_key, source_expires_at
  from public.provider_fetches
  where id = new.cache_hit_fetch_id;

  if not found then
    raise exception 'Cache source provider fetch does not exist.';
  end if;

  expected_cache_key := public.jsonb_sha256(new.cache_key_material_jsonb);
  reuse_time := coalesce(new.fetched_at, new.completed_at, new.created_at, statement_timestamp());

  if source_status <> 'succeeded' or source_produced_evidence = false then
    raise exception 'Cache source must be a successful evidence-producing fetch.';
  end if;

  if source_cache_key <> expected_cache_key then
    raise exception 'Cache source key does not match the requested evidence.';
  end if;

  if source_expires_at is not null and source_expires_at <= reuse_time then
    raise exception 'Cache source was expired at reuse time.';
  end if;

  return new;
end;
$$;

revoke all on function public.validate_provider_fetch_location() from public, anon, authenticated;
revoke all on function public.validate_provider_cache_source() from public, anon, authenticated;

create trigger provider_fetches_set_updated_at
before update on public.provider_fetches
for each row execute function public.set_updated_at();

create trigger provider_fetches_validate_location
before insert or update of farm_profile_id, request_point, request_area, coordinate_tolerance_m
on public.provider_fetches
for each row execute function public.validate_provider_fetch_location();

create trigger provider_fetches_validate_cache_source
before insert or update of result_mode, cache_hit_fetch_id, cache_key_material_jsonb,
  status, produced_evidence, fetched_at, completed_at
on public.provider_fetches
for each row execute function public.validate_provider_cache_source();

create index provider_fetches_profile_created_idx
  on public.provider_fetches(farm_profile_id, created_at desc);

create index provider_fetches_group_attempt_idx
  on public.provider_fetches(request_group_id, attempt_number);

create index provider_fetches_provider_status_idx
  on public.provider_fetches(provider, status, created_at desc);

create index provider_fetches_reusable_cache_idx
  on public.provider_fetches(cache_key, expires_at desc)
  where status = 'succeeded' and produced_evidence = true;

create index provider_fetches_activity_idx
  on public.provider_fetches(provider, provider_activity_id)
  where provider_activity_id is not null;

create index provider_fetches_point_gix
  on public.provider_fetches using gist(request_point)
  where request_point is not null;

create index provider_fetches_area_gix
  on public.provider_fetches using gist(request_area)
  where request_area is not null;

alter table public.provider_fetches enable row level security;

revoke all on table public.provider_fetches from anon, authenticated;
grant select on table public.provider_fetches to authenticated;

create policy provider_fetches_select_own_profile
on public.provider_fetches
for select
to authenticated
using (
  exists (
    select 1
    from public.farm_profiles
    join public.assessment_sessions
      on assessment_sessions.id = farm_profiles.assessment_session_id
    where farm_profiles.id = provider_fetches.farm_profile_id
      and assessment_sessions.owner_user_id = (select auth.uid())
  )
);

insert into storage.buckets (
  id,
  name,
  public,
  file_size_limit,
  allowed_mime_types
) values (
  'provider-artifacts',
  'provider-artifacts',
  false,
  52428800,
  array[
    'application/json',
    'application/geo+json',
    'application/octet-stream',
    'application/pdf',
    'text/csv'
  ]
) on conflict (id) do update
set public = excluded.public,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

comment on table public.provider_fetches is
  'One auditable provider HTTP, cache, or fallback attempt; retries and polls share request_group_id.';
comment on column public.provider_fetches.cache_key_material_jsonb is
  'Canonical provider/endpoint/location/variables/time-window parameters used to generate cache_key.';
comment on column public.provider_fetches.artifacts_jsonb is
  'Sanitized stable Storage object metadata only; never credentials, raw signed URLs, or unsanitized payloads.';
