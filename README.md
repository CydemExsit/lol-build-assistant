# LoL Build Assistant
> Offline snapshot-to-build generator for a single League of Legends champion.

## MVP scope
- Offline quickstart bundles a Varus snapshot for deterministic runs.
- Produces deterministic outputs: `*_winning.csv`, `*_sets.csv`, Markdown table, and rationale JSON.
- Runs fully offline by default; live scraping is optional and out of MVP scope.

## Quickstart (offline, single command)
```bash
python scripts/quickstart.py --hero varus --input-dir snapshots/varus
```
Outputs are written to `data/processed/`:
- `varus_aram_d2_plus_7d_winning.csv`
- `varus_aram_d2_plus_7d_sets.csv`
- `varus_aram_d2_plus_7d_build.json`
- `varus_aram_d2_plus_7d_build.md`

To regenerate the compact samples for docs:
```bash
python scripts/make_demo.py \
  --sets data/processed/varus_aram_d2_plus_7d_sets.csv \
  --winning data/processed/varus_aram_d2_plus_7d_winning.csv
```

## Validation
Run the full offline check (compilation + Quickstart + CSV assertions):
```bash
python scripts/validate_repo.py --hero varus --input-dir snapshots/varus --offline
```

## Data snapshots
- `snapshots/varus/` contains the raw JSON captures used by the offline flow.
- `data/processed/` stores deterministic outputs generated from those snapshots.

## Demo data
- [`demo/winning.sample.csv`](demo/winning.sample.csv)
- [`demo/sets.sample.csv`](demo/sets.sample.csv)

## Support matrix
See [`SUPPORTED_HEROES.md`](SUPPORTED_HEROES.md) for the up-to-date coverage table.

## Limitations
- Offline quickstart bundles a Varus snapshot for deterministic runs.
- Live scraping is optional and out of MVP; broader coverage may exist. See [`SUPPORTED_HEROES.md`](SUPPORTED_HEROES.md).
- Snapshot selectors mirror Lolalytics markup from the captured run; layout changes will require new snapshots.

### Live mode (optional, post-MVP)
Live scraping requires additional hardening and is not part of the offline MVP. See [`ISSUES_TODO.md`](ISSUES_TODO.md) for the non-blocking follow-up on enabling live mode safely.

## License
This project is released under the [MIT License](LICENSE).
