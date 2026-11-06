# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Pedro Sordo Martínez
"""Mapa 3D navegable de una escena: malla deformada (cualitativa), cuerpos, órbitas y rayos.

* Colores: el amarillo es solo del Sol; cada cuerpo tiene su color.
* Modo oscuro (por defecto) / claro con un interruptor.
* Navegación: menú de VISTAS (sistema completo, "hasta X" y "centrado en X"). Cada vista
  recalcula la malla y el zoom para que los cuerpos cercanos entre sí no se amontonen.
* La profundidad de la malla es ILUSTRATIVA (profundidad ~ masa en escala logarítmica); los
  números físicos están en la tabla de la línea de comandos. La curvatura de los rayos
  (microradianes) se dibuja exagerada por un factor K que se indica en la leyenda.
"""
from __future__ import annotations

import json
import unicodedata

import numpy as np
import plotly.graph_objects as go

AU = 1.495978707e11
SUN_YELLOW = "#FFD60A"
PALETTE = {
    "sol": SUN_YELLOW, "sun": SUN_YELLOW,
    "mercurio": "#A8A29E", "mercury": "#A8A29E",
    "venus": "#F4A261",
    "tierra": "#38BDF8", "earth": "#38BDF8",
    "luna": "#CBD5E1", "moon": "#CBD5E1",
    "marte": "#EF4444", "mars": "#EF4444",
    "jupiter": "#C2410C",
    "saturno": "#D6B88A", "saturn": "#D6B88A",
    "urano": "#2DD4BF", "uranus": "#2DD4BF",
    "neptuno": "#6366F1", "neptune": "#6366F1",
}
FALLBACK = ["#A78BFA", "#F472B6", "#34D399", "#FB7185", "#60A5FA", "#F97316", "#14B8A6", "#C084FC"]

THEMES = {
    "dark": {"bg": "#0b1020", "text": "#e5e7eb", "axis": "#94a3b8", "grid": "rgba(148,163,184,0.30)",
             "ray": "#f8fafc", "outline": "rgba(0,0,0,0.75)", "menu": "#1e293b", "border": "#475569",
             "active": "#4338ca"},
    "light": {"bg": "#f8fafc", "text": "#0f172a", "axis": "#475569", "grid": "rgba(51,65,85,0.55)",
              "ray": "#0f172a", "outline": "#1f2937", "menu": "#e2e8f0", "border": "#94a3b8",
              "active": "#c7d2fe"},
}


def _norm(name: str) -> str:
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().strip()


def body_colors(bodies):
    out, i = {}, 0
    for b in bodies:
        c = b.color or PALETTE.get(_norm(b.name))
        if c is None:
            c = FALLBACK[i % len(FALLBACK)]
            i += 1
        out[b.name] = c
    return out


def _rgba(hexc: str, a: float) -> str:
    h = hexc.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{a})"


def _unit_for(h: float):
    return (AU, "UA") if h >= 0.02 * AU else (1e3, "km")


def _ray_points(res, n=6000):
    s = np.linspace(0.0, res.s_end, n)
    return res.sol.sol(s)[:3].T


