"""Checks for water, buoyancy, waves, granular piles, wind-blown sand and snow against exact
answers (Python 3.12+, stdlib only).

Prediction (design time):
  python fluid_check.py predict float    --rho-body 500 [--rho-fluid 1000] [--height 1]
  python fluid_check.py predict heave    --mass 500 --area 1 [--rho-fluid 1000]
  python fluid_check.py predict efflux   --h 2 [--tank-area 1 --hole-area 0.01]
  python fluid_check.py predict dambreak --h0 1
  python fluid_check.py predict wave     --wavelength 10 [--depth 1000]
  python fluid_check.py predict cfl      --dx 0.25 --dt 0.0167 [--umax 3] [--depth 2]

  float: submerged fraction rho_body/rho_fluid and the draft of a box of --height (floats only
  when < 1). heave: natural frequency of a floating box, omega = sqrt(rho*g*A/m), period (added
  mass ignored — real boxes bob 10-30 % slower). efflux: Torricelli v = sqrt(2*g*h); with areas,
  the drain time of a tank t = (A_tank/A_hole)*sqrt(2*h/g). dambreak: Ritter front speed
  2*sqrt(g*h0). wave: dispersion omega^2 = g*k*tanh(k*d): period, phase speed (deep water
  sqrt(g*lambda/(2*pi)), shallow sqrt(g*d)). cfl: a grid step is stable when umax*dt/dx <= 1 and,
  for shallow water, sqrt(g*depth)*dt/dx <= 1 (report the Courant numbers and the max dt).

Prediction — wind, sand and snow (wind is --wind m/s at --z m (10) over roughness --z0 (1e-3 m),
or the friction velocity --ustar m/s directly; u* = 0.4*U/ln(z/z0)):
  python fluid_check.py predict saltation --d 0.25 [--wind 8 | --ustar 0.3] [--rho-grain 2650]
  python fluid_check.py predict sandflux  --ustar 0.4 [--d 0.25] [--sorting natural] [--active 1]
  python fluid_check.py predict dune      --dune-height 3 --q-year 100 [--width 300] [--d 0.25]
                                          [--game-move 1 --game-s 60]
  python fluid_check.py predict ripple    [--wavelength 0.1] [--index 15]
  python fluid_check.py predict werner    [--dx 1] [--aspect 0.333] [--hop 5] [--ps 0.6]
                                          [--repose 30] [--q-year 29] [--game-s 1]
  python fluid_check.py predict fill      --length 0.28 --depth 0.03 (--q 9e-6 | --ustar 0.4
                                          [--material sand|snow] [--ustar-t 0.2]) [--trap 1]
                                          [--game-s 60]
  python fluid_check.py predict blowsnow  (--wind 12 | --ustar 0.5) [--snow fresh|dry|wet]
  python fluid_check.py predict drift     --barrier 2 (--q-mass 0.005 | --wind 12) [--game-s 300]
  python fluid_check.py predict snowfall  --hours 6 (--rate 2.54 | --swe-rate 2.5) [--rho-new 100]
                                          [--rho-settled 250] [--game-s 600]
  python fluid_check.py predict settle    --hours 200 [--rho0 100] [--melting] [--depth 0.3]
                                          [--target-rho 250]
  python fluid_check.py predict footprint --mass 80 --area 0.03 --depth 0.3 --rho0 100
                                          [--rhof 500 | --fit] [--cap 0.12]
  python fluid_check.py predict avalanche --slope 38 [--slab 0.5 --rho-slab 200 --strength 1.0
                                          [--skier]] [--band 30,45] [--beta 28 --drop 500]
  python fluid_check.py predict melt      (--swe 10 | --depth 0.1 --rho0 100) --power 300
                                          [--temp -10] [--game-s 120]
  python fluid_check.py predict storm     [--visibility 200] [--count 2000 --size 1 --radius 30
                                          [--near 1] [--opacity 0.1]]

  saltation: Bagnold threshold u*t = A*sqrt((rho_p - rho_a)/rho_a*g*d), A 0.10 (fluid threshold,
  wind starts lifting grains) and 0.082 (impact threshold, saltation keeps going once started),
  with the wind at --z that gives each; with a wind, whether sand starts and keeps moving.
  sandflux: mass flux per metre of width, zero below the impact threshold — Bagnold
  C*(rho_a/g)*sqrt(d/0.25 mm)*u*^3 (C 1.5/1.8/2.8 for uniform/natural/poorly sorted sand),
  Kawamura 2.78*(rho_a/g)*u*^3*(1 - r)*(1 + r)^2 with r = u*it/u*, Lettau & Lettau
  6.7*(rho_a/g)*sqrt(d/0.25 mm)*u*^2*(u* - u*it); volume flux = Bagnold / bulk density
  rho_p*(1 - porosity); per year scaled by --active (fraction of time above threshold).
  dune: migration c = q/H (mass conservation at the crest); with --width the barchan scaling
  50*q/W, volume 0.017*W^3 and turnover 0.02*W^2/q; minimum dune width 12*L_sat, L_sat =
  2*d*rho_p/rho_a; with --game-move/--game-s the time-compression factor K = real time / game time
  and the flux the simulation must use, K*q. ripple: height = wavelength/index (normal ripples
  7-14 cm). werner: Werner (1995) slab model units — slab thickness aspect*dx, the repose rule in
  slabs, flux per time unit slab*hop*dx/ps (full sand cover, no shadowing), real time per unit
  for --q-year, K per --game-s. fill: a print or track of --length (along the wind) and --depth
  fills in t = L*D/(q*trap) when every grain blown in stays (trap 1 is the fastest case); sand q
  from Bagnold, snow q from Pomeroy & Gray Q = 0.68*rho_a*(u*t/(u* g))*(u*^2 - u*t^2) over the
  deposit density --rho-deposit (350). blowsnow: 10 m threshold wind (fresh 4.5, dry 7.7, wet
  9.9 m/s or --wind-threshold), u*t by the log law, saltation flux Pomeroy & Gray. drift: Tabler
  (1980) equilibrium drift behind a 50 % porous fence of height H — lee 30H long, 1.2H deep, area
  19.3H^2, upwind 12H x 0.5H, mean density 376 + 158*log10(depth) kg/m^3; the time to fill it
  from the transport rate. snowfall: depth and water equivalent from a rate, settled depth at
  --rho-settled, NWS heavy-snow flag (10.16 cm in 12 h or 15.24 cm in 24 h), K. settle: density
  rho(t) = rho_max + (rho0 - rho_max)*exp(-t/tau), rho_max 300 cold / 500 melting, tau 200 h
  (FSM 1.0); depth falls with the water equivalent kept; cover fraction tanh(depth/0.1 m).
  footprint: pressure m*g/A and CRREL sinkage z = h*(1 - rho0/rho_f), rho_f 500/550/600/650 kg/m^3
  for pressures <= 210 / > 210 / > 350 / > 700 kPa, or the wheel fit 519 + 2.3*p (--fit), cut to
  --cap in deep snow. avalanche: release band (30-45 deg), slab shear stress
  rho*g*h*sin(psi)*cos(psi), stability index S = strength/stress (natural) and S' with a skier
  (0.14/h kPa at 38 deg, other slopes scaled by Foehn's line-load formula), runout
  alpha = 0.97*beta - 1.4 deg (SD 3.5) and the reach drop/tan(alpha). melt: t = SWE*(L_f +
  c_ice*dT)/P. storm: extinction sigma = 3.912/visibility (Godot exponential fog_density = sigma);
  camera-following particles in a sphere of --radius: overdraw layers n*s^2*(R - near) and their
  own extinction opacity*n*s^2.

Measurement (recordings and exports from the running game):
  python fluid_check.py float    <dump> --pos box --water-y 0 --height 1 --fraction 0.5
                                 [--tol 0.05] [--settle-s 5]
  python fluid_check.py levels   <dump> --probes tank_a,tank_b [--tol 0.02] [--last-s 1]
  python fluid_check.py conserve <dump> --total volume [--tol 0.01]
  python fluid_check.py repose   <heights.json> --angle 34 [--tol 3]
  python fluid_check.py wave     <dump> --height buoy --wavelength 10 [--depth 1000] [--tol 0.05]
  python fluid_check.py fill     <dump> --depth print --expect-s 928 [--fraction 0.9] [--tol 0.25]
  python fluid_check.py accum    <dump> --depth snow --rate 2.54 [--k 1] [--tol 0.15]
  python fluid_check.py lee      <before.json> <after.json> --wind +x|x-|+z|z- [--angle 34]
                                 [--tol 3] [--lee-frac 0.7] [--vol-tol 0.001]
                                 [--speed 0.01 --dt-s 60]
  python fluid_check.py runout   <dump> --pos front (--beta 28 | --alpha 25.8) [--sd 3.5] [--k 2]
  python fluid_check.py release  <trials.json> [--band 30,45]

  float: after --settle-s the box's bottom sits (fraction*height) below the surface and its
  vertical speed stays small (no endless bobbing). levels: connected vessels end at the same level
  (max - min over the last --last-s). conserve: total water/sand volume drifts less than --tol
  relative. repose: slopes of a heightfield pile — the steepest neighbour slopes must not exceed
  the angle + tol (p99) and the pile must actually stand near it (p99 >= angle - 2*tol).
  wave: period from upward zero crossings of a surface height probe against the dispersion
  relation. fill: a print-depth probe (m) — the time to fill --fraction of the starting depth,
  scaled to a full fill (t/fraction, the model fills linearly), against --expect-s ± tol; the
  print must never deepen again by more than 5 % of its depth. accum: the fitted rate of a
  snow-depth probe against --rate cm per real hour times the compression --k. lee: two heightfield
  exports of a dune under a steady wind — most deposition downwind of each transect's crest and
  most erosion upwind of it (--lee-frac), volume kept (--vol-tol), the profile moves downwind
  (and by speed*dt ± 30 % when given), the lee never steeper than --angle + tol and the windward
  side never steeper than the lee. runout: the alpha angle atan(drop/horizontal reach) of an
  avalanche front against 0.97*beta - 1.4 (or --alpha) within --k standard deviations. release:
  trial list [{"slope": deg, "released": bool, "S": optional}] — no release outside --band; with
  S, released when S < 1 and never when S > 1.5.

Recordings: the acceptance recorder JSON or JSON Lines; position probes are [x, y, z] metres, Y up;
depth probes are metres (scalars or [x, y, z] with y as the value).
Heightfield export: {"dx": 0.1, "heights": [[...], ...]} (row-major heights[z][x], metres).
Prints one JSON object {"verdict", "metrics": [...]} (predict: {"prediction": {...}}); exit code 1
on FAIL, 2 on bad input.
"""

