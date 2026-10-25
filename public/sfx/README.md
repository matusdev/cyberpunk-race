# Sound effects

All files are mono at 44.1 kHz. Loops are WAV PCM 16-bit, and one-shots are MP3 (128 kbps, all under 150 KB) or small WAVs.
Total size is about 8.4 MB. Sources and licences (all CC0, or generated for this project) are listed in `../CREDITS.md`.

**Levels.** One-shots are peak-normalised to −1.5 dBFS (heavy crashes to −1 dBFS).
Loops are RMS-normalised: engine −18 dBFS, tyres/nitro/scrape −18 to −22 dBFS, ambiences −24 to −26 dBFS.
The "suggested gain" column is a starting point for a WebAudio `GainNode` under a master bus. Tune it by ear.

**Seamless loops.** Every loop was checked at the wrap point. There is no step or HF burst there, because tail and head are crossfaded inside the file.
Play them with `source.loop = true` and leave `loopStart`/`loopEnd` at their defaults.

---

## Engine (most important)

One engine throughout: a **Mercedes-Benz 190E 2.3-16V** (Cosworth-head 4-cylinder, 16 valves, revs past 7000).
It was recorded on a dyno day by Chippy569 ("The Dyno Sessions: 190E"). The mix is an exhaust mic (AKG D6) plus a room mic at 0.7.
No CC0 V8 or supercar set with separate steady-RPM recordings exists, so the loops were **built from continuous rev sweeps**:

1. The firing-frequency harmonic (RPM / 30 Hz for a 4-cylinder) was pitch-tracked through each sweep. This was calibrated against the author's labelled 2500 and 6500 rpm clips.
2. A short window around each target RPM (±5–12 %) was resampled with a time-varying rate, so its pitch is exactly constant at the target RPM.
3. The flattened material was cut into whole engine cycles (2 revolutions). These were reassembled in a random, non-repeating order with short crossfades at the cycle boundaries, then closed into a circular loop. Each loop is a whole number of engine cycles, so the firing rhythm never jumps at the loop point.

- **on** = wide-open throttle while the revs climb (rough, loud "pulling" sound).
- **off** = closed throttle while the revs fall (overrun burble, softer).
- All on/off loops are loudness-matched to −18 dBFS RMS, so the game sets the volume difference. A good start is off ≈ 0.6 × on.

| File | Length | Type | RPM (exact) | Notes | Suggested gain |
|---|---|---|---|---|---|
| engine_idle.wav | 2.42 s | loop | 1041 | natural idle (steady recording, pitch-locked) | 0.5 |
| engine_on_2000.wav | 0.60 s | loop | 2000 | source 1760–2240 rpm | 0.8 |
| engine_on_2600.wav | 0.60 s | loop | 2600 | source 2370–2830 rpm | 0.8 |
| engine_on_3400.wav | 0.60 s | loop | 3400 | source 3160–3640 rpm | 0.8 |
| engine_on_4400.wav | 0.60 s | loop | 4400 | source 4090–4700 rpm | 0.85 |
| engine_on_5700.wav | 0.61 s | loop | 5700 | source 5300–6100 rpm | 0.9 |
| engine_on_7000.wav | 0.60 s | loop | 7000 | source 6510–7080 rpm (rev limiter region) | 0.9 |
| engine_off_2000.wav | 0.60 s | loop | 2000 | source 1900–2100 rpm | 0.5 |
| engine_off_2600.wav | 0.60 s | loop | 2600 | source 2470–2730 rpm | 0.5 |
| engine_off_3400.wav | 0.60 s | loop | 3400 | source 3230–3570 rpm | 0.5 |
| engine_off_4400.wav | 0.60 s | loop | 4400 | source 4180–4620 rpm | 0.55 |
| engine_off_5700.wav | 0.61 s | loop | 5700 | source 5420–5980 rpm | 0.55 |
| engine_off_7000.wav | 0.60 s | loop | 7000 | **derived**: the decel sweep starts at 6500 rpm, so the 6170–6490 rpm region was pitch-raised about 10 % | 0.55 |
| engine_start.mp3 | 8.25 s | one-shot | — | ignition, catch and settle to idle (garage / race start) | 0.7 |

**Using the set.** The neighbouring loops are about 1.3× apart (2000, 2600, 3400, 4400, 5700, 7000), so each loop only ever needs about ±15 % of pitch-shift:

```
// for the current rpm, find the two neighbouring loop RPMs a <= rpm <= b
t = log(rpm / a) / log(b / a)              // 0..1 between the two loops
gainA = cos(t * PI/2), gainB = sin(t * PI/2)  // equal-power crossfade
srcA.playbackRate = rpm / a                 // 1.00 … 1.30 at most
srcB.playbackRate = rpm / b                 // 0.77 … 1.00
on/off mix: throttle 0..1 -> onGain = throttle, offGain = 1 - throttle (equal-power if preferred)
below 2000 rpm: crossfade engine_idle (rate = rpm / 1041) with the 2000 loops
```

Start every engine source at the same `start()` time and keep them all running. Change only gain and `playbackRate`, smoothed with `setTargetAtTime`, about 20–40 ms.

## Turbo, transmission, exhaust

