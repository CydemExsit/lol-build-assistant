from __future__ import annotations

import argparse

from src.data_dragon import update_static_data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", default="zh_TW")
    parser.add_argument("--out", default="data/ref/items_map.csv")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = update_static_data(
        items_path=args.out,
        language=args.lang,
        force=args.force,
    )
    print(result)


if __name__ == "__main__":
    main()