def default_views(bodies, results):
    """Lista de vistas: dict(name, center (3,), h) con h = semianchura de la caja (m)."""
    heavy = max(bodies, key=lambda b: b.mass_kg)
    c = heavy.position.astype(float)
    pts = [b.position for b in bodies]
    for r in results:
        p = r.sol.y[:3]
        pts += [p[:, 0], p[:, -1]]
    pts = np.array(pts)
    hfull = 1.15 * float(np.max(np.abs(pts[:, :2] - c[:2]))) or 1.0
    views = [{"name": "Todo el sistema", "center": c, "h": hfull}]

    def is_sat(b):
        d_h = np.linalg.norm(b.position - heavy.position)
        return any(o is not b and o is not heavy and o.mass_kg > 20 * b.mass_kg
                   and np.linalg.norm(o.position - b.position) < 0.02 * d_h for o in bodies)

    cand = [b for b in bodies if b is not heavy and not is_sat(b)]
    if len(cand) >= 4:
        cand.sort(key=lambda b: np.linalg.norm(b.position - c))
        ds = np.array([np.linalg.norm(b.position - c) for b in cand])
        seen = set()
        for f in (0.2, 0.4, 0.6, 0.8):
            t = ds[0] * (ds[-1] / ds[0]) ** f
            j = int(np.argmin(np.abs(np.log(ds) - np.log(t))))
            h = 1.2 * ds[j]
            if j in seen or h >= 0.8 * hfull:
                continue
            seen.add(j)
            views.append({"name": f"Hasta {cand[j].name}", "center": c, "h": h})
        views[1:] = sorted(views[1:], key=lambda v: v["h"])
    for b in bodies:
        others = [np.linalg.norm(o.position - b.position) for o in bodies if o is not b]
        dn = min(others) if others else np.inf
        R = b.radius if b.radius > 0 else 0.0
        if R > 0:
            h = max(60 * R, 1.25 * dn) if dn <= 2000 * R else 60 * R
        else:
            h = 0.02 * hfull
        views.append({"name": f"Centrado en {b.name}", "center": b.position.astype(float), "h": float(h)})
    return views


def _surface_factory(bodies, h):
    masses = np.array([b.mass_kg for b in bodies], float)
    lm = np.log10(np.maximum(masses, 1e-30))
    s = np.full(len(bodies), 0.5) if np.ptp(lm) < 1e-9 else (lm - lm.min()) / np.ptp(lm)
    L = 0.35 * h
    D = L * (0.12 + 0.88 * s)
    W = h * (0.10 + 0.15 * s)
    P = np.array([b.position[:2] for b in bodies], float)

    def surf(xw, yw):
        z = np.zeros_like(xw, dtype=float)
        for (px, py), d, w in zip(P, D, W):
            z -= d * w / np.sqrt((xw - px) ** 2 + (yw - py) ** 2 + w * w)
        return z

    return surf, L


def _theme_layout(name):
    T = THEMES[name]
    lay = {"paper_bgcolor": T["bg"], "plot_bgcolor": T["bg"], "font.color": T["text"],
           "title.font.color": T["text"], "scene.bgcolor": T["bg"],
           "updatemenus[0].bgcolor": T["menu"], "updatemenus[0].bordercolor": T["border"],
           "updatemenus[0].font.color": T["text"], "updatemenus[0].activecolor": T["active"],
           "annotations[0].font.color": T["axis"]}
    for ax in "xyz":
        lay[f"scene.{ax}axis.color"] = T["axis"]
        lay[f"scene.{ax}axis.gridcolor"] = T["grid"]
        lay[f"scene.{ax}axis.zerolinecolor"] = T["grid"]
    return lay


