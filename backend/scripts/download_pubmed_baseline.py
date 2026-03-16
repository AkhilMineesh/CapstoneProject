from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import httpx


BASELINE_URL = "https://ftp.ncbi.nlm.nih.gov/pubmed/baseline/"


def list_baseline_files(client: httpx.Client) -> list[str]:
    r = client.get(BASELINE_URL)
    r.raise_for_status()
    html = r.text
    # Apache-style index pages use href="pubmed26n0001.xml.gz". Be permissive.
    files = sorted(set(re.findall(r'href="(pubmed\d+n\d+\.xml\.gz)"', html)))
    if not files:
        # Fallback: match filenames anywhere in body.
        files = sorted(set(re.findall(r"(pubmed\d+n\d+\.xml\.gz)", html)))
    return files


def download_one(client: httpx.Client, name: str, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / name
    if out_path.exists() and out_path.stat().st_size > 0:
        print(f"skip {name}", file=sys.stderr)
        return
    url = BASELINE_URL + name
    print(f"downloading {name}", file=sys.stderr)
    with client.stream("GET", url, timeout=120.0) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_bytes():
                if chunk:
                    f.write(chunk)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="Output directory for .xml.gz baseline files")
    ap.add_argument("--max-files", type=int, default=0, help="If >0, only download first N files (for testing)")
    args = ap.parse_args()

    out_dir = Path(args.out)
    with httpx.Client(headers={"User-Agent": "MedRAG/0.1"}) as client:
        files = list_baseline_files(client)
        if not files:
            raise SystemExit("No baseline files found. The baseline listing format may have changed.")
        if args.max_files and args.max_files > 0:
            files = files[: args.max_files]
        for name in files:
            download_one(client, name, out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
