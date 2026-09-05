"""Reproduce all bundled synthetic inputs and sample GIS outputs."""
from pathlib import Path
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from geokrig.core import METRICS, validate_observations, read_corridor, prepare_snapshot, predict, local_grid_json, cross_validate
from geokrig.demo import demo_data
from geokrig.views import map_html

root = Path(__file__).resolve().parents[1]
if __name__ == '__main__':
    (root/'examples').mkdir(exist_ok=True)
    (root/'outputs').mkdir(exist_ok=True)
    for asset in ['Highway','Railway']:
        raw, route = demo_data(asset)
        raw.to_csv(root/'examples'/f'{asset.lower()}_monitoring.csv',index=False)
        (root/'examples'/f'{asset.lower()}_route.json').write_text(json.dumps(route,indent=2))
        df = validate_observations(raw)
        corridor = read_corridor(route)
        snap = prepare_snapshot(df,sorted(df.timestamp.unique())[-1],corridor,35)
        for metric in METRICS:
            grid = predict(snap,corridor,metric,threshold=METRICS[metric][2])
            stem = f'{asset.lower()}_{metric}'
            (root/'outputs'/f'{stem}_local.json').write_text(local_grid_json(grid,corridor))
            (root/'outputs'/f'{stem}.html').write_text(map_html(grid,snap,corridor))
            cv = cross_validate(snap,metric)
            cv.to_csv(root/'outputs'/f'{stem}_validation.csv',index=False)
            print(stem, 'supported', int(grid.supported.sum()), 'validation', cv.attrs)
