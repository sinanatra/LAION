"""One-off backfill: adds punsafe/pwatermark/exif to metadata.json entries
that were downloaded before run_pipeline.py started capturing those fields.

Uses DuckDB to query the dataset's parquet files directly, rather than
streaming row-by-row through the `datasets` library: DuckDB reads only
the 4 columns we need (url, punsafe, pwatermark, exif) in a vectorized
C++ engine, instead of Python deserializing a full 15-column object per
row. Parquet has no index on url, so there's no way to skip rows
entirely — this just makes the scan itself much cheaper.

Only scans the parquet file(s) that actually cover your current
progress.json row range (found via fast footer-only metadata reads, not
a full data scan), and does one join for every pending URL at once.

Re-reads metadata.json fresh right before writing, so it's safe to run
alongside a live run_pipeline.py session without clobbering new entries
it adds in the meantime.

Usage:
    python backfill_metadata.py
"""
import json
import os
import time
from pathlib import Path

import duckdb
from dotenv import load_dotenv
from huggingface_hub import HfApi

DATASET_NAME = "laion/relaion2B-en-research-safe"

OUTPUT_DIR = Path(__file__).parent / "../app/public/data"
METADATA_PATH = OUTPUT_DIR / "metadata.json"
PROGRESS_PATH = OUTPUT_DIR / "progress.json"

# exif is deliberately excluded here: it's legitimately absent on most
# images (no EXIF data, or an empty "{}"/"null" that we skip saving), so
# requiring it would flag nearly every entry as pending forever.
REQUIRED_FIELDS = ["punsafe", "pwatermark"]


def needs_backfill(entry):
    return any(field not in entry for field in REQUIRED_FIELDS)


def fields_from_row(punsafe, pwatermark, exif):
    fields = {}
    if punsafe is not None:
        fields["punsafe"] = punsafe
    if pwatermark is not None:
        fields["pwatermark"] = pwatermark
    if exif and exif not in ("{}", "null"):
        fields["exif"] = exif
    return fields


def main():
    load_dotenv()
    token = os.environ["HF_TOKEN"]

    metadata = json.loads(METADATA_PATH.read_text())
    pending = [entry for entry in metadata if needs_backfill(entry)]
    print(f"{len(pending)} of {len(metadata)} entries need backfilling.")
    if not pending:
        return

    max_rows = (
        json.loads(PROGRESS_PATH.read_text())["rows_scanned"]
        if PROGRESS_PATH.exists()
        else None
    )

    api = HfApi(token=token)
    all_files = sorted(
        f for f in api.list_repo_files(DATASET_NAME, repo_type="dataset")
        if f.endswith(".parquet")
    )

    con = duckdb.connect()
    con.sql(f"CREATE SECRET (TYPE huggingface, TOKEN '{token}');")

    # Walk files in order, counting rows per file (DuckDB resolves COUNT(*)
    # on parquet from its footer metadata, not a full data read) until
    # we've covered the range we actually downloaded from. Usually just
    # the first file or two.
    needed_files = []
    cumulative = 0
    for filename in all_files:
        uri = f"hf://datasets/{DATASET_NAME}/{filename}"
        count = con.sql(
            f"SELECT COUNT(*) FROM read_parquet('{uri}')"
        ).fetchone()[0]
        needed_files.append(uri)
        cumulative += count
        if max_rows is not None and cumulative >= max_rows:
            break
    print(f"Scanning {len(needed_files)} parquet file(s), ~{cumulative:,} rows.")

    con.execute("CREATE TABLE pending_urls (url VARCHAR)")
    con.executemany(
        "INSERT INTO pending_urls VALUES (?)",
        [(entry["source_url"],) for entry in pending],
    )

    file_list = ", ".join(f"'{f}'" for f in needed_files)
    start = time.time()
    rows = con.sql(f"""
        SELECT p.url, p.punsafe, p.pwatermark, p.exif
        FROM read_parquet([{file_list}]) p
        JOIN pending_urls u ON p.url = u.url
    """).fetchall()
    print(f"Query took {time.time() - start:.1f}s, matched {len(rows)} of {len(pending)}.")

    fields_by_url = {}
    for url, punsafe, pwatermark, exif in rows:
        fields = fields_from_row(punsafe, pwatermark, exif)
        if fields:
            fields_by_url[url] = fields

    # Re-read fresh right before writing, in case run_pipeline.py or
    # another process changed metadata.json in the meantime.
    metadata = json.loads(METADATA_PATH.read_text())
    updated = 0
    for entry in metadata:
        fields = fields_by_url.get(entry["source_url"])
        if fields:
            entry.update(fields)
            updated += 1
    METADATA_PATH.write_text(json.dumps(metadata, indent=2))
    print(f"Updated {updated} entries.")

    still_pending = sum(1 for entry in metadata if needs_backfill(entry))
    print(f"{still_pending} entries still pending.")
    if still_pending:
        print("(Their URL may not appear in the scanned parquet range — rare.)")


if __name__ == "__main__":
    main()
