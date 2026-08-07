# 네이버 지식iN 질문을 수집해 research/ 폴더에 저장하는 스크립트 (반려동물 블로그용).
# 제이로그(jaylog) 저장소의 kin_research.py를 가져와 반려동물 주제에 맞게 조정했다.
#
# 사용: 환경변수 NAVER_CLIENT_ID, NAVER_CLIENT_SECRET, KEYWORDS(쉼표 구분),
#       DISPLAY(선택, 기본 30), CHECK_ANSWERS(선택, y면 미답변 여부 확인)
# 네이버가 구 개발자센터/신 클라우드 API HUB 두 방식이 있어, 되는 조합을 자동 탐지한다.
#
# ※ 읽기 전용이다. 답변 자동 등록은 하지 않는다(네이버 운영정책상 매크로 금지).
import os, re, json, html, time, datetime, urllib.parse, urllib.request

CID = os.environ["NAVER_CLIENT_ID"].strip()
CSEC = os.environ["NAVER_CLIENT_SECRET"].strip()
KEYWORDS = [k.strip() for k in os.environ.get("KEYWORDS", "노령견 사료").split(",") if k.strip()]
DISPLAY = min(int(os.environ.get("DISPLAY", "30") or 30), 100)
CHECK = (os.environ.get("CHECK_ANSWERS", "y") or "y").lower().startswith("y")
KST = datetime.timezone(datetime.timedelta(hours=9))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"

# (엔드포인트, 헤더) 후보 — 위에서부터 시도해 처음 성공하는 조합 사용
# 1순위: 신규 NAVER API HUB (네이버클라우드), 2순위: 구 개발자센터
COMBOS = [
    ("https://naverapihub.apigw.ntruss.com/search/v1/kin",
     {"X-NCP-APIGW-API-KEY-ID": CID, "X-NCP-APIGW-API-KEY": CSEC}),
    ("https://openapi.naver.com/v1/search/kin.json",
     {"X-Naver-Client-Id": CID, "X-Naver-Client-Secret": CSEC}),
]

working = None  # 성공한 (url, headers)
errors = []


def search(keyword):
    """최신순으로 지식iN 질문 검색. 정렬 미지원 시 정확도순으로 한 번 더 시도."""
    global working
    combos = [working] if working else COMBOS
    for url, headers in combos:
        for sort in ("date", "sim"):
            qs = urllib.parse.urlencode(
                {"query": keyword, "display": DISPLAY, "sort": sort, "format": "json"})
            req = urllib.request.Request(f"{url}?{qs}", headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=30) as res:
                    data = json.load(res)
                if working is None:
                    working = (url, headers)
                    print(f"[인증 OK] {url} / 헤더 {list(headers)[0]} / 정렬 {sort}")
                return data.get("items", [])
            except urllib.error.HTTPError as e:
                body = e.read()[:200].decode("utf-8", "replace")
                errors.append(f"{url} (sort={sort}) → HTTP {e.code}: {body}")
            except Exception as e:
                errors.append(f"{url} (sort={sort}) → {type(e).__name__}: {e}")
    return None


def clean(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def answer_state(url):
    """질문 페이지를 열어 미답변 여부를 추정한다(정확하지 않을 수 있음)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as res:
            t = res.read().decode("utf-8", "replace")
    except Exception:
        return "❓ 확인불가"
    if ("아직 등록된 답변이 없" in t) or ("답변이 없습니다" in t):
        return "🟢 미답변"
    m = (re.search(r'"answerCount"\s*:\s*([0-9]+)', t)
         or re.search(r"답변\s*<em[^>]*>\s*([0-9]+)", t)
         or re.search(r"답변수[^0-9]{0,10}([0-9]+)", t))
    if m:
        n = int(m.group(1))
        return "🟢 미답변" if n == 0 else f"⚪ 답변 {n}개"
    return "⚪ 답변있음(추정)"


def main():
    now = datetime.datetime.now(KST)
    collected = []
    seen = set()
    for kw in KEYWORDS:
        items = search(kw)
        if items is None:
            print("::error::지식iN API 호출 실패. 시도 내역:")
            for e in errors:
                print("  -", e)
            raise SystemExit(1)
        n = 0
        for it in items:
            link = it.get("link", "")
            if not link or link in seen:
                continue
            seen.add(link)
            collected.append({"kw": kw, "title": clean(it.get("title")),
                              "desc": clean(it.get("description")), "link": link})
            n += 1
        print(f"[수집] {kw}: {n}건")

    # 미답변 우선 정렬 (답변 없는 질문이 답변 달기 좋고 채택 확률도 높다)
    for it in collected:
        it["state"] = answer_state(it["link"]) if CHECK else ""
        if CHECK:
            time.sleep(0.4)
    order = {"🟢": 0, "❓": 1, "⚪": 2}
    collected.sort(key=lambda x: order.get((x["state"][:1] or "⚪"), 2))

    lines = [f"# 지식iN 질문 조사 — {now:%Y-%m-%d %H:%M} (KST)", "",
             f"키워드: {', '.join(KEYWORDS)} / 키워드당 최대 {DISPLAY}건",
             "", "> 🟢 미답변 우선 정렬. 답변은 사람이 직접 등록한다(자동등록 금지).", ""]
    for i, it in enumerate(collected, 1):
        lines.append(f"### [{i}] {it['state']} · {it['kw']}")
        lines.append(f"**{it['title']}**")
        if it["desc"]:
            lines.append(f"> {it['desc'][:200]}")
        lines.append(f"{it['link']}")
        lines.append("")
        print(f"[{i}] {it['state']}  {it['title'][:50]}")
        print(f"     {it['link']}")

    green = sum(1 for it in collected if it["state"].startswith("🟢"))
    summary = f"총 {len(collected)}건 (미답변 추정 {green}건)"
    lines.insert(3, f"수집 결과: {summary}")
    os.makedirs("research", exist_ok=True)
    path = f"research/지식인-{now:%Y%m%d-%H%M}.md"
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n=== 저장: {path} — {summary} ===")
    if CHECK:
        print("※ 미답변 판정은 페이지를 열어 추정한 값입니다. ❓는 직접 확인하세요.")


if __name__ == "__main__":
    main()
