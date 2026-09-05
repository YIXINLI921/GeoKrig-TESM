from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_default_and_alternative_scenarios():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=60)
    assert not app.exception
    assert app.metric[0].value == '30'
    app.selectbox[0].select('Railway').run(timeout=60)
    assert not app.exception
    app.selectbox[2].select('pore_pressure_kpa').run(timeout=60)
    assert not app.exception
    next(r for r in app.radio if r.label == 'Map layer').set_value('Screening').run(timeout=60)
    assert not app.exception
    app.button[0].click().run(timeout=60)
    assert not app.exception
    assert any(m.label == 'RMSE' for m in app.metric)
