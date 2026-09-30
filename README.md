# Image Set Generator

Generate a ZIP of cropped, normalized portrait images for any TV show cast.
Built on top of TVmaze (no API key) and Wikimedia Commons (free images, license metadata included).

---

## Quick start

```bash
pip install -r requirements.txt
pip install -e .          # installs imgset and imgset-gui commands
```

### GUI

```bash
imgset-gui
```

### CLI

```bash
imgset "Breaking Bad"
imgset "Breaking Bad" --limit 15
imgset "Breaking Bad" --all-cast
imgset "Breaking Bad" --no-confirm
imgset "Breaking Bad" --size 256 --format png --output ~/Desktop/
```

---

## Output

Running either interface produces a ZIP in `sets/`:

```
sets/
  Breaking Bad.zip
    ├── Walter White.jpg
    ├── Jesse Pinkman.jpg
    ├── ...
    └── SOURCES.txt
```

Images are cropped/centered to a square (default 512 × 512 px).
`SOURCES.txt` contains the image URL, author, and license for each entry.

---

## How images are sourced

1. **Wikimedia Commons** — searched first. Returns license + attribution metadata, making it safe for open-source use.
2. **TVmaze cast photo** — fallback when Commons has nothing suitable. Not automatically freely licensed; flagged in `SOURCES.txt`.

---

## Architecture

```
imageset_generator/
├── config.py        # constants and paths
├── core.py          # download, crop, ZIP — UI-agnostic
├── cli.py           # argparse CLI (`imgset`)
├── gui.py           # CustomTkinter desktop app (`imgset-gui`)
└── providers/
    ├── tvmaze.py    # TV show search + cast fetch
    └── commons.py   # Wikimedia Commons image search
```

### Adding a new provider

A provider only needs two functions:

```python
def search(query: str) -> list[dict]:
    # Returns: [{id, name, year, genres, image_url}, ...]

def fetch_entries(topic_id, limit=None) -> list[dict]:
    # Returns: [{label, person, person_id, fallback_img}, ...]
```

Feed the returned entries into `core.build_set()` and you're done.

---

## Configuration

| CLI flag | GUI setting | Default |
|---|---|---|
| `--limit N` | Max entries | 20 |
| `--size N` | Image size | 512 |
| `--format jpeg\|png` | Image format | JPEG |
| `--output DIR` | Output folder | `./sets/` |
| `--all-cast` | — | False |
| `--no-confirm` | — | False |

---

## Notes

- Downloaded images are cached in `cache/<show>/` — rerunning a set is fast.
- Check `SOURCES.txt` before redistributing any pack publicly.
