begin;

set local search_path = public, extensions;

select plan(5);

select ok(
  not exists (
    select 1
    from unnest(array[
      'assessment_sessions',
      'farm_profiles',
      'provider_fetches',
      'evidence_records',
      'evidence_bundles',
      'evidence_bundle_records',
      'recommendation_runs',
      'crop_score_results',
      'validation_reports',
      'run_events'
    ]) as app_tables(table_name)
    cross join unnest(array['SELECT', 'INSERT', 'UPDATE']) as privileges(privilege_name)
    where not has_table_privilege(
      'service_role',
      'public.' || app_tables.table_name,
      privileges.privilege_name
    )
  ),
  'the server service role can read and perform lifecycle writes on every application table'
);

select ok(
  not exists (
    select 1
    from unnest(array[
      'assessment_sessions',
      'farm_profiles',
      'provider_fetches',
      'evidence_records',
      'evidence_bundles',
      'evidence_bundle_records',
      'recommendation_runs',
      'crop_score_results',
      'validation_reports',
      'run_events'
    ]) as app_tables(table_name)
    cross join unnest(array['DELETE', 'TRUNCATE']) as privileges(privilege_name)
    where has_table_privilege(
      'service_role',
      'public.' || app_tables.table_name,
      privileges.privilege_name
    )
  ),
  'the server service role cannot delete or truncate application records'
);

select ok(
  has_schema_privilege('service_role', 'public', 'USAGE'),
  'the server service role can resolve objects in the application schema'
);

select ok(
  case
    when to_regprocedure('public.rls_auto_enable()') is null then true
    else not has_function_privilege(
      'anon',
      to_regprocedure('public.rls_auto_enable()'),
      'EXECUTE'
    )
  end,
  'anonymous database clients cannot execute the automatic-RLS event trigger function'
);

select ok(
  case
    when to_regprocedure('public.rls_auto_enable()') is null then true
    else not has_function_privilege(
      'authenticated',
      to_regprocedure('public.rls_auto_enable()'),
      'EXECUTE'
    )
  end,
  'authenticated clients cannot execute the automatic-RLS event trigger function'
);

select * from finish();

rollback;
