# Gaits, sizes and other mounts — riding tables

Numbers for building and checking a mount's locomotion. Sources are in the research notes for this skill (kept in Kiln's development repository);
(working) = starting point to tune, [U] = unverified, (calc) = computed here. Fr = v²/(g·L), with L =
leg length; L ≈ 1.25 m for a 500 kg riding horse (derived from Griffin 2004: 0.7–1.4 m over
90–720 kg, scaled by M^⅓; working).

## Horse gaits

| | Walk | Trot | Canter | Gallop |
|---|---|---|---|---|
| Beats | 4 | 2 | 3 + suspension | 4 + suspension |
| Footfalls | LH, LF, RH, RF; 3 and 2 feet down by turns | diagonal pairs (LF+RH, RF+LH), suspension between | right lead: LH; RH+LF together; RF (left lead mirrored) | the canter's diagonal pair splits into a fourth beat; right lead LH, RH, LF, RF [U] |
| Speed | avg 1.8–1.9 m/s (6.4–7 km/h), range 0.9–2.1 | avg 3.6 m/s (13 km/h), 3.6–5.3 | 4.4–7.5 m/s (16–27 km/h); western lope 3.6–5.3 | 11–13 m/s (40–48 km/h); record 19.7 m/s over 400 m |
| Stride | 0.7–1.1 Hz, 1.3–1.9 m, duty factor 0.55–0.75 | f = 0.623 + 0.25·v (680 kg horse, 1.42–5.46 m/s): 1.5 Hz at 3.5 m/s | ~1.6–1.7 Hz: 3.7 m at 6 m/s (calc); "standard" jumping canter stride 3.66 m | sustained: f = 4.44·M^−0.156, +10 % per doubling of speed; racing 2.34 Hz (Thoroughbred), 2.88 Hz (Quarter Horse), ~7.5 m stride |
| Fr at L 1.25 | < 0.34 | 0.34–1.3 (free horses to ~2.8) | 1.3–5 (working) | > 5 |
| Withers vertical (unridden, peak to peak) | 7 cm at 1.06 m/s | 9 cm at 2.32 m/s | 18 cm at 5.82 m/s | ~15 cm (racehorse trunk) |
| Trunk pitch | 6° | 2° | 8° (pitch rate up to 67°/s) | [U] |
| Saddle bounces per stride | 2 | 2 (one per diagonal) | 1 | 1 |
| Rider seat | sitting, pelvis rocks | sitting or rising (posting) | sitting, hips roll | two-point / half-seat |

- **Transitions.** Overground walk→trot 2.0–2.5 m/s; Griffin measured 1.6–2.3 m/s at Fr 0.34
  (0.30–0.37) across 90–720 kg — use Fr, not a fixed speed. Treadmill trot→gallop (Heglund & Taylor
  1988): v = 1.54·M^0.216, f = 4.19·M^−0.150 → 500 kg: 5.90 m/s at 1.65 Hz, Fr 2.84 at L 1.25 (calc).
  Overground riding horses are asked to canter from ~4 m/s. Animals hold the old gait past the
  transition speed for short periods in both directions (hysteresis) — copy it.
- **Equivalent speeds by mass (Heglund & Taylor 1988, m/s and strides/s, M in kg):**
  preferred trot 1.09·M^0.222 at 3.35·M^−0.130; trot-gallop 1.54·M^0.216 at 4.19·M^−0.150; preferred
  gallop 2.78·M^0.176 at 4.44·M^−0.156; maximum sustained gallop 3.71·M^0.176 at 4.70·M^−0.162.
  500 kg: 4.33 m/s @ 1.49 Hz, 5.90 @ 1.65, 8.30 @ 1.68, 11.08 @ 1.72 (calc). Within a trot stride
  frequency rises ~1.55× from the slowest trot to the transition; within a gallop only ~10 % for a
  doubling of speed — speed comes from longer strides.
- **Leads.** On a circle the inside legs lead. A wrong lead unbalances the horse in tight fast turns.
  A disunited (cross) canter puts the first two footfalls on one side — penalised, rolls the rider.
