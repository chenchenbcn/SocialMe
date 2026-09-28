from pathlib import Path

from openpyxl import load_workbook

from socialme.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


def test_end_to_end_csv_report(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLLOWERS", "1000")
    cfg = tmp_path / "config.yaml"
    cfg.write_text(f"""
database: {tmp_path}/db.sqlite
accounts:
  - name: li
    type: csv
    platform: linkedin
    posts_csv: {FIXTURES}/posts.csv
    countries_csv: {FIXTURES}/countries.csv
    followers_total: ${{FOLLOWERS}}
""")
    out = tmp_path / "out"
    args = ["collect", "--config", str(cfg), "--start", "2026-08-01", "--end", "2026-08-31", "--out", str(out)]
    assert main(args) == 0

    wb = load_workbook(out / "social_report_2026-08-01_2026-08-31.xlsx")
    assert wb.sheetnames == ["Summary", "Posts", "Weekly publications", "Monthly publications", "Countries"]
    header = [c.value for c in wb["Summary"][1]]
    row = dict(zip(header, [c.value for c in wb["Summary"][2]]))
    assert row["publications"] == 3
    assert row["views"] == 2500
    assert row["followers_total"] == 1000
    assert row["new_followers"] is None  # first run, nothing to diff against
    assert row["top_countries_60pct"] == "Spain, Mexico"
    assert row["top_countries_share_%"] == 60.0
    assert wb["Posts"].max_row == 4
    assert (out / "social_report_2026-08-01_2026-08-31_posts.csv").exists()

    # Second run: followers grew -> new followers derived from stored snapshot
    monkeypatch.setenv("FOLLOWERS", "1040")
    assert main(args) == 0
    wb = load_workbook(out / "social_report_2026-08-01_2026-08-31.xlsx")
    row = dict(zip(header, [c.value for c in wb["Summary"][2]]))
    assert row["new_followers"] == 40