import argparse
import json
import math
import sys

G = 9.81
KAPPA = 0.40            # von Karman constant
YEAR_S = 365.25 * 86400.0
L_FUSION = 333.55e3     # J/kg, ice
C_ICE = 2090.0          # J/(kg K)
SAND_C = {"uniform": 1.5, "natural": 1.8, "poor": 2.8}   # Bagnold's C by sorting
SNOW_U10_THRESHOLD = {"fresh": 4.5, "dry": 7.7, "wet": 9.9}   # m/s at 10 m


class NotAssessed(Exception):
    """The input cannot answer the question."""


def metric(name, value, threshold, ok, **extra):
    return {"metric": name, "value": value, "threshold": threshold,
            "verdict": "PASS" if ok else "FAIL", **extra}


def rnd(x, n=4):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(x, n)


def load_recording(path):
    """(times in s, samples {name: [values]}) from the recorder JSON or JSON Lines."""
    with open(path, encoding="utf-8-sig") as fh:
        text = fh.read()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict) and isinstance(data.get("samples"), dict):
        samples = data["samples"]
        hz = float(data.get("physics_ticks_per_second") or 60)
        ticks = data.get("ticks") or []
        n = max((len(v) for v in samples.values()), default=0)
        times = [(t - ticks[0]) / hz for t in ticks] if ticks else [i / hz for i in range(n)]
        return times, samples
    rows = data if isinstance(data, list) else [json.loads(x) for x in text.splitlines()
                                                 if x.strip()]
    rows = [r for r in rows if r.get("type", "tick") in ("tick", "sample")]
    times = [float(r["t"]) if "t" in r else float(r.get("tick", i)) / 60.0
             for i, r in enumerate(rows)]
    if times:
        times = [t - times[0] for t in times]
    keys = []
    for row in rows:
        keys.extend(k for k in row if k not in keys and k not in ("type", "t", "tick"))
    return times, {k: [row.get(k) for row in rows] for k in keys}


def probe(samples, name):
    if name not in samples:
        raise NotAssessed(f"probe '{name}' not in recording; probes: " + ", ".join(sorted(samples)))
    return samples[name]


def height_of(v):
    if isinstance(v, list) and len(v) >= 2:
        return float(v[1])
    if isinstance(v, (int, float)):
        return float(v)
    return None


# ---------- wind, sand and snow ----------

def ustar_from(wind, z, z0):
    """Friction velocity from the wind at height z over roughness z0 (log law)."""
    return KAPPA * wind / math.log(z / z0)


