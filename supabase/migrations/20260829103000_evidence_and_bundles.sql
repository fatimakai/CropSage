-- CropSage normalized evidence facts, derivation lineage, and immutable bundle membership.

create type public.evidence_availability as enum (
  'available',
  'missing',
  'not_applicable'
);

create type public.evidence_freshness as enum (
  'fresh',
  'stale',
  'unknown',
  'not_applicable'
);

create type public.evidence_value_kind as enum (
  'numeric',
  'text',
  'boolean',
  'json'
);

create type public.bundle_record_role as enum (
  'required',
  'supplementary',
  'contextual',
  'catalog_comparison'
);

create table public.evidence_records (
  id uuid primary key default extensions.gen_random_uuid(),
  farm_profile_id uuid not null references public.farm_profiles(id) on delete restrict,
  provider_fetch_id uuid references public.provider_fetches(id) on delete restrict,

  source_type public.evidence_source_type not null,
  source_name text not null,
  source_field text,
  source_metadata_jsonb jsonb not null default '{}'::jsonb,
  canonical_variable text not null,
  availability public.evidence_availability not null default 'available',
  freshness public.evidence_freshness not null default 'unknown',

  value_kind public.evidence_value_kind,
  value_numeric numeric,
  value_text text,
  value_boolean boolean,
  value_jsonb jsonb,
  unit text,

  observed_start_at timestamptz,
  observed_end_at timestamptz,
  valid_start_at timestamptz,
  valid_end_at timestamptz,
  fetched_at timestamptz,
  expires_at timestamptz,
  evidence_point extensions.geography(Point, 4326) not null,
  evidence_area extensions.geography(MultiPolygon, 4326),
  coordinate_tolerance_m numeric(10, 2) not null default 100,
  spatial_resolution_m numeric(12, 2),

  quality_score numeric(5, 4),
  quality_flags text[] not null default '{}'::text[],
  warnings text[] not null default '{}'::text[],

  derivation_name text,
  derivation_version text,
  derivation_input_ids uuid[],
  derivation_jsonb jsonb,

  evidence_snapshot jsonb not null,
  record_hash text generated always as (public.jsonb_sha256(evidence_snapshot)) stored,
  created_at timestamptz not null default statement_timestamp(),

  constraint evidence_records_source_name_present
    check (btrim(source_name) <> '' and char_length(source_name) <= 200),
  constraint evidence_records_source_field_length
    check (source_field is null or char_length(source_field) <= 200),
  constraint evidence_records_source_metadata_object
    check (
      jsonb_typeof(source_metadata_jsonb) = 'object'
      and not public.jsonb_contains_sensitive_keys(source_metadata_jsonb)
    ),
  constraint evidence_records_variable_format
    check (canonical_variable ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$'),
  constraint evidence_records_value_shape
    check (
      (
        availability = 'available'
        and value_kind is not null
        and (
          (value_kind = 'numeric' and num_nonnulls(value_numeric, value_text, value_boolean, value_jsonb) = 1 and value_numeric is not null)
          or (value_kind = 'text' and num_nonnulls(value_numeric, value_text, value_boolean, value_jsonb) = 1 and value_text is not null)
          or (value_kind = 'boolean' and num_nonnulls(value_numeric, value_text, value_boolean, value_jsonb) = 1 and value_boolean is not null)
          or (value_kind = 'json' and num_nonnulls(value_numeric, value_text, value_boolean, value_jsonb) = 1 and value_jsonb is not null)
        )
      )
      or (
        availability in ('missing', 'not_applicable')
        and value_kind is null
        and num_nonnulls(value_numeric, value_text, value_boolean, value_jsonb) = 0
        and unit is null
      )
    ),
  constraint evidence_records_numeric_finite
    check (
      value_numeric is null
      or value_numeric::text not in ('NaN', 'Infinity', '-Infinity')
    ),
  constraint evidence_records_numeric_unit_present
    check (
      value_kind is distinct from 'numeric'
      or (unit is not null and btrim(unit) <> '')
    ),
  constraint evidence_records_unit_length
    check (unit is null or char_length(unit) <= 80),
  constraint evidence_records_observation_order
    check (
      num_nonnulls(observed_start_at, observed_end_at) in (0, 2)
      and (observed_start_at is null or observed_end_at >= observed_start_at)
    ),
  constraint evidence_records_validity_order
    check (
      num_nonnulls(valid_start_at, valid_end_at) in (0, 2)
      and (valid_start_at is null or valid_end_at >= valid_start_at)
    ),
  constraint evidence_records_expiry_order
    check (expires_at is null or fetched_at is null or expires_at > fetched_at),
  constraint evidence_records_freshness_state
    check (
      (freshness = 'fresh' and (expires_at is null or expires_at > created_at))
      or (freshness = 'stale' and expires_at is not null and expires_at <= created_at)
      or freshness in ('unknown', 'not_applicable')
    ),
  constraint evidence_records_area_valid
    check (
      evidence_area is null
      or (
        not extensions.st_isempty(evidence_area::extensions.geometry)
        and extensions.st_isvalid(evidence_area::extensions.geometry)
      )
    ),
  constraint evidence_records_coordinate_tolerance_range
    check (coordinate_tolerance_m between 0 and 100000),
  constraint evidence_records_spatial_resolution_positive
    check (spatial_resolution_m is null or spatial_resolution_m > 0),
  constraint evidence_records_quality_range
    check (quality_score is null or quality_score between 0 and 1),
  constraint evidence_records_quality_flags_no_nulls
    check (array_position(quality_flags, null) is null),
  constraint evidence_records_warnings_no_nulls
    check (array_position(warnings, null) is null),
  constraint evidence_records_origin_shape
    check (
      (source_type = 'provider' and provider_fetch_id is not null)
      or (source_type <> 'provider' and provider_fetch_id is null)
    ),
  constraint evidence_records_derivation_shape
    check (
      (
        source_type = 'derived'
        and derivation_name is not null
        and btrim(derivation_name) <> ''
        and derivation_version is not null
        and btrim(derivation_version) <> ''
        and derivation_input_ids is not null
        and cardinality(derivation_input_ids) > 0
        and array_position(derivation_input_ids, null) is null
        and jsonb_typeof(derivation_jsonb) = 'object'
      )
      or (
        source_type <> 'derived'
        and derivation_name is null
        and derivation_version is null
        and derivation_input_ids is null
        and derivation_jsonb is null
      )
    ),
  constraint evidence_records_derivation_metadata_safe
    check (
      derivation_jsonb is null
      or not public.jsonb_contains_sensitive_keys(derivation_jsonb)
    ),
  constraint evidence_records_snapshot_object
    check (
      jsonb_typeof(evidence_snapshot) = 'object'
      and not public.jsonb_contains_sensitive_keys(evidence_snapshot)
    ),
  constraint evidence_records_profile_hash_unique
    unique (farm_profile_id, record_hash)
);

create or replace function public.validate_evidence_record_origin()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  fetch_profile_id uuid;
  fetch_status public.provider_fetch_status;
  fetch_produced_evidence boolean;
  input_id uuid;
  input_profile_id uuid;
begin
  if new.source_type = 'provider' then
    select farm_profile_id, status, produced_evidence
      into fetch_profile_id, fetch_status, fetch_produced_evidence
    from public.provider_fetches
    where id = new.provider_fetch_id;

    if not found then
      raise exception 'Provider evidence must reference an existing provider fetch.';
    end if;

    if fetch_profile_id <> new.farm_profile_id then
      raise exception 'Provider evidence and provider fetch must use the same farm profile.';
    end if;

    if fetch_status <> 'succeeded' or fetch_produced_evidence = false then
      raise exception 'A failed or non-evidence provider attempt cannot become evidence.';
    end if;
  end if;

  if new.source_type = 'derived' then
    foreach input_id in array new.derivation_input_ids
    loop
      if input_id = new.id then
        raise exception 'A derived evidence record cannot depend on itself.';
      end if;

      select farm_profile_id
        into input_profile_id
      from public.evidence_records
      where id = input_id;

      if not found then
        raise exception 'Derived evidence input does not exist.';
      end if;

      if input_profile_id <> new.farm_profile_id then
        raise exception 'Derived evidence inputs must use the same farm profile.';
      end if;
    end loop;
  end if;

  return new;
end;
$$;

create or replace function public.validate_evidence_record_location()
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
    raise exception 'Evidence must reference an existing farm profile.';
  end if;

  if not extensions.st_dwithin(
    profile_point,
    new.evidence_point,
    new.coordinate_tolerance_m::double precision
  ) then
    raise exception 'Evidence point does not match the farm profile within tolerance.';
  end if;

  if new.evidence_area is not null
    and not extensions.st_covers(
      new.evidence_area::extensions.geometry,
      profile_point::extensions.geometry
    )
  then
    raise exception 'Evidence area does not cover the farm profile point.';
  end if;

  return new;
end;
$$;

revoke all on function public.validate_evidence_record_origin() from public, anon, authenticated;
revoke all on function public.validate_evidence_record_location() from public, anon, authenticated;

create trigger evidence_records_validate_origin
before insert or update of farm_profile_id, provider_fetch_id, source_type, derivation_input_ids
on public.evidence_records
for each row execute function public.validate_evidence_record_origin();

create trigger evidence_records_validate_location
before insert or update of farm_profile_id, evidence_point, evidence_area, coordinate_tolerance_m
on public.evidence_records
for each row execute function public.validate_evidence_record_location();

create table public.evidence_bundles (
  id uuid primary key default extensions.gen_random_uuid(),
  farm_profile_id uuid not null references public.farm_profiles(id) on delete restrict,
  external_bundle_id text not null unique,
  bundle_version integer not null,
  supersedes_bundle_id uuid,
  schema_version text not null,
  status public.evidence_bundle_status not null default 'assembling',

  catalog_version text not null,
  catalog_hash text,
  catalog_source_path text,
  contains_catalog_evidence boolean not null default true,
  location_snapshot_jsonb jsonb not null,
  provider_coverage_jsonb jsonb not null default '{}'::jsonb,
  freshness_summary_jsonb jsonb not null default '{}'::jsonb,
  validation_summary_jsonb jsonb not null default '{}'::jsonb,
  completeness_percent numeric(5, 2),
  missing_required_variables text[] not null default '{}'::text[],
  warnings text[] not null default '{}'::text[],
  record_count integer not null default 0,

  bundle_snapshot jsonb,
  bundle_hash text generated always as (public.jsonb_sha256(bundle_snapshot)) stored,
  assembled_at timestamptz,
  validated_at timestamptz,
  error_message text,
  created_at timestamptz not null default statement_timestamp(),
  updated_at timestamptz not null default statement_timestamp(),

  constraint evidence_bundles_external_id_format
    check (external_bundle_id ~ '^[a-z0-9][a-z0-9_-]{2,99}$'),
  constraint evidence_bundles_positive_version
    check (bundle_version > 0),
  constraint evidence_bundles_version_predecessor_presence
    check (
      (bundle_version = 1 and supersedes_bundle_id is null)
      or (bundle_version > 1 and supersedes_bundle_id is not null)
    ),
  constraint evidence_bundles_schema_version_present
    check (btrim(schema_version) <> ''),
  constraint evidence_bundles_catalog_version_present
    check (btrim(catalog_version) <> ''),
  constraint evidence_bundles_catalog_hash_format
    check (catalog_hash is null or catalog_hash ~ '^[0-9a-f]{64}$'),
  constraint evidence_bundles_location_object
    check (jsonb_typeof(location_snapshot_jsonb) = 'object'),
  constraint evidence_bundles_provider_coverage_object
    check (jsonb_typeof(provider_coverage_jsonb) = 'object'),
  constraint evidence_bundles_freshness_summary_object
    check (jsonb_typeof(freshness_summary_jsonb) = 'object'),
  constraint evidence_bundles_validation_summary_object
    check (jsonb_typeof(validation_summary_jsonb) = 'object'),
  constraint evidence_bundles_safe_metadata
    check (
      not public.jsonb_contains_sensitive_keys(location_snapshot_jsonb)
      and not public.jsonb_contains_sensitive_keys(provider_coverage_jsonb)
      and not public.jsonb_contains_sensitive_keys(freshness_summary_jsonb)
      and not public.jsonb_contains_sensitive_keys(validation_summary_jsonb)
    ),
  constraint evidence_bundles_completeness_range
    check (completeness_percent is null or completeness_percent between 0 and 100),
  constraint evidence_bundles_missing_variables_no_nulls
    check (array_position(missing_required_variables, null) is null),
  constraint evidence_bundles_warnings_no_nulls
    check (array_position(warnings, null) is null),
  constraint evidence_bundles_record_count_nonnegative
    check (record_count >= 0),
  constraint evidence_bundles_snapshot_object
    check (
      bundle_snapshot is null
      or (
        jsonb_typeof(bundle_snapshot) = 'object'
        and not public.jsonb_contains_sensitive_keys(bundle_snapshot)
      )
    ),
  constraint evidence_bundles_lifecycle
    check (
      (
        status = 'assembling'
        and validated_at is null
        and error_message is null
      )
      or (
        status = 'partial'
        and assembled_at is not null
        and validated_at is null
        and bundle_snapshot is not null
        and completeness_percent is not null
        and error_message is null
      )
      or (
        status = 'validated'
        and assembled_at is not null
        and validated_at is not null
        and validated_at >= assembled_at
        and bundle_snapshot is not null
        and completeness_percent is not null
        and record_count > 0
        and error_message is null
      )
      or (
        status = 'failed'
        and validated_at is null
        and error_message is not null
        and btrim(error_message) <> ''
      )
    ),
  constraint evidence_bundles_session_version_unique
    unique (farm_profile_id, bundle_version),
  constraint evidence_bundles_profile_id_pair_unique
    unique (farm_profile_id, id),
  constraint evidence_bundles_profile_predecessor_fk
    foreign key (farm_profile_id, supersedes_bundle_id)
    references public.evidence_bundles(farm_profile_id, id)
    on delete restrict,
  constraint evidence_bundles_updated_after_creation
    check (updated_at >= created_at)
);

create or replace function public.validate_evidence_bundle_version()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  predecessor_version integer;
begin
  if new.supersedes_bundle_id is null then
    return new;
  end if;

  select bundle_version
    into predecessor_version
  from public.evidence_bundles
  where id = new.supersedes_bundle_id
    and farm_profile_id = new.farm_profile_id;

  if predecessor_version is null then
    raise exception 'Superseded bundle must belong to the same farm profile.';
  end if;

  if new.bundle_version <> predecessor_version + 1 then
    raise exception 'Evidence bundle versions must increase by exactly one.';
  end if;

  return new;
end;
$$;

create or replace function public.validate_evidence_bundle_terminal_state()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  actual_record_count integer;
begin
  if new.status = 'validated' then
    select count(*)
      into actual_record_count
    from public.evidence_bundle_records
    where evidence_bundle_id = new.id;

    if actual_record_count = 0 or actual_record_count <> new.record_count then
      raise exception 'Validated bundle record_count must match non-empty bundle membership.';
    end if;
  end if;

  return new;
end;
$$;

revoke all on function public.validate_evidence_bundle_version() from public, anon, authenticated;
revoke all on function public.validate_evidence_bundle_terminal_state() from public, anon, authenticated;

create trigger evidence_bundles_set_updated_at
before update on public.evidence_bundles
for each row execute function public.set_updated_at();

create trigger evidence_bundles_validate_version
before insert or update of farm_profile_id, bundle_version, supersedes_bundle_id
on public.evidence_bundles
for each row execute function public.validate_evidence_bundle_version();

create table public.evidence_bundle_records (
  evidence_bundle_id uuid not null references public.evidence_bundles(id) on delete restrict,
  evidence_record_id uuid not null references public.evidence_records(id) on delete restrict,
  inclusion_role public.bundle_record_role not null,
  inclusion_order integer not null,
  inclusion_reason text,
  created_at timestamptz not null default statement_timestamp(),

  primary key (evidence_bundle_id, evidence_record_id),
  constraint evidence_bundle_records_positive_order
    check (inclusion_order > 0),
  constraint evidence_bundle_records_order_unique
    unique (evidence_bundle_id, inclusion_order),
  constraint evidence_bundle_records_reason_length
    check (inclusion_reason is null or char_length(inclusion_reason) <= 500)
);

create or replace function public.validate_evidence_bundle_membership()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  bundle_profile_id uuid;
  bundle_status public.evidence_bundle_status;
  record_profile_id uuid;
begin
  if tg_op = 'UPDATE' and new.evidence_bundle_id <> old.evidence_bundle_id then
    raise exception 'Evidence bundle membership cannot be moved between bundles.';
  end if;

  select farm_profile_id, status
    into bundle_profile_id, bundle_status
  from public.evidence_bundles
  where id = coalesce(new.evidence_bundle_id, old.evidence_bundle_id);

  if not found then
    raise exception 'Evidence bundle does not exist.';
  end if;

  if bundle_status in ('validated', 'failed') then
    raise exception 'Terminal evidence bundle membership cannot be changed.';
  end if;

  if tg_op <> 'DELETE' then
    select farm_profile_id
      into record_profile_id
    from public.evidence_records
    where id = new.evidence_record_id;

    if not found then
      raise exception 'Evidence record does not exist.';
    end if;

    if record_profile_id <> bundle_profile_id then
      raise exception 'Bundle and evidence record must use the same farm profile.';
    end if;
  end if;

  if tg_op = 'DELETE' then
    return old;
  end if;

  return new;
end;
$$;

create or replace function public.refresh_evidence_bundle_record_count()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  target_bundle_id uuid;
begin
  target_bundle_id := coalesce(new.evidence_bundle_id, old.evidence_bundle_id);

  update public.evidence_bundles
  set record_count = (
    select count(*)
    from public.evidence_bundle_records
    where evidence_bundle_id = target_bundle_id
  )
  where id = target_bundle_id;

  if tg_op = 'DELETE' then
    return old;
  end if;

  return new;
end;
$$;

revoke all on function public.validate_evidence_bundle_membership() from public, anon, authenticated;
revoke all on function public.refresh_evidence_bundle_record_count() from public, anon, authenticated;

create trigger evidence_bundle_records_validate_membership
before insert or update or delete on public.evidence_bundle_records
for each row execute function public.validate_evidence_bundle_membership();

create trigger evidence_bundle_records_refresh_count
after insert or update or delete on public.evidence_bundle_records
for each row execute function public.refresh_evidence_bundle_record_count();

create trigger evidence_bundles_validate_terminal_state
before insert or update of status, record_count
on public.evidence_bundles
for each row execute function public.validate_evidence_bundle_terminal_state();

create unique index evidence_bundles_one_successor_idx
  on public.evidence_bundles(supersedes_bundle_id)
  where supersedes_bundle_id is not null;

create index evidence_records_profile_variable_idx
  on public.evidence_records(farm_profile_id, canonical_variable, freshness);

create index evidence_records_provider_fetch_idx
  on public.evidence_records(provider_fetch_id)
  where provider_fetch_id is not null;

create index evidence_records_derivation_inputs_gin
  on public.evidence_records using gin(derivation_input_ids)
  where derivation_input_ids is not null;

create index evidence_records_point_gix
  on public.evidence_records using gist(evidence_point);

create index evidence_records_area_gix
  on public.evidence_records using gist(evidence_area)
  where evidence_area is not null;

create index evidence_bundles_profile_status_idx
  on public.evidence_bundles(farm_profile_id, status, created_at desc);

create index evidence_bundles_hash_idx
  on public.evidence_bundles(bundle_hash)
  where bundle_hash is not null;

create index evidence_bundle_records_record_idx
  on public.evidence_bundle_records(evidence_record_id, evidence_bundle_id);

alter table public.evidence_records enable row level security;
alter table public.evidence_bundles enable row level security;
alter table public.evidence_bundle_records enable row level security;

revoke all on table public.evidence_records from anon, authenticated;
revoke all on table public.evidence_bundles from anon, authenticated;
revoke all on table public.evidence_bundle_records from anon, authenticated;
grant select on table public.evidence_records to authenticated;
grant select on table public.evidence_bundles to authenticated;
grant select on table public.evidence_bundle_records to authenticated;

create policy evidence_records_select_own_profile
on public.evidence_records
for select
to authenticated
using (
  exists (
    select 1
    from public.farm_profiles
    join public.assessment_sessions
      on assessment_sessions.id = farm_profiles.assessment_session_id
    where farm_profiles.id = evidence_records.farm_profile_id
      and assessment_sessions.owner_user_id = (select auth.uid())
  )
);

create policy evidence_bundles_select_own_profile
on public.evidence_bundles
for select
to authenticated
using (
  exists (
    select 1
    from public.farm_profiles
    join public.assessment_sessions
      on assessment_sessions.id = farm_profiles.assessment_session_id
    where farm_profiles.id = evidence_bundles.farm_profile_id
      and assessment_sessions.owner_user_id = (select auth.uid())
  )
);

create policy evidence_bundle_records_select_own_bundle
on public.evidence_bundle_records
for select
to authenticated
using (
  exists (
    select 1
    from public.evidence_bundles
    join public.farm_profiles
      on farm_profiles.id = evidence_bundles.farm_profile_id
    join public.assessment_sessions
      on assessment_sessions.id = farm_profiles.assessment_session_id
    where evidence_bundles.id = evidence_bundle_records.evidence_bundle_id
      and assessment_sessions.owner_user_id = (select auth.uid())
  )
);

comment on table public.evidence_records is
  'Normalized provider, farmer, laboratory, or derived facts with explicit availability, freshness, provenance, and lineage.';
comment on column public.evidence_records.derivation_input_ids is
  'Same-profile evidence record IDs used by a named and versioned deterministic derivation.';
comment on table public.evidence_bundles is
  'Exact, versioned EvidenceBundle snapshots assembled from ordered reusable evidence records.';
comment on table public.evidence_bundle_records is
  'Ordered membership linking reusable evidence records to an EvidenceBundle without duplication.';
