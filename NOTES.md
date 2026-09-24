# Low-poly me: notes

Photo → PS1-style rigged low-poly bust → web card that sings with lip sync and dances to the beat.
Live: https://lexuzieel.github.io/lowpoly-me/ (latest), `/v1/` … `/v11/` (snapshots), `?song=2` Russian track, `?fps=6|24` body step rate.
First working card took ~10 min from the photo; v11 about 2 hours in total.

## Pipeline

| Step | Script | Output |
|---|---|---|
| Face landmarks (478 pts, 3D) + multiclass selfie segmentation | `extract.py` (MediaPipe tasks) | `out/face.json`, `out/seg.png` |
| Masks → inflated low-poly meshes, per-part inpainted textures, measurements | `build_parts.py` | `out/parts.json`, `out/tex_*.jpg`, `out/metrics.json` |
| Build scene in live Blender | `blender_build.py` | objects with front-projected UVs |
| Face rig: 11 shape keys, mouth cavity, teeth, eyeballs | `blender_face.py` | |
| 3D shells: skull, beanie, hood; hand placement; teeth | `blender_shells.py` | `out/rig_points.json` |
| Armature (chest, neck, head, eyes, forearm, hand) + procedural weights | `blender_rig.py` | |
| Export | `blender_export.py` | `web/me.glb` |
| Songs | `gen_song.py` (Lyria 3 Pro via OpenRouter, $0.08/song, needs `stream: true`) | `audio/*.mp3` |
| Vocals / instrumental split | `python -m demucs --two-stems=vocals -n htdemucs` (~40 s CPU) | `audio/sep/htdemucs/<name>/` |
| Lip sync + beat grid | `bake_lipsync.py song.mp3 [--english lyrics.txt] [--bpm N] --out web/lipsync_N.json` | cues, 50 fps envelope, dance beats |
| Cache-bust stamp | `build_web.sh` | `BUILD` id in `web/index.html` |
| Site assembly (latest + snapshots + songs) | `build_site.sh` (run by the Pages workflow) | `_site/` |

Blender runs as a GUI in WSLg with `bridge.py` (executes scripts dropped in `bridge/inbox` on the main thread); send scripts with `./run.sh script.py`.
The scene is rebuilt from scratch by the scripts: manual edits belong in `lowpoly-me.blend`, and running the pipeline overwrites them.

Checks: `shot.py` (screenshot, `BROWSER=firefox`, `--tilt x y`, `--play --at=T`), `test_lipsync.py [url]` (real audio, mouth must move),
`record.py [url] [secs]` (video with the song muxed in → `out/clip.mp4`).

## Modeling insights

- **MediaPipe face mesh is the organic low-poly face**: 854 tris, fixed topology → shape keys can be authored procedurally by landmark index.
  It has 4 boundary loops: outer, 2 eyes, mouth. Extrude only the outer loop.
- **Silhouette inflation (Teddy/Monster Mash) is 2.5D**: fine for jacket and hand, breaks at angles for hood/beanie.
  Those need real shells: skull ellipsoid from landmarks (width 234↔454, center at 168, top from the beanie mask);
  beanie cap with the front rim following the *measured* knit edge (lowest mask pixel per column); hood shell.
- **Hood with the pole facing the camera**: the face opening is simply the first ring → clean oval rim plus a folded lip.
  Cutting quads out of a sphere gives jagged steps.
- **Front projection + per-part inpainted textures**: every pixel outside a part's mask is repainted from inside it
  (inpaint on a 1/6 downscale), so backs and sides get plausible fabric colors and edges never pick up background.
  Jacket: repaint everything that isn't dark jacket (snow, blue lamps by hue, skin, beanie); keep only the logo zone bright.
- **Parts touching the photo edge**: pad the masks past the edge (`BORDER_REPLICATE`) and let UVs past 1.0 clamp.
  Then frame the camera so the real edge sits in a hidden margin: tilting shows the part running out of frame, not a cut.
