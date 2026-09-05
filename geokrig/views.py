"""Exportable GIS map and corridor profile views."""
import json
from html import escape
import folium
import numpy as np
import plotly.graph_objects as go
from branca.colormap import LinearColormap
from .core import grid_features

STATUS_COLOURS = {'Below threshold': '#2a9d8f', 'Uncertainty overlaps threshold': '#e9b44c',
                  'Threshold exceeded': '#d45151', 'No estimate': '#a9b4c2'}


def safe_label(value):
    # Folium tooltips use JavaScript template literals, not JSON string literals.
    return escape(str(value)).replace('\\', '&#92;').replace('`', '&#96;').replace('$', '&#36;')


def map_html(grid, snap, corridor, layer='Condition', candidates=None, tiles=True):
    coords = corridor.coordinates
    local = corridor.epsg is None
    m = folium.Map(location=[np.mean([c[1] for c in coords]), np.mean([c[0] for c in coords])],
                   tiles='OpenStreetMap' if tiles and not local else None,
                   crs='Simple' if local else 'EPSG3857', control_scale=not local,
                   min_zoom=-5 if local else 0)
    key = 'std_dev' if layer == 'Uncertainty' else 'prediction'
    valid = grid.loc[grid.supported, key]
    lo, hi = float(valid.min()), float(valid.max())
    colour = LinearColormap(['#d5eeed','#54ada6','#176f78','#183a58'] if key=='std_dev'
                           else ['#236a8c','#63b5ac','#f2db8c','#d96052'], vmin=lo, vmax=max(hi,lo+1e-6))
    colour.caption = f'{"Kriging standard deviation" if key=="std_dev" else grid.attrs["metric"]} ({grid.attrs["unit"]})'
    def style(feature):
        p = feature['properties']
        fill = STATUS_COLOURS[p['screening']] if layer == 'Screening' else colour(p[key]) if p['supported'] else '#a9b4c2'
        return {'fillColor': fill, 'color': fill, 'weight': .1, 'fillOpacity': .8 if p['supported'] else .16}
    folium.GeoJson(grid_features(grid,corridor), name=layer, style_function=style,
                   tooltip=folium.GeoJsonTooltip(fields=['chainage_m','prediction','std_dev','unit','screening'],
                   aliases=['Chainage (m)','Estimate','Kriging SD','Unit','Screening'])).add_to(m)
    folium.PolyLine([[c[1],c[0]] for c in coords], color='#172b41', weight=2, opacity=.7, tooltip='Reference centreline').add_to(m)
    sensors = folium.FeatureGroup(name='Sensors')
    for r in snap.itertuples():
        position = [r.y_m,r.x_m] if local else [r.latitude,r.longitude]
        folium.CircleMarker(position,radius=4,color='#fff',weight=1.3,fill=True,fill_color='#172b41',fill_opacity=1,
            tooltip=f'{safe_label(r.sensor_id)}: {getattr(r,grid.attrs["metric"]):.2f} {grid.attrs["unit"]}').add_to(sensors)
    sensors.add_to(m)
    if candidates is not None:
        for i,r in enumerate(candidates.itertuples(),1):
            position = [r.y_m,r.x_m] if local else [r.latitude,r.longitude]
            folium.Marker(position,tooltip=f'Candidate {i} · {r.chainage_m:.0f} m',
                          icon=folium.DivIcon(html=f'<div style="background:#172b41;color:white;border:2px solid white;border-radius:50%;width:24px;height:24px;text-align:center;font: bold 13px/24px sans-serif">{i}</div>')).add_to(m)
    if layer != 'Screening':
        colour.add_to(m)
    else:
        legend = ''.join(f'<span style="color:{v}">●</span> {k}<br>' for k,v in STATUS_COLOURS.items())
        m.get_root().html.add_child(folium.Element('<div style="position:fixed;bottom:25px;left:15px;z-index:999;background:white;padding:12px;border-radius:8px;font:12px sans-serif">'+legend+'</div>'))
    folium.LayerControl().add_to(m)
    margin_y,margin_x = (100,50) if local else (.0004,.0005)
    m.fit_bounds([[min(c[1] for c in coords)-margin_y,min(c[0] for c in coords)-margin_x],
                  [max(c[1] for c in coords)+margin_y,max(c[0] for c in coords)+margin_x]])
    if local:
        m.get_root().html.add_child(folium.Element('<div style="position:fixed;top:60px;left:55px;z-index:999;background:white;padding:8px;font:12px sans-serif">Synthetic corridor · local metres · no geographic location</div>'))
    return m.get_root().render()


def profile(grid, snap):
    centre = grid.loc[np.isclose(grid.offset_m, 0)].sort_values('chainage_m')
    x, y, sd = centre.chainage_m, centre.prediction, centre.std_dev
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x,y=y-1.96*sd,mode='lines',line={'width':0},showlegend=False,connectgaps=False))
    fig.add_trace(go.Scatter(x=x,y=y+1.96*sd,mode='lines',line={'width':0},fill='tonexty',
                            fillcolor='rgba(19,127,119,0.15)',name='±1.96 kriging SD',connectgaps=False))
    fig.add_trace(go.Scatter(x=x,y=y,mode='lines',line={'color':'#137f77','width':3},name='Centreline estimate',connectgaps=False))
    fig.add_trace(go.Scatter(x=snap.chainage_m,y=snap[grid.attrs['metric']],mode='markers',name='Sensors (all offsets)',
                            marker={'color':'#172b41','size':6},text=snap.sensor_id))
    fig.add_hline(y=grid.attrs['threshold'],line_dash='dash',line_color='#d45151',annotation_text='Screening threshold')
    fig.update_layout(height=310,margin={'l':10,'r':20,'t':25,'b':10},paper_bgcolor='rgba(0,0,0,0)',
                      plot_bgcolor='white',font={'color':'#172b41'},legend={'orientation':'h','y':1.2},
                      xaxis_title='Chainage from route start (m)',yaxis_title=grid.attrs['unit'])
    return fig
