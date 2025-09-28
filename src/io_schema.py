from dataclasses import dataclass
from typing import List

@dataclass
class WinningItem:
    name: str
    win_rate: float   # 0~1
    pick_rate: float  # 0~1
    sample_size: int

@dataclass
class BuiltSet:
    items: List[str]          # 中文裝備名 list
    set_win_rate: float       # 0~1
    set_pick_rate: float      # 0~1
    set_sample_size: int
