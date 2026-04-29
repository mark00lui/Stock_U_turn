# Backfill Summary — momentum + breakout signal JSONs

Reconstructed from cached yfinance history. Each date's JSON lives in
`data/agent_outputs/backfill/signals_{strategy}_{date}.json`.

| Date | Scanned | Momentum Total / Strong | Breakout Total / Strong |
|------|--------:|------------------------:|------------------------:|
| 2026-04-22 | 346 | 129 / **33** | 77 / **25** |
| 2026-04-23 | 349 | 186 / **41** | 46 / **15** |
| 2026-04-24 | 355 | 108 / **15** | 46 / **12** |
| 2026-04-27 | 355 | 91 / **14** | 40 / **13** |
| 2026-04-28 | 357 | 68 / **9** | 27 / **8** |
| 2026-04-29 | 357 | 64 / **15** | 24 / **10** |

> Bold = 5★ Strong signals — these were the picks the daily report
> would have surfaced if the cron had used `--strategy all` from day one.