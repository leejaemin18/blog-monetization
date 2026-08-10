#!/usr/bin/env python3
"""발행 전 AI 티 검사·교정 (humanize gate).

분류 체계 출처: epoko77-ai/im-not-ai "Humanize KR" v2.3 (MIT).
그쪽은 LLM 콜로 윤문하지만 우리 러너에는 Claude API 키가 없다. 대신 셋으로 쪼갰다.

  1. 검사   — LLM 없이 도는 결정적 지표. S1이 있으면 종료 코드 1 (발행 차단)
  2. 자동   — 뜻이 안 바뀌는 삭제만 기계가 한다 (연결어미 뒤 쉼표)
  3. 지목   — 판단이 필요한 건 줄 번호로 찍어주고 사람(또는 초안 작성자)이 고친다

임계는 그쪽 taxonomy를 그대로 쓰지 않고, **우리 글 11편을 실측해서** 잡았다.
근거는 각 검사의 주석에 있다. 실측 기준선(im-not-ai empirical-validation.md,
AI 60편 vs 2022년 이전 발행 한국어 산문 60편, 로그우도비 G² 검정):

    A가 아니라 B  AI 5.8 / 인간 0.6  (9.2배, 개인 블로그 대비 18배) — 최강 신호
    쉼표 과다      AI 49.1 / 인간 33.4 (1.5배)
    100자+ 장문    AI 8.1 / 인간 91.3 (11배) — AI가 "못 쓰는" 것

가져오지 않은 것:
  - 종결어미 다양성 z: 그쪽 문장 분리기가 표 행·불릿을 문장으로 세는 오탐.
    산문만 세면 우리 글은 45문장에 종결형 28~31종, 최빈 12%로 멀쩡하다.
  - 불릿·볼드·이모지 금지: 그쪽 장르표에도 블로그는 예외다(블로그 금기는
    기계적 "첫째/둘째"뿐). 우리는 모바일에서 훑어 읽는 글이라 오히려 필요하다.
  - A-16 대명사 규칙: 영어 원문 번역 맥락 전용. 자생 한국어엔 발동 금지.

사용법:
  python3 tools/humanize.py drafts/글.md              # 검사만
  python3 tools/humanize.py drafts/글.md --fix        # 안전한 것만 자동 수정
  python3 tools/humanize.py drafts/글.md --gate       # S1 있으면 종료 코드 1
  python3 tools/humanize.py drafts/글.md --json       # 기계 판독용
"""
import argparse
import json
import re
import sys

# ── 본문 추출 ────────────────────────────────────────────────
# 검사 대상에서 빼야 하는 것: 작성 지시 주석, 코드블록, 치환 토큰,
# 표·헤딩·불릿(문장이 아니다), URL.

_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_FENCE_RE = re.compile(r"```.*?```", re.S)
_TOKEN_RE = re.compile(r"\[\[[^\]]+\]\]")
_URL_RE = re.compile(r"https?://\S+")


def body(text):
    """주석·코드·토큰·URL을 뺀 본문. 줄 수는 보존한다(줄 번호 보고용)."""
    def blank(m):
        return re.sub(r"[^\n]", " ", m.group(0))
    t = _COMMENT_RE.sub(blank, text)
    t = _FENCE_RE.sub(blank, t)
    t = _TOKEN_RE.sub(blank, t)
    t = _URL_RE.sub(blank, t)
    return t


_STRUCT_LINE_RE = re.compile(r"^\s*(?:#{1,6}\s|>|\||[-*+]\s|\d+[.)]\s)")


def prose(text):
    """산문만. 헤딩·표·불릿을 뺀다 — 문장 통계용."""
    return "\n".join(
        "" if _STRUCT_LINE_RE.match(ln) else ln for ln in body(text).split("\n")
    )


_SENT_SPLIT_RE = re.compile(r"(?<=[\.!?])\s+")


def sentences(text):
    out = []
    for s in _SENT_SPLIT_RE.split(prose(text)):
        s = s.strip()
        if len(s) > 8 and re.search(r"[가-힣]", s):
            out.append(s)
    return out


