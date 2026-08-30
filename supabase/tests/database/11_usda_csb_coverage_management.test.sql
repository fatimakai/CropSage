begin;

set local search_path = public, extensions;

select plan(17);

select has_table('public', 'usda_csb_coverage', 'CSB coverage registry exists');
select has_column('public', 'usda_csb_coverage', 'coverage_status', 'coverage completeness is explicit');
select has_column('public', 'usda_csb_coverage', 'coverage_area', 'coverage retains its declared area');
select has_column('public', 'usda_csb_coverage', 'table_storage_bytes_at_import', 'coverage records storage at import');

select has_index(
  'public',
  'usda_csb_coverage',
  'usda_csb_coverage_area_gist_idx',
  'coverage lookups have a spatial index'
);

select ok(
  (select relrowsecurity from pg_class where oid = 'public.usda_csb_coverage'::regclass),
  'coverage registry has RLS enabled'
);

select ok(
  not has_table_privilege('anon', 'public.usda_csb_coverage', 'SELECT')
    and not has_table_privilege('authenticated', 'public.usda_csb_coverage', 'SELECT'),
  'browser roles cannot inspect coverage records directly'
);

select is(
  public.import_usda_csb_fields(
    '2018-2025-rev23',
    '[{
      "type":"Feature",
      "geometry":{"type":"Polygon","coordinates":[[[-101.77,34.17],[-101.75,34.17],[-101.75,34.19],[-101.77,34.19],[-101.77,34.17]]]},
      "properties":{"CSBID":"481825000000002","STATEFIPS":"48","CNTYFIPS":"189","CNTY":"Hale","CSBACRES":104.2}
    }]'::jsonb
  ),
  1,
  'coverage test field imports'
);

select is(
  public.get_usda_csb_viewport(
    '2018-2025-rev23', -101.78, 34.16, -101.74, 34.20, 350
  ) ->> 'coverage_status',
  'partial',
  'unregistered imported fields are explicitly partial'
);

select is(
  public.get_usda_csb_viewport(
    '2018-2025-rev23', -99.10, 31.00, -99.00, 31.10, 350
  ) ->> 'coverage_status',
  'not_loaded',
  'an unregistered area is not confused with empty farmland'
);

select is(
  public.register_usda_csb_coverage(
    '2018-2025-rev23',
    'hale-ready-pack',
    'Hale County complete test pack',
    'ready',
    -101.80,
    34.15,
    -101.72,
    34.22,
    '189',
    'Hale'
  ) ->> 'coverage_status',
  'ready',
  'a complete bounded pack registers as ready'
);

select is(
  (
    select field_count
    from public.usda_csb_coverage
    where dataset_version = '2018-2025-rev23'
      and coverage_id = 'hale-ready-pack'
  ),
  1,
  'coverage registration calculates its intersecting field count'
);

select is(
  public.get_usda_csb_viewport(
    '2018-2025-rev23', -101.78, 34.16, -101.74, 34.20, 350
  ) ->> 'coverage_status',
  'covered',
  'a viewport fully inside a ready pack is covered'
);

select is(
  public.get_usda_csb_viewport(
    '2018-2025-rev23', -101.81, 34.16, -101.74, 34.20, 350
  ) ->> 'coverage_status',
  'partial',
  'a viewport crossing a ready-pack edge is only partial'
);

select cmp_ok(
  (public.get_usda_csb_storage_usage('2018-2025-rev23') ->> 'table_storage_bytes')::bigint,
  '>',
  0::bigint,
  'storage usage reports table and index bytes'
);

select throws_ok(
  $$
    select public.register_usda_csb_coverage(
      '2018-2025-rev23', 'invalid pack', 'Invalid', 'ready',
      -101.80, 34.15, -101.72, 34.22, null, null
    )
  $$,
  'A lowercase coverage identifier is required.',
  'invalid coverage identifiers are rejected'
);

select throws_ok(
  $$
    select public.register_usda_csb_coverage(
      '2018-2025-rev23', 'bad-status', 'Invalid', 'complete',
      -101.80, 34.15, -101.72, 34.22, null, null
    )
  $$,
  'Coverage status must be partial or ready.',
  'unknown coverage statuses are rejected'
);

select * from finish();

rollback;
