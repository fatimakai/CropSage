begin;

set local search_path = public, extensions;

select plan(15);

select has_extension('pgcrypto', 'pgcrypto extension is installed');
select has_extension('postgis', 'PostGIS extension is installed');
select has_extension('pgtap', 'pgTAP extension is installed');

select has_type('public', 'assessment_session_status', 'assessment session status enum exists');
select has_type('public', 'farm_profile_status', 'farm profile status enum exists');
select has_type('public', 'provider_fetch_status', 'provider fetch status enum exists');
select has_type('public', 'provider_fetch_mode', 'provider fetch mode enum exists');
select has_type('public', 'evidence_source_type', 'evidence source type enum exists');
select has_type('public', 'evidence_bundle_status', 'evidence bundle status enum exists');
select has_type('public', 'recommendation_run_status', 'recommendation run status enum exists');
select has_type('public', 'evaluation_mode', 'evaluation mode enum exists');
select has_type('public', 'crop_result_status', 'crop result status enum exists');
select has_type('public', 'recommendation_class', 'recommendation class enum exists');
select has_type('public', 'confidence_band', 'confidence band enum exists');

select results_eq(
  $$
    select enumlabel::text collate "C"
    from pg_enum
    join pg_type on pg_type.oid = pg_enum.enumtypid
    join pg_namespace on pg_namespace.oid = pg_type.typnamespace
    where pg_namespace.nspname = 'public'
      and pg_type.typname = 'recommendation_run_status'
    order by enumsortorder
  $$,
  $$
    select expected_label collate "C"
    from (values
      ('pending'::text),
      ('running'::text),
      ('scored'::text),
      ('validated'::text),
      ('completed'::text),
      ('failed'::text)
    ) as expected(expected_label)
  $$,
  'recommendation run lifecycle matches the locked contract'
);

select * from finish();

rollback;