- **Turning circle by gait** (grip limit μ 0.6, r_min = v²/(μg), calc): walk 1.8 m/s → 0.55 m (turns
  on the forehand, limited by body length); trot 3.5 → 2.1 m; canter 6 → 6.1 m; gallop 13 → 28.7 m;
  racing 17 → 49 m. Turns tighter than ~30 m are grip-limited, wider ones limb-force-limited;
  racehorses slow on every bend, more on tighter ones (Tan & Wilson 2011).
- **Stopping** (calc): grip-limited a ≈ μg = 5.9 m/s²: 6 m/s → 3.1 m in 1.0 s, 15 m/s → 19.1 m in
  2.5 s. A comfortable 3 m/s² (working): 6 m/s → 6 m, 15 m/s → 37.5 m. A reining sliding stop peaks
  at ~38 m/s² measured on the saddle pad — a peak on a prepared surface, not an average.
- **Endurance.** Gallop 1.5–3 km before rest (115–230 s at 13 m/s); endurance races 160 km in a day,
  winners in 14–15 h (10.7–11.4 km/h); cavalry marched at 1.8 m/s walk and 3.6 m/s trot, 24–32 km a
  day (field manual, snippet).

## Horse sizes

| Type | Withers | Mass |
|---|---|---|
| Pony | < 147 cm (14.2 hh) | 200–400 kg [U] |
| Light riding horse | 142–163 cm | 380–550 kg |
| Larger riding horse | 157–173 cm | — |
| Draft horse | 163–183 cm | 700–1000 kg |

A hand (hh) is 4 in = 10.16 cm, measured at the withers: 15.2 hh = 62 in = 157.5 cm; 16 hh = 162.6 cm.
Saddle seat ~5–10 cm below the withers [U]. Field of view > 350°, binocular ~65° — a horse sees
behind itself except straight back, which is why it startles at things approaching from the rear.

## Rider numbers

- Mounting block (BHS): steps 240–260 mm, total ≤ 780 mm, single block ≤ ~500 mm; clear 1.8 m beside,
  3 m before and beyond, 3.7 m headroom.
- Saddle sideways sway at trot 14–24 mm per step (mean ~2 cm); each degree of rider pelvis roll away
  from the supporting hind leg cuts it by 1.1 mm (Byström 2018).
- Rider wrist relative to the bit: < 15 mm change per trot stride; rein tension peaks at the head's
  lowest point and oscillates at the step frequency (~3 Hz at trot) (Clayton 2021).
- Jockeys: very short stirrups, body forward; the horse's trunk moves ~15 cm per stride while the
  jockey barely moves and moves out of phase with it; this style cut race times 5–7 % (historical
  race data, not the 2009 measurement).
- Mount time from the ground 2.2–4.1 s (sum of phases, [U]); no measured source.

## Other mounts

| Mount | Size | Gaits and speeds | Riding notes |
|---|---|---|---|
| Dromedary | males 1.8–2.4 m at the shoulder, 400–690 kg | paces (both legs on one side together); walk ~4 km/h, jog 8–12 km/h (2.2–3.3 m/s, most used), fast 14–19 km/h; a short exhausting canter/gallop in races (racing camels: bursts to 65 km/h, conflicting) | up to 80 km/day for a week; trained to sit and stand on command for mounting; one-rider and two-rider saddles (markloofa, pakra); the pace rolls the rider side to side; rises hind end first [U] |
| Asian elephant | males 2.6–2.9 m at the shoulder | lateral-sequence walk up to 6.8 m/s (25 km/h); never all four feet off the ground — the front legs "run" while the hind legs "walk" | > 20 verbal commands; mahout on the neck, steering with feet behind the ears [U] |
| African bush elephant | males 3.0–3.4 m | as above | — |
| Fantasy / large | any | keep the horse's Fr: v ∝ √L, f ∝ 1/√L, stride ∝ L, mass ∝ L³ (`predict scale`) | a 3 m-leg mount cantering like a horse: 9.3 m/s, 1.04 Hz, 8.9 m strides, ~14× the mass (calc) |

Square-cube: a mount scaled up isometrically gets heavier faster than its legs get stronger — big
mounts stand on straighter legs, elephant-like ones never have all feet off the ground, and their
strides look slow. Playing horse-rate clips on a dragon-sized body reads as a toy
(creature-locomotion).
