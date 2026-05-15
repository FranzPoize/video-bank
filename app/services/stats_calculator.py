"""
Pure functions for computing advanced basketball statistics.

Takes a raw stats dict from the matches table (snake_case fields)
and returns computed fields: percentages, eFG%, TS%.

All functions are pure — no DB access, no side effects.
"""


def compute_all(raw: dict) -> dict:
    """Compute derived stats from a raw box-score dict.

    Args:
        raw: Dict with snake_case match stat fields (may contain None).

    Returns:
        Dict with computed fields. Percentages are returned as
        float (0.0-100.0) or None if denominator is zero.
    """
    # Field access with None → 0 coercion
    two_pa = raw.get("two_point_attempts") or 0
    two_pm = raw.get("two_point_made") or 0
    three_pa = raw.get("three_point_attempts") or 0
    three_pm = raw.get("three_point_made") or 0
    fta = raw.get("free_throw_attempts") or 0
    ftm = raw.get("free_throw_made") or 0
    pts = raw.get("points") or 0

    fga = two_pa + three_pa
    fgm = two_pm + three_pm

    return {
        "fg_attempts": fga,
        "fg_made": fgm,
        "fg_pct": _safe_pct(fgm, fga),
        "two_pct": _safe_pct(two_pm, two_pa),
        "three_pct": _safe_pct(three_pm, three_pa),
        "ft_pct": _safe_pct(ftm, fta),
        "efg_pct": _safe_efg(fgm, three_pm, fga),
        "ts_pct": _safe_ts(pts, fga, fta),
    }


def _safe_pct(made: int, attempts: int) -> float | None:
    """Return (made / attempts * 100) as float, or None if attempts == 0."""
    if attempts <= 0:
        return None
    return round((made / attempts) * 100, 1)


def _safe_efg(fgm: int, three_pm: int, fga: int) -> float | None:
    """Return effective field goal percentage * 100, or None if fga == 0.

    eFG% = (FGM + 0.5 * 3PM) / FGA
    """
    if fga <= 0:
        return None
    return round(((fgm + 0.5 * three_pm) / fga) * 100, 1)


def _safe_ts(pts: int, fga: int, fta: int) -> float | None:
    """Return true shooting percentage * 100, or None if denominator == 0.

    TS% = PTS / (2 * FGA + 0.44 * FTA)
    """
    denominator = 2 * fga + 0.44 * fta
    if denominator <= 0:
        return None
    return round((pts / denominator) * 100, 1)
