#!/usr/bin/env python3
"""Conservative NBA.com -> ESPN shot matching and lineup audit for the 2025-26 pilot.

Reads existing local CSVs. Does not contact any website. Never guesses a match
from clock alone. Matches require shooter, make/miss, and period/time agreement.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path.home() / "Downloads"
NBA_PATH = ROOT / "nba_2025_26_shot_types" / "nba_2025_26_all_shot_events_complete.csv"
ESPN_PATH = ROOT / "nba_2025_26_espn_lineup_pilot" / "espn_shot_lineups_pilot.csv"
OUT_DIR = ROOT / "nba_2025_26_espn_lineup_pilot"
GAME_ID = "0022500001"


def normalize(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s.casefold())


def seconds(clock):
    parts = str(clock).strip().split(":")
    if len(parts) == 1:
        return float(parts[0])
    if len(parts) == 2:
        return float(parts[0]) * 60 + float(parts[1])
    raise ValueError(f"Unknown clock: {clock!r}")


def event_shooter_text(text):
    """Extract shooting player's name from ESPN narrative, including blocks."""
    text = str(text).strip()
    if " blocks " in text.lower():
        after = re.split(r"\s+blocks\s+", text, maxsplit=1, flags=re.I)[1]
        # Example: "Shai blocks Tari Eason 's 1-foot two point shot"
        # Or: "Amen blocks Shai Gilgeous-Alexander's driving layup"
        m = re.match(r"(.+?)\s*['’]s\b", after)
        if m:
            return m.group(1).strip()
    m = re.match(r"^(.+?)\s+(?:makes|misses)\b", text, re.I)
    return m.group(1).strip() if m else ""


def espn_result(text):
    text = str(text).lower()
    if " blocks " in text or " misses " in text:
        return 0
    if " makes " in text:
        return 1
    return None