def wind_from(ustar, z, z0):
    return ustar / KAPPA * math.log(z / z0)


def sand_thresholds(a):
    """Bagnold fluid (A 0.10) and impact (A 0.082) threshold friction velocities, m/s."""
    d = (a.d or 0.25) * 1e-3
    s = math.sqrt((a.rho_grain - a.rho_air) / a.rho_air * G * d)
    return 0.10 * s, 0.082 * s


def ustar_of(a, required=None):
    if a.ustar is not None:
        return a.ustar
    if a.wind is not None:
        return ustar_from(a.wind, a.z, a.z0)
    if required:
        raise ValueError(f"{required} needs --ustar or --wind")
    return None


def sand_fluxes(a, us):
    """(Bagnold, Kawamura, Lettau) mass fluxes in kg/m/s; zero below the impact threshold."""
    _, uit = sand_thresholds(a)
    if us <= uit:
        return 0.0, 0.0, 0.0
    sq = math.sqrt((a.d or 0.25) / 0.25)
    base = a.rho_air / G * us ** 3
    r = uit / us
    return (SAND_C[a.sorting] * sq * base,
            2.78 * base * (1 - r) * (1 + r) ** 2,
            6.7 * sq * a.rho_air / G * us ** 2 * (us - uit))


def snow_flux(us, ust, rho_air):
    """Pomeroy & Gray (1990) saltation transport of snow, kg/m/s; zero below the threshold."""
    if us <= ust:
        return 0.0
    return 0.68 * rho_air * ust / (us * G) * (us * us - ust * ust)


def snow_threshold(a):
    """(10 m threshold wind, threshold friction velocity) for the snow state."""
    if a.ustar_t is not None:
        return wind_from(a.ustar_t, 10.0, a.z0), a.ustar_t
    u10 = a.wind_threshold if a.wind_threshold is not None else SNOW_U10_THRESHOLD[a.snow]
    return u10, ustar_from(u10, 10.0, a.z0)


def compression(real_s, game_s):
    """Time-compression factor K = real seconds per game second."""
    return rnd(real_s / game_s, 3) if game_s else None


def foehn_slope_factor(psi_deg):
    """max over alpha of cos(a)*sin(a)^2*sin(a + psi) / cos(psi) — Foehn's line-load term."""
    psi = math.radians(psi_deg)
    best = 0.0
    for i in range(1, 9000):
        al = math.radians(i / 100)
        best = max(best, math.cos(al) * math.sin(al) ** 2 * math.sin(al + psi))
    return best / math.cos(psi)


def parse_band(text):
    lo, hi = (float(x) for x in text.split(","))
    if lo >= hi:
        raise ValueError("--band needs lo,hi with lo < hi")
    return lo, hi


def predict_saltation(a):
    uft, uit = sand_thresholds(a)
    out = dict(grain_mm=a.d or 0.25, ustar_fluid=rnd(uft, 4), ustar_impact=rnd(uit, 4),
               wind_to_start_m_s=rnd(wind_from(uft, a.z, a.z0), 3),
               wind_to_keep_m_s=rnd(wind_from(uit, a.z, a.z0), 3), z_m=a.z, z0_m=a.z0)
    us = ustar_of(a)
    if us is not None:
        out.update(ustar=rnd(us, 4), starts=us >= uft, keeps_moving=us >= uit,
                   note="start at the fluid threshold, stop below the impact threshold")
    return out


def predict_sandflux(a):
    us = ustar_of(a, "sandflux")
    _, uit = sand_thresholds(a)
    bag, kaw, let = sand_fluxes(a, us)
    bulk = a.rho_grain * (1 - a.porosity)
    qv = bag / bulk
    return dict(ustar=rnd(us, 4), ustar_impact=rnd(uit, 4), moving=us > uit,
                flux_kg_m_s={"bagnold": rnd(bag, 6), "kawamura": rnd(kaw, 6),
                             "lettau": rnd(let, 6)},
                model_spread=rnd(max(bag, kaw, let) / min(bag, kaw, let), 3) if bag else None,
                bulk_density=rnd(bulk, 1), volume_flux_m2_s=rnd(qv, 10),
                per_hour_kg_m=rnd(bag * 3600, 2), per_year_m2=rnd(qv * YEAR_S * a.active, 2),
                note="volume flux from Bagnold (the lowest of the three); models differ ~2x")


def predict_dune(a):
    if not a.dune_height:
        raise ValueError("dune needs --dune-height (m)")
    if a.q_year:
        q_year = a.q_year
    else:
        us = ustar_of(a, "dune without --q-year")
        q_year = sand_fluxes(a, us)[0] / (a.rho_grain * (1 - a.porosity)) * YEAR_S * a.active
    speed = q_year / a.dune_height
    l_drag = (a.d or 0.25) * 1e-3 * a.rho_grain / a.rho_air
    out = dict(q_year_m2=rnd(q_year, 3), speed_m_year=rnd(speed, 3),
               speed_m_day=rnd(speed / 365.25, 5), l_drag_m=rnd(l_drag, 4),
               min_dune_width_m=rnd(24 * l_drag, 2))
    if a.width:
        out.update(barchan_speed_m_year=rnd(50 * q_year / a.width, 3),
                   barchan_volume_m3=rnd(0.017 * a.width ** 3, 1),
                   turnover_years=rnd(0.02 * a.width ** 2 / q_year, 2))
    if a.game_move and a.game_s:
        real_s = a.game_move / (speed / YEAR_S)
        k = real_s / a.game_s
        out.update(real_time_s=rnd(real_s, 1), real_time_days=rnd(real_s / 86400, 3),
                   compression=rnd(k, 3), game_flux_m2_s=rnd(k * q_year / YEAR_S, 8))
    return out


def predict_ripple(a):
    lam = a.wavelength or 0.10
    idx = a.index or 15.0
    return dict(wavelength_m=lam, ripple_index=idx, height_m=rnd(lam / idx, 5),
                normal_ripple=0.07 <= lam <= 0.14,
                note="crests lie across the local wind; index 12-50, ~15 typical")


