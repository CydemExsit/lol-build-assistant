# Issues TODO

## Close or update existing tickets
- [ ] Close issue #7 (Cloudflare shield workaround). Offline Quickstart no longer touches the network, so the shield bypass is obsolete.
- [ ] Update issue #8 (live scraping flakiness) to note that live mode is paused until the post-MVP follow-up lands.
- [ ] Close issue #9 (network timeout reports) because the deterministic snapshot flow replaces remote fetches.
- [ ] Review issue #10 to ensure it still reflects a real parser gap; keep only if reproducible against the bundled snapshots.
- [ ] Close issue #11 if it tracks missing demo artifacts—the repo now publishes deterministic samples in `demo/`.

## New issue draft
### Enable live scraping (post-MVP)
- **Problem**: Offline snapshots cover the MVP, but Playwright live scraping is disabled by default and lacks automated coverage.
- **Repro**: Run `python scripts/quickstart.py --hero varus --online`. The command currently requires Playwright/browser setup and has no regression tests.
- **Done**:
  - Reinstate a documented setup path for Playwright + Chromium.
  - Add selectors/unit coverage that can run against stored HTML fixtures.
  - Provide a throttled/robust fetch strategy (rate limiting + retries) that respects Lolalytics terms.
  - Update README and support matrix once live mode is validated end-to-end.
