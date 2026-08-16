"""Deterministic validation of an uploaded STL before it's persisted or sliced.

Deliberately shallow: this checks filename/size sanity, not STL geometry or
topology. Distinguishing ASCII from binary STL reliably from content alone
is a known gotcha (many binary STLs still start with the literal bytes
"solid" in their 80-byte header, a legacy convention) so no attempt is made
to fully parse or format-sniff the file — a corrupt-but-plausibly-sized file
is instead caught later by PrusaSlicer itself failing to slice it.
"""

from __future__ import annotations

# Smallest possible binary STL: an 80-byte header + a 4-byte triangle count
# (with zero triangles following). Anything smaller cannot be a valid STL of
# either format.
MIN_STL_BYTES = 84


def validate_stl(filename: str, content: bytes) -> list[str]:
    """Return a list of validation error messages; empty means valid."""
    errors: list[str] = []

    if not filename.lower().endswith(".stl"):
        errors.append(f"Filename must end with .stl, got: {filename!r}")

    if not content:
        errors.append("Uploaded file is empty.")
    elif len(content) < MIN_STL_BYTES:
        errors.append(
            f"File is too small to be a valid STL ({len(content)} bytes; "
            f"minimum possible is {MIN_STL_BYTES} bytes)."
        )

    return errors


__all__ = ["validate_stl", "MIN_STL_BYTES"]
