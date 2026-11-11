# Learning-resource collector (Module A, RFP A-07)

Collects learning resources for every concept a roadmap can contain, checks
every link, and writes `data/resources/resources.json`.

## Run

```
python scrapers/resources/collect.py   # stage 1: search sources, cache raw results (~25 min)
python scrapers/resources/build.py     # stage 2: select, verify links, write resources.json
```

- `collect.py` skips concepts already in `data/resources/raw/`. Use `--refresh` to re-search,
  and `--sources` / `--concepts` (comma-separated) to limit a run.
- **Re-run `build.py` before the demo** so every link is re-verified. Use `--no-verify` for a quick dry run.
- Requests go out directly, ignoring the Windows system proxy. They are rate-limited per host
  (1.5–2 s) and send a `RahnamaCareerBot` User-Agent.

## Sources

| Source | How | Reachable from Iran |
|---|---|---|
| Maktabkhooneh | JSON search API + course page description | yes |
| Aparat | public search API | yes |
| YouTube | search page `ytInitialData` | no (filtered) |
| Coursera | search page Apollo state + course page description | no (sanctions) |

## Files

- `data/resources/concept_seeds.json`: **draft** concept list (~145 concepts for the 25 roles in
  `categories.json`), with search queries and title filters (`match`, `exclude`).
  Track 2 owns the real taxonomy. Either adopt these `concept_id`s or give us a mapping.
- `data/resources/resources.json`:
  - `resources`: one record per resource: `resource_id`, `title`, `url`, `source`, `provider`,
    `language`, `type`, `is_free`, `accessible_from_iran`, `level`, `description`, `concept_ids`,
    `role_ids`, `verified`, `http_status`, `verified_at`
  - `by_concept`: `concept_id` → resource ids, Persian and Iran-reachable first.
    Show the first 1–3 for each roadmap gap.
- `data/resources/coverage.json`: resource counts per concept, weakest first.

## Selection rules

For each concept, take the top 5 results from each source. Keep a result only if its title
matches the concept (or, for Coursera, its skills list does) and doesn't hit an `exclude` term.
Drop videos shorter than 3 minutes. Keep at most 2 Maktabkhooneh results, 1 Aparat, 2 YouTube
(1 Persian + 1 English) and 1 Coursera. Never show a link the LLM generated; only links from
this file.