def predict_werner(a):
    dx = a.dx or 1.0
    aspect = a.aspect or 1 / 3
    hop = a.hop or 5.0
    ps = a.ps or 0.6
    repose = a.repose or 30.0
    slab = aspect * dx
    max_step = math.tan(math.radians(repose)) * dx / slab
    steps = math.floor(max_step + 1e-9)
    q_unit = slab * hop * dx / ps
    out = dict(slab_m=rnd(slab, 4), max_step_slabs=rnd(max_step, 4), max_step_whole=steps,
               effective_repose_deg=rnd(math.degrees(math.atan(steps * slab / dx)), 2),
               shadow_length_per_m_height=rnd(1 / math.tan(math.radians(15)), 4),
               flux_per_unit_m2=rnd(q_unit, 4))
    if a.q_year:
        unit_s = q_unit / (a.q_year / YEAR_S)
        out.update(real_s_per_unit=rnd(unit_s, 1), real_days_per_unit=rnd(unit_s / 86400, 3),
                   compression=compression(unit_s, a.game_s))
    return out


def predict_fill(a):
    if not (a.length and a.depth):
        raise ValueError("fill needs --length (along the wind) and --depth (m)")
    if a.q is not None:
        q, source = a.q, "given"
    else:
        us = ustar_of(a, "fill without --q")
        if a.material == "snow":
            ust = a.ustar_t if a.ustar_t is not None else snow_threshold(a)[1]
            q, source = snow_flux(us, ust, a.rho_air) / a.rho_deposit, "Pomeroy & Gray"
        else:
            q = sand_fluxes(a, us)[0] / (a.rho_grain * (1 - a.porosity))
            source = "Bagnold"
    out = dict(volume_flux_m2_s=rnd(q, 10), flux_source=source, trap=a.trap)
    if q <= 0:
        out.update(fill_s=None, note="no transport: wind below the threshold")
        return out
    t = a.length * a.depth / (q * a.trap)
    out.update(fill_s=rnd(t, 1), fill_min=rnd(t / 60, 2),
               depth_rate_m_s=rnd(q * a.trap / a.length, 10), compression=compression(t, a.game_s),
               note="trap 1 = every grain blown in stays: the fastest real fill")
    return out


def predict_blowsnow(a):
    u10t, ust = snow_threshold(a)
    us = ustar_of(a, "blowsnow")
    flux = snow_flux(us, ust, a.rho_air)
    return dict(snow=a.snow, wind_threshold_10m=rnd(u10t, 3), ustar_threshold=rnd(ust, 4),
                ustar=rnd(us, 4), blowing=us > ust, flux_kg_m_s=rnd(flux, 6),
                per_hour_kg_m=rnd(flux * 3600, 2),
                note="saltation only; suspension adds more in strong winds")


def predict_drift(a):
    if not a.barrier:
        raise ValueError("drift needs --barrier (fence or ridge height, m)")
    h = a.barrier
    depth = 1.2 * h
    area = 19.3 * h * h
    rho = 376 + 158 * math.log10(depth)
    out = dict(lee_length_m=rnd(30 * h, 2), lee_depth_m=rnd(depth, 3), lee_area_m2=rnd(area, 2),
               upwind_length_m=rnd(12 * h, 2), upwind_depth_m=rnd(0.5 * h, 3), tail_slope=0.06,
               density=rnd(rho, 1), mass_kg_per_m=rnd(area * rho, 1))
    if a.q_mass:
        q = a.q_mass
    elif a.ustar is not None or a.wind is not None:
        q = snow_flux(ustar_of(a), snow_threshold(a)[1], a.rho_air)
    else:
        return out
    out.update(transport_kg_m_s=rnd(q, 6))
    if q > 0:
        t = area * rho / q
        out.update(fill_s=rnd(t, 0), fill_days=rnd(t / 86400, 2),
                   compression=compression(t, a.game_s))
    return out


def predict_snowfall(a):
    if not a.hours:
        raise ValueError("snowfall needs --hours")
    if a.rate is not None:
        depth = a.rate * a.hours / 100
        swe = depth * a.rho_new
    elif a.swe_rate is not None:
        swe = a.swe_rate * a.hours
        depth = swe / a.rho_new
    else:
        raise ValueError("snowfall needs --rate (cm/h) or --swe-rate (mm water/h)")
    rate_cm_h = depth * 100 / a.hours
    out = dict(depth_fresh_m=rnd(depth, 4), swe_mm=rnd(swe, 3), rate_cm_h=rnd(rate_cm_h, 4),
               nws_heavy_snow=rate_cm_h * min(a.hours, 12) >= 10.16
               or rate_cm_h * min(a.hours, 24) >= 15.24)
    if a.rho_settled:
        out.update(depth_settled_m=rnd(swe / a.rho_settled, 4))
    if a.game_s:
        out.update(compression=compression(a.hours * 3600, a.game_s),
                   game_rate_m_s=rnd(depth / a.game_s, 8))
    return out


def predict_settle(a):
    rho0 = a.rho0 or 100.0
    rho_max = a.rho_max or (500.0 if a.melting else 300.0)
    tau = a.tau_h or 200.0
    hours = a.hours or 0.0
    rho = rho_max + (rho0 - rho_max) * math.exp(-hours / tau)
    out = dict(rho_start=rho0, rho_max=rho_max, tau_h=tau, hours=hours, rho_now=rnd(rho, 2))
    if a.depth:
        hf = a.hf or 0.1
        now = a.depth * rho0 / rho
        out.update(depth_start_m=a.depth, depth_now_m=rnd(now, 4), swe_mm=rnd(a.depth * rho0, 3),
                   cover_start=rnd(math.tanh(a.depth / hf), 4),
                   cover_now=rnd(math.tanh(now / hf), 4))
    if a.target_rho:
        if not min(rho0, rho_max) < a.target_rho < max(rho0, rho_max):
            out.update(hours_to_target=None, note="target outside start..max density")
        else:
            out.update(hours_to_target=rnd(-tau * math.log((rho_max - a.target_rho)
                                                           / (rho_max - rho0)), 3))
    return out


def predict_footprint(a):
    if not (a.mass and a.area):
        raise ValueError("footprint needs --mass (kg) and --area (m2 contact)")
    p = a.mass * G / a.area / 1000
    table = 650.0 if p > 700 else 600.0 if p > 350 else 550.0 if p > 210 else 500.0
    fit = (0.519 + 0.0023 * p) * 1000
    rho_f = a.rhof or (fit if a.fit else table)
    out = dict(pressure_kpa=rnd(p, 3), rho_final=rnd(rho_f, 2), rho_final_table=table,
               rho_final_fit=rnd(fit, 2))
    if a.depth and a.rho0:
        full = a.depth * (1 - a.rho0 / rho_f) if a.rho0 < rho_f else 0.0
        sink = min(full, a.cap) if a.cap else full
        out.update(full_compaction_m=rnd(full, 4), sinkage_m=rnd(sink, 4), capped=sink < full,
                   note="shallow snow on a firm base compacts to rho_f; deep soft snow "
                        "needs --cap (measured boots 0.118 m, snowshoes 0.057 m)")
    return out


