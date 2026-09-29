#!/usr/bin/env python3
"""
GuessWho automatic set generator.

Examples:
    python make_set.py "The Boys"
    python make_set.py "Breaking Bad" --limit 15
    python make_set.py "Friends" --all-cast
    python make_set.py "Naruto" --limit 25
    python make_set.py "The Office" --no-confirm

Default workflow:
    1. Find the TV show using TVmaze (no API key).
    2. Fetch its cast and character names.
    3. Prefer Wikimedia Commons images of the actor/person.
    4. Fall back to the TVmaze cast image when Commons has no usable photo.
    5. Ask you to confirm/edit the character list.
    6. Crop images to a consistent square.
    7. Write <Show>.zip with files named <Character>.jpg.

The generated ZIP also contains SOURCES.txt.

This is designed for a private/open-source game. Image rights vary by source.
Wikimedia Commons files carry their own license metadata; TVmaze images are
not automatically freely licensed. Check SOURCES.txt before redistributing
a generated pack publicly.
"""

import argparse
import html
import io
import re
import sys
import time
import zipfile
from pathlib import Path

import requests
from PIL import Image, ImageOps

TVMAZE = "https://api.tvmaze.com"
COMMONS = "https://commons.wikimedia.org/w/api.php"
HEADERS = {
    "User-Agent": "GuessWhoSetGenerator/1.0 (personal open-source project)"
}
IMAGE_SIZE = (512, 512)
TIMEOUT = 30

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "cache"
OUTPUT = ROOT / "sets"


def clean_name(s: str) -> str:
    s = html.unescape(s or "").strip()
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", s)
    s = re.sub(r"\s+", " ", s)
    return s.rstrip(". ")


def get_json(url, params=None):
    r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def choose_show(query):
    results = get_json(f"{TVMAZE}/search/shows", {"q": query})
    if not results:
        raise RuntimeError(f'Could not find a TV show matching "{query}".')

    print("\nMatches:")
    for i, item in enumerate(results[:10], 1):
        show = item["show"]
        year = (show.get("premiered") or "")[:4]
        genres = ", ".join(show.get("genres") or [])
        print(f"  {i}. {show['name']} {f'({year})' if year else ''}"
              f"{f' - {genres}' if genres else ''}")

    if len(results) == 1:
        print(f"\nUsing: {results[0]['show']['name']}")
        return results[0]["show"]

    raw = input("\nChoose a number [1]: ").strip()
    if not raw:
        return results[0]["show"]
    try:
        return results[int(raw) - 1]["show"]
    except (ValueError, IndexError):
        raise RuntimeError("Invalid selection.")


def fetch_cast(show_id):
    return get_json(f"{TVMAZE}/shows/{show_id}/cast")


def build_character_list(cast, limit=None, all_cast=False):
    seen = set()
    out = []

    for entry in cast:
        character = (entry.get("character") or {}).get("name")
        person = entry.get("person") or {}
        actor = person.get("name")

        if not character or not actor:
            continue

        # TVmaze cast order is generally useful, so retain it.
        key = character.casefold()
        if key in seen:
            continue
        seen.add(key)

        out.append({
            "character": character,
            "actor": actor,
            "actor_id": person.get("id"),
            "tvmaze_image": (person.get("image") or {}).get("original")
                               or (person.get("image") or {}).get("medium"),
        })

        if limit and len(out) >= limit:
            break

    return out


def edit_characters(chars):
    print("\nCharacters found:")
    for i, c in enumerate(chars, 1):
        print(f"  {i:2}. {c['character']}  [{c['actor']}]")

    print(
        "\nPress Enter to use this list.\n"
        "Or type numbers to remove, e.g. 3,7,11\n"
        "Or type names separated by | to replace the list."
    )
    raw = input("> ").strip()

    if not raw:
        return chars

    if "|" in raw:
        names = [clean_name(x) for x in raw.split("|") if clean_name(x)]
        lookup = {c["character"].casefold(): c for c in chars}
        result = []
        for name in names:
            result.append(
                lookup.get(name.casefold(), {
                    "character": name,
                    "actor": name,
                    "actor_id": None,
                    "tvmaze_image": None,
                })
            )
        return result

    try:
        remove = {int(x.strip()) for x in raw.split(",") if x.strip()}
        return [c for i, c in enumerate(chars, 1) if i not in remove]
    except ValueError:
        print("Couldn't parse that. Keeping the original list.")
        return chars


def commons_candidates(person_name):
    # Quoted exact-ish search first, then looser search.
    searches = [
        f'"{person_name}" portrait',
        f'"{person_name}"',
        person_name,
    ]

    results = []
    seen = set()

    for term in searches:
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": term,
            "gsrnamespace": 6,
            "gsrlimit": 8,
            "prop": "imageinfo",
            "iiprop": "url|extmetadata|mime",
            "iiurlwidth": 900,
            "format": "json",
        }
        try:
            data = get_json(COMMONS, params)
        except Exception:
            continue

        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            title = page.get("title", "")
            info = (page.get("imageinfo") or [{}])[0]
            url = info.get("thumburl") or info.get("url")
            mime = info.get("mime", "")
            if not url or not mime.startswith("image/"):
                continue
            if title.casefold() in seen:
                continue

            bad = (
                "logo", "poster", "screenshot", "signature",
                "flag", "coat of arms", "icon", "collage"
            )
            if any(x in title.casefold() for x in bad):
                continue

            seen.add(title.casefold())
            results.append((title, url, info.get("extmetadata") or {}))

        if results:
            break

    return results


