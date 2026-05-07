from __future__ import annotations

from charkive import __version__
from charkive.config import CharkiveConfig


def fmt_bytes(nbytes: float | int) -> str:
    n = float(nbytes)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(n) < 1024.0 or unit == "PB":
            if unit == "B":
                return f"{int(n)} {unit}"
            return f"{n:.2f} {unit}"
        n /= 1024.0


def ascii_bar_fraction(frac: float, width: int = 14) -> str:
    frac = max(0.0, min(1.0, frac))
    filled = int(round(frac * width))
    filled = max(0, min(width, filled))
    return "[" + ("█" * filled) + ("░" * (width - filled)) + "]"


def render_report(cfg: CharkiveConfig, summary: dict) -> str:
    root = cfg.root.resolve()
    san_abs = cfg.sanitorium_absolute()
    fluff = summary.get("fluff", {"bytes": 0, "files": 0})
    protected = summary.get("protected", {"bytes": 0, "files": 0})
    tier_map = summary.get("by_tier", {})
    fluff_b = float(fluff["bytes"])
    fluff_files = int(fluff["files"])

    order = ("shyte", "kiloshyte", "megashyte", "gigashyte")
    amps: list[tuple[int, str, int, float]] = []
    for name in order:
        if name not in tier_map:
            continue
        info = tier_map[name]
        amps.append((0, name, info.get("files", 0), float(info.get("bytes", 0))))

    label_map = {"shyte": 1, "kiloshyte": 5, "megashyte": 10, "gigashyte": 11}
    amps2: list[tuple[int, str, int, float]] = [
        (label_map.get(nm, 0), nm, int(files), nbytes) for _z, nm, files, nbytes in amps
    ]
    amps2.sort(key=lambda z: label_map.get(z[1], 0))

    lines = [
        f'Charkive v{__version__} — "Smell the Glove" SANity summary',
        f"Root : {root}",
        f"",
        "Amp levels:",
    ]
    for lv, nm, files, nbytes in amps2:
        pct = nbytes / fluff_b if fluff_b else 0
        emoji = ""
        lines.append(
            f"  {nm.capitalize()} [{lv:2d}] {ascii_bar_fraction(pct)}  {fmt_bytes(nbytes)}  "
            f"({files:,} files) {emoji}"
        )

    if not amps2:
        lines.append("  (no Tier-matched fluff this pass)")

    lines.extend(
        [
            "",
            f"Fluff (candidate tiers summed): {fmt_bytes(fluff_b)} in {fluff_files:,} files",
            f"Shielded masters / sanctuary paths: {fmt_bytes(float(protected['bytes']))}",
            "",
            "SANitary status:",
            f"  • Protected (sanctuary rules honored): ~{fmt_bytes(float(protected['bytes']))}",
            f"  • Ready for sanitise preview: ~{fmt_bytes(fluff_b)}",
            "",
            "SANitorium:",
            f"  {san_abs}",
            "",
            (
                'Files moved to SANitorium stay recoverable for the retention window.'
                if cfg.spinal_tap_mode
                else "Files staged to SANitorium stay recoverable for the retention window."
            ),
        ]
    )
    lines.append('')
    lines.append('All tiers go to 11.')
    return "\n".join(lines)
