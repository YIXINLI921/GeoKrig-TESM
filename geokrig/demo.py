"""Seeded synthetic data, deliberately unrelated to any real infrastructure asset."""
import numpy as np
import pandas as pd
from .core import read_corridor


def demo_data(asset='Highway'):
    railway = asset == 'Railway'
    route = {'type': 'LocalRoute', 'coordinate_system': 'local_metres',
             'name': f'Synthetic {asset.lower()} embankment', 'synthetic': True,
             'coordinates': [[0.,0.], [1160.,0.]]}
    corridor = read_corridor(route)
    rng = np.random.default_rng(71 if railway else 42)
    # Three cross-track positions at ten stations; a deliberate longitudinal coverage gap.
    stations = np.array([45, 130, 220, 310, 400, 670, 760, 860, 950, 1040])
    stations = stations/stations.max()*(corridor.line.length-45)
    locations = [(s+rng.uniform(-8,8), o+rng.uniform(-1.5,1.5)) for s in stations for o in [-23,0,23]]
    rows = []
    for day, factor in [('2026-08-01', .35), ('2026-08-08', .70), ('2026-08-15', 1.0)]:
        for i, (s,o) in enumerate(locations):
            lon,lat = corridor.lonlat(s,o)
            wet = np.exp(-((s-corridor.line.length*.67)/190)**2)
            side = 1+.22*o/25
            rows.append({'sensor_id': f'{"R" if railway else "H"}{i+1:02d}', 'timestamp': day,
                         'x_m': lon, 'y_m': lat,
                         'settlement_mm': round(5+23*factor*wet*side+rng.normal(0,.35),3),
                         'pore_pressure_kpa': round(12+36*factor*wet*side+rng.normal(0,.7),3),
                         'moisture_pct': round(22+14*factor*wet*side+rng.normal(0,.3),3)})
    return pd.DataFrame(rows), route
