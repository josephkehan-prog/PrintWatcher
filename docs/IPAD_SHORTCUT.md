# iPad Shortcut: one-tap interactive printing

The desktop UI is great when you're at the Windows machine, but the iPad share
sheet is the only thing you have on the move. This guide walks through building
three Apple Shortcuts that turn the share sheet into a real interactive
print dialog:

- **Quick Print** — pick a destination preset folder, save. Two taps.
- **Custom Print** — prompts for copies, sides, color, and (optionally)
  submitter, then builds the path automatically. Roughly five taps.
- **Schedule Print** — share PDF → pick a release time → file holds in
  `_scheduled/` until that moment, then prints. Three taps.

All three rely on the watcher's existing path-options convention
(`PrintInbox/Submitter__opts/file__opts.pdf`). Nothing new on the Windows side
beyond the helper scripts in `scripts/` (already shipped).

## Prerequisites

- Apple Shortcuts app (built into iOS/iPadOS — install from the App Store if
  you removed it).
- OneDrive app installed and signed in to the same account that syncs
  `PrintInbox` to your Windows machine.
- Run these two commands once on Windows so the supporting infrastructure
  exists:

  ```powershell
  python scripts\setup_inbox_presets.py     # creates __copies=30, __duplex, etc.
  python scripts\schedule_print.py --daemon # release loop for "Schedule Print"
  ```

  Drop the daemon into your Startup folder (the same way you wired up the
  main watcher) so it survives reboots.

## Recipe A — Quick Print (no prompts)

Three Shortcuts actions. Adds a one-tap entry to the share sheet that just
asks "which preset?" and saves.

1. Open **Shortcuts** → **+** → **New Shortcut**.
2. Tap the shortcut name at the top → rename to **Print** → **Done**.
3. Tap the **(i)** button → **Show in Share Sheet** → **on**.
4. Under "Share Sheet Types", deselect everything except **Files** and
   **Images**. **Done**.
5. Add action **Choose from List**:
   - List items, one per line:
     ```
     30 copies | __copies=30
     15 copies | __copies=15
     Duplex    | __duplex
     Mono      | __mono
     Draft     | __duplex_mono
     Class set | __copies=30_duplex
     ```
   - Toggle on **Allow Multiple Selection**: off.
   - Prompt: `Print as…`
6. Add action **Get Text from Input** (under Text). This isolates the part of
   the menu line *after* `|`. To do that, tap **Match Text** → set "Match"
   to a regex `(?<=\| ).+`, target the previous output. (If regex feels
   fiddly, you can simply use named menu items like `__copies=30` directly
   and skip this step.)
7. Add action **Save File**:
   - Service: **iCloud Drive** (the dialog actually shows all File providers
     including OneDrive)
   - Destination path: `OneDrive\Apps\…\PrintInbox\<value-from-step-6>` —
     pick **Ask Each Time** the first run, navigate to your inbox, then
     into the chosen preset folder. After that the path is remembered.
   - **File Name**: keep `Shortcut Input` (the original PDF name).
   - **Overwrite if exists**: off.

Now: select any PDF on iPad → Share → tap **Print** → pick preset → done.

## Recipe B — Custom Print (full prompts)

Six prompts; outputs a path like
`OneDrive/PrintInbox/MaryDoe__copies=30_duplex/quiz.pdf`. About a minute to
run end-to-end on iPad, but still faster than typing the filename manually.

Build steps:

1. **New Shortcut** → name it **Custom Print** → enable **Show in Share
   Sheet** for Files + Images.
2. **Ask for Input** (Number) — Prompt: `How many copies?` Default: `1`.
   Variable: `Copies`.
3. **Choose from List** (single select) — Prompt: `Sides?` Items:
   ```
   default
   single
   duplex
   short
   ```
   Variable: `Sides`.
4. **Choose from List** — Prompt: `Color?` Items:
   ```
   default
   color
   mono
   ```
   Variable: `Color`.
