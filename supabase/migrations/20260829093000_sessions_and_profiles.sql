-- CropSage assessment sessions and immutable-version farm profile foundation.

create type public.location_source as enum (
  'map_pin',
  'gps',
  'address_geocoding',
  'demo_farm',
  'manual_coordinates'
);

create or replace function public.jsonb_sha256(value jsonb)
returns text
language sql
immutable
strict
parallel safe
set search_path = ''
as $$
  select pg_catalog.encode(
    extensions.digest(pg_catalog.convert_to(value::text, 'UTF8'), 'sha256'),
    'hex'
  )
$$;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  new.updated_at = statement_timestamp();
  return new;
end;
$$;

revoke all on function public.jsonb_sha256(jsonb) from public, anon, authenticated;
revoke all on function public.set_updated_at() from public, anon, authenticated;

create table public.assessment_sessions (
  id uuid primary key default extensions.gen_random_uuid(),
  owner_user_id uuid references auth.users(id) on delete restrict,
  status public.assessment_session_status not null default 'active',
  active_profile_id uuid,
  expires_at timestamptz,
  created_at timestamptz not null default statement_timestamp(),
  updated_at timestamptz not null default statement_timestamp(),

  constraint assessment_sessions_expiry_after_creation
    check (expires_at is null or expires_at > created_at),
  constraint assessment_sessions_updated_after_creation
    check (updated_at >= created_at)
);

create table public.farm_profiles (
  id uuid primary key default extensions.gen_random_uuid(),
  assessment_session_id uuid not null
    references public.assessment_sessions(id) on delete restrict,
  external_profile_id text not null unique,
  profile_version integer not null,
  schema_version text not null,
  status public.farm_profile_status not null default 'draft',
  supersedes_profile_id uuid,
  captured_at timestamptz,

  farm_point extensions.geography(Point, 4326) not null,
  farm_boundary extensions.geography(MultiPolygon, 4326),
  farm_name text,
  location_label text,
  location_source public.location_source not null,
  resolved_region_id text,
  region_resolution_method text,
  region_resolution_version text,
  timezone text,
  timezone_resolution_method text,
  timezone_resolution_version text,
  location_resolution_jsonb jsonb not null default '{}'::jsonb,

  planned_planting_date date,
  planned_planting_month date,
  planting_flexibility_days smallint,
  requested_crop_id text,

  irrigation_jsonb jsonb,
  soil_overrides_jsonb jsonb,
  current_soil_moisture_jsonb jsonb,
  recent_rainfall_jsonb jsonb,
  farmer_goal_jsonb jsonb,
  field_sources_jsonb jsonb not null default '{}'::jsonb,
  missing_fields text[] not null default '{}'::text[],
  completeness_notes text[] not null default '{}'::text[],

  profile_snapshot jsonb not null,
  input_hash text generated always as (public.jsonb_sha256(profile_snapshot)) stored,
  created_at timestamptz not null default statement_timestamp(),
  updated_at timestamptz not null default statement_timestamp(),

  constraint farm_profiles_external_id_format
    check (external_profile_id ~ '^[a-z0-9][a-z0-9_-]{2,79}$'),
  constraint farm_profiles_schema_version_format
    check (schema_version ~ '^[0-9]+\.[0-9]+\.[0-9]+([+-][A-Za-z0-9.-]+)?$'),
  constraint farm_profiles_positive_version
    check (profile_version > 0),
  constraint farm_profiles_version_predecessor_presence
    check (
      (profile_version = 1 and supersedes_profile_id is null)
      or (profile_version > 1 and supersedes_profile_id is not null)
    ),
  constraint farm_profiles_farm_name_length
    check (farm_name is null or char_length(farm_name) <= 120),
  constraint farm_profiles_location_label_length
    check (location_label is null or char_length(location_label) <= 200),
  constraint farm_profiles_planting_time_exactly_one
    check (num_nonnulls(planned_planting_date, planned_planting_month) = 1),
  constraint farm_profiles_planting_month_normalized
    check (
      planned_planting_month is null
      or planned_planting_month = date_trunc('month', planned_planting_month)::date
    ),
  constraint farm_profiles_flexibility_range
    check (
      planting_flexibility_days is null
      or planting_flexibility_days between 0 and 120
    ),
  constraint farm_profiles_requested_crop_id_format
    check (requested_crop_id is null or requested_crop_id ~ '^[a-z0-9][a-z0-9_]*$'),
  constraint farm_profiles_resolution_object
    check (jsonb_typeof(location_resolution_jsonb) = 'object'),
  constraint farm_profiles_irrigation_object
    check (irrigation_jsonb is null or jsonb_typeof(irrigation_jsonb) = 'object'),
  constraint farm_profiles_soil_overrides_object
    check (soil_overrides_jsonb is null or jsonb_typeof(soil_overrides_jsonb) = 'object'),
  constraint farm_profiles_soil_moisture_object
    check (
      current_soil_moisture_jsonb is null
      or jsonb_typeof(current_soil_moisture_jsonb) = 'object'
    ),
  constraint farm_profiles_recent_rainfall_object
    check (recent_rainfall_jsonb is null or jsonb_typeof(recent_rainfall_jsonb) = 'object'),
  constraint farm_profiles_farmer_goal_object
    check (farmer_goal_jsonb is null or jsonb_typeof(farmer_goal_jsonb) = 'object'),
  constraint farm_profiles_field_sources_object
    check (jsonb_typeof(field_sources_jsonb) = 'object'),
  constraint farm_profiles_snapshot_object
    check (jsonb_typeof(profile_snapshot) = 'object'),
  constraint farm_profiles_boundary_not_empty
    check (farm_boundary is null or not extensions.st_isempty(farm_boundary::extensions.geometry)),
  constraint farm_profiles_boundary_valid
    check (farm_boundary is null or extensions.st_isvalid(farm_boundary::extensions.geometry)),
  constraint farm_profiles_point_within_boundary
    check (
      farm_boundary is null
      or extensions.st_covers(
        farm_boundary::extensions.geometry,
        farm_point::extensions.geometry
      )
    ),
  constraint farm_profiles_session_version_unique
    unique (assessment_session_id, profile_version),
  constraint farm_profiles_session_id_pair_unique
    unique (assessment_session_id, id),
  constraint farm_profiles_session_predecessor_fk
    foreign key (assessment_session_id, supersedes_profile_id)
    references public.farm_profiles(assessment_session_id, id)
    on delete restrict
);

