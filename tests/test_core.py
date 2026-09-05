import json
import numpy as np
import pytest
from shapely.geometry import shape
from geokrig.core import (METRICS, validate_observations, read_corridor, prepare_snapshot, predict,
                          fit_model, cross_validate, grid_geojson, local_grid_json, monitoring_candidates)
from geokrig.demo import demo_data


@pytest.fixture
def sample():
    raw, route = demo_data()
    df = validate_observations(raw)
    corridor = read_corridor(route)
    snap = prepare_snapshot(df, sorted(df.timestamp.unique())[-1], corridor, 35)
    return df,corridor,snap


@pytest.mark.parametrize('asset',['Highway','Railway'])
@pytest.mark.parametrize('metric',list(METRICS))
def test_end_to_end_export(asset,metric):
    raw,route = demo_data(asset)
    df = validate_observations(raw)
    corridor = read_corridor(route)
    snap = prepare_snapshot(df,df.timestamp.iloc[-1],corridor,35)
    grid = predict(snap,corridor,metric,threshold=METRICS[metric][2])
    assert 0 < grid.supported.mean() < 1
    assert grid.loc[~grid.supported,'prediction'].isna().all()
    assert np.isfinite(grid.loc[grid.supported,'prediction']).all()
    assert (grid.loc[grid.supported,'std_dev'] >= 0).all()
    obj = json.loads(local_grid_json(grid,corridor))
    assert len(obj['cells']) == 1170
    assert all(shape(f['geometry']).is_valid for f in obj['cells'])
    assert all(f['properties']['prediction'] is None for f in obj['cells'] if not f['properties']['supported'])
    assert obj['metadata']['epsg'] is None
    assert 'longitude' not in grid and 'latitude' not in grid
    with pytest.raises(ValueError,match='no geographic CRS'):
        grid_geojson(grid,corridor)


def test_exact_interpolation_and_coordinate_roundtrip(sample):
    _,corridor,snap = sample
    pts = snap[['chainage_m','offset_m']].to_numpy()
    fitted = fit_model(pts,snap.settlement_mm.to_numpy(),'spherical',4.)
    values,variance = fitted.execute('points',pts[:,0],pts[:,1]*4.)
    np.testing.assert_allclose(values,snap.settlement_mm,atol=1e-6)
    np.testing.assert_allclose(variance,0,atol=1e-6)
    for s,o in [(100,-20),(500,10),(900,0)]:
        np.testing.assert_allclose(corridor.locate(*corridor.lonlat(s,o)),[s,o],atol=.001)


def test_support_and_thresholds(sample):
    _,corridor,snap = sample
    grid = predict(snap,corridor,'settlement_mm',max_distance=50,threshold=1e6)
    assert (grid.loc[grid.supported,'nearest_sensor_m'] <= 50).all()
    assert set(grid.loc[grid.supported,'screening']) == {'Below threshold'}
    lower = predict(snap,corridor,'settlement_mm',threshold=-1e6)
    assert set(lower.loc[lower.supported,'screening']) == {'Threshold exceeded'}
    sites=monitoring_candidates(grid)
    for i in range(len(sites)):
        for j in range(i):
            assert abs(sites.chainage_m.iloc[i]-sites.chainage_m.iloc[j]) >= 120


def test_loocv_residuals(sample):
    _,_,snap = sample
    cv = cross_validate(snap,'settlement_mm')
    assert len(cv) == len(snap)
    assert np.isfinite(cv.predicted).all()
    assert cv.attrs['rmse'] == pytest.approx(np.sqrt(np.mean((cv.predicted-cv.observed)**2)))


def test_reject_bad_inputs(sample):
    df,corridor,snap = sample
    with pytest.raises(ValueError,match='Missing'):
        validate_observations(df.drop(columns='x_m'))
    bad = df.copy(); bad.loc[0,'moisture_pct']=101
    with pytest.raises(ValueError,match='water content'):
        validate_observations(bad)
    bad=df.copy(); bad.loc[0,'x_m']=np.inf
    with pytest.raises(ValueError,match='finite'):
        validate_observations(bad)
    with pytest.raises(ValueError,match='Duplicate'):
        validate_observations(__import__('pandas').concat([df,df.iloc[:1]]))
    with pytest.raises(ValueError,match='constant'):
        fit_model(snap[['chainage_m','offset_m']].to_numpy(),np.ones(len(snap)),'spherical',4)
    with pytest.raises(ValueError,match='outside'):
        prepare_snapshot(df,df.timestamp.iloc[-1],corridor,2)
    with pytest.raises(ValueError,match='LineString'):
        read_corridor({'type':'Polygon','coordinates':[]})
    with pytest.raises(ValueError,match='JSON object'):
        read_corridor([])
    with pytest.raises(ValueError,match='LineString'):
        read_corridor({'type':'Feature','geometry':None})


def test_collinear_rejected(sample):
    _,corridor,snap=sample
    flat=snap.copy()
    for i,r in flat.iterrows():
        flat.loc[i,['x_m','y_m']]=corridor.lonlat(r.chainage_m,0)
    with pytest.raises(ValueError,match='collinear'):
        prepare_snapshot(flat,flat.timestamp.iloc[0],corridor,35)


def test_geographic_upload_still_exports_wgs84(sample):
    _,_,local=sample
    corridor=read_corridor({'type':'LineString','coordinates':[[0.,0.],[.011,0.]]})
    field=local.drop(columns=['x_m','y_m']).copy()
    for i,r in field.iterrows():
        field.loc[i,['longitude','latitude']]=corridor.lonlat(r.chainage_m,r.offset_m)
    field=validate_observations(field)
    snap=prepare_snapshot(field,field.timestamp.iloc[0],corridor,35)
    grid=predict(snap,corridor,'settlement_mm')
    obj=json.loads(grid_geojson(grid,corridor))
    assert obj['type']=='FeatureCollection'
    assert obj['metadata']['coordinate_system']=='WGS84'