5. **Ask for Input** (Text) — Prompt: `Submitter? (leave empty for your
   own user)` Default: empty. Variable: `Submitter`.
6. **Text** — build the options block:
   ```
   __copies=[Copies]_[Sides]_[Color]
   ```
   When Sides or Color is `default`, leave it out by chaining **Replace
   Text** actions afterward to strip `_default`.
   Variable: `OptsBlock`.
7. **If** action: `Submitter is not empty` →
   - **Text**: `[Submitter]/`
   - In **Otherwise**: empty text.
   - End **If**. Variable: `SubmitterPrefix`.
8. **Get Name of File** (input from share sheet). Variable: `OriginalName`.
9. **Text** — build the destination subpath:
   ```
   [SubmitterPrefix][OriginalName-no-extension][OptsBlock].pdf
   ```
   Use **Get Variable** + **Match Text** with a regex `(.+?)\.[^.]+$` to
   strip the original extension before re-adding `.pdf`.
10. **Save File**: target `OneDrive/PrintInbox/`, **File Name** = output
    of step 9, **Overwrite if exists** off, **Ask Where to Save** off.

Now: select PDF → Share → **Custom Print** → answer prompts → Saved.
Watcher detects the file, applies path overrides, prints, logs the
submitter.

## Recipe C — Schedule Print (release at a specific time)

Send a PDF to the inbox *now* but have it sit in `_scheduled/` until a
chosen time. Useful when you want a class set ready on the printer at 7:55 AM
without sprinting to the workroom in the morning, or when the printer is
busy and you'd rather defer a long packet to lunchtime.

The Windows-side `schedule_print.py --daemon` watches `_scheduled/` and
moves files into the main inbox when their `YYYY-MM-DDTHH-MM__` filename
prefix is reached. This Shortcut does the iPad half: prompts for a time,
formats it, prepends to the filename, saves to `_scheduled/`.

Build steps:

1. **New Shortcut** → name it **Schedule Print** → enable **Show in Share
   Sheet** for Files + Images.
