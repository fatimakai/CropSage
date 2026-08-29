-- CropSage user-safe run events and final persistence/security hardening.

create type public.run_event_kind as enum (
  'provider',
  'evidence',
  'scoring',
  'validation',
  'system'
);

create type public.run_event_status as enum (
  'started',
  'succeeded',
  'failed',
  'info'
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
          'download_link',
          'chain_of_thought',
          'hidden_reasoning',
          'internal_reasoning'
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

revoke all on function public.jsonb_contains_sensitive_keys(jsonb) from public, anon, authenticated;

create table public.run_events (
  id uuid primary key default extensions.gen_random_uuid(),
  recommendation_run_id uuid not null references public.recommendation_runs(id) on delete restrict,
  sequence_number integer not null,
  event_kind public.run_event_kind not null,
  event_name text not null,
  status public.run_event_status not null,
  tool_name text,
  provider_fetch_id uuid references public.provider_fetches(id) on delete restrict,
  evidence_bundle_id uuid references public.evidence_bundles(id) on delete restrict,
  cache_state public.provider_fetch_mode,
  arguments_summary_jsonb jsonb not null default '{}'::jsonb,
  safe_summary text not null,
  error_code text,
  error_message text,
  started_at timestamptz,
  finished_at timestamptz,
  occurred_at timestamptz not null default statement_timestamp(),
  event_snapshot jsonb not null,
  event_hash text generated always as (public.jsonb_sha256(event_snapshot)) stored,
  created_at timestamptz not null default statement_timestamp(),

  constraint run_events_sequence_positive
    check (sequence_number > 0),
  constraint run_events_name_format
    check (event_name ~ '^[a-z][a-z0-9_.-]{1,99}$'),
  constraint run_events_tool_name_format
    check (tool_name is null or tool_name ~ '^[a-z][a-z0-9_.-]{1,99}$'),
  constraint run_events_summary_length
    check (char_length(btrim(safe_summary)) between 1 and 500),
  constraint run_events_error_lengths
    check (
      (error_code is null or char_length(error_code) between 1 and 100)
      and (error_message is null or char_length(error_message) between 1 and 1000)
    ),
  constraint run_events_arguments_safe
    check (
      jsonb_typeof(arguments_summary_jsonb) = 'object'
      and not public.jsonb_contains_sensitive_keys(arguments_summary_jsonb)
    ),
  constraint run_events_snapshot_safe
    check (
      jsonb_typeof(event_snapshot) = 'object'
      and not public.jsonb_contains_sensitive_keys(event_snapshot)
    ),
  constraint run_events_status_shape
    check (
      (
        status = 'started'
        and started_at is not null
        and finished_at is null
        and error_code is null
        and error_message is null
      )
      or (
        status = 'succeeded'
        and started_at is not null
        and finished_at is not null
        and finished_at >= started_at
        and error_code is null
        and error_message is null
      )
      or (
        status = 'failed'
        and started_at is not null
        and finished_at is not null
        and finished_at >= started_at
        and error_code is not null
        and error_message is not null
      )
      or (
        status = 'info'
        and started_at is null
        and finished_at is null
        and error_code is null
        and error_message is null
      )
    ),
  constraint run_events_occurred_after_start
    check (started_at is null or occurred_at >= started_at),
  constraint run_events_created_after_occurrence
    check (created_at >= occurred_at),
  constraint run_events_run_sequence_unique
    unique (recommendation_run_id, sequence_number)
);

create or replace function public.validate_run_event()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  run_profile_id uuid;
  run_bundle_id uuid;
  fetch_profile_id uuid;
  expected_sequence integer;
begin
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(new.recommendation_run_id::text, 0)
  );

  select farm_profile_id, evidence_bundle_id
    into run_profile_id, run_bundle_id
  from public.recommendation_runs
  where id = new.recommendation_run_id;

  if not found then
    raise exception 'Run event must reference an existing recommendation run.';
  end if;

  select coalesce(max(sequence_number), 0) + 1
    into expected_sequence
  from public.run_events
  where recommendation_run_id = new.recommendation_run_id;

  if new.sequence_number <> expected_sequence then
    raise exception 'Run event sequence must be the next contiguous number: expected %.', expected_sequence;
  end if;

  if new.provider_fetch_id is not null then
    select farm_profile_id
      into fetch_profile_id
    from public.provider_fetches
    where id = new.provider_fetch_id;

    if not found or fetch_profile_id <> run_profile_id then
      raise exception 'Run event provider fetch must use the recommendation run farm profile.';
    end if;
  end if;

  if new.evidence_bundle_id is not null and new.evidence_bundle_id <> run_bundle_id then
    raise exception 'Run event evidence bundle must match the recommendation run bundle.';
  end if;

  return new;
end;
$$;

create or replace function public.reject_run_event_mutation()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  raise exception 'Run events are append-only and cannot be updated or deleted.';
end;
$$;