def _lines_of(text, pattern):
    """패턴이 걸린 (줄번호, 발췌) 목록."""
    hits = []
    for i, ln in enumerate(body(text).split("\n"), 1):
        for m in pattern.finditer(ln):
            a, b = max(0, m.start() - 22), min(len(ln), m.end() + 16)
            hits.append((i, ("…" if a else "") + ln[a:b].strip() + ("…" if b < len(ln) else "")))
    return hits


# ── 검사 ─────────────────────────────────────────────────────
FINDINGS = []


def finding(code, sev, title):
    def deco(fn):
        FINDINGS.append((code, sev, title, fn))
        return fn
    return deco


# C-11 연결어미 뒤 쉼표.
# im-not-ai 임계 그대로: 6회+ S1 / 3~5회 S2 (KatFish 에세이 인간 4.10% vs AI 19.83%).
# 우리 글 11편은 전부 5~8회였다.
#
# '고' 는 명사 끝소리로도 흔해서(사고, 광고, 참고…) 그쪽 정규식은 오탐이 난다.
# 우리는 어절 전체를 보고 명사를 걸러낸다.
_NOUN_GO = {
    "사고", "광고", "참고", "보고", "신고", "경고", "예고", "충고", "창고", "냉장고",
    "중고", "최고", "원고", "고", "생각고", "미고", "삼고",
}
_ENDING_COMMA_RE = re.compile(r"(\S*?)((?:지만|면서|으며|아서|어서|고|며))\s*,")


def _ending_comma_hits(text):
    hits = []
    for i, ln in enumerate(body(text).split("\n"), 1):
        for m in _ENDING_COMMA_RE.finditer(ln):
            word = (m.group(1) + m.group(2))
            if m.group(2) in ("고", "며") and word in _NOUN_GO:
                continue          # 명사다 — 쉼표를 지우면 안 된다
            if m.group(2) in ("고", "며") and len(word) < 2:
                continue          # 한 글자면 판단 불가 — 손대지 않는다
            a = max(0, m.start() - 22)
            hits.append((i, m.start(), m.end(),
                         ("…" if a else "") + ln[a:m.end() + 14].strip() + "…"))
    return hits


@finding("C-11", "S1", "연결어미 뒤 쉼표")
def f_ending_comma(text):
    hits = _ending_comma_hits(text)
    n = len(hits)
    if n < 3:
        return None
    return {
        "count": n,
        "severity": "S1" if n >= 6 else "S2",
        "message": (f"'~고, ~지만, ~어서,' 처럼 연결어미 뒤 쉼표가 {n}번. "
                    "한국어에선 대부분 없어도 되는데 AI가 영어 습관대로 찍는다. "
                    "뜻이 안 바뀌니 --fix 로 지울 수 있다."),
        "hits": [(h[0], h[3]) for h in hits],
        "fixable": True,
    }


# C-8 'A가 아니라 B' 대구.
# im-not-ai 실측에서 taxonomy 전체 최강 신호 (AI 5.8 vs 인간 0.6, G²=41.7).
# 우리 글은 6편 전부에 있었고 3편은 3회씩, 그것도 매번 소제목 결론 자리였다.
_ANTITHESIS_RE = re.compile(r"(?:가|이)\s*아니라|이기\s*이전에|이기보다|라기보다")


@finding("C-8", "S1", "'A가 아니라 B' 대구 반복")
def f_antithesis(text):
    hits = _lines_of(text, _ANTITHESIS_RE)
    n = len(hits)
    if n < 2:
        return None
    return {
        "count": n,
        "severity": "S1" if n >= 3 else "S2",
        "message": (f"'~가 아니라 ~' 구문이 {n}번. AI 글 판별에서 가장 센 신호다"
                    "(AI가 사람보다 9.2배, 개인 블로그 대비 18배). "
                    "한 번만 남기고 나머지는 그냥 단언으로 바꾼다."),
        "hits": hits,
        "fixable": False,
    }