def predict_avalanche(a):
    if a.slope is None:
        raise ValueError("avalanche needs --slope (deg)")
    lo, hi = parse_band(a.band)
    out = dict(slope_deg=a.slope, band=[lo, hi], in_release_band=lo <= a.slope <= hi)
    if a.slab and a.strength:
        psi = math.radians(a.slope)
        tau = a.rho_slab * G * a.slab * math.sin(psi) * math.cos(psi) / 1000
        s_nat = a.strength / tau if tau > 0 else None
        out.update(slab_stress_kpa=rnd(tau, 4), stability_natural=rnd(s_nat, 3))
        used = s_nat
        if a.skier:
            add = 0.14 / a.slab * foehn_slope_factor(a.slope) / foehn_slope_factor(38.0)
            used = a.strength / (tau + add)
            out.update(skier_stress_kpa=rnd(add, 4), stability_skier=rnd(used, 3))
        out.update(stability_class=None if used is None else "unstable" if used < 1
                   else "transitional" if used <= 1.5 else "stable",
                   releases=bool(out["in_release_band"] and used is not None and used < 1))
    if a.beta is not None:
        alpha = 0.97 * a.beta - 1.4
        out.update(alpha_deg=rnd(alpha, 3), alpha_sd_deg=3.5)
        if a.drop:
            out.update(reach_m=rnd(a.drop / math.tan(math.radians(alpha)), 1),
                       reach_1sd_m=rnd(a.drop / math.tan(math.radians(alpha - 3.5)), 1))
    return out


def predict_melt(a):
    if a.swe:
        swe = a.swe
    elif a.depth and a.rho0:
        swe = a.depth * a.rho0
    else:
        raise ValueError("melt needs --swe (kg/m2) or --depth with --rho0")
    if not a.power:
        raise ValueError("melt needs --power (net W/m2 into the snow)")
    cold = max(0.0, -(a.temp or 0.0))
    energy = swe * (L_FUSION + C_ICE * cold)
    t = energy / a.power
    return dict(swe_kg_m2=rnd(swe, 3), energy_mj_m2=rnd(energy / 1e6, 4), melt_s=rnd(t, 1),
                melt_h=rnd(t / 3600, 4), compression=compression(t, a.game_s))


def predict_storm(a):
    out = {}
    if a.visibility:
        sigma = 3.912 / a.visibility
        cat = ("severe" if a.visibility < 200 else "sandstorm" if a.visibility < 1000
               else "blowing")
        out.update(visibility_m=a.visibility, extinction_per_m=rnd(sigma, 6),
                   godot_fog_density=rnd(sigma, 6), category=cat)
    if a.count and a.size and a.radius:
        near = a.near or 0.0
        n = a.count / (4 / 3 * math.pi * a.radius ** 3)
        out.update(particles_per_m3=rnd(n, 6),
                   overdraw_layers=rnd(n * a.size ** 2 * (a.radius - near), 4))
        if a.opacity:
            sp = a.opacity * n * a.size ** 2
            out.update(particle_extinction_per_m=rnd(sp, 7),
                       particle_visibility_m=rnd(3.912 / sp, 1))
    if not out:
        raise ValueError("storm needs --visibility and/or --count --size --radius")
    return out


WIND_CASES = {"saltation": predict_saltation, "sandflux": predict_sandflux, "dune": predict_dune,
              "ripple": predict_ripple, "werner": predict_werner, "fill": predict_fill,
              "blowsnow": predict_blowsnow, "drift": predict_drift, "snowfall": predict_snowfall,
              "settle": predict_settle, "footprint": predict_footprint,
              "avalanche": predict_avalanche, "melt": predict_melt, "storm": predict_storm}


# ---------- predictions ----------

def predict(a):
    out = {"case": a.case}
    if a.case in WIND_CASES:
        out.update(WIND_CASES[a.case](a))
    elif a.case == "float":
        if a.rho_body is None:
            raise ValueError("float needs --rho-body")
        frac = a.rho_body / a.rho_fluid
        out.update(submerged_fraction=rnd(frac, 4), floats=frac < 1,
                   draft_m=rnd(min(frac, 1.0) * a.height, 4),
                   freeboard_m=rnd(max(0.0, 1 - frac) * a.height, 4))
    elif a.case == "heave":
        if not (a.mass and a.area):
            raise ValueError("heave needs --mass and --area")
        w = math.sqrt(a.rho_fluid * G * a.area / a.mass)
        out.update(omega_rad_s=rnd(w, 4), period_s=rnd(2 * math.pi / w, 4),
                   note="added mass ignored: real bodies bob 10-30 % slower (working)")
    elif a.case == "efflux":
        if a.h is None:
            raise ValueError("efflux needs --h")
        out.update(speed_m_s=rnd(math.sqrt(2 * G * a.h), 4))
        if a.tank_area and a.hole_area:
            out.update(drain_s=rnd(a.tank_area / a.hole_area * math.sqrt(2 * a.h / G), 3))
    elif a.case == "dambreak":
        if a.h0 is None:
            raise ValueError("dambreak needs --h0")
        out.update(front_speed_m_s=rnd(2 * math.sqrt(G * a.h0), 4),
                   wave_speed_m_s=rnd(math.sqrt(G * a.h0), 4))
    elif a.case == "wave":
        if not a.wavelength:
            raise ValueError("wave needs --wavelength")
        k = 2 * math.pi / a.wavelength
        depth = a.depth or 1000.0
        w = math.sqrt(G * k * math.tanh(k * depth))
        out.update(period_s=rnd(2 * math.pi / w, 4), phase_speed_m_s=rnd(w / k, 4),
                   deep_water=k * depth > math.pi, shallow_water=k * depth < math.pi / 10,
                   max_steepness_h_over_lambda=round(1 / 7, 4))
    elif a.case == "cfl":
        if not (a.dx and a.dt):
            raise ValueError("cfl needs --dx and --dt")
        limits = []
        if a.umax:
            c = a.umax * a.dt / a.dx
            out.update(courant_flow=rnd(c, 4))
            limits.append(a.dx / a.umax)
        if a.depth:
            cw = math.sqrt(G * a.depth)
            c = cw * a.dt / a.dx
            out.update(courant_wave=rnd(c, 4), wave_speed_m_s=rnd(cw, 4))
            limits.append(a.dx / cw)
        if not limits:
            raise ValueError("cfl needs --umax and/or --depth")
        out.update(max_dt_s=rnd(min(limits), 6), stable=a.dt <= min(limits))
    return {"prediction": out}


# ---------- measurements ----------

