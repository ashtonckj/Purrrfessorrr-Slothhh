# Assets: drawing your own art

Every image the app uses is a PNG under `static/assets/`, described by
`static/assets/manifest.json`. The sprite engine (`static/js/sprites.js`)
reads the manifest, so **you can replace any PNG with your own drawing without
touching code**, as long as the manifest numbers match your file.

Preview everything at **http://127.0.0.1:8765/sprites.html** (the sprite
gallery). It uses the real engine, with 1x-4x zoom, a pause toggle, and a
preview of the placeholder you get when a file is missing.

## How sprite sheets work

A sheet is a **horizontal strip of equal-size frames**, played left to right
in a loop:

```
detective_work.png  (4 frames of 32x32 = 128x32 px)
+--------+--------+--------+--------+
| frame0 | frame1 | frame2 | frame3 |
+--------+--------+--------+--------+
```

Each manifest entry:

```json
"detective_work": {
  "file": "sprites/cats/detective_work.png",
  "frameWidth": 32, "frameHeight": 32,
  "frameCount": 4, "fps": 8,
  "group": "cats", "label": "Detective Cat", "color": "#c79a6b",
  "usedIn": "cat desk while its progress bar fills"
}
```

- `frameWidth`, `frameHeight`: size of one frame in pixels (your drawing size, not the on-screen size).
- `frameCount`: number of frames in the strip. PNG width must equal `frameWidth * frameCount`.
- `fps`: playback speed. Single-frame sprites ignore it.
- `label`, `color`: used for the placeholder block if the PNG is missing.
- `group`, `usedIn`: documentation only (gallery sections, the table below).

You can change the frame count freely: draw 6 frames instead of 4, set
`"frameCount": 6`, and you're done. If the PNG size doesn't match the numbers,
the browser console prints a warning naming the file.

The app scales sprites by **whole numbers only** (2x, 3x, ...) with
`image-rendering: pixelated`, so keep your art at its native pixel size.

## Replacing art (Aseprite / Piskel / LibreSprite)

1. Open the existing PNG to see the size and pose, or start a canvas of `frameWidth x frameHeight`.
2. Draw each frame (Aseprite: one frame per timeline frame; Piskel: one frame per frame).
3. Export as a **horizontal sprite sheet**:
   - Aseprite: *File > Export Sprite Sheet*, Layout **Horizontal Strip**, no padding / borders / trim, **Output scale 100%**.
   - Piskel: *Export > PNG*, **Columns = number of frames**, Rows = 1, scale **1x**.
4. Save over the file in `static/assets/...` (same name), or save a new name and update `file` in the manifest.
5. Reload the gallery page and check it.

