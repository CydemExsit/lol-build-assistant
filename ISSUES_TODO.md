# Issues TODO

## Close or update existing tickets
- [ ] Close issue #7 (legacy network shield workaround). Offline Quickstart no longer touches the network, so the bypass is obsolete.
- [ ] Update issue #8 (live scraping flakiness) to note that live mode is paused until the post-MVP follow-up lands.
- [ ] Close issue #9 (network timeout reports) because the deterministic snapshot flow replaces remote fetches.
- [ ] Review issue #10 to ensure it still reflects a real parser gap; keep only if reproducible against the bundled snapshots.
- [ ] Close issue #11 if it tracks missing demo artifacts—the repo now publishes deterministic samples in `demo/`.

## New issue draft
### Enable live mode safely (post-MVP)
- **Problem**: Offline snapshots cover the MVP, but Playwright live scraping is disabled by default and lacks guardrails.
- **Repro**: Run `python scripts/quickstart.py --hero varus --online`. The command currently requires Playwright/browser setup and has no regression tests.
- **Done (non-blocking)**:
  - Add rate limiting and retry policies for outbound requests.
  - Create selector tests that run against stored HTML fixtures.
  - Provide a lightweight snapshot recorder to refresh fixtures on demand.
  - Define an error taxonomy so live failures surface actionable messages.