# E-1 장문 결핍. AI가 과다한 게 아니라 '못 쓰는' 축.
# 기준선: AI 8.1 / 개인 블로그 27.7 / 출판 산문 91.3 (1000문장당).
# 우리 11편 평균 20.1, 그중 6편은 100자+ 문장이 아예 0개였다.
# 처방이 안전하다 — 인접 문장을 잇기만 하고 내용은 더하지 않는다.
@finding("E-1", "S2", "장문 결핍")
def f_long_sentence(text):
    ss = sentences(text)
    if len(ss) < 15:
        return None
    long_ = [s for s in ss if len(s) >= 100]
    per1k = len(long_) / len(ss) * 1000
    if per1k >= 25:
        return None
    return {
        "count": len(long_),
        "severity": "S2" if len(long_) == 0 else "S3",
        "message": (f"100자 넘는 문장이 {len(long_)}개 ({per1k:.0f}/1000문장). "
                    "짧은 문장만 이어지면 리듬이 없어 AI 글처럼 읽힌다"
                    "(기준: AI 8 · 사람 블로그 28). "
                    "인접한 두 문장을 이어 긴 호흡을 하나 만든다 — 내용은 더하지 말 것."),
        "hits": [],
        "fixable": False,
    }


# A 계열 번역투. 현재 우리 글엔 0건 — 회귀 방지용.
_TRANSLATIONESE = [
    (r"되어진|되어졌|여진다|보여진|쓰여진|잊혀진", "이중 피동 → '~된다'"),
    (r"에\s*의(?:해|하여)\s+\S{0,10}?(?:되|받|당하)", "'~에 의해' 피동 → 행위자를 주어로"),
    (r"가지고\s*있(?:다|어|습니다|어요)", "'가지고 있다' → '~가 있다/~이 강하다'"),
    (r"에\s*있어서?\s", "'~에 있어서' → '~에서'"),
    (r"에서의|에로의|으로의|에의|으로부터의", "이중 조사 → 절·구로 풀어쓰기"),
]


@finding("A", "S1", "번역투")
def f_translationese(text):
    b = body(text)
    hits, tips = [], []
    for pat, tip in _TRANSLATIONESE:
        h = _lines_of(text, re.compile(pat))
        if h:
            hits += h
            tips.append(tip)
    if not hits:
        return None
    return {"count": len(hits), "severity": "S1",
            "message": "영어 번역투 — " + " / ".join(tips),
            "hits": hits, "fixable": False}


# D 계열 AI 관용구. 결산·의의 과장 lexicon.
_AI_SIGNATURE_RE = re.compile(
    r"결론적으로|시사하는\s*바|주목할\s*만|다음과\s*같습니다|크게\s*세\s*가지"
    r"|중요한\s*역할을\s*합니다|혁신적|획기적|전례\s*없는|필수적입니다"
)


@finding("D", "S2", "AI 관용구")
def f_ai_signature(text):
    hits = _lines_of(text, _AI_SIGNATURE_RE)
    if not hits:
        return None
    return {"count": len(hits), "severity": "S2",
            "message": "AI가 유난히 좋아하는 상투구다. 삭제하거나 구체적 사실로 바꾼다.",
            "hits": hits, "fixable": False}


# G-2 이중 완곡.
_HEDGE_RE = re.compile(r"(?:할|될|일)\s*수\s*있을\s*(?:것으로|것\s*같)|가능성이\s*있을\s*수\s*있")


@finding("G-2", "S2", "이중 완곡")
def f_hedging(text):
    hits = _lines_of(text, _HEDGE_RE)
    if not hits:
        return None
    return {"count": len(hits), "severity": "S2",
            "message": "'~할 수 있을 것으로 보인다' 식 이중 완곡. 완곡은 하나만 남긴다.",
            "hits": hits, "fixable": False}


# H-1 문두 접속사. 해요체 블로그라 임계를 그쪽(5회+)보다 느슨하게 6회로 뒀다.
_CONJ_RE = re.compile(r"^\s*(?:또한|따라서|즉|나아가|아울러|게다가|더욱이|그러므로)[\s,]", re.M)