def html_value(meta, key, default="Unknown"):
    value = (meta.get(key) or {}).get("value")
    if not value:
        return default
    return re.sub(r"<[^>]+>", "", html.unescape(str(value))).strip()


def download_image(url):
    r = requests.get(url, headers=HEADERS, timeout=45)
    r.raise_for_status()
    image = Image.open(io.BytesIO(r.content)).convert("RGB")
    return ImageOps.fit(
        image,
        IMAGE_SIZE,
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.45),
    )


def get_image_for_person(actor, tvmaze_image):
    # Prefer Commons because it exposes license/author metadata.
    for title, url, meta in commons_candidates(actor):
        try:
            image = download_image(url)
            return image, {
                "provider": "Wikimedia Commons",
                "source": title,
                "url": f"https://commons.wikimedia.org/wiki/{title.replace(' ', '_')}",
                "author": html_value(meta, "Artist"),
                "license": html_value(meta, "LicenseShortName"),
                "license_url": html_value(meta, "LicenseUrl"),
            }
        except Exception:
            continue

    if tvmaze_image:
        try:
            image = download_image(tvmaze_image)
            return image, {
                "provider": "TVmaze",
                "source": "TVmaze person image",
                "url": tvmaze_image,
                "author": "See TVmaze source",
                "license": "Not assumed to be freely licensed",
                "license_url": "",
            }
        except Exception:
            pass

    return None, None


def write_set(show_name, chars):
    slug = clean_name(show_name)
    work = CACHE / slug
    work.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(exist_ok=True)

    sources = []
    successful = 0

    print("\nDownloading images...\n")

    for n, item in enumerate(chars, 1):
        character = clean_name(item["character"])
        actor = item["actor"]
        target = work / f"{character}.jpg"

        if target.exists():
            print(f"[{n}/{len(chars)}] cached: {character}")
            successful += 1
            continue

        print(f"[{n}/{len(chars)}] {character} <- {actor}", end=" ... ", flush=True)

        try:
            image, source = get_image_for_person(actor, item.get("tvmaze_image"))
        except Exception as exc:
            image, source = None, None
            print(f"error: {exc}")
            continue

        if image is None:
            print("NO IMAGE")
            continue

        image.save(target, "JPEG", quality=90, optimize=True)
        successful += 1

        sources.append(
            f"Character: {character}\n"
            f"Portrayed by: {actor}\n"
            f"Provider: {source['provider']}\n"
            f"Source: {source['source']}\n"
            f"URL: {source['url']}\n"
            f"Author: {source['author']}\n"
            f"License: {source['license']}\n"
            f"License URL: {source['license_url'] or 'See source page'}\n"
        )
        print("OK")
        time.sleep(0.25)

    if successful == 0:
        raise RuntimeError("No images could be downloaded.")

    zip_path = OUTPUT / f"{slug}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for image_file in sorted(work.glob("*.jpg")):
            z.write(image_file, image_file.name)

        source_text = (
            f"GuessWho set: {show_name}\n"
            f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Images: {successful}/{len(chars)}\n\n"
            + "\n\n".join(sources)
            + "\n\n"
            "IMPORTANT:\n"
            "Check each source/license before redistributing this ZIP publicly.\n"
            "Wikimedia Commons files may have different licenses and attribution\n"
            "requirements. TVmaze fallback images are not assumed to be freely\n"
            "licensed. This generator is intended for private/open-source game use.\n"
        )
        z.writestr("SOURCES.txt", source_text)

    print(f"\nCreated: {zip_path}")
    print(f"Images: {successful}/{len(chars)}")
    return zip_path


def main():
    parser = argparse.ArgumentParser(
        description="Create a GuessWho ZIP from a TV show name."
    )
    parser.add_argument("show", nargs="?", help='Show name, e.g. "The Boys"')
    parser.add_argument("--limit", type=int, default=20,
                        help="Maximum characters to include (default: 20)")
    parser.add_argument("--all-cast", action="store_true",
                        help="Use the full available TVmaze cast")
    parser.add_argument("--no-confirm", action="store_true",
                        help="Skip the character-list confirmation")
    args = parser.parse_args()

    query = args.show or input("Show name: ").strip()
    if not query:
        print("No show name supplied.")
        sys.exit(1)

    show = choose_show(query)
    cast = fetch_cast(show["id"])

    limit = None if args.all_cast else args.limit
    chars = build_character_list(cast, limit=limit)

    if not chars:
        raise RuntimeError("The show has no usable cast/character data.")

    if not args.no_confirm:
        chars = edit_characters(chars)

    if not chars:
        raise RuntimeError("Character list is empty.")

    print(f"\nBuilding {len(chars)} characters for {show['name']}...")
    write_set(show["name"], chars)


if __name__ == "__main__":
    main()
