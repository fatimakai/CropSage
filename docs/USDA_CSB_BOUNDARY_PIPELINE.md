# USDA CSB Boundary Pipeline

## Source And Scope

- Official source: USDA NASS Crop Sequence Boundaries (CSB).
- Active version: `2018-2025 rev23`, released March 27, 2026.
- National download: [`NationalCSB_2018-2025_rev23.zip`](https://www.nass.usda.gov/Research_and_Science/Crop-Sequence-Boundaries/datasets/NationalCSB_2018-2025_rev23.zip) from the [USDA NASS CSB page](https://data.nass.usda.gov/Research_and_Science/Crop-Sequence-Boundaries/).
- Application scope: Texas features (`STATEFIPS = 48`).
- Stored attributes: `CSBID`, `STATEFIPS`, `CNTYFIPS`, `CNTY`, `CSBACRES`, geometry, representative point, dataset version, source URL, and import time.

CSB polygons are synthetic crop-field boundaries. They are not property, ownership, cadastral, or tax-parcel boundaries. CropSage uses them only as an optional way to choose a farm field on the map.

## Prepare A Texas Export

The national archive is several gigabytes. Extract its file geodatabase locally, then use GDAL to select Texas and reproject to WGS84. GeoJSON Sequence keeps the export streamable:

```powershell
ogr2ogr -f GeoJSONSeq data/usda-csb/texas-2018-2025.geojsonseq `
  C:\path\to\CSB1825.gdb national1825 `
  -where "STATEFIPS = '48'" `
  -t_srs EPSG:4326 `
  -select CSBID,STATEFIPS,CNTYFIPS,CNTY,CSBACRES
```

Run a validation pass before touching the database:

```powershell
npm run db:csb:import -- --input data/usda-csb/texas-2018-2025.geojsonseq --dry-run
```

Import a complete rectangular data pack into the configured local or hosted Supabase project. The export must contain every source feature intersecting the same `-spat` bounds:

```powershell
ogr2ogr -f GeoJSONSeq data/usda-csb/plainview-tile.geojsonseq `
  C:\path\to\CSB1825.gdb national1825 `
  -spat -101.80 34.15 -101.72 34.22 `
  -spat_srs EPSG:4326 `
  -t_srs EPSG:4326 `
  -select CSBID,STATEFIPS,CNTYFIPS,CNTY,CSBACRES

npm run db:csb:import -- `
  --input data/usda-csb/plainview-tile.geojsonseq `
  --coverage-id plainview-tile `
  --coverage-label "Plainview complete tile" `
  --coverage-status ready `
  --coverage-bbox -101.80,34.15,-101.72,34.22 `
  --county-fips 189 `
  --county-name Hale
```

Only use `--coverage-status ready` when every feature intersecting the declared bounding box was included in the export. A county-filtered export cannot claim its rectangular bounding box as ready because that rectangle can include neighboring counties. Samples or incomplete extracts must use `partial`. The viewport API reports `covered`, `partial`, or `not_loaded`, so missing data is never presented as land without crop fields.

The importer reads `.geojsonseq`, `.geojsonl`, and `.jsonl` line by line and sends at most 250 validated features per RPC. Small `.geojson` FeatureCollections are also supported, with a 100 MB safety limit. It enforces a 200 MB CSB table-and-index budget by default; a paid deployment can deliberately override this with `--max-storage-mb` after capacity is provisioned.

## Local Demo

After `npm run db:reset`, load the bounded official Plainview fixture:

```powershell
npm run db:csb:demo
```

`db:csb:demo` uses `--local`, which obtains its URL and secret key from the running Supabase CLI stack. For hosted imports, omit `--local` and configure the target in `apps/web/.env.local` or the process environment.

The map requests fields through `/api/field-boundaries`. The browser never receives a Supabase service key and cannot query or mutate the reference table directly.

Run the web application against the local Supabase stack without changing hosted credentials:

```powershell
npm run web:dev:local
```

## Deployment Capacity

The official Texas Earth Engine asset is approximately 506 MB before PostGIS and index overhead, so full Texas coverage cannot fit safely inside Supabase Free's 500 MB database quota. The Free-plan MVP reserves at most 200 MB for CSB boundaries and imports selected site or county packs incrementally. Manual field drawing and point selection remain available throughout Texas.

Use `public.get_usda_csb_storage_usage('2018-2025-rev23')` from a server-authorized context to monitor field count and total CSB table-plus-index bytes. Supabase Pro currently includes an 8 GB disk, but a full statewide PostGIS export must still be measured before deployment.
