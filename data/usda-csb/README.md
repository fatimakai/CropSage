# USDA Crop Sequence Boundaries

This directory contains bounded development fixtures only. Production data must be obtained from the official USDA NASS Crop Sequence Boundaries release and imported through `scripts/import-usda-csb.mjs`.

The boundaries are synthetic crop-field boundaries. They are useful for selecting agricultural fields, but they are not legal property, ownership, cadastral, or tax parcels.

`plainview-2018-2025.geojson` is a small, reproducible sample from the official public `2018-2025 rev23` Texas CSB asset. It is registered as `partial`, never as complete area coverage. It exists so local development can exercise the real map-selection flow without checking the multi-gigabyte national release into Git.
