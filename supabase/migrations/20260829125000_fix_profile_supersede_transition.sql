-- Stored generated columns are recomputed after BEFORE triggers. Exclude the
-- derived input_hash when checking the one permitted ready-profile transition.

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
      and (pg_catalog.to_jsonb(new) - 'status' - 'updated_at' - 'input_hash')
        = (pg_catalog.to_jsonb(old) - 'status' - 'updated_at' - 'input_hash')
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

revoke all on function public.enforce_farm_profile_immutability()
  from public, anon, authenticated;

comment on function public.enforce_farm_profile_immutability() is
  'Keeps ready profiles immutable while allowing status-only supersession; input_hash is excluded because PostgreSQL recomputes stored generated columns after BEFORE triggers.';