_JS = r"""
(function(){
  var gd = document.getElementById('{plot_id}');
  var THEMES = __THEMES__, LAYOUT = __LAYOUT__;
  document.body.style.margin = '0';
  gd.style.height = '100vh';
  function idx(role){ var o=[]; gd.data.forEach(function(t,i){ if(t.meta===role) o.push(i); }); return o; }
  function apply(n){
    var T = THEMES[n];
    document.body.style.background = T.bg;
    document.documentElement.style.setProperty('--rm-menu', T.menu);
    document.documentElement.style.setProperty('--rm-text', T.text);
    document.documentElement.style.setProperty('--rm-active', T.active);
    Plotly.relayout(gd, LAYOUT[n]);
    var g = idx('grid'), r = idx('ray'), b = idx('body');
    if (g.length) Plotly.restyle(gd, {'line.color': T.grid}, g);
    if (r.length) Plotly.restyle(gd, {'line.color': T.ray}, r);
    if (b.length) Plotly.restyle(gd, {'textfont.color': T.text, 'marker.line.color': T.outline}, b);
    sw.style.color = T.text; sw.style.background = T.menu; sw.style.borderColor = T.border;
    ico.textContent = (n === 'dark') ? '\u263E' : '\u2600'; txt.textContent = (n === 'dark') ? 'Modo oscuro' : 'Modo claro';
  }
  var st = document.createElement('style');
  st.textContent = '#rm-sw{position:fixed;top:10px;left:14px;z-index:10;display:flex;align-items:center;gap:8px;padding:6px 12px;border:1px solid;border-radius:999px;font:13px system-ui,sans-serif;cursor:pointer;user-select:none}' +
    '#rm-sw .tr{position:relative;width:38px;height:20px;border-radius:999px;background:#64748b;transition:.2s}' +
    '#rm-sw .tr::after{content:"";position:absolute;top:2px;left:2px;width:16px;height:16px;border-radius:50%;background:#fff;transition:.2s}' +
    '.updatemenu-header-arrow{fill:var(--rm-text) !important}.updatemenu-item-rect{fill:var(--rm-menu) !important}.updatemenu-dropdown-button:hover .updatemenu-item-rect,.updatemenu-header:hover .updatemenu-item-rect{fill:var(--rm-active) !important}' +
    '#rm-sw input{display:none}#rm-sw input:checked + .tr{background:#6366f1}#rm-sw input:checked + .tr::after{left:20px}';
  document.head.appendChild(st);
  var sw = document.createElement('label'); sw.id = 'rm-sw'; sw.title = 'Cambiar modo oscuro / claro';
  var ico = document.createElement('span'); var txt = document.createElement('span');
  var inp = document.createElement('input'); inp.type = 'checkbox'; inp.checked = true;
  var tr = document.createElement('span'); tr.className = 'tr';
  sw.appendChild(ico); sw.appendChild(inp); sw.appendChild(tr); sw.appendChild(txt);
  document.body.appendChild(sw);
  inp.addEventListener('change', function(){ apply(inp.checked ? 'dark' : 'light'); });
  Plotly.Plots.resize(gd);
  apply('dark');
})();
"""


