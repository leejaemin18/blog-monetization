#!/usr/bin/env python3
"""발행 전 컴플라이언스 검사기.

제휴/광고 글을 발행하기 전에 정책 위반 소지를 자동으로 점검합니다.
공정위 추천·보증 심사지침 + 쿠팡 파트너스 운영정책 기준 (docs/90-정책-준수-가이드.md).

이 검사는 보조 도구입니다. 통과했다고 정책을 100% 지킨 것은 아닙니다.
최종 판단은 사람이 합니다.

사용법:
  python3 tools/compliance.py drafts/글.md
  python3 tools/compliance.py drafts/글.md --affiliate   # 제휴 글로 강제(광고표시 필수)
  echo "본문..." | python3 tools/compliance.py -

종료 코드: 오류(ERROR)가 있으면 1, 없으면 0.
"""
import argparse
import re
import sys

# (레벨, 이름, 판정 함수(text, is_affiliate) -> 위반이면 메시지 or None)
CHECKS = []


def check(level, name):
    def deco(fn):
        CHECKS.append((level, name, fn))
        return fn
    return deco


# ---- 광고 표시 (공정위) ----
DISCLOSURE_PATTERNS = [
    r"제휴\s*링크", r"수수료를?\s*(받|제공)", r"쿠팡\s*파트너스\s*활동",
    r"일정액의?\s*수수료", r"경제적\s*(대가|이해관계)",
]
BAD_DISCLOSURE_ONLY = [r"체험\s*후기", r"홍보성\s*글", r"소정의\s*원고료"]


@check("ERROR", "광고 표시 문구")
def c_disclosure(text, is_affiliate):
    if not is_affiliate:
        return None
    if not any(re.search(p, text) for p in DISCLOSURE_PATTERNS):
        return ("제휴 글인데 경제적 이해관계 공개 문구가 없습니다. "
                "'제휴 링크가 포함되며 구매 시 수수료를 받습니다' 등을 제목/첫 부분에 넣으세요.")
    return None


