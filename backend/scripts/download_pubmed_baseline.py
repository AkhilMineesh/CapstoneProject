from __future__ import annotations

import argparse
import random
import re
import sys
import time
from pathlib import Path

import httpx


BASELINE_URL = "https://ftp.ncbi.nlm.nih.gov/pubmed/baseline/"


def list_baseline_files(client: httpx.Client, retries: int = 5) -> list[str]:
    last_exc: Exception | None = None
    for attempt in range(max(1, retries)):
        try:
            r = client.get(BASELINE_URL)
            r.raise_for_status()
            html = r.text
            # Apache-style index pages use href="pubmed26n0001.xml.gz". Be permissive.
            files = sorted(set(re.findall(r'href="(pubmed\d+n\d+\.xml\.gz)"', html)))
            if not files:
                # Fallback: match filenames anywhere in body.
                files = sorted(set(re.findall(r"(pubmed\d+n\d+\.xml\.gz)", html)))
            return files
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError, httpx.RemoteProtocolError) as e:
            last_exc = e
            status = getattr(getattr(e, "response", None), "status_code", None)
            retryable = isinstance(e, (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)) or status in (
                429,
                500,
                502,
                503,
                504,
            )
            if not retryable or attempt >= retries - 1:
                raise
            sleep_s = min(20.0, (2.0**attempt)) + random.random()
            print(f"retry list ({attempt + 1}/{retries}) in {sleep_s:.1f}s: {e}", file=sys.stderr)
            time.sleep(sleep_s)
    if last_exc:
        raise last_exc
    return []


def download_one(client: httpx.Client, name: str, out_dir: Path, timeout_s: float = 300.0, retries: int = 6) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / name
    part_path = out_dir / f"{name}.part"
    if out_path.exists() and out_path.stat().st_size > 0:
        print(f"skip {name}", file=sys.stderr)
        return
    url = BASELINE_URL + name
    print(f"downloading {name}", file=sys.stderr)
    for attempt in range(max(1, retries)):
        try:
            with client.stream("GET", url, timeout=timeout_s) as r:
                r.raise_for_status()
                with open(part_path, "wb") as f:
                    for chunk in r.iter_bytes():
                        if chunk:
                            f.write(chunk)
            part_path.replace(out_path)
            return
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError, httpx.RemoteProtocolError) as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            retryable = isinstance(e, (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)) or status in (
                429,
                500,
                502,
                503,
                504,
            )
            if part_path.exists():
                try:
                    part_path.unlink()
                except Exception:  # noqa: BLE001
                    pass
            if not retryable or attempt >= retries - 1:
                raise
            sleep_s = min(30.0, (2.0**attempt)) + random.random()
            print(f"retry {name} ({attempt + 1}/{retries}) in {sleep_s:.1f}s: {e}", file=sys.stderr)
            time.sleep(sleep_s)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="Output directory for .xml.gz baseline files")
    ap.add_argument("--max-files", type=int, default=0, help="If >0, only download first N files (for testing)")
    ap.add_argument(
        "--latest",
        action="store_true",
        help="When used with --max-files, download the most recent N files instead of the first N.",
    )
    ap.add_argument("--timeout", type=float, default=300.0, help="Per-file download timeout in seconds.")
    ap.add_argument("--retries", type=int, default=6, help="Retry attempts for transient network/protocol failures.")
    args = ap.parse_args()

    out_dir = Path(args.out)
    timeout = httpx.Timeout(connect=30.0, read=max(60.0, float(args.timeout)), write=max(60.0, float(args.timeout)), pool=30.0)
    limits = httpx.Limits(max_connections=5, max_keepalive_connections=2)
    with httpx.Client(headers={"User-Agent": "MedRAG/0.1"}, timeout=timeout, limits=limits, follow_redirects=True) as client:
        files = list_baseline_files(client, retries=max(1, int(args.retries)))
        if not files:
            raise SystemExit("No baseline files found. The baseline listing format may have changed.")
        if args.max_files and args.max_files > 0:
            files = files[-args.max_files :] if args.latest else files[: args.max_files]
        for name in files:
            download_one(
                client,
                name,
                out_dir,
                timeout_s=float(args.timeout),
                retries=max(1, int(args.retries)),
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