def float_check(a):
    times, samples = load_recording(a.dump)
    ys = [(t, height_of(v)) for t, v in zip(times, probe(samples, a.pos))]
    ys = [(t, y) for t, y in ys if y is not None]
    tail = [(t, y) for t, y in ys if t >= a.settle_s]
    if len(tail) < 5:
        raise NotAssessed(f"fewer than 5 samples after {a.settle_s} s")
    center = sum(y for _, y in tail) / len(tail)
    # the probe is the box centre: bottom = centre - height/2
    draft = a.water_y - (center - a.height / 2)
    frac = draft / a.height
    swing = max(y for _, y in tail) - min(y for _, y in tail)
    return [metric("submerged_fraction", rnd(frac, 4), f"{a.fraction} ± {a.tol}",
                   abs(frac - a.fraction) <= a.tol, draft_m=rnd(draft, 4)),
            metric("bobbing_after_settle_m", rnd(swing, 4), f"≤ {rnd(0.02 * a.height, 4)}",
                   swing <= 0.02 * a.height, note="peak-to-peak after --settle-s")]


def levels(a):
    times, samples = load_recording(a.dump)
    names = [n.strip() for n in a.probes.split(",") if n.strip()]
    if len(names) < 2:
        raise ValueError("--probes needs at least two names")
    t_end = times[-1] if times else 0
    finals = {}
    for n in names:
        vals = [height_of(v) for t, v in zip(times, probe(samples, n)) if t >= t_end - a.last_s]
        vals = [v for v in vals if v is not None]
        if not vals:
            raise NotAssessed(f"no samples of '{n}' in the last {a.last_s} s")
        finals[n] = sum(vals) / len(vals)
    spread = max(finals.values()) - min(finals.values())
    return [metric("level_difference_m", rnd(spread, 4), f"≤ {a.tol}", spread <= a.tol,
                   levels={k: rnd(v, 4) for k, v in finals.items()})]


def conserve(a):
    _, samples = load_recording(a.dump)
    vals = [v for v in probe(samples, a.total) if isinstance(v, (int, float))]
    if len(vals) < 2:
        raise NotAssessed("fewer than 2 samples of the total")
    ref = vals[0]
    scale = abs(ref) or 1.0
    drift = max(abs(v - ref) for v in vals) / scale
    return [metric("volume_drift", rnd(drift, 6), f"≤ {a.tol}", drift <= a.tol,
                   start=rnd(ref, 6), end=rnd(vals[-1], 6))]


def repose(a):
    with open(a.heights, encoding="utf-8-sig") as fh:
        data = json.load(fh)
    dx = float(data["dx"])
    h = data["heights"]
    slopes = []
    for j in range(len(h)):
        for i in range(len(h[j])):
            for di, dj in ((1, 0), (0, 1)):
                ii, jj = i + di, j + dj
                if jj < len(h) and ii < len(h[jj]):
                    dh = abs(h[jj][ii] - h[j][i])
                    if dh > 1e-9:
                        slopes.append(math.degrees(math.atan(dh / dx)))
    if len(slopes) < 10:
        raise NotAssessed("pile too flat to measure")
    slopes.sort()
    p99 = slopes[min(len(slopes) - 1, int(len(slopes) * 0.99))]
    too_steep = p99 > a.angle + a.tol
    never_stands = p99 < a.angle - 2 * a.tol
    return [metric("repose_angle_p99_deg", rnd(p99, 3), f"{a.angle} ± {a.tol}",
                   not too_steep and not never_stands, steepest_deg=rnd(slopes[-1], 3),
                   note="too steep: pile doesn't flow; far below: it flows flat like a liquid")]


def wave(a):
    times, samples = load_recording(a.dump)
    pts = [(t, height_of(v)) for t, v in zip(times, probe(samples, a.height))]
    pts = [(t, y) for t, y in pts if y is not None]
    if len(pts) < 10:
        raise NotAssessed("fewer than 10 height samples")
    mean = sum(y for _, y in pts) / len(pts)
    ups = []
    for (t0, y0), (t1, y1) in zip(pts, pts[1:]):
        if y0 - mean < 0 <= y1 - mean:
            ups.append(t0 + (t1 - t0) * (mean - y0) / (y1 - y0))
    if len(ups) < 3:
        raise NotAssessed("fewer than 3 upward zero crossings")
    period = (ups[-1] - ups[0]) / (len(ups) - 1)
    k = 2 * math.pi / a.wavelength
    expected = 2 * math.pi / math.sqrt(G * k * math.tanh(k * a.depth))
    err = abs(period - expected) / expected
    return [metric("wave_period_s", rnd(period, 4), f"{rnd(expected, 4)} ± {a.tol:.0%}",
                   err <= a.tol, relative_error=rnd(err, 5), crossings=len(ups))]


def series(a, name):
    times, samples = load_recording(a.dump)
    pts = [(t, height_of(v)) for t, v in zip(times, probe(samples, name))]
    return [(t, y) for t, y in pts if y is not None]


def fill(a):
    pts = series(a, a.depth)
    if len(pts) < 5:
        raise NotAssessed("fewer than 5 depth samples")
    d0 = pts[0][1]
    if d0 <= 0:
        raise NotAssessed("the print has no depth at the start")
    target = (1 - a.fraction) * d0
    t_hit = None
    for (t0, y0), (t1, y1) in zip(pts, pts[1:]):
        if y0 > target >= y1:
            t_hit = t0 + (t1 - t0) * (y0 - target) / (y0 - y1)
            break
    low = d0
    rise = 0.0
    for _, y in pts:
        low = min(low, y)
        rise = max(rise, y - low)
    regrow = metric("print_deepens_m", rnd(rise, 5), f"≤ {rnd(0.05 * d0, 5)}", rise <= 0.05 * d0,
                    note="a filling print must not dig itself out again")
    if t_hit is None:
        if pts[-1][0] < a.expect_s * a.fraction * (1 + a.tol):
            raise NotAssessed(f"recording ends at {rnd(pts[-1][0], 1)} s, before the expected "
                              f"fill of {a.fraction:.0%}")
        return [metric("fill_time_s", None, f"{a.expect_s} ± {a.tol:.0%}", False,
                       note=f"never filled {a.fraction:.0%} of the print"), regrow]
    full = t_hit / a.fraction
    err = abs(full - a.expect_s) / a.expect_s
    return [metric("fill_time_s", rnd(full, 2), f"{a.expect_s} ± {a.tol:.0%}", err <= a.tol,
                   time_to_fraction_s=rnd(t_hit, 2), start_depth_m=rnd(d0, 5),
                   relative_error=rnd(err, 4)), regrow]


