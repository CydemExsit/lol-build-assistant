import argparse
from .pipeline import run

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--winning", required=True)
    p.add_argument("--sets", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--explain", action="store_true")
    p.add_argument("--topk", type=int, default=50)
    p.add_argument("--cover", type=float, default=0.80)
    return p.parse_args()

if __name__ == "__main__":
    args = parse_args()
    run(args.winning, args.sets, args.out, explain=args.explain, topk=args.topk, cover=args.cover)
