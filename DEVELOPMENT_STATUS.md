# Development checkpoint

## Intended release

GeoKrig-TESM v0.1.0: Streamlit GIS application with corridor-coordinate ordinary
Kriging, three monitored quantities, conditional uncertainty, threshold screening,
monitoring candidates, validation, and GIS exports. Synthetic highway and railway
examples only; no claims of field deployment or validated instability prediction.

## Scope agreed with owner

- Replace all thesis files in the current repository tree; leave the original local
  thesis directory untouched.
- Push the finished project to YIXINLI921/GeoKrig-TESM, main.
- Do not change repository visibility. It is currently private.
- Prior history was explicitly reconstructed as placeholders with preserved dates.
  The previous 1.11 snapshot contains thesis code; ordinary replacement here does
  not purge that historical snapshot. A separate cleanup is needed before public release.

## Resume instructions

Read this file and README.md, inspect git status and recent commits, then run
`python -m pytest -q` in an environment with requirements.txt installed. Do not
rebuild from scratch or reset user changes. The app entry point is app.py;
the numerical implementation is geokrig/core.py. Generate example outputs with
`python scripts/export_demo.py`. Complete any checks listed below, then push only
the intended new project changes to the existing main branch.

## Current checkpoint

Location privacy update: examples now use arbitrary local metres (LocalRoute
JSON and x_m/y_m CSV), rendered with Leaflet CRS.Simple without map tiles.
Local exports use LocalGrid JSON rather than claiming WGS84 coordinates.
Geographic field uploads still support WGS84 GIS export; their basemap is off
by default. These uploads are not anonymised. Old Git snapshots are not purged.
All 15 tests passed for this update. Browser inspection confirmed the local map
contains no geographic basemap or location labels. Example inputs and preview
were regenerated; obsolete local WGS84 example output files were removed.

Implementation and English README are complete. All 13 tests passed locally on
Python 3.12; these cover six asset/variable combinations, exact interpolation,
coordinate round trips, invalid data, masking, thresholds, validation, safe
tooltip labels and Streamlit interactions. Browser QA verified that Leaflet
renders, the validation result is 1.36 mm RMSE for the default settlement demo,
and the ZIP download triggers successfully. docs/analysis-preview.png was generated
from actual results and visually checked. GitHub Actions is configured for
Python 3.11 and 3.12 but its remote result has not yet been checked.

Final input hardening is complete and the final local suite passed: 13 tests in
6.11 seconds. The v0.1.0 implementation was pushed to main successfully.
GitHub's README and updated About description were verified in the browser.
The README workflow uses a plain numbered sequence to avoid a GitHub Mermaid
rendering failure. Remote CI was pending when last viewed; local verification is
complete. Do not treat this as an unbuilt project or repeat the initial replacement.