@finding("H-1", "S2", "문두 접속사 과다")
def f_conjunction(text):
    hits = _lines_of(text, _CONJ_RE)
    if len(hits) < 6:
        return None
    return {"count": len(hits), "severity": "S2",
            "message": f"문두 접속사가 {len(hits)}번. 흐름은 문장 내용이 잡게 두고 대부분 지운다.",
            "hits": hits, "fixable": False}


# ── 어휘 회귀 방지 ───────────────────────────────────────────
# 지금 우리 글에 0건인 패턴들. 하나라도 나오면 문체가 흘러내리기 시작한 것이다.
# 임계가 0이라 조용히 있다가, 새 글에 섞이는 순간 잡는다.
_ZERO_GUARD = [
    ("A-1", r"에\s*대(?:해|하여)\s", "'~에 대해' → 목적격 조사로 직결"),
    ("A-4", r"라는\s*점에서", "'~라는 점에서' → '~서', '~라는 이유로'"),
    ("A-5", r"와\s*관련(?:하여|된|해)", "'~와 관련하여' → '~에', '~의'"),
    ("A-6", r"에\s*기반(?:하여|한)|을\s*바탕으로", "'~에 기반하여' → '~로', '~을 보고'"),
    ("A-12", r"만들어지|이루어지", "자동 피동 → 능동으로"),
    ("A-15", r"보여줍니다|보여준다|가져옵니다|가져온다", "추상 주어 + 만능 동사 → 구체 주어로"),
    ("B-4", r"라고\s*알려진|로\s*일컬어지", "'~라고 알려진' → 출처를 밝히거나 삭제"),
    ("C-1", r"첫째|둘째|셋째", "기계적 '첫째/둘째' → 소제목이나 서술로"),
    ("C-6", r"이\s*(?:섹션|장|글)에서는", "섹션 안내문 → 삭제하고 본문 바로"),
    ("C-9", r"^\s*\d\)\s", "'1) 2) 3)' 인덱싱 → 본문에 녹이기"),
    ("C-10", r"^#{2,3} [^\n:]{2,30}:\s", "콜론 부제 헤딩 'X: Y' → 단일 명사구로"),
    ("D-5", r"(?:기술|시대|시장|데이터)(?:이|가)\s*(?:묻|말하|요구하|부르)", "의인화 주어 → 사람·기관 주어로"),
    ("D-6", r"할\s*때입니다|시점입니다|순간입니다", "'~할 때입니다' 결말 공식 → 구체 동사 단언"),
    ("F-2", r"매우\s*중요한|정말\s*중요한|아주\s*큰", "동의어 이중 수식 → 하나만"),
    ("G-1", r"로\s*보입니다|판단됩니다|여겨집니다|인\s*듯합니다", "추측 종결 → 단언 가능한 곳은 단언"),
    ("H-2", r"^\s*(?:하지만|그러나)[\s,]", "문두 역접 → 문장 안으로 흡수"),
    ("H-3", r"^\s*이는\s|이\s*점에서|이\s*관점에서", "'이는 ~' 메타 진입 → 본문에 녹이기"),
    ("I-1", r"것입니다|것이다", "'것이다' 종결 → '~다' 확정 서술"),
    ("I-2", r"주목할\s*점|중요한\s*점(?:은|이)", "형식명사 강조 → 'X는 ~다' 직설"),
]


@finding("ZERO", "S2", "새로 섞인 AI 어휘")
def f_zero_guard(text):
    hits, tips = [], []
    for code, pat, tip in _ZERO_GUARD:
        h = _lines_of(text, re.compile(pat, re.M))
        if h:
            hits += h
            tips.append(f"{code} {tip}")
    if not hits:
        return None
    return {"count": len(hits), "severity": "S2",
            "message": ("지금까지 우리 글에 한 번도 없던 표현이 들어왔습니다 — "
                        + " / ".join(tips)),
            "hits": hits, "fixable": False}