def accum(a):
    pts = series(a, a.depth)
    if len(pts) < 10 or pts[-1][0] - pts[0][0] <= 0:
        raise NotAssessed("fewer than 10 depth samples over a positive duration")
    n = len(pts)
    mt = sum(t for t, _ in pts) / n
    my = sum(y for _, y in pts) / n
    stt = sum((t - mt) ** 2 for t, _ in pts)
    slope = sum((t - mt) * (y - my) for t, y in pts) / stt
    expected = a.rate / 100 / 3600 * a.k
    err = abs(slope - expected) / expected
    return [metric("accumulation_m_s", rnd(slope, 9), f"{rnd(expected, 9)} ± {a.tol:.0%}",
                   err <= a.tol, cm_per_game_hour=rnd(slope * 360000, 3),
                   relative_error=rnd(err, 4))]


def load_grid(path):
    with open(path, encoding="utf-8-sig") as fh:
        data = json.load(fh)
    return float(data["dx"]), [[float(v) for v in row] for row in data["heights"]]


WIND_DIRS = {"+x": "+x", "x": "+x", "x+": "+x", "-x": "-x", "x-": "-x",
             "+z": "+z", "z": "+z", "z+": "+z", "-z": "-z", "z-": "-z"}


def along_wind(grid, wind):
    """Rows are transects with the wind blowing toward increasing index."""
    wind = WIND_DIRS.get(wind.strip().lower())
    if wind is None:
        raise ValueError("--wind must be +x, x-, +z or z- (the direction the wind blows toward)")
    if wind in ("+z", "-z"):
        grid = [list(col) for col in zip(*grid)]
    if wind in ("-x", "-z"):
        grid = [row[::-1] for row in grid]
    return grid


def lee(a):
    dx, before = load_grid(a.before)
    dx2, after = load_grid(a.after)
    if dx != dx2 or len(before) != len(after) or any(len(r) != len(s)
                                                       for r, s in zip(before, after)):
        raise ValueError("before and after heightfields differ in dx or size")
    before, after = along_wind(before, a.wind), along_wind(after, a.wind)
    dep_lee = dep_all = ero_stoss = ero_all = 0.0
    shifts, lee_max, stoss_max = [], 0.0, 0.0
    for b, f in zip(before, after):
        base = min(b)
        if max(b) - base < 1e-6:
            continue
        c = b.index(max(b))
        for i, (hb, hf) in enumerate(zip(b, f)):
            d = hf - hb
            if d > 0:
                dep_all += d
                dep_lee += d if i > c else 0.0
            elif d < 0:
                ero_all -= d
                ero_stoss -= d if i <= c else 0.0
        wb = [h - base for h in b]
        wf = [max(0.0, h - base) for h in f]
        if sum(wf) > 0:
            xb = sum(i * w for i, w in enumerate(wb)) / sum(wb)
            xf = sum(i * w for i, w in enumerate(wf)) / sum(wf)
            shifts.append((xf - xb) * dx)
        ca = f.index(max(f))
        for i in range(len(f) - 1):
            ang = math.degrees(math.atan(abs(f[i + 1] - f[i]) / dx))
            if i >= ca and f[i + 1] < f[i]:
                lee_max = max(lee_max, ang)
            elif i < ca and f[i + 1] > f[i]:
                stoss_max = max(stoss_max, ang)
    if not shifts or dep_all <= 0 or ero_all <= 0:
        raise NotAssessed("no dune relief or no change between the two exports")
    floor = min(map(min, before))
    vol_b = sum(h - floor for row in before for h in row)
    drift = abs(sum(map(sum, after)) - sum(map(sum, before))) / (vol_b or 1.0)
    shift = sum(shifts) / len(shifts)
    out = [metric("lee_deposition_fraction", rnd(dep_lee / dep_all, 4), f"≥ {a.lee_frac}",
                  dep_lee / dep_all >= a.lee_frac, note="deposition downwind of the crest"),
           metric("windward_erosion_fraction", rnd(ero_stoss / ero_all, 4), f"≥ {a.lee_frac}",
                  ero_stoss / ero_all >= a.lee_frac, note="erosion upwind of the crest"),
           metric("volume_drift", rnd(drift, 6), f"≤ {a.vol_tol}", drift <= a.vol_tol),
           metric("slip_face_deg", rnd(lee_max, 3), f"≤ {a.angle + a.tol}",
                  lee_max <= a.angle + a.tol, windward_max_deg=rnd(stoss_max, 3)),
           metric("windward_gentler_than_lee", rnd(stoss_max - lee_max, 3), "< 0",
                  stoss_max < lee_max, note="dunes are asymmetric: gentle stoss, steep lee")]
    if a.speed is not None and a.dt_s:
        want = a.speed * a.dt_s
        err = abs(shift - want) / want
        out.append(metric("migration_m", rnd(shift, 4), f"{rnd(want, 4)} ± 30%", err <= 0.3,
                          relative_error=rnd(err, 4)))
    else:
        out.append(metric("migration_m", rnd(shift, 4), "> 0 (downwind)", shift > 0))
    return out


def runout(a):
    times, samples = load_recording(a.dump)
    pts = [p for p in probe(samples, a.pos) if isinstance(p, list) and len(p) >= 3]
    if len(pts) < 5:
        raise NotAssessed("fewer than 5 front positions")
    x0, y0, z0 = pts[0][:3]
    far = max(pts, key=lambda p: math.hypot(p[0] - x0, p[2] - z0))
    reach = math.hypot(far[0] - x0, far[2] - z0)
    drop = y0 - far[1]
    if drop <= 0 or reach <= 0:
        raise NotAssessed("the front never moved down and away from its start")
    alpha = math.degrees(math.atan(drop / reach))
    if a.alpha is not None:
        want = a.alpha
    elif a.beta is not None:
        want = 0.97 * a.beta - 1.4
    else:
        raise ValueError("runout needs --beta or --alpha")
    band = a.k * a.sd
    return [metric("runout_alpha_deg", rnd(alpha, 3), f"{rnd(want, 3)} ± {rnd(band, 2)}",
                   abs(alpha - want) <= band, reach_m=rnd(reach, 2), drop_m=rnd(drop, 2),
                   note="alpha = atan(drop / horizontal reach); smaller alpha = longer runout")]


