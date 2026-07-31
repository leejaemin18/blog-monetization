// Service worker (MV3). API 키는 여기에 두지 않는다 — 백엔드 프록시가 쥔다.
// 확장은 프록시만 호출하고, 결과를 사이드패널/콘텐트 스크립트로 전달한다.

// 프록시 주소. 배포 시 본인 서버로 교체. 기본은 로컬 개발용.
const PROXY_URL = "http://localhost:8787/generate";

chrome.action.onClicked.addListener(async (tab) => {
  // 툴바 아이콘 클릭 시 사이드패널 열기
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

async function generateDraft(payload) {
  // payload: { title, keywords, niche, program, channel }
  const res = await fetch(PROXY_URL, {
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
