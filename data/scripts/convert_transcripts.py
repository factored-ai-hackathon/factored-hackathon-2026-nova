"""Convert call_transcripts CSV files to one Parquet file that Athena can read.

Every transcript's full_text contains line breaks. Athena reads CSV one line
at a time, so it splits each transcript into several broken rows. Parquet keeps
the text intact. The original CSV files are only read, never changed.

Usage (from the repo root):
    uv run python data/scripts/convert_transcripts.py <local data dir> <output .parquet>

Then upload the result (see data/dbt/README.md):
    aws s3 cp <output .parquet> s3://fh26-hackaton-data/converted/call_transcripts/call_transcripts.parquet
"""

import sys
from pathlib import Path

import duckdb


def main(data_dir: str, output: str) -> None:
    pattern = str(Path(data_dir) / "call_transcripts" / "**" / "*.csv")
    con = duckdb.connect()
    con.execute(
        f"""
        COPY (
            SELECT * FROM read_csv(
                '{pattern}',
                header = true,
                all_varchar = true,      -- keep values exactly as delivered
                quote = '"',
                escape = '"',
                hive_partitioning = false,
                union_by_name = true
            )
        ) TO '{output}' (FORMAT parquet, COMPRESSION zstd)
        """
    )
    rows = con.execute(f"SELECT count(*) FROM '{output}'").fetchone()[0]
    print(f"wrote {rows:,} transcripts to {output}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
