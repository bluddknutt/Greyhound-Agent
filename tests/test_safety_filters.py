"""Safety-filter + deploy-guard tests (hotfix/box1-vacant-maiden-deploy-guard).

Covers the scrape-time runner/race filters (vacant boxes, low-info maiden races)
and the deploy guard that blocks bad picks before latest_picks.json is written.
"""

import pandas as pd

from src.tab_pipeline_service import (
    _apply_race_filters,
    _is_vacant_runner_name,
)


def _race_rows(venue, race_number, runners):
    """runners: list of (dog_name, grade, career_starts)."""
    rows = []
    for i, (name, grade, starts) in enumerate(runners, start=1):
        rows.append({
            "venue": venue,
            "race_number": race_number,
            "dog_name": name,
            "_dog_number": i,
            "grade": grade,
            "_career_starts": starts,
        })
    return rows


# --------------------------------------------------------------------------- #
# Task 2 — vacant box hard filter
# --------------------------------------------------------------------------- #
def test_vacant_name_matcher():
    assert _is_vacant_runner_name("Vacant Box")
    assert _is_vacant_runner_name("vacant box 4")
    assert _is_vacant_runner_name("Vacant Trap")   # /^vacant/i, no "box"
    assert _is_vacant_runner_name("VACANT")
    assert _is_vacant_runner_name("")
    assert _is_vacant_runner_name(None)
    assert not _is_vacant_runner_name("Swift Vacancy")  # contains 'vacan' but not ^vacant
    assert not _is_vacant_runner_name("Fast Dog")


def test_vacant_boxes_dropped_from_race():
    # 7 real + 2 vacants -> vacants dropped, race kept (>=5 valid runners).
    runners = [(f"Dog {i}", "5", 20) for i in range(7)]
    runners += [("Vacant Box", "5", 0), ("Vacant Trap", "5", 0)]
    df = pd.DataFrame(_race_rows("Albion Park", 1, runners))
    out = _apply_race_filters(df, {"source": "tab", "skipped_races": []})
    names = set(out["dog_name"])
    assert not any(n.lower().startswith("vacant") for n in names)
    assert len(out) == 7


def test_race_skipped_when_too_few_after_vacant_drop():
    # 4 real + 2 vacants -> only 4 valid (<5) -> whole race dropped.
    meta = {"source": "tab", "skipped_races": []}
    runners = [(f"Dog {i}", "5", 20) for i in range(4)]
    runners += [("Vacant Box", "5", 0), ("Vacant Box", "5", 0)]
    df = pd.DataFrame(_race_rows("Sale", 3, runners))
    out = _apply_race_filters(df, meta)
    assert out.empty
    reasons = {s["reason"] for s in meta["skipped_races"]}
    assert "insufficient_valid_runners" in reasons
