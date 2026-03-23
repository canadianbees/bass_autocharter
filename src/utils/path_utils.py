import re
from pathlib import Path


def normalize_filename(name: str) -> str:
    """
    Normalizes a filename:
    - removes special characters
    - replaces spaces with underscores
    - collapses repeated underscores
    """
    name = name.strip()

    # replace spaces with underscore
    name = name.replace(" ", "_")

    # remove anything not alphanumeric, underscore, or dash
    name = re.sub(r"[^a-zA-Z0-9_\-]", "", name)

    # collapse multiple underscores
    name = re.sub(r"_+", "_", name)

    return name


def normalize_path(input_path: str, output_dir: str, extension: str = None) -> str:
    """
    Creates a sanitized copy of a file path in a safe directory.

    Example:
    "PinkPantheress_-_Stateside__Zara..." → "PinkPantheress_Stateside_Zara..."

    Returns new safe path.
    """
    input_path = Path(input_path)
    output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    stem = normalize_filename(input_path.stem)

    if extension:
        filename = f"{stem}.{extension.lstrip('.')}"
    else:
        filename = f"{stem}{input_path.suffix}"

    return str(output_dir / filename)