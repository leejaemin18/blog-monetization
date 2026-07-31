#!/usr/bin/env python3
"""키워드 우선순위 점수화 (프레스런 5강 점수표 기반).

data/keywords.csv 를 읽어 각 키워드의 총점과 우선순위(A/B/C/D)를 계산합니다.
검색량은 참고 지표일 뿐이며 점수에는 반영하지 않습니다(5강 원칙: 검색량이 아니라 구매 의도).

가중치(합=1.0):
  구매의도 0.30 · 상품관련성 0.20 · 콘텐츠차별화 0.20 · 경쟁용이성 0.15 · 정책안전성 0.15
각 항목 1~5점 → 총점 1.0~5.0 스케일.

사용법:
  python3 tools/kwscore.py                 # 표 출력
  python3 tools/kwscore.py --top 10        # 상위 10개만
  python3 tools/kwscore.py --status 후보   # 특정 상태만
"""
import argparse
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "..", "data", "keywords.csv")

WEIGHTS = {
    "buy_intent": 0.30,
    "relevance": 0.20,
    "differentiation": 0.20,
    "competition_ease": 0.15,
    "policy_safety": 0.15,
}


def tier(score):
    if score >= 4.3:
        return "A"
    if score >= 3.6:
        return "B"
    if score >= 2.8:
        return "C"
    return "D"


def load_rows(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(r for r in f if not r.lstrip().startswith("#"))
        for r in reader:
            if not r.get("keyword", "").strip():
                continue
            rows.append(r)
    return rows


def score_row(r):
    try:
        total = sum(float(r[k]) * w for k, w in WEIGHTS.items())
    except (ValueError, KeyError):
        return None
    return round(total, 2)


def main():
    ap = argparse.ArgumentParser(description="키워드 우선순위 점수화")
    ap.add_argument("--top", type=int, default=0, help="상위 N개만 출력")
    ap.add_argument("--status", default="", help="특정 status만 필터")
    ap.add_argument("--csv", default=CSV_PATH, help="입력 CSV 경로")
    args = ap.parse_args()

    if not os.path.exists(args.csv):
        print(f"[오류] 파일 없음: {args.csv}", file=sys.stderr)
        return 1

    rows = load_rows(args.csv)
    scored = []
    for r in rows:
        if args.status and r.get("status", "").strip() != args.status:
            continue
        s = score_row(r)
        if s is None:
            print(f"[건너뜀] 점수 파싱 실패: {r.get('keyword')}", file=sys.stderr)
            continue
        scored.append((s, tier(s), r))

    scored.sort(key=lambda x: x[0], reverse=True)
    if args.top:
        scored = scored[: args.top]

    if not scored:
        print("점수화할 키워드가 없습니다. data/keywords.csv 를 채우세요.")
        return 0

    print(f"\n키워드 우선순위  (총 {len(scored)}개)")
    print("=" * 78)
    print(f"{'순위':<4}{'총점':<6}{'검색량':>8}  {'플랫폼':<10}키워드")
    print("-" * 78)
    for prio, tr, r in scored:
        vol = r.get("search_volume", "").strip() or "-"
        kw = r.get("keyword", "")
        plat = (r.get("platform", "") or "-")[:9]
        print(f"[{tr}]  {prio:<6}{vol:>8}  {plat:<10}{kw}")

    # 요약
    from collections import Counter
    c = Counter(tr for _, tr, _ in scored)
    print("-" * 78)
    print("등급 분포:  " + "   ".join(f"{k}:{c.get(k,0)}" for k in "ABCD"))
    print("\n권장: A·B 등급부터 작성. C는 보강 후, D는 재검토.")
    print("(총점은 구매의도 30% 가중. 검색량은 참고용입니다 — 5강 원칙)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