- **Frame by photo width** (a 9:16 photo in a 2:3 card): framing by height cropped the hand away.
- **Eyeball depth from the lids, not the iris**: MediaPipe's iris z is noisy; one eyeball poked through the lid.
- **Blender 5 creates new shape keys at value 1.0**: set `kb.value = 0`, otherwise every expression is on and glTF exports weights of 1.
- **Mouth cavity edges must curl far back**, or the rotating jaw pulls them through the cheeks (dark streak at the corner).
- **Forearm sleeve in front of the palm hid a finger**: anchoring the hand to the frame edge worked better than a fake arm.

## Animation insights (the big ones)

- **Snappy beats smooth.** Smoothing reads as "jelly". The loved versions snapped poses; the most-worked version (v8) was the worst.
- **Structure on the beat grid beats reacting to every sound.** Reacting to every detected kick/snare = random twitching.
  What works: librosa beats → half-time grid (86 BPM for 172 DnB), downbeat from kick energy, pattern per 4-bar phrase
  (nod / side-to-side / look around / double-time bounce), hand pumps on 2 and 4, everything symmetric around neutral.
- **Impulses that only push one way accumulate**: a kick-only-down nod left the head permanently lowered.
- **Motion vs display**: compute with springs (per-bone character: heavy chest, head with slight overshoot),
  show on a coarse step grid (12 fps body). Anchor the step grid to the beats and **lead by one shown frame**,
  so the pose lands on the beat instead of 83 ms late.
- **Springs**: explicit Euler blew up (values in the millions) with a stiff mouth spring at 30 fps.
  Use semi-implicit Euler with 1/240 s substeps.
- **Lip sync**: the jaw follows a fast 50 fps envelope of the vocal's F1 band (250–1000 Hz, vowels), with local
  contrast (above the 250 ms average) so every syllable is its own opening. Rhubarb (phonetic for any language,
  `pocketSphinx` + lyrics for English) only shapes the lips. Near-instant shape swaps, mouth 60 ms ahead of the sound,
  a silence gate closes it. Rhubarb hallucinates phonemes in instrumental intros: the gate handles it.
- **Rhubarb's English model fails when writing to stdout**: use `-o file`.
- **Card tilt / gyro**: a high-pass on the phone orientation (reference follows in ~0.45 s) makes the card resist
  a quick turn and settle back to level; inverted, so the card keeps facing you. One spring (w 11, ζ 0.55) for the card.
  Too strong a tilt gets in the way of watching.

## Web / deploy gotchas

- GitHub Pages caches for 10 min: a new page with an old `lipsync.json` looked like "lip sync is broken" in Firefox.
  Every asset URL carries `?v=BUILD` (`build_web.sh`).
- Firefox ignores `overflow: hidden` rounding on a transformed WebGL canvas: use `clip-path: inset(0 round 18px)`.
- iOS needs `DeviceOrientationEvent.requestPermission()` from a gesture; listen always, request on the first tap.
- `python -m http.server` has no Range support, so audio can't seek locally; the headless-shell Chromium has no audio
  clock (use `channel="chromium"`).
- A WebGL canvas reads back blank without `preserveDrawingBuffer`: check rendering with screenshots.
- Test windows must start at *sustained* singing: a stray breath frame made a test sample silence.

## Open tasks

- Gestures synced to song sections (chorus, high notes, energy / timbre changes).
- Facial dynamics beyond the mouth: eye darts, brows on accents.
- Manual cleanup of the model in `lowpoly-me.blend` (hood seams, beanie edge, glossy hood sides).
- Generalize to any photo (`make photo.jpg`): remove photo-specific hacks (yellow beanie hue, Puma logo zone,
  blue lamp filter, hand nudge); detect hat / hood / glasses from segmentation. Glasses need their own geometry.
- Song ideas the user liked: game-soundtrack liquid DnB (Gran Turismo / Wipeout era). Songs *about* the card feel
  cringey and the voice isn't his; keep songs as a fun extra.