2. **Date** action (under Date) — Get Current Date. Variable: `Now`.
3. **Adjust Date** — *Add `1` Hour to* `Now`. Variable: `DefaultWhen`.
   (Used as the picker's default — one hour from now.)
4. **Get Date from Input** action — Prompt: `Print at?` Default Date:
   `DefaultWhen`. Style: **Date and Time**. Variable: `When`.
5. **Format Date** — Date: `When`. Format: **Custom**.
   - Format String: `yyyy-MM-dd'T'HH-mm`
   - Variable: `Stamp` (produces e.g. `2026-04-30T07-55`).
6. **Get Name of File** (the share-sheet input). Variable: `OriginalName`.
7. **Text** — build the destination filename:
   ```
   [Stamp]__[OriginalName]
   ```
   Variable: `ScheduledName`.
8. **Save File** — target `OneDrive/PrintInbox/_scheduled/`. **File Name** =
   `ScheduledName`. **Overwrite if exists** off, **Ask Where to Save** off.

Now: select PDF → Share → **Schedule Print** → pick a date/time → Saved.

The Windows daemon polls every 30 s; when the prefix time arrives it strips
the prefix and moves the file into the inbox root, where the main watcher
picks it up and prints with whatever options the desktop UI is currently set
to.

### Combining Schedule with options

Want "30 copies, duplex, at 7:55 AM"? Edit step 7 to also append the options
suffix you'd use in Recipe A or B:

```
[Stamp]__[OriginalName-no-extension]__copies=30_duplex.pdf
```

The watcher parses both the `_scheduled` filename prefix (handled by the
daemon) and the `__opts` suffix (handled by the watcher itself), so they
compose cleanly. Verify on Windows with:

```powershell
python scripts\preview_shortcut_path.py --copies 30 --sides duplex --filename "2026-04-30T07-55__quiz.pdf"
```

### Cancel or list scheduled files from Windows

```powershell
python scripts\schedule_print.py --list             # show what's queued
python scripts\schedule_print.py --cancel quiz      # cancel anything matching "quiz"
```

There is no iPad-side cancel; deleting the file from the OneDrive Files app
in `_scheduled/` works equally well.

## Adding the shortcut to the iPad Home Screen

Both Shortcuts can be added as a Home Screen icon:

1. Shortcuts app → long-press the shortcut → **Share** → **Add to Home Screen**
2. Optionally rename the icon to **Print 30** / **Print Duplex** etc.

Tapping the icon runs the shortcut on whatever file you most recently
selected — combined with iPadOS multitasking, that's *one tap* from
Files app.

## Verifying the output filename

Run on your Windows machine:

```powershell
python scripts/preview_shortcut_path.py --copies 30 --sides duplex --color mono --submitter MaryDoe --filename "quiz.pdf"
```

That prints what the resulting OneDrive path will be, so you can compare
against what your Shortcut actually generates. (Script lives at
`scripts/preview_shortcut_path.py`.)

## Tools running quietly behind the scenes

Several `scripts/*.py` helpers improve the iPad experience without you
having to think about them. Run each once or wire to your Startup folder
once, then forget.

| Helper | What it fixes for iPad users |
|---|---|
| `scripts/dedupe_inbox.py --apply` | iPad share sheet sometimes saves a file twice on a flaky cellular connection. Run this on a daily Task Scheduler job (or before a class set) and accidental duplicates move to `_skipped/` instead of double-printing 60 sheets. |
| `scripts/schedule_print.py --daemon` | Powers the Schedule Print Shortcut above. Without the daemon, files saved to `_scheduled/` will never release. |
| `scripts/cleanup_printed.py` *(if you've added it)* | Sweeps old `_printed/<submitter>/` files so OneDrive doesn't bloat — relevant because every iPad-shared PDF lives there forever otherwise. |
| `scripts/pdf_inspect.py` | Run on the Windows side before triggering a giant iPad-shared packet: confirms page count, detects unusually large files. |
| `scripts/clear_queue.py` | When a Printix job gets stuck and a re-share from iPad keeps "not printing", clear the queue once and re-share. Saves the trip to Windows Settings. |
| `scripts/web_to_pdf.py` | If you can't share a webpage from Safari on iPad (e.g. it's a paywall or Edge-only resource), render it from Windows and drop in inbox; no iPad work required. |

## Common Shortcut gotchas

| Symptom | Cause / fix |
|---|---|
| File saves but nothing prints | Saved into the wrong OneDrive account or outside `PrintInbox`. Run **Save File** with **Ask Each Time** once and navigate manually so the path is remembered. |
| Shortcut errors with "no input" | Share sheet sent text/URL instead of a file. Ensure step 1 enables Files + Images and not URLs. |
| Filename doubles up `.pdf.pdf` | Step 9 didn't strip the extension. Add a **Match Text** action before re-adding `.pdf`. |
| Submitter shows as `local` in History | Submitter prompt was left empty — that's fine, expected. |
| Preset folder unknown when typed | Spelling differs from what `setup_inbox_presets.py` created. Run `python scripts/setup_inbox_presets.py --list` to confirm. |
| Schedule Print file never releases | `schedule_print.py --daemon` isn't running on the Windows side. Restart it from Startup or PowerShell. `python scripts\schedule_print.py --list` confirms what's queued. |
| Same iPad share creates two prints | Cellular flake duplicated the OneDrive write. `python scripts\dedupe_inbox.py` will catch it; `--apply` moves the duplicate aside before it prints. |

## What this gives you

- Real iPad UI for per-job options without ever editing a filename.
- Submitter attribution from the iPad (matters when several staff share
  the same OneDrive inbox).
- Time-scheduled printing — set 7:55 AM from the iPad the night before.
- Same path-options grammar the desktop UI already understands — no
  watcher changes.
- Home Screen tile for one-tap repeat workflows.