def release(a):
    with open(a.trials, encoding="utf-8-sig") as fh:
        data = json.load(fh)
    trials = data.get("trials") if isinstance(data, dict) else data
    if not trials:
        raise NotAssessed("no trials")
    lo, hi = parse_band(a.band)
    outside = [t for t in trials if t.get("released") and not lo <= float(t["slope"]) <= hi]
    out = [metric("releases_outside_band", len(outside), 0, not outside,
                  slopes=[t["slope"] for t in outside],
                  released=sum(1 for t in trials if t.get("released")), trials=len(trials))]
    with_s = [t for t in trials if t.get("S") is not None]
    if with_s:
        wrong = [t for t in with_s
                 if (t.get("released") and float(t["S"]) > 1.5)
                 or (not t.get("released") and float(t["S"]) < 1
                     and lo <= float(t["slope"]) <= hi)]
        out.append(metric("stability_mismatches", len(wrong), 0, not wrong,
                          cases=[{"slope": t["slope"], "S": t["S"],
                                  "released": bool(t.get("released"))} for t in wrong],
                          note="S < 1 in the band must release; S > 1.5 must not"))
    return out


# ---------- cli ----------

def build_parser():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("predict")
    pr.add_argument("case", choices=["float", "heave", "efflux", "dambreak", "wave", "cfl",
                                     *WIND_CASES])
    for name in ("rho-body", "mass", "area", "h", "tank-area", "hole-area", "h0", "wavelength",
                 "dx", "dt", "umax", "depth",
                 # wind, sand and snow
                 "d", "wind", "ustar", "q", "q-year", "q-mass", "dune-height", "width",
                 "game-move", "game-s", "index", "aspect", "hop", "ps", "repose", "length",
                 "ustar-t", "wind-threshold", "barrier", "rate", "swe-rate", "hours",
                 "rho-settled", "rho0", "rhof", "rho-max", "tau-h", "hf", "target-rho", "cap",
                 "slope", "slab", "strength", "beta", "drop", "swe", "power", "temp",
                 "visibility", "count", "size", "radius", "near", "opacity"):
        pr.add_argument(f"--{name}", type=float)
    pr.add_argument("--rho-fluid", type=float, default=1000.0)
    pr.add_argument("--height", type=float, default=1.0)
    pr.add_argument("--z", type=float, default=10.0)
    pr.add_argument("--z0", type=float, default=1e-3)
    pr.add_argument("--rho-air", type=float, default=1.225)
    pr.add_argument("--rho-grain", type=float, default=2650.0)
    pr.add_argument("--porosity", type=float, default=0.4)
    pr.add_argument("--active", type=float, default=1.0)
    pr.add_argument("--trap", type=float, default=1.0)
    pr.add_argument("--rho-deposit", type=float, default=350.0)
    pr.add_argument("--rho-new", type=float, default=100.0)
    pr.add_argument("--rho-slab", type=float, default=200.0)
    pr.add_argument("--sorting", choices=sorted(SAND_C), default="natural")
    pr.add_argument("--material", choices=["sand", "snow"], default="sand")
    pr.add_argument("--snow", choices=sorted(SNOW_U10_THRESHOLD), default="dry")
    pr.add_argument("--band", default="30,45")
    pr.add_argument("--melting", action="store_true")
    pr.add_argument("--skier", action="store_true")
    pr.add_argument("--fit", action="store_true")

    f = sub.add_parser("float")
    f.add_argument("dump")
    f.add_argument("--pos", required=True)
    f.add_argument("--water-y", type=float, required=True)
    f.add_argument("--height", type=float, required=True)
    f.add_argument("--fraction", type=float, required=True)
    f.add_argument("--tol", type=float, default=0.05)
    f.add_argument("--settle-s", type=float, default=5.0)

    lv = sub.add_parser("levels")
    lv.add_argument("dump")
    lv.add_argument("--probes", required=True)
    lv.add_argument("--tol", type=float, default=0.02)
    lv.add_argument("--last-s", type=float, default=1.0)

    c = sub.add_parser("conserve")
    c.add_argument("dump")
    c.add_argument("--total", required=True)
    c.add_argument("--tol", type=float, default=0.01)

    r = sub.add_parser("repose")
    r.add_argument("heights")
    r.add_argument("--angle", type=float, required=True)
    r.add_argument("--tol", type=float, default=3.0)

    w = sub.add_parser("wave")
    w.add_argument("dump")
    w.add_argument("--height", required=True)
    w.add_argument("--wavelength", type=float, required=True)
    w.add_argument("--depth", type=float, default=1000.0)
    w.add_argument("--tol", type=float, default=0.05)

    fl = sub.add_parser("fill")
    fl.add_argument("dump")
    fl.add_argument("--depth", required=True)
    fl.add_argument("--expect-s", type=float, required=True)
    fl.add_argument("--fraction", type=float, default=0.9)
    fl.add_argument("--tol", type=float, default=0.25)

    ac = sub.add_parser("accum")
    ac.add_argument("dump")
    ac.add_argument("--depth", required=True)
    ac.add_argument("--rate", type=float, required=True)
    ac.add_argument("--k", type=float, default=1.0)
    ac.add_argument("--tol", type=float, default=0.15)

    le = sub.add_parser("lee")
    le.add_argument("before")
    le.add_argument("after")
    le.add_argument("--wind", required=True)
    le.add_argument("--angle", type=float, default=34.0)
    le.add_argument("--tol", type=float, default=3.0)
    le.add_argument("--lee-frac", type=float, default=0.7)
    le.add_argument("--vol-tol", type=float, default=1e-3)
    le.add_argument("--speed", type=float)
    le.add_argument("--dt-s", type=float)

    ro = sub.add_parser("runout")
    ro.add_argument("dump")
    ro.add_argument("--pos", required=True)
    ro.add_argument("--beta", type=float)
    ro.add_argument("--alpha", type=float)
    ro.add_argument("--sd", type=float, default=3.5)
    ro.add_argument("--k", type=float, default=2.0)

    rl = sub.add_parser("release")
    rl.add_argument("trials")
    rl.add_argument("--band", default="30,45")
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        if a.cmd == "predict":
            print(json.dumps(predict(a), ensure_ascii=False))
            return 0
        metrics = {"float": float_check, "levels": levels, "conserve": conserve,
                   "repose": repose, "wave": wave, "fill": fill, "accum": accum, "lee": lee,
                   "runout": runout, "release": release}[a.cmd](a)
    except NotAssessed as exc:
        print(json.dumps({"verdict": "NOT ASSESSED", "reason": str(exc), "metrics": []},
                         ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"verdict": "ERROR", "reason": f"{type(exc).__name__}: {exc}"}))
        return 2
    verdict = "FAIL" if any(m["verdict"] == "FAIL" for m in metrics) else "PASS"
    print(json.dumps({"verdict": verdict, "metrics": metrics}, ensure_ascii=False))
    return 1 if verdict == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
