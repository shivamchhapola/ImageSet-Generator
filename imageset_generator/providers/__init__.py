"""
Providers package — pluggable data sources for cast/character discovery.

Each provider must expose:
    search(query: str) -> list[dict]          # returns show/topic candidates
    fetch_entries(show_id) -> list[Entry]     # returns list of Entry dicts

An Entry is:
    {
        "label":        str,   # display name (character name, person name, etc.)
        "person":       str,   # real-world name used for image lookup
        "person_id":    Any,   # provider-specific ID (may be None)
        "fallback_img": str|None,  # direct image URL as last resort
    }
"""
