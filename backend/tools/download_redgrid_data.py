#!/usr/bin/env python3
"""
RedGrid - dataset downloader.

Downloads every dataset the backend (and the model team) needs, clipped to the
Jezero region 77.20-77.70 E, 18.20-18.70 N (Mars 2000, east-positive).

Big rasters are CLIPPED straight from the link with GDAL (only the Jezero part is
read), small files are downloaded whole. Finished files are skipped on a re-run,
so the script can be stopped and started again safely.

Requirements
  - Python 3.9+
  - GDAL 3+ command-line tools (gdalwarp) on PATH
      Windows/macOS/Linux:  conda install -c conda-forge gdal

Usage
  python download_redgrid_data.py                    # everything
  python download_redgrid_data.py --group backend    # backend only
  python download_redgrid_data.py --group model      # model team only
  python download_redgrid_data.py --only sim3464 traverse
  python download_redgrid_data.py --list             # show what would be downloaded
  python download_redgrid_data.py --out D:/redgrid-data
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Region (the official RedGrid limits)
# ---------------------------------------------------------------------------
WEST, SOUTH, EAST, NORTH = 77.20, 18.20, 77.70, 18.70
MARS_LONLAT = "+proj=longlat +a=3396190 +b=3396190 +no_defs"

S3_TRN = "https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/mars2020_trn/"

# mode: "clip"   = gdalwarp clip at native resolution
#       "clip1m" = gdalwarp clip, averaged down to 1 m (for the 25 cm ortho)
#       "whole"  = plain HTTP download
DATASETS = [
    {
        "key": "hirise_dtm", "group": "backend+model", "mode": "clip",
        "name": "HiRISE terrain height model, 1 m (USGS Mars 2020 TRN)",
        "url": S3_TRN + "HiRISE/JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40.tif",
        "out": "hirise_dtm_jezero.tif",
    },
    {
        "key": "hirise_ortho", "group": "backend", "mode": "clip1m",
        "name": "HiRISE orthoimage, 25 cm, saved at 1 m (USGS Mars 2020 TRN)",
        "url": S3_TRN + "HiRISE/JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first.tif",
        "out": "hirise_ortho_jezero.tif",
    },
    {
        "key": "ctx_dem", "group": "backend", "mode": "clip",
        "name": "CTX terrain height model, 20 m (Mars 2020 science investigation)",
        "url": S3_TRN + "CTX/ScienceInvestigationMaps_JPL/M20_JezeroCrater_CTXDEM_20m.tif",
        "out": "ctx_dem_jezero.tif",
    },
    {
        "key": "ctx_ortho", "group": "backend", "mode": "clip",
        "name": "CTX orthoimage, 5 m (Mars 2020 science investigation)",
        "url": S3_TRN + "CTX/ScienceInvestigationMaps_JPL/M20_JezeroCrater_CTXortho_mosaic_5m.tif",
        "out": "ctx_ortho_jezero.tif",
    },
    {
        "key": "sim3464", "group": "backend", "mode": "whole",
        "name": "USGS SIM 3464 geologic map database (Sun and Stack, 2020)",
        "url": "https://pubs.usgs.gov/sim/3464/sim3464_database.zip",
        "out": "sim3464_database.zip",
    },
    {
        "key": "themis_ti", "group": "backend", "mode": "clip",
        "name": "THEMIS quantitative thermal inertia, 100 m, tile 00N060E",
        "url": "https://asc-astropedia.s3.us-west-2.amazonaws.com/Mars/Odyssey/"
               "THEMIS-Global-Thermal-Inertia-Mosaic/Quantitative-32-Bit/"
               "THEMIS_TI_Mosaic_Quant_00N060E_100mpp.cub",
        "out": "themis_ti_jezero.tif",
    },
    {
        "key": "traverse", "group": "backend+model", "mode": "whole",
        "name": "Perseverance traverse (NASA/JPL MMGIS)",
        "url": "https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_traverse.json",
        "out": "m20_traverse.json",
    },
    {
        "key": "apollo14", "group": "model", "mode": "whole",
        "name": "Apollo 14 full mapping dataset (LROC shapefiles)",
        "url": "https://pds.lroc.im-ldi.com/data/LRO-L-LROC-5-RDR-V1.0/LROLRC_2001/EXTRAS/SHAPEFILE/APOLLO_14/APOLLO_14.ZIP",
        "out": "APOLLO_14.ZIP",
    },
    {
        "key": "nasa_tn_d7883", "group": "backend", "mode": "whole",
        "name": "Apollo metabolic expenditures report, NASA TN D-7883 (reference PDF)",
        "url": "https://www.nasa.gov/wp-content/uploads/static/history/alsj/tnD7883Metabolic.pdf",
        "out": "reference/tnD7883Metabolic.pdf",
    },
    {
        "key": "apollo14_plss", "group": "backend", "mode": "whole",
        "name": "Apollo 14 PLSS operations report (reference PDF)",
        "url": "https://www.nasa.gov/wp-content/uploads/static/history/alsj/a14/Ap14PLSS_OPS-Report.pdf",
        "out": "reference/Ap14PLSS_OPS-Report.pdf",
    },
]

# Not a single file: printed as a manual step at the end.
MANUAL = [
    ("MEDA weather (PDS Atmospheres Node) - browse the folder and take the newest 30 sols",
     "https://pds-atmospheres.nmsu.edu/PDS/data/PDS4/Mars2020/mars2020_meda"),
]

# GDAL settings for reading over HTTP: no directory listing, retries on flaky links.
GDAL_ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "GDAL_HTTP_MAX_RETRY": "6",
    "GDAL_HTTP_RETRY_DELAY": "5",
    "GDAL_HTTP_TIMEOUT": "120",
    "VSI_CACHE": "TRUE",
    "VSI_CACHE_SIZE": "100000000",
}


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def in_group(d: dict, group: str) -> bool:
    return group == "all" or group in d["group"].split("+")


def download_whole(url: str, dest: Path) -> None:
    part = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "RedGrid-downloader/1.0"})
    for attempt in range(1, 6):
        try:
            with urllib.request.urlopen(req, timeout=120) as res, open(part, "wb") as fh:
                total = int(res.headers.get("Content-Length") or 0)
                done, last = 0, 0.0
                while True:
                    chunk = res.read(1 << 20)
                    if not chunk:
                        break
                    fh.write(chunk)
                    done += len(chunk)
                    if time.time() - last > 1:
                        pct = f" ({done * 100 / total:.0f}%)" if total else ""
                        print(f"\r    {human(done)}{pct}   ", end="", flush=True)
                        last = time.time()
            print()
            part.replace(dest)
            return
        except Exception as exc:  # noqa: BLE001 - report and retry
            print(f"\n    attempt {attempt} failed: {exc}")
            time.sleep(5 * attempt)
    raise RuntimeError(f"could not download {url}")


def clip(url: str, dest: Path, one_metre: bool) -> None:
    tmp = dest.with_name(dest.stem + ".part.tif")
    cmd = [
        "gdalwarp", "-overwrite", "-multi", "-wm", "1024",
        f"/vsicurl/{url}", str(tmp),
        "-te", str(WEST), str(SOUTH), str(EAST), str(NORTH),
        "-te_srs", MARS_LONLAT,
        "-co", "COMPRESS=DEFLATE", "-co", "TILED=YES", "-co", "BIGTIFF=IF_SAFER",
    ]
    if one_metre:
        cmd += ["-tr", "1", "1", "-r", "average"]
    env = {**os.environ, **GDAL_ENV}
    print("    " + " ".join(cmd[:4]) + " ...")
    result = subprocess.run(cmd, env=env)
    if result.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"gdalwarp failed for {url}")
    tmp.replace(dest)


def main() -> int:
    ap = argparse.ArgumentParser(description="Download the RedGrid datasets.")
    ap.add_argument("--out", default="redgrid-data", help="output folder (default: redgrid-data)")
    ap.add_argument("--group", choices=["all", "backend", "model"], default="all")
    ap.add_argument("--only", nargs="*", metavar="KEY", help="download only these keys")
    ap.add_argument("--list", action="store_true", help="list the datasets and exit")
    args = ap.parse_args()

    chosen = [d for d in DATASETS if in_group(d, args.group)]
    if args.only:
        unknown = set(args.only) - {d["key"] for d in DATASETS}
        if unknown:
            print(f"Unknown key(s): {', '.join(sorted(unknown))}")
            return 2
        chosen = [d for d in chosen if d["key"] in args.only]

    if args.list:
        for d in chosen:
            print(f"{d['key']:<15} {d['mode']:<7} {d['group']:<14} {d['name']}")
        return 0

    needs_gdal = any(d["mode"].startswith("clip") for d in chosen)
    if needs_gdal and not shutil.which("gdalwarp"):
        print("gdalwarp was not found. Install GDAL 3+ first:\n"
              "    conda install -c conda-forge gdal\n"
              "then run this script from the same terminal.")
        return 1

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    failed = []
    for i, d in enumerate(chosen, 1):
        dest = out / d["out"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"[{i}/{len(chosen)}] {d['name']}")
        if dest.exists() and dest.stat().st_size > 0:
            print(f"    already there ({human(dest.stat().st_size)}), skipping")
            continue
        try:
            if d["mode"] == "whole":
                download_whole(d["url"], dest)
            else:
                clip(d["url"], dest, one_metre=(d["mode"] == "clip1m"))
            manifest[d["key"]] = {
                "name": d["name"],
                "url": d["url"],
                "file": d["out"],
                "bytes": dest.stat().st_size,
                "clippedTo": None if d["mode"] == "whole" else [WEST, SOUTH, EAST, NORTH],
                "accessedOn": dt.date.today().isoformat(),
            }
            manifest_path.write_text(json.dumps(manifest, indent=2))
            print(f"    saved {dest} ({human(dest.stat().st_size)})")
        except Exception as exc:  # noqa: BLE001 - keep going with the rest
            print(f"    FAILED: {exc}")
            failed.append(d["key"])

    print("\nManual step (not a single file):")
    for name, url in MANUAL:
        print(f"  - {name}\n    {url}")

    print(f"\nManifest for the data-source register: {manifest_path}")
    if failed:
        print(f"Failed: {', '.join(failed)}. Run the script again to retry only these.")
        return 1
    print("All done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
