# GuessWho Auto Set Generator

Type a show name and get a ready-to-upload ZIP.

## Quick start

```bash
pip install -r requirements.txt
python make_set.py "Breaking Bad"
```

Or interactive:

```bash
python make_set.py
```

Then type:

```text
The Boys
```

The script finds the show, lists characters, lets you remove/edit them, fetches
images, and creates:

```text
sets/
  The Boys.zip
```

The ZIP contains:

```text
Homelander.jpg
Billy Butcher.jpg
Hughie Campbell.jpg
...
SOURCES.txt
```

## Useful options

Limit to 15 characters:

```bash
python make_set.py "The Boys" --limit 15
```

Use the whole available cast:

```bash
python make_set.py "The Boys" --all-cast
```

Skip the confirmation step:

```bash
python make_set.py "Breaking Bad" --no-confirm
```

## How character discovery works

TVmaze is used to identify the show and retrieve its cast/character
relationships. It does not require an API key.

For images, the script tries Wikimedia Commons first. Commons' MediaWiki
Imageinfo API exposes image URLs and metadata such as author and license,
which is why it is preferable for an open-source project.

If Commons has no usable image, the script falls back to the cast member's
TVmaze image. That fallback is not automatically a freely licensed asset, so
the generated SOURCES.txt explicitly flags it.

## Adding non-TV sets

The architecture is deliberately simple. The next useful extension would be
a provider for:

- movies/franchises
- anime
- sports players
- celebrities
- video games

Those can feed the same `write_set()` function after producing:

```python
{
    "character": "Character Name",
    "actor": "Person Name",
    "tvmaze_image": "optional image URL"
}
```

## Notes

- Images are normalized to 512x512 JPEG.
- Existing downloaded images are cached in `cache/`, so rerunning a set is
  much faster.
- Generated ZIPs are placed in `sets/`.
- Check image licenses before public redistribution.