Export tips:
- **PNG with a transparent background.**
- **No anti-aliasing**: pencil tool only, no soft brushes, no smooth resize.
- **No scaling on export** (1x). The app does the scaling.
- **No padding, spacing or trimming** between frames: frames must sit edge to edge.
- Keep characters in the same spot across frames so animations don't jitter.
- Optional: reuse the palette below (it's also in `manifest.json` > `palette`) so your art matches the UI.

A missing or broken file never breaks the app: it shows a coloured block with
the sprite's name instead.

## Regenerating the placeholders

```bash
python tools/generate_placeholders.py
```

By default this **only creates missing PNGs** and keeps manifest entries for
files that already exist, so your art and your manifest edits are safe.
`--force` redraws every placeholder and **overwrites your art**.

## Sizes and scales

| kind | frame size | on-screen scale |
|---|---|---|
| sloth and cats | 32x32 | 2x-3x (depends on window width) |
| desks | 48x24 (cats), 64x24 (sloth) | same scale as the characters |
| papers, zzz, progress-bar cat | 16x16 | 2x |
| paper stack | 24x24 | same scale as the characters |
| branch | 64x16 | same scale as the characters |
| avatars | 48x48 | 1x (48 px in chat) |
| UI icons | 16x16 | 1x-2x |

## Palette

| char | hex | name | | char | hex | name |
|---|---|---|---|---|---|---|
| K | `#2b1d14` | ink / outline | | T | `#c79a6b` | tan |
| C | `#f4ead5` | cream paper | | P | `#e98aa3` | pink |
| c | `#e3d3b0` | cream shadow | | p | `#f6c1cc` | light pink |
| W | `#fffaf0` | white | | R | `#c8473d` | red |
| G | `#2f5d3a` | forest green | | Y | `#f2c14e` | yellow |
| g | `#5f8f4e` | leaf green | | U | `#4a6fa5` | blue |
| l | `#a8c686` | light green | | S | `#9a948c` | grey |
| B | `#8a5a3b` | wood brown | | D | `#4a4250` | charcoal |
| b | `#5c3b26` | dark wood | | O | `#e08a3c` | orange |

The same colours are CSS variables in `static/css/palette.css`.

## Other folders

- `static/assets/audio/`: optional sound effects and music. List files in `sounds.json`:

  | name | when it plays |
  |---|---|
  | `pop` | the sloth posts a chat message |
  | `drop` | a file finished uploading |
  | `paper` | a paper lands on a cat's desk |
  | `done` | a cat finished its job |
  | `copy` | code was copied |
  | `error` | a cat gave up |
  | `music` | loops quietly while sound is on |

  Short `.ogg`, `.mp3` or `.wav` files work. Sound is off until the speaker button
  in the header is pressed; names without a file use a built-in chiptune blip.
- Chat bubble tails and borders are drawn in CSS (so they follow the day/night theme), not PNGs.

## Every sprite

The generator rewrites this table from the manifest.

<!-- sprite-table:start -->
| id | file | frame size | frames | fps | where it appears |
|---|---|---|---|---|---|
| `sloth_idle` | `sprites/sloth/sloth_idle.png` | 32x32 | 4 | 2 | Professor's desk while waiting |
| `sloth_sleep` | `sprites/sloth/sloth_sleep.png` | 32x32 | 2 | 1 | Professor's desk when nothing is happening (with zzz) |
| `sloth_talk` | `sprites/sloth/sloth_talk.png` | 32x32 | 3 | 6 | Professor's desk while a sloth chat message arrives |
| `sloth_happy` | `sprites/sloth/sloth_happy.png` | 32x32 | 2 | 3 | Professor's desk when health score > 80 |
| `sloth_grumpy` | `sprites/sloth/sloth_grumpy.png` | 32x32 | 2 | 4 | Professor's desk when health score < 40 |
| `detective_idle` | `sprites/cats/detective_idle.png` | 32x32 | 4 | 3 | cat desk before / between jobs |
| `detective_work` | `sprites/cats/detective_work.png` | 32x32 | 4 | 8 | cat desk while its progress bar fills |
| `detective_done` | `sprites/cats/detective_done.png` | 32x32 | 2 | 3 | cat desk after its results arrive |
| `detective_error` | `sprites/cats/detective_error.png` | 32x32 | 2 | 3 | cat desk when the cat reports an error |
| `artist_idle` | `sprites/cats/artist_idle.png` | 32x32 | 4 | 3 | cat desk before / between jobs |
| `artist_work` | `sprites/cats/artist_work.png` | 32x32 | 4 | 8 | cat desk while its progress bar fills |
| `artist_done` | `sprites/cats/artist_done.png` | 32x32 | 2 | 3 | cat desk after its results arrive |
| `artist_error` | `sprites/cats/artist_error.png` | 32x32 | 2 | 3 | cat desk when the cat reports an error |
| `scribe_idle` | `sprites/cats/scribe_idle.png` | 32x32 | 4 | 3 | cat desk before / between jobs |
| `scribe_work` | `sprites/cats/scribe_work.png` | 32x32 | 4 | 8 | cat desk while its progress bar fills |
| `scribe_done` | `sprites/cats/scribe_done.png` | 32x32 | 2 | 3 | cat desk after its results arrive |
| `scribe_error` | `sprites/cats/scribe_error.png` | 32x32 | 2 | 3 | cat desk when the cat reports an error |
| `coder_idle` | `sprites/cats/coder_idle.png` | 32x32 | 4 | 3 | cat desk before / between jobs |
| `coder_work` | `sprites/cats/coder_work.png` | 32x32 | 4 | 8 | cat desk while its progress bar fills |
| `coder_done` | `sprites/cats/coder_done.png` | 32x32 | 2 | 3 | cat desk after its results arrive |
| `coder_error` | `sprites/cats/coder_error.png` | 32x32 | 2 | 3 | cat desk when the cat reports an error |
| `janitor_idle` | `sprites/cats/janitor_idle.png` | 32x32 | 4 | 3 | cat desk before / between jobs |
| `janitor_work` | `sprites/cats/janitor_work.png` | 32x32 | 4 | 8 | cat desk while its progress bar fills |
| `janitor_done` | `sprites/cats/janitor_done.png` | 32x32 | 2 | 3 | cat desk after its results arrive |
| `janitor_error` | `sprites/cats/janitor_error.png` | 32x32 | 2 | 3 | cat desk when the cat reports an error |
| `paper` | `sprites/props/paper.png` | 16x16 | 2 | 6 | papers flying sloth -> cats, and the piles on each desk |
| `paper_stack` | `sprites/props/paper_stack.png` | 24x24 | 1 | 1 | the big pile on the professor's desk |
| `desk` | `sprites/props/desk.png` | 48x24 | 1 | 1 | in front of each cat |
| `desk_sloth` | `sprites/props/desk_sloth.png` | 64x24 | 1 | 1 | in front of the professor |
| `branch` | `sprites/props/branch.png` | 64x16 | 2 | 1 | decoration above the professor |
| `zzz` | `sprites/props/zzz.png` | 16x16 | 3 | 2 | above the sloth while sleeping |
| `progress_cat_run` | `sprites/props/progress_cat_run.png` | 16x16 | 4 | 10 | runs along each progress bar |
| `progress_cat_sit` | `sprites/props/progress_cat_sit.png` | 16x16 | 2 | 2 | sits at the end of a finished progress bar (with check icon) |
| `avatar_sloth` | `avatars/sloth.png` | 48x48 | 1 | 1 | chat bubbles and the results drawer header; chat header |
| `avatar_detective` | `avatars/detective.png` | 48x48 | 1 | 1 | chat bubbles and the results drawer header |
| `avatar_artist` | `avatars/artist.png` | 48x48 | 1 | 1 | chat bubbles and the results drawer header |
| `avatar_scribe` | `avatars/scribe.png` | 48x48 | 1 | 1 | chat bubbles and the results drawer header |
| `avatar_coder` | `avatars/coder.png` | 48x48 | 1 | 1 | chat bubbles and the results drawer header |
| `avatar_janitor` | `avatars/janitor.png` | 48x48 | 1 | 1 | chat bubbles and the results drawer header |
| `avatar_user` | `avatars/user.png` | 48x48 | 1 | 1 | your chat bubbles |
| `icon_send` | `ui/icon_send.png` | 16x16 | 1 | 1 | chat send button |
| `icon_paperclip` | `ui/icon_paperclip.png` | 16x16 | 1 | 1 | chat attach button |
| `icon_upload` | `ui/icon_upload.png` | 16x16 | 1 | 1 | drop zone |
| `icon_download` | `ui/icon_download.png` | 16x16 | 1 | 1 | download buttons |
| `icon_copy` | `ui/icon_copy.png` | 16x16 | 1 | 1 | copy code button |
| `icon_check` | `ui/icon_check.png` | 16x16 | 1 | 1 | finished progress bars, copied |
| `icon_warning` | `ui/icon_warning.png` | 16x16 | 1 | 1 | error states, warnings in cards |
| `icon_file` | `ui/icon_file.png` | 16x16 | 1 | 1 | uploaded file bubble |
| `icon_gear` | `ui/icon_gear.png` | 16x16 | 1 | 1 | settings button |
| `icon_close` | `ui/icon_close.png` | 16x16 | 1 | 1 | close drawer / dialogs |
| `icon_chevron` | `ui/icon_chevron.png` | 16x16 | 1 | 1 | accordion cards |
| `icon_moon` | `ui/icon_moon.png` | 16x16 | 1 | 1 | night mode toggle |
| `icon_sun` | `ui/icon_sun.png` | 16x16 | 1 | 1 | day mode toggle |
| `icon_sound_on` | `ui/icon_sound_on.png` | 16x16 | 1 | 1 | sound toggle |
| `icon_sound_off` | `ui/icon_sound_off.png` | 16x16 | 1 | 1 | sound toggle (muted) |
| `icon_magnifier` | `ui/icon_magnifier.png` | 16x16 | 1 | 1 | Detective Cat chat messages |
| `icon_brush` | `ui/icon_brush.png` | 16x16 | 1 | 1 | Artist Cat chat messages |
| `icon_quill` | `ui/icon_quill.png` | 16x16 | 1 | 1 | Scribe Cat chat messages |
| `icon_laptop` | `ui/icon_laptop.png` | 16x16 | 1 | 1 | Coder Cat chat messages |
| `icon_broom` | `ui/icon_broom.png` | 16x16 | 1 | 1 | Janitor Cat chat messages |
<!-- sprite-table:end -->

## Known issues

### High-detail icons are unreadable at normal size (logged 2026-10-23, not fixed)

**Seen:** icons redrawn at 32x32, 48x48 or 64x64 look sharp when zoomed in,
but at normal size the details merge and it's hard to tell which icon is which.

**Why:** icons show at 16-32 px on screen (`icon(name, { scale: 1 | 2 })` in
`static/js/*.js`, 1x-2x in the table above). A 64x64 drawing in a 16 px slot is
shrunk 4x, and `image-rendering: pixelated` (`static/css/sprites.css`) keeps
only one source pixel out of every 16. Thin lines and small details drop out
or turn into noise. This is a mismatch between the drawing size and the display
size, not a rendering bug: smoother scaling would only blur the details.

**Options (pick one before redrawing):**
1. Draw icons at the size they are shown: 16x16, with a bold silhouette and
   at most 2-3 colours. This matches the current manifest and needs no code change.
2. Show icons bigger: draw at 32x32, set `frameWidth`/`frameHeight` to 32 in
   `manifest.json`, and lower every `icon(..., { scale })` so slots don't double
   (buttons are about 40 px, so 32 px icons fit at 1x).
3. Keep detailed 64x64 masters for print or marketing, and hand-export a
   simplified 16x16 (or 32x32) copy for the app. Don't auto-downscale it.

Whichever you pick, check readability at 100% browser zoom from about an
arm's length away, not zoomed in.
