"""Validated, corridor-coordinate ordinary Kriging; no UI dependencies."""
from dataclasses import dataclass
import json
import warnings

import numpy as np
import pandas as pd
from pykrige.ok import OrdinaryKriging
from pyproj import Transformer
from scipy.spatial import Delaunay, cKDTree, QhullError
from shapely.geometry import LineString, Point

METRICS = {
    'settlement_mm': ('Settlement', 'mm', 18.0),
    'pore_pressure_kpa': ('Pore-water pressure', 'kPa', 35.0),
    'moisture_pct': ('Volumetric water content', '%', 32.0),
}
MODELS = ('spherical', 'exponential', 'gaussian')


@dataclass
class Corridor:
    line: LineString
    forward: Transformer
    inverse: Transformer
    epsg: int | None
    coordinates: list

    def locate(self, lon, lat):
        x, y = self.forward.transform(lon, lat)
        point = Point(x, y)
        s = self.line.project(point)
        centre = self.line.interpolate(s)
        a = self.line.interpolate(max(0, s - 0.1))
        b = self.line.interpolate(min(self.line.length, s + 0.1))
        tangent = np.array([b.x-a.x, b.y-a.y])
        delta = np.array([x-centre.x, y-centre.y])
        cross = tangent[0]*delta[1] - tangent[1]*delta[0]
        return s, float(np.copysign(point.distance(centre), cross))

    def lonlat(self, s, offset):
        centre = self.line.interpolate(float(s))
        a = self.line.interpolate(max(0, float(s)-0.1))
        b = self.line.interpolate(min(self.line.length, float(s)+0.1))
        dx, dy = b.x-a.x, b.y-a.y
        length = np.hypot(dx, dy)
        return self.inverse.transform(centre.x-offset*dy/length, centre.y+offset*dx/length)