def build_scene_map(scene, results, exaggerate="auto", out_html=None, title="relmap — escena",
                    orbits=None, offline=False):
    bodies = list(scene.bodies)
    colors = body_colors(bodies)
    views = default_views(bodies, results)
    dark = THEMES["dark"]
    masses = np.array([b.mass_kg for b in bodies], float)
    rank = np.argsort(np.argsort(-masses))            # 0 = más masivo
    sizes = {b.name: (20 if rank[i] == 0 else 8 + 4 * (1 - rank[i] / max(len(bodies) - 1, 1)))
             for i, b in enumerate(bodies)}

    # ---- muestras de cada rayo: posiciones (solo para ubicar) y direcciones (precisas) ----
    ray_data = []
    for r in results:
        sgrid = np.linspace(0.0, r.s_end, 6000)
        y = r.sol.sol(sgrid)
        d = y[3:6].T
        d = d / np.linalg.norm(d, axis=1, keepdims=True)
        ray_data.append((r, y[:3].T, d, sgrid))

    fig = go.Figure()
    owners = []                                       # vista a la que pertenece cada traza
    view_meta = []
    for vi, v in enumerate(views):
        c, h = v["center"], v["h"]
        u, ulabel = _unit_for(h)
        nd = max(0, int(np.ceil(5 - np.log10(h / u))))
        surf, L = _surface_factory(bodies, h)

        def rel(P):                                    # mundo (m) -> vista (unidad)
            return np.round((np.asarray(P, float) - c) / u, nd)

        def inside(P, margin=1.02):
            return (np.abs(P[:, 0] - c[0]) <= h * margin) & (np.abs(P[:, 1] - c[1]) <= h * margin)

        # malla
        n, m = 27, 80
        g = np.linspace(-h, h, n)
        t = np.linspace(-h, h, m)
        GX, GY = [], []
        for val in g:
            GX += list(c[0] + t) + [np.nan]; GY += list(np.full(m, c[1] + val)) + [np.nan]
        for val in g:
            GX += list(np.full(m, c[0] + val)) + [np.nan]; GY += list(c[1] + t) + [np.nan]
        GX, GY = np.array(GX), np.array(GY)
        GZ = surf(GX, GY)
        zb = surf(np.array([b.position[0] for b in bodies]), np.array([b.position[1] for b in bodies]))
        zmin = float(min(np.nanmin(GZ), zb.min()))
        fig.add_trace(go.Scatter3d(x=np.round((GX - c[0]) / u, nd), y=np.round((GY - c[1]) / u, nd),
                                   z=np.round(GZ / u, nd), mode="lines", meta="grid", showlegend=False,
                                   hoverinfo="skip", line=dict(color=dark["grid"], width=1),
                                   visible=(vi == 0)))
        owners.append(vi)

        # órbitas
        for name, pts in (orbits or []):
            pts = np.asarray(pts, float)
            ok = inside(pts)
            if not ok.any():
                continue
            X = np.where(ok, (pts[:, 0] - c[0]) / u, np.nan)
            Y = np.where(ok, (pts[:, 1] - c[1]) / u, np.nan)
            Z = np.where(ok, surf(pts[:, 0], pts[:, 1]) / u, np.nan)
            fig.add_trace(go.Scatter3d(x=np.round(X, nd), y=np.round(Y, nd), z=np.round(Z, nd), mode="lines",
                                       meta="orbit", showlegend=False, hoverinfo="skip",
                                       line=dict(color=_rgba(colors.get(name, "#94a3b8"), 0.65), width=2),
                                       visible=(vi == 0)))
            owners.append(vi)

        # rayos: se reconstruye el tramo visible integrando las DIRECCIONES (precisas) y se exagera
        # su curvatura respecto a la cuerda del tramo, para poder verla
        for r, path, dirs, sg in ray_data:
            idx = np.flatnonzero(inside(path))
            if len(idx) < 8:
                continue
            i0, i1 = idx[0], idx[-1]
            ds = np.diff(sg[i0:i1 + 1])
            d = dirs[i0:i1 + 1]
            seg_len = float(ds.sum())
            if seg_len < 0.4 * 2 * h:
                continue
            seg = path[i0] + np.vstack([np.zeros(3), np.cumsum(0.5 * (d[1:] + d[:-1]) * ds[:, None], axis=0)])
            chord = seg[-1] - seg[0]
            dc = chord / np.linalg.norm(chord)
            base = seg[0] + np.outer((seg - seg[0]) @ dc, dc)
            dev = seg - base
            maxdev = float(np.abs(dev).max())
            if exaggerate == "auto":
                K = min(0.08 * seg_len / maxdev, 1e14) if maxdev > 1e-16 * seg_len else 1.0
            else:
                K = float(exaggerate)
            show = base + K * dev
            Z = surf(show[:, 0], show[:, 1])
            R = rel(show)
            lab = f"{r.name} (curvatura ×{K:.3g})" + (f" — IMPACTA {r.hit}" if r.hit else "")
            fig.add_trace(go.Scatter3d(x=R[:, 0], y=R[:, 1], z=np.round(Z / u, nd), mode="lines",
                                       name=lab, meta="ray", line=dict(color=dark["ray"], width=5),
                                       visible=(vi == 0)))
            owners.append(vi)

        # cuerpos
        for i, b in enumerate(bodies):
            P = b.position[None, :]
            if not inside(P, 1.05)[0]:
                continue
            z = float(surf(np.array([b.position[0]]), np.array([b.position[1]]))[0]) / u
            fig.add_trace(go.Scatter3d(
                x=[round(float((b.position[0] - c[0]) / u), nd)], y=[round(float((b.position[1] - c[1]) / u), nd)],
                z=[round(z, nd)], mode="markers+text", text=[b.name], textposition="top center", name=b.name,
                meta="body", hovertext=f"{b.name} — {b.mass_kg:.4g} kg", hoverinfo="text",
                textfont=dict(color=dark["text"], size=12),
                marker=dict(size=sizes[b.name], color=colors[b.name], line=dict(color=dark["outline"], width=1.5)),
                visible=(vi == 0)))
            owners.append(vi)
        view_meta.append({"u": u, "ulabel": ulabel, "h": h / u, "zmin": zmin / u, "L": L / u})

    # ---- botones de vista ----
    buttons = []
    for vi, (v, vm) in enumerate(zip(views, view_meta)):
        vis = [o == vi for o in owners]
        zmin, zmax = 1.15 * vm["zmin"], 0.12 * vm["L"]
        asp = float(np.clip((zmax - zmin) / (2 * vm["h"]), 0.18, 0.6))
        cname = "el origen" if np.allclose(v["center"], views[0]["center"]) else v["name"].replace("Centrado en ", "")
        buttons.append(dict(label=v["name"], method="update", args=[
            {"visible": vis},
            {"title.text": f"{title} — {v['name']}",
             "scene.xaxis.range": [-vm["h"], vm["h"]], "scene.yaxis.range": [-vm["h"], vm["h"]],
             "scene.zaxis.range": [zmin, zmax],
             "scene.xaxis.title.text": f"Δx ({vm['ulabel']})", "scene.yaxis.title.text": f"Δy ({vm['ulabel']})",
             "scene.zaxis.title.text": "profundidad (ilustrativa)",
             "scene.aspectratio": dict(x=1, y=1, z=asp),
             "scene.camera": dict(eye=dict(x=1.5, y=-1.6, z=0.9))}]))
    v0, m0 = views[0], view_meta[0]
    z0min, z0max = 1.15 * m0["zmin"], 0.12 * m0["L"]
    asp0 = float(np.clip((z0max - z0min) / (2 * m0["h"]), 0.18, 0.6))
    axis = dict(showbackground=False, color=dark["axis"], gridcolor=dark["grid"], zerolinecolor=dark["grid"])
    fig.update_layout(
        title=dict(text=f"{title} — {v0['name']}", x=0.5, font=dict(color=dark["text"])),
        paper_bgcolor=dark["bg"], plot_bgcolor=dark["bg"], font=dict(color=dark["text"]),
        margin=dict(l=0, r=0, t=60, b=0),
        legend=dict(bgcolor="rgba(0,0,0,0)", x=0.01, y=0.85, xanchor="left"),
        updatemenus=[dict(type="dropdown", buttons=buttons, active=0, x=0.01, y=0.935, xanchor="left",
                          yanchor="top", bgcolor=dark["menu"], bordercolor=dark["border"],
                          showactive=False, font=dict(color=dark["text"]))],
        annotations=[dict(text="Malla ilustrativa (profundidad ~ log masa) · curvatura de los rayos exagerada ×K · "
                               "rueda = zoom, arrastrar = girar, menú = cambiar de vista",
                          x=0.5, y=0.0, xref="paper", yref="paper", showarrow=False,
                          font=dict(color=dark["axis"], size=11))],
        scene=dict(bgcolor=dark["bg"], aspectmode="manual", aspectratio=dict(x=1, y=1, z=asp0),
                   xaxis=dict(range=[-m0["h"], m0["h"]], title=f"Δx ({m0['ulabel']})", **axis),
                   yaxis=dict(range=[-m0["h"], m0["h"]], title=f"Δy ({m0['ulabel']})", **axis),
                   zaxis=dict(range=[z0min, z0max], title="profundidad (ilustrativa)", showticklabels=False, **axis),
                   camera=dict(eye=dict(x=1.5, y=-1.6, z=0.9))))
    if out_html:
        js = (_JS.replace("__THEMES__", json.dumps(THEMES))
                 .replace("__LAYOUT__", json.dumps({k: _theme_layout(k) for k in THEMES})))
        fig.write_html(out_html, include_plotlyjs=True if offline else "cdn", post_script=js,
                       config={"scrollZoom": True, "displaylogo": False})
    return fig
