"""Run with: streamlit run app.py"""
import io
import json
from zipfile import ZipFile, ZIP_DEFLATED
import pandas as pd
import streamlit as st
from geokrig.core import (METRICS, MODELS, read_corridor, validate_observations, prepare_snapshot,
                          predict, monitoring_candidates, cross_validate, grid_geojson, local_grid_json)
from geokrig.demo import demo_data
from geokrig.views import map_html, profile

st.set_page_config(page_title='GeoKrig-TESM | Earthwork monitoring', page_icon='◈', layout='wide')
st.markdown('''<style>
.block-container{padding-top:4.5rem;max-width:1500px}
h1{letter-spacing:-1.5px;font-weight:750!important}
[data-testid="stMetric"]{background:white;border:1px solid #e1e7ed;padding:16px;border-radius:12px}
.eyebrow{font-size:12px;font-weight:700;letter-spacing:2px;color:#137f77}
.subtitle{color:#617287;font-size:17px;max-width:880px;margin-bottom:24px}
</style>''', unsafe_allow_html=True)
st.markdown('<div class="eyebrow">TRANSPORT EARTHWORKS / SPATIAL MONITORING</div>',unsafe_allow_html=True)
st.title('GeoKrig-TESM')
st.markdown('<div class="subtitle">Map settlement, pore-water pressure and water content along transport embankments. Review interpolation uncertainty and measurements exceeding your selected threshold.</div>',unsafe_allow_html=True)

with st.sidebar:
    st.header('Analysis workspace')
    source = st.radio('Data source', ['Synthetic demo', 'Upload field data'])
    if source == 'Synthetic demo':
        asset = st.selectbox('Transport asset', ['Highway','Railway'])
        raw, route = demo_data(asset)
        st.caption('30 synthetic sensors · 3 snapshots · local coordinates. No real location, buildings or basemap.')
    else:
        csv = st.file_uploader('Monitoring CSV',type=['csv'])
        geo = st.file_uploader('Route GeoJSON or local route JSON',type=['geojson','json'])
        st.caption('Both files required. Download templates from the demo’s Data & exports tab.')
        if csv is None or geo is None:
            st.info('Upload sensor readings and a route to start.')
            st.stop()
        try:
            raw,route = pd.read_csv(csv),json.load(geo)
        except Exception as exc:
            st.error(f'Could not read input files: {exc}')
            st.stop()
    try:
        df = validate_observations(raw)
        corridor = read_corridor(route)
    except (ValueError,TypeError,KeyError) as exc:
        st.error(str(exc)); st.stop()
    timestamps = sorted(df.timestamp.unique())
    timestamp = st.selectbox('Monitoring snapshot',timestamps,index=len(timestamps)-1)
    metric = st.selectbox('Measurement',list(METRICS),format_func=lambda v:f'{METRICS[v][0]} ({METRICS[v][1]})')
    threshold = st.number_input('Upper screening threshold',value=METRICS[metric][2],key=f'threshold_{metric}')
    st.caption('Defaults are illustrative—not design limits or safety criteria. Higher values trigger screening.')
    with st.expander('Spatial model settings'):
        half_width = st.slider('Corridor half-width (m)',10,100,35,5)
        max_distance = st.slider('Maximum sensor support distance (m)',30,500,180,10)
        cross_scale = st.slider('Cross-track distance multiplier',1.,12.,4.,.5,
            help='Multiplies lateral offsets before fitting; larger values reduce assumed cross-track continuity. Scenario assumption, not calibrated anisotropy.')
        model = st.selectbox('Variogram',MODELS)
        basemap = False
        if corridor.epsg is not None:
            basemap = st.checkbox('Online basemap',False,help='For uploaded geographic data only. Tiles reveal the viewport location to OpenStreetMap. Disabling tiles does not anonymise the uploaded coordinates.')
    st.divider()
    st.caption('v0.1.0 · Ordinary Kriging')
    st.caption('Geospatial Kriging for Transport Earthwork Stability Monitoring')

