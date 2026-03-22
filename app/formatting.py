import re
from datetime import datetime


def format_date_ru(date_str: str) -> str:
    """Convert dates to DD.MM.YYYY, MM.YYYY or YYYY."""
    try:
        if "T" in date_str:
            dt = datetime.fromisoformat(date_str)
            return dt.strftime("%d.%m.%Y")
        if len(date_str) == 10:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            return dt.strftime("%d.%m.%Y")
        if len(date_str) == 7:
            dt = datetime.strptime(date_str, "%Y-%m")
            return dt.strftime("%m.%Y")
        if len(date_str) == 4:
            return date_str
    except Exception:
        pass
    return date_str


def get_meta_content(soup, *, property_name: str | None = None, name: str | None = None):
    attrs = {}
    if property_name:
        attrs["property"] = property_name
    if name:
        attrs["name"] = name

    tag = soup.find("meta", attrs=attrs)
    if not tag:
        return None
    return tag.get("content") or None


def build_track_payload(
    *,
    artist: str,
    track: str,
    album: str,
    image: str | None,
    label: str,
    release_date: str,
    source: str,
    source_url: str,
):
    return {
        "artist": artist or "Unknown Artist",
        "track": track or "Unknown Track",
        "album": album or "Unknown Album",
        "image": image,
        "label": label or source,
        "release_date": release_date or "Unknown Date",
        "source": source,
        "source_url": source_url,
    }


def normalize_text(value: str) -> str:
    normalized = (value or "").lower().replace("ё", "е")
    normalized = re.sub(r"\b(feat|featuring|ft)\b", " ", normalized)
    normalized = re.sub(r"[^a-z0-9а-я]+", " ", normalized)
    return " ".join(normalized.split())


def tokenize_text(value: str) -> set[str]:
    return set(normalize_text(value).split())


def is_suspicious_yandex_label(label: str) -> bool:
    normalized = normalize_text(label)
    suspicious_parts = {
        "креатив",
        "creative",
        "distribution",
        "distro",
        "aggregator",
        "freshtunes",
        "fresh tunes",
        "one rpm",
        "onerpm",
        "believe",
        "orchard",
        "symphonic",
        "tunecore",
    }
    return any(part in normalized for part in suspicious_parts)


def should_show_label(source: str, label: str) -> bool:
    if not label:
        return False
    if source == "apple_music" and label == "Apple Music":
        return False
    if source != "yandex_music":
        return True
    return label != "Яндекс.Музыка" and not is_suspicious_yandex_label(label)


def build_caption(
    artist: str,
    track: str,
    album: str,
    release_date: str,
    label: str,
    source: str,
) -> str:
    lines = [
        f"`{artist} — {track}`",
        f"***{album}***",
        "",
        f"Release date: {release_date}",
    ]
    if should_show_label(source, label):
        lines.append(f"Label: {label}")
    return "\n".join(lines)


def build_inline_description(album: str, label: str, source: str) -> str:
    if should_show_label(source, label):
        return f"{album} | {label}"
    return album