def main():
    for path in (NBA_PATH, ESPN_PATH):
        if not path.is_file():
            raise SystemExit(f"Missing input: {path}\nPlease check that file exists before running.")
    nba = pd.read_csv(NBA_PATH, low_memory=False, dtype={"GAME_ID": str, "PLAYER_ID": str})
    nba = nba[nba["GAME_ID"].str.zfill(10) == GAME_ID].copy().reset_index(drop=True)
    espn = pd.read_csv(ESPN_PATH, dtype={"nba_game_id": str, "espn_event_id": str})
    espn = espn[~espn["text"].fillna("").str.contains("free throw", case=False)].copy().reset_index(drop=True)
    if nba.empty or espn.empty:
        raise SystemExit("No shots for selected game. Check input paths and game ID.")
    nba["p"] = pd.to_numeric(nba["PERIOD"], errors="coerce")
    nba["sec"] = (pd.to_numeric(nba["MINUTES_REMAINING"], errors="coerce") * 60 +
                  pd.to_numeric(nba["SECONDS_REMAINING"], errors="coerce"))
    nba["made"] = pd.to_numeric(nba["SHOT_MADE_FLAG"], errors="coerce")
    nba["name_key"] = nba["PLAYER_NAME"].map(normalize)
    espn["p"] = pd.to_numeric(espn["period"], errors="coerce")
    espn["sec"] = espn["clock"].map(lambda c: seconds(c) if pd.notna(c) else float("nan"))
    espn["made"] = espn["text"].map(espn_result)
    espn["shooter"] = espn["text"].map(event_shooter_text)
    espn["name_key"] = espn["shooter"].map(normalize)

    # Score candidate pairs only if both name and result agree. One-to-one matching.
    possible = []
    for ni, n in nba.iterrows():
        if not n["name_key"] or pd.isna(n["p"]) or pd.isna(n["sec"]):
            continue
        for ei, e in espn.iterrows():
            if e["p"] != n["p"] or e["name_key"] != n["name_key"] or e["made"] != n["made"]:
                continue
            if pd.isna(e["sec"]):
                continue
            diff = abs(float(e["sec"]) - float(n["sec"]))
            # NBA chart clocks are integer seconds; ESPN may be tenths.
            if int(e["sec"]) == int(n["sec"]):
                tier = 0
            elif diff <= 1.0:
                tier = 1
            else:
                continue
            possible.append((tier, diff, ni, ei))
    possible.sort()
    used_nba, used_espn = set(), set()
    matches = {}
    for tier, diff, ni, ei in possible:
        if ni in used_nba or ei in used_espn:
            continue
        # If multiple equally good candidates, do not silently guess.
        tied = [x for x in possible if x[2] == ni and x[0] == tier and abs(x[1] - diff) < 0.00001 and x[3] not in used_espn]
        if len(tied) > 1:
            continue
        used_nba.add(ni)
        used_espn.add(ei)
        matches[ni] = (ei, tier, diff)

    out_rows = []
    issues = Counter()
    for ni, n in nba.iterrows():
        row = {k: n[k] for k in nba.columns if k not in {"p", "sec", "made", "name_key"}}
        row.update({"match_status": "unmatched", "espn_event_id": "", "espn_clock": "",
                    "espn_text": "", "espn_shooter": "", "clock_difference_seconds": "",
                    "espn_lineup_verified": "", "shooter_in_lineup": "", "team_1": "", "lineup_1": "",
                    "team_2": "", "lineup_2": "", "validation_note": ""})
        if ni in matches:
            ei, tier, diff = matches[ni]
            e = espn.iloc[ei]
            players1 = [normalize(v.strip()) for v in str(e.get("lineup_1", "")).split("|")]
            players2 = [normalize(v.strip()) for v in str(e.get("lineup_2", "")).split("|")]
            shooter_on_court = n["name_key"] in players1 + players2
            verified = str(e.get("lineup_verified", "0")) in ("1", "1.0", "True", "true")
            row.update({"match_status": "exact_second" if tier == 0 else "within_one_second",
                        "espn_event_id": e["espn_event_id"], "espn_clock": e["clock"],
                        "espn_text": e["text"], "espn_shooter": e["shooter"],
                        "clock_difference_seconds": round(diff, 2),
                        "espn_lineup_verified": verified,
                        "shooter_in_lineup": shooter_on_court,
                        "team_1": e.get("team_1", ""), "lineup_1": e.get("lineup_1", ""),
                        "team_2": e.get("team_2", ""), "lineup_2": e.get("lineup_2", ""),
                        "validation_note": "Period-transition lineups still require independent validation"})
            if not shooter_on_court:
                issues["shooter_not_in_reconstructed_lineup"] += 1
            if not verified:
                issues["pilot_lineup_not_verified"] += 1
        else:
            issues["nba_unmatched"] += 1
        out_rows.append(row)
    out = pd.DataFrame(out_rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    match_path = OUT_DIR / "nba_espn_shot_lineup_matches_v6.csv"
    out.to_csv(match_path, index=False)
    extra = espn.loc[~espn.index.isin(used_espn),
                     ["espn_event_id", "period", "clock", "text", "shooter", "made", "lineup_verified"]]
    extra_path = OUT_DIR / "unmatched_espn_shots_v6.csv"
    extra.to_csv(extra_path, index=False)
    print("\nV6 SHOT-TO-LINEUP MATCH REPORT")
    print("NBA.com attempts:", len(nba))
    print("ESPN field-goal candidates:", len(espn))
    print("Matched:", len(matches))
    print("Exact-second matches:", sum(tier == 0 for _, tier, _ in matches.values()))
    print("Within-one-second matches:", sum(tier == 1 for _, tier, _ in matches.values()))
    print("Unmatched NBA.com shots:", len(nba) - len(matches))
    print("Unmatched ESPN candidates:", len(extra))
    print("Matched shooters NOT in reconstructed lineup:", issues["shooter_not_in_reconstructed_lineup"])
    print("Matched shots with unverified pilot lineup:", issues["pilot_lineup_not_verified"])
    print("\nUNMATCHED ESPN EVENTS")
    print(extra[["period", "clock", "text"]].to_string(index=False) if len(extra) else "None")
    if issues["nba_unmatched"]:
        print("\nUNMATCHED NBA EVENTS")
        print(out.loc[out.match_status == "unmatched", ["PERIOD", "MINUTES_REMAINING", "SECONDS_REMAINING", "PLAYER_NAME", "ACTION_TYPE", "SHOT_MADE_FLAG"]].to_string(index=False))
    if issues["shooter_not_in_reconstructed_lineup"]:
        print("\nSHOOTER/LINEUP CONFLICTS")
        print(out.loc[out.shooter_in_lineup == False, ["PLAYER_NAME", "PERIOD", "espn_clock", "espn_text"]].to_string(index=False))
    print("\nSaved:", match_path)
    print("Saved:", extra_path)
    print("IMPORTANT: Successful matching does not independently validate lineup accuracy across period boundaries.")


if __name__ == "__main__":
    main()
