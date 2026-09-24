# Test fixtures - provenance

These files are **unmodified rows from real NASA FIRMS data**, used only by the test suite
(they are never loaded into the database).

| File | Source | Retrieved |
|------|--------|-----------|
| `firms_viirs_snpp_sample.csv` | FIRMS public NRT feed, VIIRS S-NPP C2, South Asia 7d: `https://firms.modaps.eosdis.nasa.gov/data/active_fire/suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_South_Asia_7d.csv` | 2026-09-23 17:00 UTC |
| `firms_modis_sample.csv` | FIRMS public NRT feed, MODIS C6.1, South Asia 7d: `https://firms.modaps.eosdis.nasa.gov/data/active_fire/modis-c6.1/csv/MODIS_C6_1_South_Asia_7d.csv` | 2026-09-23 17:00 UTC |

Each file holds 30 detections inside India's monitoring area (official-claim boundary + EEZ)
followed by 10 detections outside it (neighbouring countries), so clipping can be tested.