def read_corridor(obj):
    if not isinstance(obj, dict):
        raise ValueError('Route GeoJSON must be a JSON object.')
    if obj.get('type') == 'LocalRoute':
        xy = np.asarray(obj.get('coordinates', []), dtype=float)
        if xy.ndim != 2 or xy.shape[0] < 2 or xy.shape[1] != 2 or not np.isfinite(xy).all():
            raise ValueError('Local route needs finite [x_m, y_m] coordinates.')
        line = LineString(xy)
        if not line.is_simple or not 100 <= line.length <= 20000:
            raise ValueError('Local route must be simple and 100 m–20 km long.')
        if (np.linalg.norm(np.diff(xy, axis=0), axis=1) < .01).any():
            raise ValueError('Remove repeated adjacent route vertices.')
        identity = Transformer.from_pipeline('+proj=noop')
        return Corridor(line, identity, identity, None, xy.tolist())
    if obj.get('type') == 'FeatureCollection':
        if not isinstance(obj.get('features'), list) or len(obj['features']) != 1:
            raise ValueError('Route GeoJSON must contain exactly one LineString feature.')
        obj = obj['features'][0]
        if not isinstance(obj, dict):
            raise ValueError('Route feature must be a JSON object.')
    if obj.get('type') == 'Feature':
        obj = obj.get('geometry', {})
    if not isinstance(obj, dict):
        raise ValueError('Route geometry must be a LineString object.')
    if obj.get('type') != 'LineString':
        raise ValueError('Route must be a WGS84 GeoJSON LineString, not a polygon or MultiLineString.')
    xy = np.asarray(obj.get('coordinates', []), dtype=float)
    if xy.ndim != 2 or xy.shape[0] < 2 or xy.shape[1] != 2 or not np.isfinite(xy).all():
        raise ValueError('Route needs at least two finite [longitude, latitude] positions.')
    if (np.abs(xy[:, 0]) > 180).any() or (xy[:, 1] < -80).any() or (xy[:, 1] > 84).any():
        raise ValueError('Coordinates must be WGS84 within the UTM latitude range (-80 to 84).')
    if np.ptp(xy[:, 0]) > 180:
        raise ValueError('Routes crossing the antimeridian are not supported.')
    lon, lat = xy.mean(axis=0)
    zone = min(60, int((lon+180)//6)+1)
    epsg = (32600 if lat >= 0 else 32700)+zone
    forward = Transformer.from_crs(4326, epsg, always_xy=True)
    inverse = Transformer.from_crs(epsg, 4326, always_xy=True)
    line = LineString(np.column_stack(forward.transform(xy[:, 0], xy[:, 1])))
    if not line.is_simple or not 100 <= line.length <= 20000:
        raise ValueError('Use a simple, non-self-intersecting route between 100 m and 20 km long.')
    if (np.linalg.norm(np.diff(np.asarray(line.coords), axis=0), axis=1) < 0.01).any():
        raise ValueError('Remove repeated adjacent route vertices.')
    return Corridor(line, forward, inverse, epsg, xy.tolist())


def validate_observations(frame):
    local = {'x_m', 'y_m'} <= set(frame.columns)
    if local and ({'longitude', 'latitude'} & set(frame.columns)):
        raise ValueError('Use either local x_m/y_m or longitude/latitude, not both.')
    coordinate_columns = ['x_m', 'y_m'] if local else ['longitude', 'latitude']
    required = {'sensor_id', 'timestamp', *coordinate_columns} | set(METRICS)
    missing = required - set(frame.columns)
    if missing:
        raise ValueError('Missing CSV columns: '+', '.join(sorted(missing)))
    if len(frame) > 10000 or frame.empty:
        raise ValueError('Upload between 1 and 10,000 rows.')
    df = frame.copy()
    if df['sensor_id'].isna().any() or df['sensor_id'].astype(str).str.strip().eq('').any():
        raise ValueError('Every row needs a sensor_id.')
    df['sensor_id'] = df.sensor_id.astype(str)
    times = pd.to_datetime(df.timestamp, errors='coerce', utc=True)
    if times.isna().any():
        raise ValueError('Timestamps must be valid ISO dates or date-times.')
    df['timestamp'] = times.dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    for col in [*coordinate_columns, *METRICS]:
        df[col] = pd.to_numeric(df[col], errors='coerce')
        if not np.isfinite(df[col]).all():
            raise ValueError(f'{col} must contain finite numeric values without blanks.')
    if not local and ((df.longitude.abs() > 180).any() or (df.latitude.abs() > 90).any()):
        raise ValueError('Longitude/latitude values are outside WGS84 bounds.')
    if not df.moisture_pct.between(0, 100).all():
        raise ValueError('Volumetric water content must be between 0 and 100 percent.')
    if df.duplicated(['sensor_id', 'timestamp']).any():
        raise ValueError('Duplicate sensor_id/timestamp pairs: use one reading per sensor per snapshot.')
    return df


def prepare_snapshot(df, timestamp, corridor, half_width):
    snap = df.loc[df.timestamp == timestamp].copy().reset_index(drop=True)
    if not 8 <= len(snap) <= 80:
        raise ValueError('Each snapshot must contain 8–80 sensors.')
    cols = ['x_m', 'y_m'] if corridor.epsg is None else ['longitude', 'latitude']
    if not set(cols) <= set(snap.columns):
        raise ValueError('Sensor and route coordinate systems must match.')
    positions = np.array([corridor.locate(x,y) for x,y in snap[cols].to_numpy()])
    snap['chainage_m'], snap['offset_m'] = positions.T
    if (np.abs(positions[:, 1]) > half_width).any():
        raise ValueError('Some sensors lie outside the corridor width. Check route/coordinates or increase half-width.')
    if cKDTree(positions).query(positions, k=2)[0][:, 1].min() < 0.05:
        raise ValueError('Sensor positions must be at least 5 cm apart; aggregate colocated readings first.')
    if np.linalg.matrix_rank(positions-positions.mean(axis=0), tol=0.1) < 2:
        raise ValueError('Sensors are collinear. Two-dimensional mapping needs sensors across the embankment as well as along it.')
    return snap


def fit_model(points, values, model, cross_scale):
    if model not in MODELS or not 1 <= cross_scale <= 20:
        raise ValueError('Invalid variogram model or cross-track scaling.')
    if np.ptp(values) < 1e-10:
        raise ValueError('This snapshot is constant; a spatial variogram cannot be fitted reliably.')
    with warnings.catch_warnings():
        warnings.simplefilter('error', RuntimeWarning)
        return OrdinaryKriging(points[:, 0], points[:, 1]*cross_scale, values,
                               variogram_model=model, nlags=6, weight=True,
                               pseudo_inv=True, exact_values=True, verbose=False)


def predict(snap, corridor, metric, half_width=35., max_distance=180., cross_scale=4.,
            model='spherical', threshold=18., nx=90, ny=13):
    if metric not in METRICS or half_width <= 0 or max_distance <= 0 or not np.isfinite(threshold):
        raise ValueError('Invalid analysis parameters.')
    points = snap[['chainage_m', 'offset_m']].to_numpy()
    values = snap[metric].to_numpy(dtype=float)
    fitted = fit_model(points, values, model, cross_scale)
    ds, do = corridor.line.length/nx, 2*half_width/ny
    ss, oo = np.meshgrid((np.arange(nx)+.5)*ds, -half_width+(np.arange(ny)+.5)*do)
    target = np.column_stack([ss.ravel(), oo.ravel()])
    try:
        inside = Delaunay(points).find_simplex(target) >= 0
    except QhullError as exc:
        raise ValueError('Sensor geometry cannot support a two-dimensional surface.') from exc
    distances = cKDTree(points).query(target)[0]
    supported = inside & (distances <= max_distance)
    if not supported.any():
        raise ValueError('No grid cells have adequate spatial support. Increase the support distance or check sensor geometry.')
    pred, variance = fitted.execute('points', target[supported, 0], target[supported, 1]*cross_scale)
    pred, variance = np.asarray(pred), np.asarray(variance)
    if not np.isfinite(pred).all() or not np.isfinite(variance).all() or variance.min() < -1e-6:
        raise ValueError('Kriging produced invalid predictions/variance. Try another model or check the data.')
    grid = pd.DataFrame(target, columns=['chainage_m', 'offset_m'])
    grid['supported'] = supported
    grid['nearest_sensor_m'] = distances
    grid['prediction'] = np.nan
    grid['std_dev'] = np.nan
    grid.loc[supported, 'prediction'] = pred
    grid.loc[supported, 'std_dev'] = np.sqrt(np.maximum(variance, 0))
    grid['screening'] = 'No estimate'
    grid.loc[supported, 'screening'] = 'Below threshold'
    grid.loc[supported & (grid.prediction >= threshold), 'screening'] = 'Threshold exceeded'
    # Gaussian upper bound is only a sensitivity flag, not a calibrated failure probability.
    uncertain = supported & (grid.prediction < threshold) & (grid.prediction+1.96*grid.std_dev >= threshold)
    grid.loc[uncertain, 'screening'] = 'Uncertainty overlaps threshold'
    coords = np.array([corridor.lonlat(s, o) for s, o in target])
    cols = ['x_m', 'y_m'] if corridor.epsg is None else ['longitude', 'latitude']
    grid[cols[0]], grid[cols[1]] = coords.T
    grid.attrs = {'metric': metric, 'unit': METRICS[metric][1], 'threshold': float(threshold),
                  'variogram': model, 'cross_track_scale': float(cross_scale), 'epsg': corridor.epsg,
                  'snapshot': str(snap.timestamp.iloc[0]), 'ds': ds, 'do': do,
                  'max_distance_m': float(max_distance), 'half_width_m': float(half_width),
                  'coordinate_system': 'local_metres' if corridor.epsg is None else 'WGS84',
                  'interpretation': 'Screening only; kriging standard deviation is conditional on the fitted variogram, not failure probability.'}
    return grid


def cross_validate(snap, metric, model='spherical', cross_scale=4.):
    """LOOCV refits the variogram within each fold to avoid parameter leakage."""
    pts = snap[['chainage_m', 'offset_m']].to_numpy()
    values = snap[metric].to_numpy(dtype=float)
    rows = []
    for i in range(len(snap)):
        keep = np.arange(len(snap)) != i
        fitted = fit_model(pts[keep], values[keep], model, cross_scale)
        prediction, _ = fitted.execute('points', pts[i:i+1, 0], pts[i:i+1, 1]*cross_scale)
        rows.append({'sensor_id': str(snap.sensor_id.iloc[i]), 'observed': values[i],
                     'predicted': float(prediction[0]), 'residual': float(prediction[0])-values[i]})
    result = pd.DataFrame(rows)
    result.attrs = {'rmse': float(np.sqrt(np.mean(result.residual**2))),
                    'mae': float(np.abs(result.residual).mean()), 'bias': float(result.residual.mean())}
    return result


def monitoring_candidates(grid, count=3, separation=120.):
    """Prioritize conditional uncertainty; avoid clusters of suggested stations."""
    candidates = grid.loc[grid.supported & (grid.nearest_sensor_m >= 10)].sort_values('std_dev', ascending=False)
    chosen = []
    for _, row in candidates.iterrows():
        if all(abs(row.chainage_m-other.chainage_m) >= separation for other in chosen):
            chosen.append(row)
        if len(chosen) == count:
            break
    return pd.DataFrame(chosen, columns=grid.columns).reset_index(drop=True)


def grid_features(grid, corridor):
    ds, do = grid.attrs['ds'], grid.attrs['do']
    features = []
    for row in grid.itertuples():
        s, o = row.chainage_m, row.offset_m
        ring = [corridor.lonlat(s+a*ds/2, o+b*do/2) for a,b in [(-1,-1),(1,-1),(1,1),(-1,1),(-1,-1)]]
        props = {'chainage_m': s, 'offset_m': o, 'supported': bool(row.supported),
                 'prediction': float(row.prediction) if row.supported else None,
                 'std_dev': float(row.std_dev) if row.supported else None,
                 'nearest_sensor_m': row.nearest_sensor_m, 'screening': row.screening,
                 'unit': grid.attrs['unit'], 'metric': grid.attrs['metric']}
        features.append({'type': 'Feature', 'geometry': {'type': 'Polygon', 'coordinates': [ring]}, 'properties': props})
    return {'type': 'FeatureCollection', 'metadata': grid.attrs, 'features': features}


def grid_geojson(grid, corridor):
    if corridor.epsg is None:
        raise ValueError('Local coordinates have no geographic CRS; export local grid JSON instead.')
    return json.dumps(grid_features(grid,corridor), allow_nan=False)


def local_grid_json(grid, corridor):
    obj = grid_features(grid,corridor)
    return json.dumps({'type':'LocalGrid','coordinate_system':'local_metres',
                       'metadata':grid.attrs,'cells':obj['features']},allow_nan=False)
