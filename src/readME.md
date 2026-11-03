# Source Code

This directory contains Python modules supporting the NBA Analytics Atlas.

## Published modules

- `collection/nba_xfg_extractor.py` — checkpointed NBA shot-quality data collector.
- `shooting/nba_xfg_repair.py` — shot-quality data repair workflow.
- `shooting/match_espn_nba_shots_v6.py` — ESPN and NBA shot matching.
- `validation/audit_xfg_coverage_v1.py` — xFG coverage audit.
- `integration/nba_combined_b37.py` — combined NBA data integration.

## Validation status

These selected files passed Python syntax checks. Full runtime testing and source-data redistribution review remain pending. Collection scripts may depend on external NBA endpoints and local input files; respect source access and rate limits.
