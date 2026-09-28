# SocialMe — social media analytics collector

Collects, for each of our social media accounts and for any period (week, month, custom):

| Metric | Where it appears in the report |
|---|---|
| Number of publications per week / per month | `Weekly publications`, `Monthly publications` sheets; `publications`, `publications_per_week` in `Summary` |
| Views, likes, shares, comments of every publication / video | `Posts` sheet (one row per post, with link) and totals in `Summary` |
| Total followers | `followers_total` in `Summary` |
| New followers gained in the period | `new_followers` in `Summary` |
| Top countries that together make ≥ 60 % of views | `top_countries_60pct` + `top_countries_share_%` in `Summary`; full breakdown in `Countries` |

Output: one Excel workbook `reports/social_report_<start>_<end>.xlsx` plus a CSV per sheet.
Every run is also stored in a SQLite history (`data/socialme.db`).

## Supported sources

| `type` | Platform | API | Credentials needed |
|---|---|---|---|
| `youtube` | YouTube channel | Data API v3 + YouTube Analytics API | OAuth client id/secret + refresh token with `youtube.readonly` and `yt-analytics.readonly` scopes |
| `instagram` | Instagram professional (Business/Creator) account | Meta Graph API | Instagram user id + access token with `instagram_basic`, `instagram_manage_insights`, `pages_read_engagement` |
| `facebook` | Facebook Page | Meta Graph API | Page id + **Page** access token with `read_insights`, `pages_read_engagement` |
| `tiktok` | TikTok Business account | TikTok API for Business (Accounts API v1.3) | business id + access token (scopes `user.info.basic`, `video.list`, `user.insights`/`video.insights`) |
| `csv` | Anything else (LinkedIn, X, …) or metrics an API does not expose | Native analytics exports | none |

### Per-platform notes (what the APIs actually give)

- **YouTube** – views/likes/comments are lifetime per video; shares come from YouTube Analytics.
  New followers = `subscribersGained` in the period. Countries are true **views** per country.
- **Instagram** – views and shares come from media insights. New followers use the
  `follower_count` insight, which Instagram keeps only for the **last 30 days** – run the
  collection at least monthly. Instagram has no views-by-country; we use
  `reached_audience_demographics` (accounts reached per country, `country_timeframe` in config)
  as the closest proxy – the report's `country_metric` column says so.
- **Facebook** – views use `post_media_view` (configurable via `post_views_metric`), new followers
  `page_daily_follows_unique`. Meta no longer exposes views-by-country for Pages: export it from
  Meta Business Suite and add a `csv` source with `countries_csv`, or set `country_metric` if your
  API version still offers one.
- **TikTok** – views/likes/comments/shares per video; country views are estimated as
  `video_views × audience_countries share` summed over the period's videos. Field names are
  configurable (`account_fields`, `video_fields`) in case TikTok renames them.
- If a platform does not report new followers, the tool computes it as
  *followers now − followers at the previous run* from the SQLite history.
- Any metric that fails is reported as a warning (log + `notes` column) and the other data is kept.

## Setup

```bash
pip install .                      # or: pip install -e ".[dev]" for development
cp config.example.yaml socialme.yaml   # keep only the accounts you use
cp .env.example .env                   # fill in ids / tokens (never commit .env)
```

`${VARS}` in the YAML are replaced from the environment (and `.env`), so `socialme.yaml`
contains no secrets and can be committed.

## Usage

```bash
socialme collect --config socialme.yaml --period last-month
socialme collect --config socialme.yaml --period last-week
socialme collect --config socialme.yaml --start 2026-01-01 --end 2026-06-30
socialme collect --config socialme.yaml --period last-30-days --only our-youtube our-tiktok
```

Periods: `last-week` (previous Mon–Sun), `this-week`, `last-month`, `this-month`, `last-N-days`.
The ≥ 60 % threshold can be changed with `top_countries_threshold` in the config.

### CSV source format

Headers are matched case-insensitively; common native-export names work
(`Date`/`Publish time`, `Views`/`Impressions`/`Plays`, `Reactions`, `Reposts`, …).

- `posts_csv`: `published_at, title, url, views, likes, shares, comments` (+ optional `post_id`, `media_type`)
- `countries_csv`: `country, views` (country name or ISO code)
- `followers_csv` (optional): `date, followers_total, new_followers` — or set `followers_total` /
  `new_followers` directly in the config.

## Automatic weekly / monthly reports

`.github/workflows/collect.yml` runs every Monday (previous week) and on the 1st of each month
(previous month), and can be started manually. Add the tokens as repository **secrets** with the
names in `.env.example` and commit `socialme.yaml`. Reports are attached to the run as artifacts.

## Development

```bash
pip install -e ".[dev]"
pytest
```

Tests use canned API responses, no network or credentials needed.
