begin;

set local search_path = public, extensions;

select plan(18);

select has_table('public', 'usda_csb_fields', 'USDA CSB reference table exists');
select has_column('public', 'usda_csb_fields', 'dataset_version', 'CSB rows retain dataset version');
select has_column('public', 'usda_csb_fields', 'field_id', 'CSB rows retain the source identifier');
select has_column('public', 'usda_csb_fields', 'boundary', 'CSB rows retain field geometry');
select has_column('public', 'usda_csb_fields', 'representative_point', 'CSB rows retain an interior point');

select col_type_is(
  'public',
  'usda_csb_fields',
  'boundary',
  'extensions.geometry(MultiPolygon,4326)',
  'CSB boundaries use indexed PostGIS MultiPolygon geometry'
);

select has_index(
  'public',
  'usda_csb_fields',
  'usda_csb_fields_boundary_gist_idx',
  'CSB viewport intersections have a spatial index'
);

select ok(
  (select relrowsecurity from pg_class where oid = 'public.usda_csb_fields'::regclass),
  'CSB reference rows have RLS enabled'
);

select ok(
  not has_table_privilege('anon', 'public.usda_csb_fields', 'SELECT')
    and not has_table_privilege('authenticated', 'public.usda_csb_fields', 'SELECT'),
  'browser roles cannot read CSB rows directly'
);

select ok(
  not has_function_privilege(
    'authenticated',
    'public.get_usda_csb_viewport(text,double precision,double precision,double precision,double precision,integer)',
    'EXECUTE'
  ),
  'authenticated clients cannot execute the server viewport function'
);

select is(
  public.import_usda_csb_fields(
    '2018-2025-rev23',
    '[{
      "type":"Feature",
      "geometry":{"type":"Polygon","coordinates":[[[-101.77,34.17],[-101.75,34.17],[-101.75,34.19],[-101.77,34.19],[-101.77,34.17]]]},
      "properties":{"CSBID":"481825000000001","STATEFIPS":"48","CNTYFIPS":"189","CNTY":"Hale","CSBACRES":104.2}
    }]'::jsonb
  ),
  1,
  'a valid official-shape CSB feature imports through the bounded RPC'
);

select is(
  (
    select count(*)
    from public.usda_csb_fields
    where dataset_version = '2018-2025-rev23'
      and field_id = '481825000000001'
  ),
  1::bigint,
  'the imported field is stored once'
);

select ok(
  (
    select extensions.st_isvalid(boundary)
      and extensions.st_covers(boundary, representative_point)
    from public.usda_csb_fields
    where dataset_version = '2018-2025-rev23'
      and field_id = '481825000000001'
  ),
  'the stored field has valid geometry and an interior representative point'
);

select is(
  public.get_usda_csb_viewport(
    '2018-2025-rev23',
    -101.78,
    34.16,
    -101.74,
    34.20,
    350
  ) ->> 'available',
  'true',
  'the viewport reports an imported dataset as available'
);

select is(
  pg_catalog.jsonb_array_length(
    public.get_usda_csb_viewport(
      '2018-2025-rev23',
      -101.78,
      34.16,
      -101.74,
      34.20,
      350
    ) -> 'features'
  ),
  1,
  'the viewport returns intersecting fields'
);

select is(
  public.get_usda_csb_viewport(
    '2018-2025-rev23',
    -101.78,
    34.16,
    -101.74,
    34.20,
    350
  ) #>> '{features,0,properties,field_id}',
  '481825000000001',
  'the viewport preserves the official CSB identifier'
);

select throws_ok(
  $$
    select public.get_usda_csb_viewport(
      '2018-2025-rev23', -106.0, 26.0, -94.0, 36.0, 350
    )
  $$,
  'The CSB viewport is too large; zoom in before requesting fields.',
  'oversized viewport requests are rejected'
);

select throws_ok(
  $$
    select public.import_usda_csb_fields(
      '2018-2025-rev23',
      '[{
        "type":"Feature",
        "geometry":{"type":"Polygon","coordinates":[[[-97.8,30.2],[-97.7,30.2],[-97.7,30.3],[-97.8,30.3],[-97.8,30.2]]]},
        "properties":{"CSBID":"401825000000001","STATEFIPS":"40","CSBACRES":20}
      }]'::jsonb
    )
  $$,
  'A Texas CSBID is required for every imported feature.',
  'non-Texas CSB identifiers are rejected'
);

select * from finish();

rollback;
