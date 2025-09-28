from __future__ import annotations
import argparse, subprocess, sys, pathlib

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--heroes", nargs="+", required=True, help="e.g. varus ezreal lux jhin")
    ap.add_argument("--mode", default="aram")
    ap.add_argument("--tier", default="d2_plus")
    ap.add_argument("--patch", default="7")
    ap.add_argument("--lang", default="zh_tw")
    args = ap.parse_args()

    for h in args.heroes:
        print(f"==> {h}")
        subprocess.run([
            sys.executable, "src/scrape_lolalytics.py",
            "--hero", h,
            "--mode", args.mode,
            "--tier", args.tier,
            "--patch", args.patch,
            "--lang", args.lang,
            "--winning_out", f"data/raw/{h}_{args.mode}_{args.tier}_{args.patch}d_winning.csv",
            "--sets_out",    f"data/raw/{h}_{args.mode}_{args.tier}_{args.patch}d_sets.csv",
            "--headless"
        ], check=False)

if __name__ == "__main__":
    main()