alter table public.assessment_sessions
  add constraint assessment_sessions_active_profile_fk
  foreign key (id, active_profile_id)
  references public.farm_profiles(assessment_session_id, id)
  on delete restrict;

create or replace function public.validate_farm_profile_version()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  predecessor_version integer;
begin
  if new.supersedes_profile_id is null then
    return new;
  end if;

  select profile_version
    into predecessor_version
  from public.farm_profiles
  where id = new.supersedes_profile_id
    and assessment_session_id = new.assessment_session_id;

  if predecessor_version is null then
    raise exception 'Superseded profile must belong to the same assessment session.';
  end if;

  if new.profile_version <> predecessor_version + 1 then
    raise exception 'Farm profile versions must increase by exactly one.';
  end if;

  return new;
end;
$$;

revoke all on function public.validate_farm_profile_version() from public, anon, authenticated;

create trigger assessment_sessions_set_updated_at
before update on public.assessment_sessions
for each row execute function public.set_updated_at();

create trigger farm_profiles_set_updated_at
before update on public.farm_profiles
for each row execute function public.set_updated_at();

create trigger farm_profiles_validate_version
before insert or update of assessment_session_id, profile_version, supersedes_profile_id
on public.farm_profiles
for each row execute function public.validate_farm_profile_version();

create unique index farm_profiles_one_successor_idx
  on public.farm_profiles(supersedes_profile_id)
  where supersedes_profile_id is not null;

create index assessment_sessions_owner_idx
  on public.assessment_sessions(owner_user_id)
  where owner_user_id is not null;

create index assessment_sessions_status_expiry_idx
  on public.assessment_sessions(status, expires_at);

create index farm_profiles_session_version_idx
  on public.farm_profiles(assessment_session_id, profile_version desc);

create index farm_profiles_point_gix
  on public.farm_profiles using gist(farm_point);

create index farm_profiles_boundary_gix
  on public.farm_profiles using gist(farm_boundary)
  where farm_boundary is not null;

alter table public.assessment_sessions enable row level security;
alter table public.farm_profiles enable row level security;

revoke all on table public.assessment_sessions from anon, authenticated;
revoke all on table public.farm_profiles from anon, authenticated;
grant select on table public.assessment_sessions to authenticated;
grant select on table public.farm_profiles to authenticated;

create policy assessment_sessions_select_own
on public.assessment_sessions
for select
to authenticated
using (owner_user_id = (select auth.uid()));

create policy farm_profiles_select_own_session
on public.farm_profiles
for select
to authenticated
using (
  exists (
    select 1
    from public.assessment_sessions
    where assessment_sessions.id = farm_profiles.assessment_session_id
      and assessment_sessions.owner_user_id = (select auth.uid())
  )
);

comment on table public.assessment_sessions is
  'Groups the baseline farm profile and later recommendation scenarios.';
comment on table public.farm_profiles is
  'Versioned farm inputs. Coordinates are authoritative; optional farmer evidence remains explicit JSONB.';
comment on column public.farm_profiles.profile_snapshot is
  'Exact FarmProfile contract document used to derive typed columns.';
comment on column public.farm_profiles.input_hash is
  'SHA-256 of PostgreSQL canonical JSONB text for deterministic replay.';