create or replace function public.enforce_farm_profile_immutability()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if old.status = 'superseded' then
    raise exception 'Superseded farm profiles are immutable.';
  end if;

  if old.status = 'ready' then
    if new.status = 'superseded'
      and (pg_catalog.to_jsonb(new) - 'status' - 'updated_at')
        = (pg_catalog.to_jsonb(old) - 'status' - 'updated_at')
    then
      return new;
    end if;

    raise exception 'Ready farm profiles are immutable; create a successor profile version.';
  end if;

  if old.status = 'draft' and new.status not in ('draft', 'ready') then
    raise exception 'A draft farm profile may only remain draft or become ready.';
  end if;

  return new;
end;
$$;

create or replace function public.reject_evidence_record_mutation()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  raise exception 'Evidence records are append-only; create a new record for corrections.';
end;
$$;

create or replace function public.enforce_provider_fetch_lifecycle()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if old.status in ('succeeded', 'failed') then
    raise exception 'Succeeded or failed provider fetches are immutable.';
  end if;

  if not (
    (old.status = 'pending' and new.status in ('pending', 'running', 'succeeded', 'failed'))
    or (old.status = 'running' and new.status in ('running', 'succeeded', 'failed'))
  ) then
    raise exception 'Invalid provider fetch status transition from % to %.', old.status, new.status;
  end if;

  return new;
end;
$$;

create or replace function public.enforce_evidence_bundle_lifecycle()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if old.status in ('validated', 'failed') then
    raise exception 'Validated or failed evidence bundles are immutable.';
  end if;

  if not (
    (old.status = 'assembling' and new.status in ('assembling', 'partial', 'validated', 'failed'))
    or (old.status = 'partial' and new.status in ('partial', 'validated', 'failed'))
  ) then
    raise exception 'Invalid evidence bundle status transition from % to %.', old.status, new.status;
  end if;

  return new;
end;
$$;

revoke all on function public.validate_run_event() from public, anon, authenticated;
revoke all on function public.reject_run_event_mutation() from public, anon, authenticated;
revoke all on function public.enforce_farm_profile_immutability() from public, anon, authenticated;
revoke all on function public.reject_evidence_record_mutation() from public, anon, authenticated;
revoke all on function public.enforce_provider_fetch_lifecycle() from public, anon, authenticated;
revoke all on function public.enforce_evidence_bundle_lifecycle() from public, anon, authenticated;

create trigger run_events_validate_insert
before insert on public.run_events
for each row execute function public.validate_run_event();

create trigger run_events_reject_mutation
before update or delete on public.run_events
for each row execute function public.reject_run_event_mutation();

create trigger farm_profiles_enforce_immutability
before update on public.farm_profiles
for each row execute function public.enforce_farm_profile_immutability();

create trigger evidence_records_reject_mutation
before update or delete on public.evidence_records
for each row execute function public.reject_evidence_record_mutation();

create trigger provider_fetches_enforce_lifecycle
before update on public.provider_fetches
for each row execute function public.enforce_provider_fetch_lifecycle();

create trigger evidence_bundles_enforce_lifecycle
before update on public.evidence_bundles
for each row execute function public.enforce_evidence_bundle_lifecycle();

create index run_events_run_occurred_idx
  on public.run_events(recommendation_run_id, occurred_at, sequence_number);

create index run_events_provider_fetch_idx
  on public.run_events(provider_fetch_id)
  where provider_fetch_id is not null;

create index run_events_evidence_bundle_idx
  on public.run_events(evidence_bundle_id)
  where evidence_bundle_id is not null;

create index assessment_sessions_active_profile_idx
  on public.assessment_sessions(active_profile_id)
  where active_profile_id is not null;

create index provider_fetches_cache_hit_idx
  on public.provider_fetches(cache_hit_fetch_id)
  where cache_hit_fetch_id is not null;

create index recommendation_runs_evidence_bundle_idx
  on public.recommendation_runs(evidence_bundle_id);

alter table public.run_events enable row level security;

revoke all on table public.run_events from anon, authenticated;
grant select on table public.run_events to authenticated;

create policy run_events_select_own_run
on public.run_events
for select
to authenticated
using (
  exists (
    select 1
    from public.recommendation_runs
    join public.assessment_sessions
      on assessment_sessions.id = recommendation_runs.assessment_session_id
    where recommendation_runs.id = run_events.recommendation_run_id
      and assessment_sessions.owner_user_id = (select auth.uid())
  )
);

-- Storage remains server-only for the MVP: no browser RLS policies are created.
-- Supabase manages base Storage table grants; service-role requests bypass RLS.

comment on table public.run_events is
  'Append-only, user-safe progress and audit events for a recommendation run; never hidden reasoning or credentials.';
comment on column public.run_events.arguments_summary_jsonb is
  'Sanitized structured argument summary only; full provider requests remain on provider_fetches.';
comment on column public.run_events.safe_summary is
  'Short presentation-safe status text suitable for logs or application progress UI.';
