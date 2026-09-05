from geokrig.views import safe_label
from geokrig.views import map_html
from geokrig.demo import demo_data
from geokrig.core import validate_observations,read_corridor,prepare_snapshot,predict


def test_tooltip_escapes_html_and_js_template_literals():
    text=safe_label('sensor` ${alert(1)} </script> \\')
    assert '`' not in text and '${' not in text and '<' not in text and '\\' not in text


def test_local_map_has_no_geographic_basemap_even_when_requested():
    raw,route=demo_data()
    df=validate_observations(raw)
    corridor=read_corridor(route)
    snap=prepare_snapshot(df,df.timestamp.iloc[-1],corridor,35)
    grid=predict(snap,corridor,'settlement_mm')
    html=map_html(grid,snap,corridor,tiles=True)
    assert 'L.CRS.Simple' in html
    assert 'L.tileLayer(' not in html
    assert 'tile.openstreetmap' not in html
    assert 'no geographic location' in html
