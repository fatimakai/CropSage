-- Align persisted scoring results with the finalized regional-eligibility gate contract.

create or replace function public.applied_gates_include(
  gates jsonb,
  required_gate text
)
returns boolean
language sql
immutable
strict
parallel safe
set search_path = ''
as $$
  select
    pg_catalog.jsonb_typeof(gates) = 'array'
    and exists (
      select 1
      from pg_catalog.jsonb_array_elements(gates) as entry(value)
      where
        (
          pg_catalog.jsonb_typeof(entry.value) = 'string'
          and entry.value #>> '{}' = required_gate
        )
        or (
          pg_catalog.jsonb_typeof(entry.value) = 'object'
          and coalesce(
            entry.value ->> 'gate',
            entry.value ->> 'gate_id',
            entry.value ->> 'gate_code',
            entry.value ->> 'code'
          ) = required_gate
        )
    );
$$;

revoke all on function public.applied_gates_include(jsonb, text)
  from public, anon, authenticated;

alter table public.crop_score_results
  drop constraint crop_score_results_ineligible_policy;

alter table public.crop_score_results
  add constraint crop_score_results_ineligible_policy
  check (
    status <> 'scored'
    or regionally_eligible
    or (
      recommendation = 'not_recommended'
      and suitability_score is not null
      and suitability_score <= 54
      and public.applied_gates_include(applied_gates_jsonb, 'unsupported_region')
    )
  );

comment on function public.applied_gates_include(jsonb, text) is
  'Returns true when a gate array contains the required gate code as a string or normalized gate object.';

comment on constraint crop_score_results_ineligible_policy on public.crop_score_results is
  'A scored regionally ineligible crop must be capped at 54, classified not_recommended, and retain the unsupported_region gate.';