# ── 문서 단위 지표 ───────────────────────────────────────────
# 낱개 표현이 아니라 글 전체 분포로만 보이는 것들.

# C-12 쉼표 포함률. 인간 26% vs AI 61%. 우리 11편은 6~28%로 건강하다 — 방어선만 둔다.
@finding("C-12", "S2", "쉼표 과다")
def f_comma_rate(text):
    ss = sentences(text)
    if len(ss) < 15:
        return None
    rate = sum(1 for s in ss if "," in s) / len(ss)
    if rate < 0.45:
        return None
    return {"count": int(rate * 100), "severity": "S2",
            "message": (f"쉼표가 들어간 문장이 {rate:.0%}입니다(사람 평균 26%, AI 61%). "
                        "일부는 마침표로 끊거나 쉼표를 그냥 지우세요."),
            "hits": [], "fixable": False}


# E-2 같은 종결어미 연속. 우리는 대개 2~3인데 한 편이 4였다.
@finding("E-2", "S2", "같은 종결어미 연속")
def f_ending_streak(text):
    ss = sentences(text)
    ends = [m.group(1) for m in
            (re.search(r"([가-힣]{2})[\.!?]\s*$", s) for s in ss) if m]
    best = cur = 1
    where = 0
    for i, (a, b) in enumerate(zip(ends, ends[1:])):
        cur = cur + 1 if a == b else 1
        if cur > best:
            best, where = cur, i
    if best < 4:
        return None
    return {"count": best, "severity": "S2",
            "message": (f"'…{ends[where]}.' 로 끝나는 문장이 {best}번 연달아 나옵니다. "
                        "하나는 다른 종결형으로 바꾸세요(거든요 · 죠 · 명사 종결 · 물음)."),
            "hits": [], "fixable": False}


# F-4 한자어 명사화 누적. 그쪽 임계 12회. 우리 최대 7회 — 방어선.
@finding("F-4", "S2", "명사화 남발")
def f_nominalizer(text):
    n = len(re.findall(r"[가-힣]{2,}(?:성|적|화)(?=[\s을를이가은는의에로,\.])", body(text)))
    if n < 12:
        return None
    return {"count": n, "severity": "S2",
            "message": f"'~성/~적/~화' 명사화가 {n}번입니다. 동사·형용사로 풀어쓰세요.",
            "hits": [], "fixable": False}


# A-10 "~할 수 있다" 남발. 해요체 블로그엔 자연스러워서 임계를 6으로 뒀다(우리 최대 5).
@finding("A-10", "S3", "'~할 수 있다' 남발")
def f_can(text):
    hits = _lines_of(text, re.compile(r"(?:할|될|볼|쓸|들|먹일)\s*수\s*있"))
    if len(hits) < 6:
        return None
    return {"count": len(hits), "severity": "S3",
            "message": (f"'~할 수 있다'가 {len(hits)}번. 단언해도 되는 곳은 단언하세요"
                        "('높일 수 있어요' → '높아져요')."),
            "hits": hits, "fixable": False}


# J-2 따옴표 강조. 우리 최대 8 — 임계 6.
@finding("J-2", "S3", "따옴표 강조 과다")
def f_quotes(text):
    hits = _lines_of(text, re.compile(r'"[^"\n]{1,30}"|"[^"\n]{1,30}"'))
    if len(hits) < 6:
        return None
    return {"count": len(hits), "severity": "S3",
            "message": (f"따옴표 강조가 {len(hits)}번. 진짜 인용만 남기고 평서문으로 바꾸세요."),
            "hits": hits, "fixable": False}


# C-4 계열 — '**라벨** — 설명' 골격 반복.
# 대시 자체는 문제가 아니다(우리 88개 중 72개가 목록 라벨이고 읽기 편하다).
# 문제는 매 글이 같은 뼈대로 조립된다는 것이다. 3.5 D "기계적으로 붙는 블록" 위반.
_LABEL_DASH_RE = re.compile(r"^\s*(?:[-*+]\s|\d+[.)]\s|[①-⑩]\s*)?\*\*[^*\n]{1,24}\*\*\s*—", re.M)