| File | Length | Type | Notes | Suggested gain |
|---|---|---|---|---|
| turbo_whistle.wav | 1.35 s | loop | Real turbo whine (Toyota Supra on a dyno). The tone was isolated with a tracking band-pass and resynthesised at a constant **5.0 kHz** (the original was about 10.3 kHz at full boost), keeping its natural flutter. Map boost to `playbackRate` 0.5–1.6 and to gain 0–0.3. | 0.25 × boost |
| blowoff.mp3 | 1.70 s | one-shot | Turbo dump/flutter "pshh-tu-tu-tu" on throttle lift. Play when throttle drops after boost > ~50 %. | 0.6 |
| shift.mp3 | 0.62 s | one-shot | Mechanical gear-lever "clunk-clack" (Lotus Elise gearbox). | 0.5 |
| shift_2.mp3 | 0.50 s | one-shot | Alternative shift, slightly lighter. | 0.5 |
| backfire_1.mp3 | 0.33 s | one-shot | Single sharp exhaust bang. | 0.6 |
| backfire_2.mp3 | 1.30 s | one-shot | Big backfire with a tail. Use it rarely, e.g. at the rev limiter. | 0.6 |
| backfire_3.mp3 | 0.23 s | one-shot | Anti-lag pop. | 0.5 |
| backfire_4.mp3 | 0.23 s | one-shot | Anti-lag pop. | 0.5 |
| backfire_5.mp3 | 0.24 s | one-shot | Anti-lag pop. | 0.5 |
| backfire_crackle.mp3 | 1.35 s | one-shot | A burst of overrun pops and crackles. Play on lift-off at high RPM. | 0.5 |

## Tyres, wind, surfaces

| File | Length | Type | Notes | Suggested gain |
|---|---|---|---|---|
| tire_screech.wav | 3.00 s | loop | Steady tyre squeal (handbrake/drift). Gain = slip, rate 0.9–1.1 with speed. | 0.6 × slip |
| tire_wet.wav | 6.00 s | loop | Wet-road tyre spray/hiss at highway speed (high-passed at 220 Hz, so there is no engine in it). Important in rain: gain and rate follow speed. | 0.5 × speed |
| wind.wav | 8.00 s | loop | Strong wind/airflow noise around the car. Fade in above ~80 km/h. | 0–0.45 × speed |
| scrape_metal.wav | 2.00 s | loop | Metal grinding/scraping (car along a barrier or wall). Gain from contact force. | 0.6 |

## Impacts

| File | Length | Type | Notes | Suggested gain |
|---|---|---|---|---|
| crash_heavy_1.mp3 | 3.20 s | one-shot | Big car crash with debris tail. | 0.9 |
| crash_heavy_2.mp3 | 2.11 s | one-shot | Car crash with glass. | 0.9 |
| crash_heavy_3.mp3 | 2.06 s | one-shot | Heavy metal crash. | 0.9 |
| crash_light_1.mp3 | 0.44 s | one-shot | Short metallic clank (glancing hit). | 0.7 |
| crash_light_2.mp3 | 0.26 s | one-shot | Quick collision thump. | 0.7 |
| crash_light_3.mp3 | 1.25 s | one-shot | Car hood/body panel impact. | 0.7 |
| glass_break.mp3 | 1.23 s | one-shot | Glass smash (windows, shop fronts, bus stops). | 0.7 |
| hit_plastic.mp3 | 0.12 s | one-shot | Hollow plastic hit (cones, bins). | 0.6 |
| hit_plastic_2.mp3 | 0.11 s | one-shot | Variation. | 0.6 |
| hit_metal_pole.mp3 | 0.70 s | one-shot | Resonant metal pipe clang (lamp posts, sign poles). | 0.8 |
| landing.mp3 | 0.53 s | one-shot | Low suspension thump plus spring creak (landing after a jump). Scale gain with vertical speed. | 0.7 |

## Nitro, pass-bys

| File | Length | Type | Notes | Suggested gain |
|---|---|---|---|---|
| nitro_start.mp3 | 2.70 s | one-shot | Nitro activation burst. | 0.8 |
| nitro_loop.wav | 4.00 s | loop | Steady jet/flame roar while nitro is held. Crossfade in about 150 ms after nitro_start. | 0.5 |
| whoosh_pass.mp3 | 3.50 s | one-shot | Car passing on a **wet** road (spray plus doppler). Use for near misses or traffic passing. Play at rate 1.2–1.6 for very fast passes. | 0.7 |
| whoosh_pass_dry.mp3 | 2.70 s | one-shot | Fast car pass-by, dry road. | 0.7 |

## Ambience (2D background loops)

| File | Length | Type | Notes | Suggested gain |
|---|---|---|---|---|
| amb_rain.wav | 14.0 s | loop | Steady heavy rain in a city. Constant bed during rain. | 0.45 |
| amb_city.wav | 16.0 s | loop | Late-night downtown (LA Little Tokyo), distant traffic and city hum. | 0.35 |
| amb_siren.mp3 | 12.0 s | one-shot | Distant ambulance siren (fades in and out). Trigger randomly every 30–90 s, with random pan. | 0.25 |
| amb_tunnel.wav | 10.0 s | loop | Tunnel fan drone and roomy hum. Crossfade in while inside the megabuilding tunnel. | 0.5 |
| amb_market.wav | 14.0 s | loop | Busy night-market crowd chatter (Asian street market). Kabuki market street and market hall. | 0.35 |

## UI

| File | Length | Type | Notes | Suggested gain |
|---|---|---|---|---|
| ui_click.wav | 0.06 s | one-shot | Menu move/select tick. | 0.5 |
| ui_confirm.wav | 0.29 s | one-shot | Confirm/accept. | 0.5 |
| ui_back.wav | 0.09 s | one-shot | Back/cancel. | 0.5 |
| countdown_beep.wav | 0.20 s | one-shot | 3-2-1 beep, 880 Hz (synthesised). | 0.6 |
| countdown_go.wav | 0.65 s | one-shot | GO tone, 1760 Hz, one octave up (synthesised). | 0.6 |
