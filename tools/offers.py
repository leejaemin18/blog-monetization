#!/usr/bin/env python3
"""제휴 오퍼 만료 감시기 (6강: 만료된 쿠폰 정보 방치 금지).

data/offers.csv 를 읽어 유효기간이 임박했거나 지난 쿠폰/프로모션을 알려줍니다.
발행한 글의 쿠폰 정보가 만료되면 즉시 수정/삭제해야 합니다.

날짜 계산은 인자로 받은 기준일을 씁니다(기본: 오늘). 재현성을 위해 --today 로 고정 가능.

사용법:
  python3 tools/offers.py                       # 오늘 기준
  python3 tools/offers.py --days 7              # 7일 내 만료 임박만
  python3 tools/offers.py --today 2026-08-15    # 기준일 지정
"""
import argparse
import csv
import datetime as dt
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "..", "data", "offers.csv")


def parse_date(s):
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def load(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(r for r in f if not r.lstrip().startswith("#"))
        for r in reader:
            if r.get("program", "").strip():
                rows.append(r)
    return rows


def main():
    ap = argparse.ArgumentParser(description="제휴 오퍼 만료 감시")
    ap.add_argument("--days", type=int, default=14, help="만료 임박 기준(일). 기본 14")
    ap.add_argument("--today", default="", help="기준일 YYYY-MM-DD (기본: 시스템 오늘)")
    ap.add_argument("--csv", default=CSV_PATH)
    args = ap.parse_args()

    if not os.path.exists(args.csv):
        print(f"[오류] 파일 없음: {args.csv}", file=sys.stderr)
        return 1

    today = parse_date(args.today) if args.today else dt.date.today()
    if today is None:
        print(f"[오류] 잘못된 --today: {args.today}", file=sys.stderr)
        return 2

    rows = load(args.csv)
    expired, soon, ok, undated = [], [], [], []

    for r in rows:
        d = parse_date(r.get("valid_until", ""))
        label = f"{r['program']} / {r.get('product','')}".strip(" /")
        code = r.get("coupon_code", "").strip()
        tag = f"{label}" + (f"  [{code}]" if code else "")
        if d is None:
            undated.append((tag, r))
            continue
        delta = (d - today).days
        if delta < 0:
            expired.append((delta, d, tag, r))
        elif delta <= args.days:
            soon.append((delta, d, tag, r))
        else:
            ok.append((delta, d, tag, r))

    print(f"\n제휴 오퍼 만료 점검  (기준일 {today}, 임박 기준 {args.days}일)")
    print("=" * 66)

    if expired:
        print(f"\n🔴 만료됨 ({len(expired)}) — 관련 글을 즉시 수정/삭제하세요")
        for delta, d, tag, r in sorted(expired):
            print(f"   {d} ({-delta}일 지남)  {tag}")

    if soon:
        print(f"\n🟡 만료 임박 ({len(soon)})")
        for delta, d, tag, r in sorted(soon):
            print(f"   {d} (D-{delta})  {tag}")

    if undated:
        print(f"\n🔵 유효기간 미기재 ({len(undated)}) — 공식 출처에서 확인 후 valid_until 채우기")
        for tag, r in undated:
            src = r.get("official_source", "")
            print(f"   {tag}   {src}")

    if ok and not (expired or soon):
        print(f"\n✅ 임박/만료 오퍼 없음. (유효 {len(ok)}건)")

    # 오래된 확인일 경고
    stale = []
    for r in rows:
        vd = parse_date(r.get("verified_at", ""))
        if vd and (today - vd).days > 30:
            stale.append((r["program"], r.get("product", ""), vd, (today - vd).days))
    if stale:
        print(f"\n🕑 확인일이 30일 이상 지난 오퍼 ({len(stale)}) — 재확인 권장")
        for prog, prod, vd, ago in stale:
            print(f"   {prog}/{prod}  마지막 확인 {vd} ({ago}일 전)")

    print()
    return 1 if expired else 0


if __name__ == "__main__":
    sys.exit(main())
