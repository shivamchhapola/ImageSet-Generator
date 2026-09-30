"""
CLI entrypoint — `imgset` command.

Usage:
    imgset "Breaking Bad"
    imgset "Breaking Bad" --limit 15
    imgset "Breaking Bad" --all-cast
    imgset "Breaking Bad" --no-confirm
    imgset "Breaking Bad" --size 256
    imgset "Breaking Bad" --format png
    imgset "Breaking Bad" --output ~/Desktop/
"""

from __future__ import annotations

import argparse

from imageset_generator import __version__
from imageset_generator.config import DEFAULT_IMAGE_SIZE, DEFAULT_LIMIT
from imageset_generator.core import build_set, clean_filename
from imageset_generator.providers import tvmaze


# ── Helpers ───────────────────────────────────────────────────────────────────

def _choose_show(query: str) -> dict:
    results = tvmaze.search(query)
    if not results:
        raise SystemExit(f'No TV show found matching "{query}".')

    print("\nMatches:")
    for i, show in enumerate(results, 1):
        year = f" ({show['year']})" if show["year"] else ""
        genres = f" — {', '.join(show['genres'])}" if show["genres"] else ""
        print(f"  {i}. {show['name']}{year}{genres}")

    if len(results) == 1:
        print(f"\nUsing: {results[0]['name']}")
        return results[0]

    raw = input("\nChoose a number [1]: ").strip()
    if not raw:
        return results[0]
    try:
        return results[int(raw) - 1]
    except (ValueError, IndexError):
        raise SystemExit("Invalid selection.")


def _edit_entries(entries: list[dict]) -> list[dict]:
    print("\nEntries found:")
    for i, e in enumerate(entries, 1):
        print(f"  {i:2}. {e['label']}  [{e['person']}]")

    print(
        "\nPress Enter to use this list.\n"
        "Or type numbers to remove, e.g. 3,7,11\n"
        "Or type labels separated by | to replace the list."
    )
    raw = input("> ").strip()

    if not raw:
        return entries

    if "|" in raw:
        names = [clean_filename(x) for x in raw.split("|") if clean_filename(x)]
        lookup = {e["label"].casefold(): e for e in entries}
        return [
            lookup.get(name.casefold(), {
                "label": name, "person": name,
                "person_id": None, "fallback_img": None,
            })
            for name in names
        ]

    try:
        remove = {int(x.strip()) for x in raw.split(",") if x.strip()}
        return [e for i, e in enumerate(entries, 1) if i not in remove]
    except ValueError:
        print("Couldn't parse that. Keeping the original list.")
        return entries


def _progress(current: int, total: int, label: str, status: str) -> None:
    tag = {
        "cached":      "CACHED",
        "ok":          "OK",
        "no_image":    "NO IMAGE",
        "downloading": "...",
    }.get(status, status.upper())

    pad = len(str(total))
    print(f"  [{current:{pad}}/{total}] {label:<40} {tag}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="imgset",
        description="Generate a ZIP of portrait images from a TV show cast.",
    )
    parser.add_argument(
        "show", nargs="?",
        help='Show name, e.g. "Breaking Bad"',
    )
    parser.add_argument(
        "--limit", type=int, default=DEFAULT_LIMIT,
        help=f"Max characters to include (default: {DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--all-cast", action="store_true",
        help="Use the full available cast (overrides --limit)",
    )
    parser.add_argument(
        "--no-confirm", action="store_true",
        help="Skip the entry-list confirmation step",
    )
    parser.add_argument(
        "--size", type=int, default=DEFAULT_IMAGE_SIZE[0],
        help=f"Output image size in pixels (default: {DEFAULT_IMAGE_SIZE[0]})",
    )
    parser.add_argument(
        "--format", choices=["jpeg", "png"], default="jpeg",
        dest="fmt",
        help="Output image format (default: jpeg)",
    )
    parser.add_argument(
        "--output", default=None,
        help="Directory to write the ZIP into (default: ./sets/)",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}",
    )
    args = parser.parse_args(argv)

    query = args.show or input("Show name: ").strip()
    if not query:
        parser.error("No show name supplied.")

    show = _choose_show(query)
    limit = None if args.all_cast else args.limit
    entries = tvmaze.fetch_entries(show["id"], limit=limit)

    if not entries:
        raise SystemExit("The show has no usable cast/character data.")

    if not args.no_confirm:
        entries = _edit_entries(entries)

    if not entries:
        raise SystemExit("Entry list is empty.")

    print(f"\nBuilding {len(entries)} entries for '{show['name']}'...\n")

    from pathlib import Path
    output_dir = Path(args.output) if args.output else None
    size = (args.size, args.size)

    zip_path = build_set(
        show["name"],
        entries,
        image_size=size,
        image_format=args.fmt.upper(),
        output_dir=output_dir,
        on_progress=_progress,
    )

    print(f"\n[OK] Created: {zip_path}")


if __name__ == "__main__":
    main()
