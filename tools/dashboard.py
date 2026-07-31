#!/usr/bin/env python3
"""프로젝트 진행 대시보드.

niche.yaml, content_ledger.csv, metrics.csv, offers.csv 를 종합해
현재 어디까지 왔고 다음에 뭘 해야 하는지 한 화면에 보여줍니다.

외부 의존성 없음(YAML은 간단 파서 자체 구현). 파이썬 3.9+.

사용법:
  python3 tools/dashboard.py
"""
import csv
import datetime as dt
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")


def load_yaml_flat(path):
    """의존성 없이 쓰기 위한 최소 YAML 리더.
    중첩 키를 'a.b.c' 형태로 평탄화. 리스트/복잡 구조는 무시하고 스칼라만 취함."""
    if not os.path.exists(path):
        return {}
    out = {}
    stack = []  # (indent, key)
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            indent = len(line) - len(line.lstrip(" "))
            s = line.strip()
            if s.startswith("- "):
                continue
            if ":" not in s:
                continue
            key, _, val = s.partition(":")
            key = key.strip()
            val = val.split(" #", 1)[0].strip().strip('"').strip("'")
            while stack and stack[-1][0] >= indent:
                stack.pop()
            full = ".".join([k for _, k in stack] + [key])
            if val == "":
                stack.append((indent, key))
            else:
                out[full] = val
    return out


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(r for r in f if not r.lstrip().startswith("#")))


def bar(done, total, width=24):
    if total == 0:
        return "[" + " " * width + "] 0/0"
    filled = int(width * done / total)
    return "[" + "█" * filled + "·" * (width - filled) + f"] {done}/{total}"


def phase_status(cfg):
    """설정 기반으로 단계별 완료 여부 추정."""
    def truthy(k):
        return str(cfg.get(k, "")).lower() in ("true", "1", "yes")

    phases = []
    phases.append(("Day0 사전준비·예산",
                   truthy("budget.can_sustain_6_months") and bool(cfg.get("adsense_blog.topic"))))
    phases.append(("Day1-2 1번 블로그 개설",
                   bool(cfg.get("adsense_blog.created_at"))))
    se = [truthy(f"adsense_blog.search_engines_registered.{s}") for s in ("naver", "google", "bing", "daum")]
    phases.append(("  └ 검색엔진 등록(1번)", all(se)))
    phases.append(("Day3-5 애드센스 검토요청",
                   bool(cfg.get("adsense_blog.adsense_review_requested_at"))))
    phases.append(("Day5 2번 블로그 개설",
                   bool(cfg.get("affiliate_blog.created_at"))))
    return phases


def main():
    cfg = load_yaml_flat(os.path.join(DATA, "niche.yaml"))
    ledger = read_csv(os.path.join(DATA, "content_ledger.csv"))
    metrics = read_csv(os.path.join(DATA, "metrics.csv"))
    offers = read_csv(os.path.join(DATA, "offers.csv"))

    print("\n" + "=" * 56)
    print("  블로그 수익화 프로젝트 — 진행 대시보드")
    print("=" * 56)

    start = cfg.get("project.start_date", "")
    if start:
        try:
            d0 = dt.datetime.strptime(start, "%Y-%m-%d").date()
            print(f"  시작일 {start}  (D+{(dt.date.today()-d0).days})")
        except ValueError:
            print(f"  시작일 {start}")

    # 단계 진행
    print("\n▶ 단계 진행")
    for name, done in phase_status(cfg):
        print(f"   {'✅' if done else '⬜'} {name}")

    # 애드센스 상태
    st = cfg.get("adsense_blog.adsense_status", "미시작")
    print(f"\n▶ 애드센스 상태: {st}")

    # 콘텐츠
    print("\n▶ 콘텐츠 대장")
    if ledger:
        from collections import Counter
        by_status = Counter(r.get("status", "?").strip() for r in ledger)
        by_type = Counter(r.get("type", "?").strip() for r in ledger)
        published = by_status.get("발행", 0)
        print(f"   총 {len(ledger)}건 · 발행 {published}")
        print("   상태: " + "  ".join(f"{k}={v}" for k, v in by_status.items()))
        print("   유형: " + "  ".join(f"{k}={v}" for k, v in by_type.items()))
        # 광고표시 누락 경고
        missing = [r for r in ledger if r.get("type") == "제휴"
                   and r.get("ad_disclosure", "").strip().lower() != "y"
                   and r.get("status") in ("예약", "발행")]
        if missing:
            print(f"   🔴 제휴 글 {len(missing)}건에 광고표시(y) 미기록 — 확인 필요")
    else:
        print("   (아직 없음) data/content_ledger.csv 에 기록하세요")

    # 성과
    print("\n▶ 성과 (내 데이터 기준)")
    if metrics:
        total_rev = 0
        total_posts = 0
        for r in metrics:
            try:
                total_rev += int(float(r.get("revenue_won", 0) or 0))
                total_posts += int(float(r.get("posts_published", 0) or 0))
            except ValueError:
                pass
        target = cfg.get("goals.monthly_revenue_target_won", "0")
        try:
            target_n = int(float(target))
        except ValueError:
            target_n = 0
        print(f"   누적 수익 {total_rev:,}원 · 누적 발행 {total_posts}건")
        if target_n:
            print(f"   월 목표 {target_n:,}원  " + bar(min(total_rev, target_n), target_n))
    else:
        print("   (아직 없음)")

    # 오퍼 만료 요약
    print("\n▶ 제휴 오퍼")
    if offers:
        today = dt.date.today()
        exp = 0
        soon = 0
        for r in offers:
            v = (r.get("valid_until") or "").strip()
            try:
                d = dt.datetime.strptime(v.replace(".", "-").replace("/", "-"), "%Y-%m-%d").date()
                delta = (d - today).days
                if delta < 0:
                    exp += 1
                elif delta <= 14:
                    soon += 1
            except ValueError:
                pass
        print(f"   등록 {len(offers)}건 · 만료 {exp} · 임박(14일) {soon}")
        if exp or soon:
            print("   → python3 tools/offers.py 로 상세 확인")
    else:
        print("   (아직 없음)")

    # 다음 액션 제안
    print("\n▶ 다음 할 일")
    for name, done in phase_status(cfg):
        if not done:
            nxt = name.strip().lstrip("└ ")
            print(f"   → {nxt}")
            break
    else:
        print("   → 일일 루틴 진행 (playbook/일일루틴.md)")

    print("\n" + "=" * 56 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
