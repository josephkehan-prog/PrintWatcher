# iPad — Quick reference

Everything you can do from the iPad share sheet, on one page. For the
full step-by-step Shortcut build instructions, see
[IPAD_SHORTCUT.md](IPAD_SHORTCUT.md).

## TL;DR — three ways to print from iPad

| Method | What you tap | When to use |
|---|---|---|
| **Save into a preset folder** | Share → Save to Files → `OneDrive/PrintInbox/__copies=30/` | Fast, no typing. Pick a pre-made folder. |
| **Rename with options** | Share → Save to Files → tap **Edit** → add `__copies=30` before `.pdf` | Per-job options without committing to a preset. |
| **Run a Shortcut** | Share → **Print** / **Custom Print** / **Schedule Print** | One-tap workflows with prompts. |

## Filename / folder grammar

Append `__opt1_opt2…` to a filename **or** to a folder name. Tokens
separated by `_`, `,`, or whitespace. Filename overrides folder.

| Token | Effect |
|---|---|
| `copies=N` (or `n=N`, `x=N`) | 1–99 copies |
| `duplex` / `long` | Duplex, long edge |
| `duplexshort` / `short` | Duplex, short edge |
| `simplex` / `single` | Force single-sided |
| `color` | Color print |
| `mono` / `bw` | Monochrome |

Out-of-range or unknown tokens are silently ignored. Printer choice
can't be encoded — set it once in the desktop UI.

## Path patterns

```
PrintInbox/quiz.pdf                        → defaults from desktop UI
PrintInbox/quiz__copies=30.pdf             → 30 copies
PrintInbox/__copies=30/quiz.pdf            → 30 copies (preset folder)
PrintInbox/MaryDoe/quiz.pdf                → submitter MaryDoe
PrintInbox/MaryDoe__duplex/quiz.pdf        → submitter + duplex
PrintInbox/Class3__copies=30_duplex/q.pdf  → submitter + 30 + duplex
PrintInbox/MaryDoe/__copies=30/quiz.pdf    → submitter + 30 (nested)
PrintInbox/MaryDoe__duplex/quiz__copies=2.pdf → file overrides folder
```

## Suggested preset folders

Run on the Windows side once:

```powershell
python scripts\setup_inbox_presets.py
```

Creates: `__copies=30 · __copies=15 · __duplex · __mono · __duplex_mono · __copies=30_duplex`.

Add custom presets:

```powershell
python scripts\setup_inbox_presets.py __color __copies=5_duplex
```

## Apple Shortcuts cheat sheet

| Shortcut | Taps to use | What you get |
|---|---|---|
| **Quick Print** | Share → Print → pick from menu | One menu prompt → save to chosen preset folder |
| **Custom Print** | Share → Custom Print → answer 4 prompts | Asks copies / sides / color / submitter, builds the path |
| **Schedule Print** | Share → Schedule Print → date-time picker | Holds in `_scheduled/` until release time (needs `schedule_print.py --daemon` running on Windows) |

Build instructions: [IPAD_SHORTCUT.md](IPAD_SHORTCUT.md). Add any
shortcut to Home Screen via long-press → Share → Add to Home Screen.

## Verifying what you saved

On the Windows side, before trusting a Shortcut with a class set:

```powershell
python scripts\preview_shortcut_path.py --copies 30 --sides duplex \
    --submitter MaryDoe --filename quiz.pdf
```

Prints the exact OneDrive path your Shortcut should land at and the
options PrintWatcher will apply.

## Common iPad-side gotchas

| Symptom | Likely cause | Fix |
|---|---|---|
| Saved but didn't print | Wrong OneDrive account or outside `PrintInbox` | In Save File, **Ask Each Time** once and navigate manually |
| `.pdf.pdf` filename | Shortcut didn't strip the original extension | Add a Match Text action with regex `(.+?)\.[^.]+$` before re-adding `.pdf` |
| Submitter shows `local` | Submitter prompt left empty | Expected; print attributes to current Windows user |
| Same iPad share, two prints | Cellular flake duplicated the OneDrive write | `python scripts\dedupe_inbox.py --apply` catches it |
| Schedule never releases | `schedule_print.py --daemon` not running on Windows | Start it (or wire to Startup folder) |
| Preset folder typo silently uses defaults | `__` typo or unknown token | `python scripts\setup_inbox_presets.py --list` to confirm |

## Background tools (Windows side, run once or daemonised)

These quietly improve the iPad workflow:

| Helper | Effect |
|---|---|
| `dedupe_inbox.py --apply` | Removes accidental duplicate iPad shares |
| `schedule_print.py --daemon` | Releases `_scheduled/` files on time |
| `auto_merge.py` | Drop several PDFs in `__merge/`, get one packet |
| `cleanup_printed.py --apply` | Sweeps old `_printed/` files to `_archive/<YYYY-MM>/` |

## Quickest one-tap iPad recipes

**30 copies of any PDF for the class:**
1. Share → Save to Files → `PrintInbox/__copies=30/` → Save.

**Print as duplex monochrome (draft-friendly):**
1. Share → Save to Files → `PrintInbox/__duplex_mono/` → Save.

**Specific scholar's worksheet:**
1. Share → Save to Files → `PrintInbox/MaryDoe/` → Save.
   (Make MaryDoe folders first via `roster.py folders <Class> --prefix`.)

**Hold a print until 7:55 AM tomorrow:**
1. Share → **Schedule Print** Shortcut → pick 7:55 AM → Save.
   (Daemon releases it at 7:55, watcher prints immediately.)