try:
    snap = prepare_snapshot(df,timestamp,corridor,half_width)
    grid = predict(snap,corridor,metric,half_width,max_distance,cross_scale,model,threshold)
except (ValueError,RuntimeWarning,ArithmeticError) as exc:
    st.error(f'Analysis cannot proceed: {exc}'); st.stop()
candidates = monitoring_candidates(grid)
supported = grid.loc[grid.supported]
local = corridor.epsg is None
coordinate_label = 'Local coordinates (m) · no geographic reference' if local else f'Projected CRS EPSG:{corridor.epsg}'
st.caption(f'{"SYNTHETIC DEMONSTRATION" if source=="Synthetic demo" else "USER-SUPPLIED DATA"}  ·  {timestamp}  ·  {coordinate_label}')
cols=st.columns(4)
cols[0].metric('Monitoring points',len(snap))
cols[1].metric('Route length',f'{corridor.line.length/1000:.2f} km')
cols[2].metric('Supported grid cells',f'{grid.supported.mean():.0%}')
cols[3].metric('Above threshold¹',f'{(supported.prediction>=threshold).mean():.0%}')
st.caption('¹ Percentage of supported cells, not the whole embankment. Unsupported areas have no estimate.')
map_tab,check_tab,data_tab,method_tab = st.tabs(['Spatial overview','Model checks','Data & exports','Method & limits'])
with map_tab:
    left,right = st.columns([3,1])
    with left:
        layer = st.radio('Map layer',['Condition','Uncertainty','Screening'],horizontal=True)
        html = map_html(grid,snap,corridor,layer,candidates,basemap)
        st.iframe(html,height=470)
        st.caption('Grey cells: outside the sensor convex hull or beyond the support distance. Pan/zoom and hover to inspect cells. All layers are also available in the export bundle.')
    with right:
        st.subheader('Screening results')
        st.write('**Threshold exceeded** highlights a predicted measurement above your selected limit.')
        st.write('**Uncertainty overlaps threshold** flags where the estimate is below the limit but its upper uncertainty bound reaches it.')
        st.subheader('Suggested monitoring sites')
        st.caption('Ranked by kriging SD within supported cells; candidates are spaced ≥120 m in chainage. Coverage gaps outside the supported area still need a separate survey.')
        for i,row in candidates.iterrows():
            st.markdown(f'**{i+1:02d} · Chainage {row.chainage_m:.0f} m**  \nOffset {row.offset_m:+.0f} m · SD {row.std_dev:.2f} {METRICS[metric][1]}')
    st.subheader('Along the corridor')
    st.plotly_chart(profile(grid,snap),width='stretch')
    st.caption('Band = estimate ±1.96 × kriging SD under a Gaussian approximation; not a validated confidence interval. Gaps remain unestimated. Sensor markers include all lateral offsets.')
with check_tab:
    st.subheader('Leave-one-out validation')
    st.write('Leave one sensor out, refit the variogram, and predict its reading from the others. These residuals assess interpolation—not slope stability or future performance.')
    if st.button('Run leave-one-out validation',type='primary'):
        try:
            with st.spinner('Refitting the model for each held-out sensor…'):
                cv = cross_validate(snap,metric,model,cross_scale)
            a,b,c = st.columns(3)
            a.metric('RMSE',f'{cv.attrs["rmse"]:.2f} {METRICS[metric][1]}')
            b.metric('MAE',f'{cv.attrs["mae"]:.2f} {METRICS[metric][1]}')
            c.metric('Bias (predicted − observed)',f'{cv.attrs["bias"]:+.2f} {METRICS[metric][1]}')
            st.dataframe(cv,hide_index=True,width='stretch')
            st.download_button('Download validation residuals',cv.to_csv(index=False),'validation.csv','text/csv')
        except (ValueError,RuntimeWarning,ArithmeticError) as exc:
            st.error(f'Validation failed: {exc}. Try another variogram or check constant/degenerate folds.')
    st.info('Compare models and distance multipliers using validation and engineering knowledge. Selecting settings on the same residuals does not provide independent validation.')
