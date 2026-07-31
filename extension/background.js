// Service worker (MV3) — 개인용 직접 모드.
//
// 두 가지 경로를 지원한다:
//  1) 직접 모드(기본): 사이드패널 설정에 저장한 내 Anthropic API 키로 api.anthropic.com을 바로 호출.
//     서버 필요 없음. 키는 이 컴퓨터의 chrome.storage.local 에만 저장된다.
//     ⚠️ 이 방식은 "개인용·미배포" 확장에서만 안전하다. 스토어에 올리거나 남에게 배포하지 말 것.
//  2) 프록시 모드(선택): 설정에서 프록시 URL을 넣으면 그쪽으로 위임. 키는 프록시가 쥔다.
//
// 발행 기능은 없다. 결과는 초안일 뿐이며 사람이 검수 후 수동 발행한다.

const ANTHROPIC_URL = "https://api.anthropic.com/v1/messages";
const DEFAULT_MODEL = "claude-opus-5";
const MAX_TOKENS = 8000;

// 스타일 가이드(docs/20, templates/제휴글-스타일가이드)를 압축한 system 프롬프트.
const SYSTEM_PROMPT = `당신은 한국어 제휴 마케팅 블로그 글쓰기 어시스턴트입니다.
아래 규칙을 반드시 지켜 "초안"을 작성합니다. 초안은 사람이 검수 후 발행합니다.

[말투]
- 친근한 존댓말(~해요/~더라고요), 1인칭 경험담 톤. 과한 이모지 금지.
- 장점만 아니라 단점·주의사항도 함께. 최상급/과장 금지(최고·무조건·100%·완벽·강력추천 금지).
- 짧은 문장·문단(3~4문장), 줄바꿈 자주.

[구조]
- 맨 위 첫 문단에 광고 표시 문구를 넣는다(제휴/쿠팡 글이면 필수):
  "이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."
  (제휴처가 쿠팡이 아니면 "제휴 링크가 포함되며 구매 시 수수료를 받습니다" 형태로.)
- 도입(왜/누구에게) → 본문 소제목 3~5개 → 자주 묻는 질문 5~7개 → 마무리.
- 본문에 [사진: 설명] 형태의 이미지 자리표시자를 300~500자마다 넣는다(실제 이미지는 사람이 삽입).
- 제휴 링크는 실제 URL을 만들지 말고 "👉 (제품명) 최저가 확인하기  <!-- 실제 딥링크로 교체 -->" 형태의
  자리표시자로 1~3개만. 링크 클릭 강요 문구 금지.
- 직접 경험/공식 사양/제3자 후기를 구분해 쓴다. 안 써본 것을 써본 것처럼 쓰지 않는다.
- 존재하지 않는 할인·가격·쿠폰을 지어내지 않는다. 수치가 필요하면 "(확인 후 기입)"으로 비워둔다.
- 맨 끝에 "확인일: (오늘 날짜) · 정보는 공식 페이지 기준이며 변경될 수 있습니다."

[제목/키워드]
- 핵심 키워드를 제목 앞쪽에, 관련어 3~5개를 자연스럽게. 나열 금지.

[분량]
- 1,500~2,500자 내외. 마크다운으로 출력. 코드펜스로 감싸지 말고 본문만.`;

function buildUserPrompt({ title, keywords, niche, program, channel }) {
  const channelNote =
    channel === "naver"
      ? "채널: 네이버 블로그. 외부 링크 반복을 피하고 텍스트 앵커 위주. 워드프레스 원문 복제 금지."
      : "채널: 워드프레스. 표/비교는 마크다운 표로.";
  return `아래 조건으로 제휴 글 초안을 작성해줘.
제목: ${title}
핵심 키워드: ${keywords || "(제목에서 유추)"}
니치/메모: ${niche || "(없음)"}
제휴처: ${program}
${channelNote}`;
}

chrome.action.onClicked.addListener(async (tab) => {
  if (chrome.sidePanel && tab?.windowId != null) {
    try {
      await chrome.sidePanel.open({ windowId: tab.windowId });
    } catch (e) {
      // 일부 환경에서는 사용자 제스처 필요. 무시.
    }
  }
});

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === "GENERATE_DRAFT") {
    generateDraft(msg.payload)
      .then((draft) => sendResponse({ ok: true, draft }))
      .catch((err) => sendResponse({ ok: false, error: String(err?.message || err) }));
    return true; // async
  }
  if (msg?.type === "INSERT_INTO_EDITOR") {
    insertIntoActiveTab(msg.markdown)
      .then(() => sendResponse({ ok: true }))
      .catch((err) => sendResponse({ ok: false, error: String(err?.message || err) }));
    return true;
  }
});

async function getSettings() {
  const s = await chrome.storage.local.get(["apiKey", "model", "proxyUrl"]);
  return {
    apiKey: (s.apiKey || "").trim(),
    model: s.model || DEFAULT_MODEL,
    proxyUrl: (s.proxyUrl || "").trim(),
  };
}

async function generateDraft(payload) {
  // payload: { title, keywords, niche, program, channel }
  const { apiKey, model, proxyUrl } = await getSettings();

  // 1) 프록시 모드 — 설정에 프록시 URL이 있으면 우선.
  if (proxyUrl) return generateViaProxy(proxyUrl, payload);

  // 2) 직접 모드 — 내 API 키로 api.anthropic.com 호출.
  if (!apiKey) {
    throw new Error("API 키가 없습니다. 사이드패널의 ⚙ 설정에서 키를 저장하거나 프록시 URL을 입력하세요.");
  }
  return generateDirect(apiKey, model, payload);
}

async function generateDirect(apiKey, model, payload) {
  const res = await fetch(ANTHROPIC_URL, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-api-key": apiKey,
      "anthropic-version": "2023-06-01",
      // 브라우저/확장에서 직접 호출을 허용하는 헤더.
      "anthropic-dangerous-direct-browser-access": "true",
    },
    body: JSON.stringify({
      model: model || DEFAULT_MODEL,
      max_tokens: MAX_TOKENS,
      system: SYSTEM_PROMPT,
      messages: [{ role: "user", content: buildUserPrompt(payload) }],
    }),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    let hint = "";
    if (res.status === 401) hint = " (API 키가 올바른지 확인하세요.)";
    else if (res.status === 429) hint = " (요청 한도/크레딧을 확인하세요.)";
    throw new Error(`Anthropic 오류 ${res.status}${hint}: ${text.slice(0, 300)}`);
  }
  const data = await res.json();
  const draft = (data.content || [])
    .filter((b) => b.type === "text")
    .map((b) => b.text)
    .join("\n")
    .trim();
  if (!draft) throw new Error("빈 응답을 받았습니다. 잠시 후 다시 시도하세요.");
  return draft;
}

async function generateViaProxy(proxyUrl, payload) {
  const res = await fetch(proxyUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`프록시 오류 ${res.status}: ${text.slice(0, 200)}`);
  }
  const data = await res.json();
  return data.draft; // 마크다운 초안 문자열
}

async function insertIntoActiveTab(markdown) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) throw new Error("활성 탭을 찾을 수 없습니다.");
  await chrome.tabs.sendMessage(tab.id, { type: "INSERT_DRAFT", markdown });
}