@check("ERROR", "광고 표시 위치(첫 부분)")
def c_disclosure_position(text, is_affiliate):
    if not is_affiliate:
        return None
    # 문서 앞부분(첫 25% 또는 첫 800자)에 공개 문구가 있는지
    head = text[: max(800, len(text) // 4)]
    if any(re.search(p, text) for p in DISCLOSURE_PATTERNS) and not any(
        re.search(p, head) for p in DISCLOSURE_PATTERNS
    ):
        return "광고 표시 문구가 본문 뒷부분에만 있습니다. 제목 또는 첫 문단으로 옮기세요."
    return None


@check("WARN", "모호한 표시 문구")
def c_vague_disclosure(text, is_affiliate):
    hits = [p for p in BAD_DISCLOSURE_ONLY if re.search(p, text)]
    strong = any(re.search(p, text) for p in DISCLOSURE_PATTERNS)
    if hits and not strong:
        return f"'{ '/'.join(h.replace(chr(92)+'s*','') for h in hits) }' 만으로는 부족합니다. 구체적인 수수료 관계를 명시하세요."
    return None


# ---- 클릭 유도 (쿠팡) ----
CLICK_BAIT = [
    r"도와주세요", r"일단\s*(눌러|클릭)", r"무조건\s*(눌러|클릭)",
    r"클릭\s*(부탁|해\s*주세요)", r"눌러야?\s*(볼|확인)", r"클릭\s*시\s*(내용|결과|정답)",
]


@check("ERROR", "클릭 유도 문구")
def c_clickbait(text, is_affiliate):
    hits = [p for p in CLICK_BAIT if re.search(p, text)]
    if hits:
        return ("무의미한 클릭 유도 문구가 있습니다(쿠팡 무효클릭 정책 위반). "
                "링크 도착지에서 무엇을 확인할 수 있는지 사실대로 설명하세요.")
    return None


@check("WARN", "콘텐츠 잠금/강제 이동")
def c_gate(text, is_affiliate):
    if re.search(r"(방문|가입|클릭)\s*(해야|하면)\s*(볼|확인|공개|해제)", text) or re.search(
        r"쿠팡\s*(방문|접속)\s*(후|해야)", text
    ):
        return "쿠팡 방문/클릭을 조건으로 콘텐츠를 잠그는 '더보기 광고' 패턴이 의심됩니다. 금지 행위입니다."
    return None


# ---- 허위/과장 ----
@check("WARN", "수익 보장 표현")
def c_income_promise(text, is_affiliate):
    if re.search(r"(무조건|반드시|누구나)\s*(월|일)?\s*\d", text) or re.search(
        r"(거뜬히|쉽게)\s*(벌|번다|법니다)", text
    ):
        return "수익 보장/과장 표현이 의심됩니다. 사례와 예측을 분리하고 결과 보장 표현을 피하세요."
    return None


# ---- 최상급/과장 (광고법 + 네이버 저품질) ----
SUPERLATIVES = [r"최고", r"무조건", r"100\s*%", r"완벽", r"유일", r"강력\s*추천", r"초특가"]


@check("WARN", "최상급/과장 표현")
def c_superlative(text, is_affiliate):
    hits = [re.search(p, text).group(0) for p in SUPERLATIVES if re.search(p, text)]
    if hits:
        return (f"최상급/과장 표현이 있습니다({', '.join(hits)}). "
                "광고법 위반·네이버 저품질 유발 소지가 있으니 구체적 사실로 바꾸세요.")
    return None


# ---- 광고 표시 확정성 (공정위) ----
@check("WARN", "광고 표시 확정 표현")
def c_disclosure_wording(text, is_affiliate):
    if not is_affiliate:
        return None
    # 대가 발생을 불확정으로 흐리는 표현
    if re.search(r"수수료를?\s*(받을\s*수\s*있|제공받을\s*수\s*있)", text):
        return "'받을 수 있음'은 불확정 표현입니다. '수수료를 제공받습니다'처럼 확정 표현으로 바꾸세요."
    if re.search(r"활동의?\s*일환입니다", text) and not re.search(
        r"수수료를?\s*(제공)?받", text
    ):
        return "'활동의 일환입니다'만으로는 대가 발생이 불명확합니다. 수수료를 받는다는 사실을 명시하세요."
    return None


# ---- 링크 도배 (네이버 저품질) ----
@check("WARN", "링크 과다/도배")
def c_link_flood(text, is_affiliate):
    # markdown 링크 + 원시 URL 대략 카운트
    md = len(re.findall(r"\]\(https?://", text))
    raw = len(re.findall(r"https?://", text))
    links = max(md, raw - md)  # 대략적 실제 링크 수
    if links >= 6:
        return (f"링크가 약 {links}개로 많습니다. 한 글당 1~3개를 권장합니다"
                "(네이버는 외부링크 반복 시 저품질 위험).")
    return None


@check("WARN", "허위 후기 소지")
def c_fake_review(text, is_affiliate):
    if re.search(r"(직접\s*써\s*보니|사용해\s*보니|제가\s*써\s*본)", text):
        return "직접 경험 표현이 있습니다. 실제 사용한 게 아니라면 삭제하세요(기만광고 위험). 사용했다면 무시."
    return None


# ---- 링크/최신성 ----
@check("WARN", "쿠폰 만료일 확인")
def c_coupon_date(text, is_affiliate):
    if re.search(r"(할인\s*코드|쿠폰|프로모션)", text) and not re.search(
        r"(만료|유효|기간|까지|\d{4}[-.년]\s*\d{1,2})", text
    ):
        return "할인/쿠폰 언급이 있으나 유효기간이 없습니다. 공식 출처의 마감일을 명시하세요."
    return None


@check("INFO", "확인일 기재")
def c_verified_date(text, is_affiliate):
    if is_affiliate and not re.search(r"(확인일|기준|업데이트)\s*[:：]?\s*\d{4}", text):
        return "확인일/기준일(예: '2026-07-31 기준')을 본문에 남기면 신뢰도와 유지보수에 좋습니다."
    return None


# ─────────────────────────────────────────────────────────────
# 집사의 발견 전용 검사 (스타일가이드 3.5·3.6·6.5 강제)
# 규칙을 문서에만 두면 지켜지지 않아서, 실제로 어겼던 것들을 검사로 옮겼다.
# ─────────────────────────────────────────────────────────────

# 3.6 A — 실제로 굳어버렸던 상투구
STOCK_PHRASES = [
    "검색하게 되는 건", "찾아보게 되는 건",
    "저도 ", "기억이 나요",
    "정리하면",
    "순으로 챙기면", "순으로 따져보면",
    "관련해서 아래 글도",
]


def _body(text):
    """HTML 주석(작성 지시문)을 뺀 본문만."""
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


@check("WARN", "굳어버린 상투구")
def c_stock_phrases(text, is_affiliate):
    body = _body(text)
    hits = [p for p in STOCK_PHRASES if p in body]
    if hits:
        return ("최근 글에서 반복된 표현입니다: "
                + ", ".join(f"'{h}'" for h in hits)
                + " — 스타일가이드 3.6 A 참고해 다른 말로 바꾸세요.")
    return None


@check("WARN", "'우리 아이' 남발")
def c_our_kid(text, is_affiliate):
    n = _body(text).count("우리 아이")
    if n > 2:
        return f"'우리 아이'가 {n}회 나옵니다(권장 2회 이하). 품종·나이·상황 표현으로 바꿔보세요."
    return None


@check("ERROR", "지어낸 1인칭 경험")
def c_fake_experience(text, is_affiliate):
    body = _body(text)
    pat = r"저(?:는|도|희)[^.\n]{0,40}(써봤|사용해\s?봤|먹여\s?봤|길러|키워\s?봤|경험)"
    if re.search(pat, body):
        return ("운영자의 실제 경험이 아니면 1인칭 체험 서술을 쓰지 않습니다. "
                "독자를 향한 서술로 바꾸거나 실제 경험일 때만 남기세요.")
    return None


@check("WARN", "분량")
def c_length(text, is_affiliate):
    n = len(_body(text).split())
    if n < 180:
        return f"본문이 {n}단어로 짧습니다. 최근 글들은 210~270단어 수준입니다."
    return None


@check("WARN", "내부 링크")
def c_internal_links(text, is_affiliate):
    n = len(re.findall(r"\]\(/", _body(text)))
    if n < 2:
        return f"내부 링크가 {n}개입니다. 2~4개를 권장합니다(스타일가이드 6.5)."
    return None


@check("INFO", "외부 dofollow 링크")
def c_external_link(text, is_affiliate):
    if not re.search(r"\]\(https?://", _body(text)):
        return "권위 있는 출처로 가는 외부 링크가 없습니다. 1개 넣으면 신뢰도에 도움이 됩니다."
    return None


@check("WARN", "깨진 한글")
def c_broken_hangul(text, is_affiliate):
    # API로 워크플로우를 돌릴 때 유니코드 이스케이프를 잘못 만들어 실제로 발생했던 사고
    suspects = ["덴탈찍", "겹총", "겹쳨", "씩기", "봽는", "자일리퇨", "헹괄", "퉘가전", "펫캐"]
    hits = [w for w in suspects if w in text]
    if hits:
        return "깨진 글자로 보이는 문자열: " + ", ".join(hits)
    return None


@check("ERROR", "미치환 토큰")
def c_tokens(text, is_affiliate):
    left = re.findall(r"__(?:LINK|IMG)\d__", text)
    if left:
        return f"자리표시자가 남아 있습니다: {', '.join(sorted(set(left)))} — 실제 배너로 채우세요."
    return None


@check("INFO", "GEO — 답변 요약")
def c_geo_summary(text, is_affiliate):
    """AI 답변 엔진에 인용되려면 뽑아 쓰기 좋은 요약이 앞에 있어야 한다."""
    body = _body(text).strip()
    head = "\n".join(body.split("\n")[:12])
    # 짧은 굵은 글씨 한 줄로 답을 먼저 던지는 형태도 요약으로 인정 (예: **분당 30회.**)
    lead_bold = re.search(r"^\*\*[^*\n]{2,40}\*\*\s*$", head, re.M)
    if lead_bold:
        return None
    if not re.search(r"(결론부터|먼저 답부터|한 줄로 말하면|요약하면|답부터)", head):
        return ("도입부에 한 문단짜리 '답' 요약이 없습니다. "
                "답변 엔진은 추출 가능한 요약을 인용합니다(GEO).")
    return None


@check("INFO", "GEO — FAQ 구조")
def c_geo_faq(text, is_affiliate):
    body = _body(text)
    if "자주 묻는 질문" in body:
        qs = len(re.findall(r"^\*\*Q[.．]", body, re.M))
        if qs == 0:
            return "FAQ 섹션이 있지만 'Q.' 형식이 아닙니다. FAQPage 스키마로 뽑으려면 형식을 맞추세요."
    return None


def detect_affiliate(text):
    kws = [r"제휴", r"쿠팡", r"파트너스", r"할인\s*코드", r"쿠폰", r"affiliate", r"Trip\.com"]
    return any(re.search(k, text, re.IGNORECASE) for k in kws)


def run(text, force_affiliate=False):
    is_aff = force_affiliate or detect_affiliate(text)
    results = []
    for level, name, fn in CHECKS:
        msg = fn(text, is_aff)
        if msg:
            results.append((level, name, msg))
    return is_aff, results


def main():
    ap = argparse.ArgumentParser(description="발행 전 컴플라이언스 검사")
    ap.add_argument("path", help="검사할 파일 경로 ('-' 는 표준입력)")
    ap.add_argument("--affiliate", action="store_true", help="제휴 글로 강제(광고표시 필수)")
    args = ap.parse_args()

    if args.path == "-":
        text = sys.stdin.read()
    else:
        try:
            with open(args.path, encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            print(f"[오류] {e}", file=sys.stderr)
            return 2

    is_aff, results = run(text, args.affiliate)

    icon = {"ERROR": "🔴", "WARN": "🟡", "INFO": "🔵"}
    print(f"\n컴플라이언스 검사  ({'제휴/광고 글' if is_aff else '일반 글'})")
    print("=" * 60)

    if not results:
        print("✅ 자동 검사 항목 통과. (사람 최종 검수는 여전히 필요)")
        print("   → checklists/발행전-체크리스트.md 확인\n")
        return 0

    errors = 0
    for level, name, msg in results:
        if level == "ERROR":
            errors += 1
        print(f"{icon[level]} [{level}] {name}")
        print(f"     {msg}\n")

    print("-" * 60)
    print(f"오류 {errors}건 · 경고 {sum(1 for l,_,_ in results if l=='WARN')}건 · "
          f"안내 {sum(1 for l,_,_ in results if l=='INFO')}건")
    if errors:
        print("🔴 오류가 있습니다. 수정 전에는 발행하지 마세요.\n")
        return 1
    print("🟡 오류는 없습니다. 경고를 확인 후 발행하세요.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