with data_tab:
    st.subheader('Analysis exports')
    st.write('Local-coordinate exports contain no geographic reference. Geographic uploads can be exported as WGS84 GeoJSON. Both include CSV tables, HTML maps and analysis settings.')
    package=io.BytesIO()
    with ZipFile(package,'w',ZIP_DEFLATED) as z:
        z.writestr('grid_local.json' if local else 'grid.geojson',local_grid_json(grid,corridor) if local else grid_geojson(grid,corridor))
        z.writestr('grid.csv',grid.to_csv(index=False))
        z.writestr('monitoring_candidates.csv',candidates.to_csv(index=False))
        z.writestr('settings.json',json.dumps(grid.attrs,indent=2))
        z.writestr('selected_observations.csv',snap.to_csv(index=False))
        z.writestr('route_local.json' if local else 'route.geojson',json.dumps(route))
        for name in ['Condition','Uncertainty','Screening']:
            z.writestr(f'{name.lower()}_map.html',map_html(grid,snap,corridor,name,candidates,basemap))
        z.writestr('READ_ME.txt','GeoKrig-TESM screening export.\nSource: '+source+'\nCoordinates: '+coordinate_label+'\nLocalGrid/LocalRoute JSON uses metres, not WGS84 GeoJSON.\nNo failure probability or factor of safety is calculated.\nHTML maps need internet access for Leaflet libraries. Local maps make no tile requests.\nGrey/null cells are unsupported.\n')
    st.download_button('Download analysis bundle (.zip)',package.getvalue(),'geokrig_analysis.zip','application/zip',type='primary')
    a,b = st.columns(2)
    a.download_button('Download input CSV',raw.to_csv(index=False),'monitoring.csv','text/csv')
    b.download_button('Download route JSON' if local else 'Download route GeoJSON',json.dumps(route,indent=2),'route_local.json' if local else 'route.geojson','application/json')
    st.dataframe(snap,hide_index=True,width='stretch')
with method_tab:
    st.subheader('Method and assumptions')
    st.markdown('''
1. Validate sensor coordinates and one reading per sensor per snapshot. Demonstrations use an arbitrary local coordinate system in metres.
2. For geographic uploads, project the route to local UTM. Derive chainage and signed lateral offset.
3. Fit ordinary Kriging with an automatic variogram in corridor coordinates. The lateral distance multiplier is a user assumption.
4. Predict a 90 × 13 grid and conditional kriging standard deviation. Mask cells outside the sensor convex hull or the maximum support distance.
5. Compare estimates with an illustrative upper threshold; rank possible extra measurement locations by uncertainty.

**Scope:** settlement (positive downward), pore-water pressure (negative values permitted for suction), and volumetric water content. Each snapshot and variable is analysed independently; no temporal interpolation or sensor fusion is performed.

**Limits:** 8–80 sensors per snapshot; a gently curving, non-branching route 100 m–20 km long. Chainage zero is the first route vertex. Do not use this coordinate mapping for hairpins or overlapping corridor buffers. Width is user-defined, not a surveyed earthwork boundary. Support tests use cell centres.

Kriging SD excludes sensor error, variogram parameter uncertainty and model bias. Spatially varying trends can violate ordinary Kriging assumptions. Estimates are not clipped, so physically implausible predictions should prompt model review. Screening classes do not establish instability, a factor of safety, or a probability of failure. No operational alarms are issued.

**Privacy:** demonstration data uses local metres with no link to a real place. No buildings, roads, place names or map tiles are loaded for the demonstration. Uploaded geographic data retains its coordinates, including in exports; hiding its basemap does not anonymise it. Calculations run on the app host. Interactive maps load third-party JavaScript. Self-host for private field data.
''')
    st.markdown('[PyKrige method reference](https://geostat-framework.readthedocs.io/projects/pykrige/en/stable/generated/pykrige.ok.OrdinaryKriging.html) · [Source repository](https://github.com/YIXINLI921/GeoKrig-TESM)')
