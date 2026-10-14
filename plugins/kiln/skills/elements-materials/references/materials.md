# Materials, game-scale values and worked test numbers

Physical values at ~20 °C, SI units, from the research notes for this skill (kept in Kiln's development repository)
(Engineering ToolBox, NIST, USDA Wood Handbook, Babrauskas, SFPE, Wikipedia with cited sources).
Ranges where sources disagree. Use them for **ordering and ratios**; game times come from one
time-compression factor K (SKILL.md §3.1).

## Physical properties

ρ density kg/m³ · c specific heat kJ/(kg·K) · k conductivity W/(m·K) · α = k/(ρc) m²/s ·
ρe resistivity Ω·m

| Material | ρ | c | k | Thresholds | Electric |
|---|---|---|---|---|---|
| Wood, oak / pine, dry | 600–900 / 350–510 | 1.24 (dry, Wood Handbook) – 2.0/2.5 (ToolBox) | 0.17 / 0.12 | piloted ignition: glowing 250 °C, flaming softwood 300–310, hardwood 349–364; HHV 16.2 MJ/kg; char 0.65 mm/min softwood, 0.5 oak (near-UNVERIFIED) | 1e14–1e16 (insulator) |
| Wood, wet | — | 1.62 at 12 % moisture, 1.92 at 25 % | 0.135 dry → 0.196 at 25 % (G 0.6) | fibre saturation ≈ 30 %; burns well < 20 % | 1e3–1e4 damp (poor conductor) |
| Paper | 700–1150 | 1.34 | 0.05 | autoignition 218–246 °C | insulator |
| Cotton | 80 bulk | 1.34 | 0.04 | autoignition UNVERIFIED (~450 °C) | insulator |
| Hay / straw | UNVERIFIED | UNVERIFIED | 0.09 (straw slab) | ignition 407 °C hay, 380 °C straw (radiant test) | — |
| Kerosene | 775–840 | 2.01 | 0.15 | flash 37–65 °C, autoignition 210–220 °C, HHV 46.2 MJ/kg | insulator |
| Coal bituminous / anthracite | 1200–1500 / 1400–1800 | 1.38 / 1.26 | 0.2 | glow 454 / 600 °C; charcoal autoignition 349 °C | — |
| Steel carbon / stainless | 7820 | 0.49 | 43 / 14.4 | melts 1425–1540 °C; brittle below a transition temperature (body-centred cubic) | 1.43e-7 / 6.9e-7 |
| Iron | 7000–7400 (cast) | 0.46 | 83.5 | melts cast 1127–1204, wrought 1482–1593 °C | 9.7e-8 |
| Copper | 8790 | 0.39 | 390 | melts 1084 °C, L_f 206 kJ/kg | 1.68e-8 |
| Aluminium | 2700 | 0.87 | 236 | melts 660 °C, L_f 396 kJ/kg | 2.82e-8 |
| Granite | 2650–2750 | 0.79 | 1.7–4.0 | melts 1215–1260 °C | — |
| Concrete, dense | 2000–2400 | 0.75–0.96 | 1.0–1.8 | — | UNVERIFIED |
| Glass, soda-lime | 2520 | 0.84 | 0.96–1.05 | Tg 564–573 °C, softens ~700 °C | 1e11–1e15 |
| Ice | 917 | 2.09 | 2.18 | melts 0 °C, L_f 334 kJ/kg | — |
| Water | ~998 | 4.18 | 0.606 | boils 100 °C, L_v 2256 kJ/kg | ultrapure 0.055 µS/cm, tap 200–800 µS/cm, sea ~50 mS/cm |
| Snow, fresh | ~100 | ≈ ice | 0.05–0.25 | as ice | — |
| Rubber | 1100–1200 | 2.01 | 0.13 | tyre Tg −70 °C; loses springback near 0 °C (Challenger) | 1e13 hard |
| Skin / muscle | 1109 / 1090 | 3.39 / 3.42 | 0.37 / 0.49 | burns when the basal layer passes 44 °C; skin pain/burn time t ≈ 4·q^−1.35 min (q kW/m²) | body ~100 kΩ dry, ~1 kΩ sweaty |

Heat transfer coefficient h (W/m²K): free convection gas 2–25, liquid 50–1000; forced gas
25–250, liquid 100–20 000; boiling/condensing 2500–100 000; moving air
h = 1.16·(10.45 − v + 10√v), 2–20 m/s (5 m/s → 32). Radiation adds εσ(T²+T∞²)(T+T∞)
(ε 0.8: 33 W/m²K at 500 °C, 5 at 50 °C).

Fire: flame tips 320–400 °C, small-fire continuous flame ~900 °C, large pools 1100–1200 °C;
flashover when the hot layer passes ~600 °C and the floor gets > 20 kW/m²; engulfing pool fires
60–250 kW/m². Wood ignites from 12.5 kW/m² piloted (handbook; measured 7–8; true minimum ~4.3 after
hours). Skin tolerates < 2.5 kW/m² for 30 min; burn time 70 s at 2.5, 11 s at 10, 4 s at 20 kW/m².

## Game-scale starting values (working)

Times in game seconds at a typical action-game compression; keep the order, tune the numbers in a
gym. τ = cooling time constant toward ambient; "ignite" = seconds in contact with a small fire.

| Material | τ heat/cool | Ignite | Burns | End state | Conducts | Notes |
|---|---|---|---|---|---|---|
| Dry grass | 2 | 0.5 | 3–5 | ash (non-flammable) | no | spread p high; wind carrier |
| Dry wood (crate, plank) | 8 | 2–3 | 15–30 | charred, brittle | no | wet: no ignition until dry (10–20 s near fire) |
| Log / thick wood | 20 | 6–10 | 60+ | charred | no | thick: surface burns first |
| Cloth | 3 | 1 | 5–8 | ash | no | carries fire on characters |
| Oil puddle | 2 | 0.2 | 8–12 | gone | no | spreads on surfaces (DOS2) |
| Metal object | 4 | never | — | glows when hot, hurts to hold | yes | heats and cools fastest per mass |
| Stone | 30 | never | — | — | no | slow heat store |
| Ice block | — | melts at 0 with a plateau | — | water | wet surface conducts | freeze at ≤ 0, thaw at ≥ +1 |
| Water body | 60 | extinguishes | — | steam with strong heat | yes | freezes at the surface first |
| Flesh / character | 10 | via clothing | — | — | wet = yes | damage zones like BotW |

## Worked test numbers (from the research, recomputed)

- Newton cooling, 5 cm steel cube (m 0.9775 kg, A 0.015 m², h 10), 500 → 20 °C: τ = 3193 s,
  Bi = 0.0019; T(600 s) 417.8, T(τ) 196.6, T(3600 s) 175.5, T(3τ) 43.9 °C.
- 1-D rod, ends 100 / 0, start 0: steady T = 100·(1 − x/L); transient
  T = T_s − Σ (200/(nπ))·sin(nπx/L)·exp(−n²π²·Fo), Fo = αt/L². T(x = 0.5) = 11.38 / 26.28 / 41.16 /
  49.54 at Fo 0.05 / 0.1 / 0.2 / 0.5 (FTCS 51 nodes, r 0.25: 26.287 vs 26.276 at Fo 0.1).
- Hot spot: per-axis variance grows by 2αt; in FTCS exactly 2·r·steps (dx² units): 4 / 20 / 80
  after 10 / 50 / 200 steps at r 0.2.
- Ice cube 25 g from −18 °C: melt 9290 J (93 s at 100 W, 90 % latent); to 20 °C water 11 382 J; to
  steam 76 160 J.
- Mixing: 1 kg steel at 500 °C into 2 kg water at 20 °C → 46.55 °C (closed system).
- Circuit: 12 V, 100 Ω + (200 ∥ 300 Ω) → 220 Ω, 54.55 mA, branches 32.73 / 21.82 mA.
- Fire on a grid: 1-D persistent burning → p cells/tick; 1-D burning B ticks → q = 1 − (1 − p)^B,
  mean run q/(1 − q) (p 0.5, B 3 → 7 cells); 2-D 4-neighbour persistent → 0.184 / 0.507 / 0.698
  cells/tick at p 0.1 / 0.3 / 0.5; B = 1 → bond percolation, threshold 0.5 (big fires 0 % at 0.45,
  50 % at 0.5, 95 % at 0.55); fuel present with density d and certain ignition → site percolation
  threshold 0.5927.
- Lake ice (Stefan): thickness ≈ 3.5 cm per √(°C·day) — 10 K of frost: 11 cm after 1 day, 29 cm
  after 7.
- Wildfire forward spread ≈ 10 % (forest) / 20 % (cured grass) of the 10 m wind speed.