@finding("C-4", "S3", "'**라벨** — 설명' 골격 반복")
def f_label_skeleton(text):
    hits = _lines_of(text, _LABEL_DASH_RE)
    if len(hits) < 8:
        return None
    return {"count": len(hits), "severity": "S3",
            "message": (f"'**라벨** — 설명' 형태가 {len(hits)}번. 글마다 같은 뼈대로 조립되면 "
                        "양산형으로 읽힙니다(3.5 D). 일부는 산문 문단이나 표로 바꾸세요."),
            "hits": hits, "fixable": False}


# ── 자동 수정 (삭제만) ────────────────────────────────────────
def fix(text):
    """뜻이 안 바뀌는 것만 고친다. 지금은 연결어미 뒤 쉼표 삭제 하나뿐."""
    lines = text.split("\n")
    blines = body(text).split("\n")
    changes = []
    for i, bln in enumerate(blines):
        for m in reversed(list(_ENDING_COMMA_RE.finditer(bln))):
            word = m.group(1) + m.group(2)
            if m.group(2) in ("고", "며") and (word in _NOUN_GO or len(word) < 2):
                continue
            # 원본 줄의 같은 위치를 직접 자른다(주석 처리로 길이가 보존돼 있다)
            src = lines[i]
            cut = m.end() - 1                     # 쉼표 위치
            if src[cut] != ",":
                continue                          # 위치가 어긋나면 손대지 않는다
            lines[i] = src[:cut] + src[cut + 1:]
            changes.append((i + 1, word + ","))
    return "\n".join(lines), changes


# ── 실행 ─────────────────────────────────────────────────────
def analyze(text):
    out = []
    for code, _sev, title, fn in FINDINGS:
        r = fn(text)
        if r:
            r.update(code=code, title=title)
            out.append(r)
    return out


def main():
    ap = argparse.ArgumentParser(description="발행 전 AI 티 검사·교정")
    ap.add_argument("path")
    ap.add_argument("--fix", action="store_true", help="안전한 것만 자동 수정(파일을 덮어씀)")
    ap.add_argument("--gate", action="store_true", help="S1이 있으면 종료 코드 1")
    ap.add_argument("--json", action="store_true", help="기계 판독용 출력")
    a = ap.parse_args()

    text = sys.stdin.read() if a.path == "-" else open(a.path, encoding="utf-8").read()

    if a.fix:
        new, changes = fix(text)
        if changes:
            if a.path != "-":
                with open(a.path, "w", encoding="utf-8") as f:
                    f.write(new)
            print(f"쉼표 {len(changes)}개 삭제:")
            for ln, w in changes:
                print(f"   {a.path}:{ln}  {w} → {w[:-1]}")
        else:
            print("자동으로 고칠 것 없음.")
        text = new

    res = analyze(text)

    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 1 if (a.gate and any(r["severity"] == "S1" for r in res)) else 0

    ss = sentences(text)
    print(f"\nAI 티 검사 — {a.path}   (산문 {len(ss)}문장)")
    print("=" * 62)
    if not res:
        print("통과. 걸린 패턴 없음.\n")
        return 0

    icon = {"S1": "🔴 S1", "S2": "🟡 S2", "S3": "🔵 S3"}
    for r in res:
        print(f"{icon[r['severity']]}  [{r['code']}] {r['title']} — {r['count']}건")
        print(f"      {r['message']}")
        for ln, snippet in r["hits"][:6]:
            print(f"      · {a.path}:{ln}  {snippet}")
        if len(r["hits"]) > 6:
            print(f"      · … 외 {len(r['hits']) - 6}건")
        print()

    s1 = sum(1 for r in res if r["severity"] == "S1")
    print("-" * 62)
    print(f"S1 {s1}건 · S2 {sum(1 for r in res if r['severity']=='S2')}건")
    if s1 and a.gate:
        print("🔴 S1이 있어 발행을 막습니다. 고치고 다시 돌리세요.\n")
        return 1
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
