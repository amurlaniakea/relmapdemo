# relmap 🌌

Navegación relativista y mapa del espacio-tiempo. **Experimental.**

- **Fase 1** — geodésicas de luz y de masa de prueba en Schwarzschild (un cuerpo), malla de Flamm.
- **Fase 3** — catálogo del Sistema Solar (Sol, 8 planetas, Luna) a una fecha dada, `relmap-solar`.
- **Fase 2** — varios cuerpos en **campo débil**: rayos de luz con deflexión y retraso tipo Shapiro,
  dilatación temporal, escena en YAML y propagación de incertidumbre por Monte Carlo.

## Uso
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
relmap examples/sistema_solar.yaml --mc 200 --out mapa.html
```

## Sistema Solar completo
```bash
relmap-solar --date 2026-11-05 --out sistema_solar.html --dump escena_solar.yaml
relmap-solar --include Sol Tierra Luna --b-factor 3
relmap-solar --rays mis_rayos.yaml --mc 100
```
Posiciones: elementos keplerianos aproximados de JPL (Standish, Tabla 1, válidos 1800-2050), marco
eclíptico J2000 heliocéntrico. Errores nominales JPL: Mercurio ~1 000 km, Venus ~4 000, Tierra ~6 000,
Marte ~25 000, Júpiter ~600 000, Saturno ~1,5 M km, Urano ~1 M, Neptuno ~200 000. Masas y radios:
JPL Planetary Physical Parameters. La Luna usa un modelo circular simple (error de decenas de miles
de km). `--dump` guarda la escena generada en YAML, editable y reutilizable con `relmap`.
Tabla de salida: «total» = todo el sistema sobre el rayo; «aporte» = lo que añade el propio cuerpo.

## El mapa (HTML interactivo)
- **Colores:** el amarillo es solo del Sol; cada cuerpo tiene su color (`color: "#rrggbb"` opcional en la escena).
- **Modo oscuro / claro:** interruptor arriba a la derecha; arranca en oscuro.
- **Navegar:** menú arriba a la izquierda con vistas «Todo el sistema», «Hasta Venus/Marte/Júpiter/Saturno»
  y «Centrado en <cuerpo>». Cada vista recalcula zoom, escala de ejes (UA o km) y malla, así los planetas
  interiores no se amontonan. Rueda = zoom, arrastrar = girar.
- **Órbitas** de los planetas y de la Luna dibujadas sobre la malla.
- **Sin internet:** añade `--offline` para incrustar plotly.js (el HTML pesa ~7 MB).
- La malla es **ilustrativa** (profundidad ~ log de la masa); los números físicos están en la tabla de la terminal.

## Formato de escena (YAML o JSON)
```yaml
unit: au                  # m, km, au, ly, pc, rsun  (distancias, posiciones y radios)
bodies:
  - name: Sol
    mass: 1.0
    mass_unit: msun       # kg, msun, mearth, mjup
    position: [0, 0, 0]
    radius: 0.0046505     # opcional; 0 = cuerpo puntual
    mass_sigma_rel: 0.01  # incertidumbre relativa de la masa
    position_sigma: 0.0   # incertidumbre de la posición (misma unidad que 'unit')
rays:
  - {name: rayo, origin: [-5, 0.0047, 0], direction: [1, 0, 0], length: 10}
```

## Qué calcula
Métrica isótropa de campo débil, `ds² = −(1+2Φ)dt² + (1−2Φ)dx²`, con `Φ = −Σ GMᵢ/(c² rᵢ)`.
La luz sigue `d/ds(n dx/ds) = ∇n` con `n = 1 − 2Φ`. Salidas por rayo: ángulo de deflexión,
retraso gravitacional del trayecto y, con `--mc N`, mediana e intervalo del 90 %.

## Validación (pytest)
Deflexión solar 1,75″; acuerdo con Schwarzschild exacto (Fase 1); cancelación por simetría de dos
masas; superposición; retraso de Shapiro analítico `4M·asinh(a/b)`; dilatación temporal en la Tierra
(6,95·10⁻¹⁰); propagación de incertidumbre de masa; validación de escenas inválidas.

## Límites (importante)
- Campo débil y cuerpos estáticos durante el paso de la luz: no vale cerca de horizontes ni para
  campos fuertes. Para un solo cuerpo en campo fuerte usa la Fase 1 (Schwarzschild).
- La malla del mapa es **cualitativa** (profundidad comprimida): muestra dónde se curva el espacio,
  no cuánto. Las desviaciones de los rayos (microradianes) se dibujan exageradas; el factor se indica.
- La incertidumbre en la posición manda: si `position_sigma` es mayor que el parámetro de impacto
  de un rayo rasante, el efecto de lente de ese cuerpo se pierde en el ruido (es físico, no un fallo).
- No hay dwarf planets, asteroides ni lunas de otros planetas todavía (sin elementos fiables a mano).
- Sin órbitas de masas de prueba multi-cuerpo ni relatividad numérica todavía.

Licencia: AGPL-3.0-or-later. © 2026 Pedro Sordo Martínez.
