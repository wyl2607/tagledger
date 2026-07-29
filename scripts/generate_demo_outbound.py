#!/usr/bin/env python3
"""Create a generic outbound sample workbook for portfolio demos.

Safe to re-run: overwrites data/outbound/outbound_today.xlsx only.
Does not touch any company-named exports that may exist locally.
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "outbound" / "outbound_today.xlsx"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()

    shipping = wb.active
    shipping.title = "shipping"
    shipping.append(["order_no", "qty", "part_code", "part_name"])
    shipping.append(["SO-DEMO-001", 4, "PART-AA-001", "Demo bracket"])
    shipping.append(["SO-DEMO-001", 2, "PART-BB-002", "Demo fastener kit"])
    shipping.append(["SO-DEMO-002", 1, "PART-CC-003", "Demo controller"])

    cutting = wb.create_sheet("cutting")
    cutting.append(["order_no", "qty", "part_code", "part_name", "location"])
    cutting.append(["SO-DEMO-001", 2, "PART-AA-001", "Demo bracket", "A-01-01"])
    cutting.append(["SO-DEMO-001", 2, "PART-AA-001", "Demo bracket", "A-01-02"])
    cutting.append(["SO-DEMO-001", 2, "PART-BB-002", "Demo fastener kit", "B-02-01"])
    cutting.append(["SO-DEMO-002", 1, "PART-CC-003", "Demo controller", "C-03-01"])

    wb.save(OUT)
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
