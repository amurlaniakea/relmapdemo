# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Pedro Sordo Martínez
from datetime import datetime, timezone

import numpy as np
import pytest

from relmap import default_rays, solar_system_bodies, trace_ray
from relmap.scene import Scene
from relmap.scene_map import SUN_YELLOW, body_colors, build_scene_map, default_views
from relmap.solar_system import orbit_path

WHEN = datetime(2026, 11, 5, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def solar():
    bodies = solar_system_bodies(WHEN)
    rays = default_rays(bodies)
    res = [trace_ray(bodies, r.origin, r.direction, r.length, name=r.name) for r in rays]
    orbits = [(b.name, p) for b in bodies if (p := orbit_path(b.name, WHEN)) is not None]
    return Scene(bodies=bodies, rays=rays), res, orbits


def test_amarillo_solo_para_el_sol(solar):
    cols = body_colors(solar[0].bodies)
    assert [n for n, c in cols.items() if c.lower() == SUN_YELLOW.lower()] == ["Sol"]
    assert len(set(cols.values())) == len(cols)  # todos distintos


def test_color_explicito_y_fallback_sin_amarillo():
    from relmap.scene import Body

    bs = [Body(f"x{i}", 1e24, np.array([i, 0, 0.0])) for i in range(12)]
    cols = body_colors(bs)
    assert SUN_YELLOW.lower() not in [c.lower() for c in cols.values()]


def test_vistas_incluyen_interior_y_cada_cuerpo(solar):
    scene, res, _ = solar
    views = default_views(scene.bodies, res)
    names = [v["name"] for v in views]
    assert names[0] == "Todo el sistema"
    assert any(n.startswith("Hasta ") for n in names)
    for b in scene.bodies:
        assert f"Centrado en {b.name}" in names
    interior = [v for v in views if v["name"] == "Hasta Marte"]
    assert interior and interior[0]["h"] < 3 * 1.495978707e11  # zoom real a la zona interior


def test_cada_vista_tiene_trazas_propias_y_la_primera_visible(solar):
    scene, res, orbits = solar
    fig = build_scene_map(scene, res, orbits=orbits)
    btns = fig.layout.updatemenus[0].buttons
    assert len(btns) == len(default_views(scene.bodies, res))
    assert all(sum(b.args[0]["visible"]) > 0 for b in btns)
    first = [t for t, v in zip(fig.data, btns[0].args[0]["visible"]) if v]
    assert all(t.visible for t in first)
    sun = [t for t in first if t.name == "Sol"][0]
    assert sun.marker.color == SUN_YELLOW


def test_modo_oscuro_por_defecto_y_interruptor_en_html(solar, tmp_path):
    scene, res, orbits = solar
    out = tmp_path / "m.html"
    fig = build_scene_map(scene, res, orbits=orbits, out_html=str(out))
    assert fig.layout.paper_bgcolor == "#0b1020"
    html = out.read_text(encoding="utf-8")
    assert "Modo oscuro" in html and "rm-sw" in html and "inp.checked = true" in html
    assert "Plotly.relayout" in html


def test_cuerpo_pequeno_visible_en_su_vista(solar):
    scene, res, orbits = solar
    fig = build_scene_map(scene, res, orbits=orbits)
    btns = fig.layout.updatemenus[0].buttons
    i = [b.label for b in btns].index("Centrado en Tierra")
    vis = btns[i].args[0]["visible"]
    nombres = {t.name for t, v in zip(fig.data, vis) if v and t.meta == "body"}
    assert {"Tierra", "Luna"} <= nombres
    assert "Sol" not in nombres


def test_orbit_path_cierra_y_esta_a_la_distancia_correcta():
    p = orbit_path("Tierra", WHEN)
    r = np.linalg.norm(p, axis=1) / 1.495978707e11
    assert 0.98 < r.min() and r.max() < 1.02 and np.allclose(p[0], p[-1])
    assert orbit_path("Sol", WHEN) is None
    m = orbit_path("Luna", WHEN)
    e = solar_system_bodies(WHEN, include=["Tierra"])[0].position
    assert np.linalg.norm(m - e, axis=1).mean() == pytest.approx(384.4e6, rel=1e-6)
