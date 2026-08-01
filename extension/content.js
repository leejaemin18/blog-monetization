// Content script: 생성된 초안을 현재 페이지의 에디터에 삽입한다.
// 발행은 하지 않는다. 사람이 검수 후 직접 발행한다.
//
// 지원(베스트에포트): 워드프레스 클래식/구텐베르크, 네이버 스마트에디터의 텍스트 영역,
// 그리고 일반 textarea / contenteditable. 실제 DOM 구조는 수시로 바뀌므로,
// 삽입이 안 되면 클립보드 복사로 폴백한다.

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === "INSERT_DRAFT") {
    try {
      const ok = insertDraft(msg.markdown);
      sendResponse({ ok });
    } catch (e) {
      sendResponse({ ok: false, error: String(e?.message || e) });
    }
    return true;
  }
});

function insertDraft(markdown) {
  const el = findEditor();
  if (el) {
    if (el.tagName === "TEXTAREA" || el.tagName === "INPUT") {
      el.value = (el.value ? el.value + "\n\n" : "") + markdown;
      el.dispatchEvent(new Event("input", { bubbles: true }));
    } else {
      // contenteditable
      el.focus();
      // 줄바꿈 보존을 위해 텍스트 노드로 삽입
      const text = document.createTextNode("\n\n" + markdown);
      el.appendChild(text);
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }
    flash("초안을 에디터에 삽입했습니다. 검수 후 발행하세요.");
    return true;
  }
  // 폴백: 클립보드 복사
  copyToClipboard(markdown);
  flash("에디터를 찾지 못해 초안을 클립보드에 복사했습니다. 붙여넣기 하세요.");
  return false;
}

function findEditor() {
  // 우선순위: 포커스된 편집 요소 → 알려진 에디터 셀렉터 → 첫 textarea
  const active = document.activeElement;
  if (isEditable(active)) return active;

  const selectors = [
    "textarea#content",              // 워드프레스 클래식
    ".wp-block-post-content [contenteditable='true']", // 구텐베르크(대략)
    "[contenteditable='true']",      // 일반 contenteditable (네이버 등)
    "textarea",
  ];
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el && isEditable(el)) return el;
  }
  return null;
}

function isEditable(el) {
  if (!el) return false;
  if (el.tagName === "TEXTAREA" || el.tagName === "INPUT") return true;
  return el.getAttribute && el.getAttribute("contenteditable") === "true";
}

function copyToClipboard(text) {
  try {
    navigator.clipboard.writeText(text);
  } catch (_) {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
}

function flash(message) {
  const div = document.createElement("div");
  div.textContent = message;
  Object.assign(div.style, {
    position: "fixed", bottom: "16px", right: "16px", zIndex: 2147483647,
    background: "#111", color: "#fff", padding: "10px 14px", borderRadius: "8px",
    font: "14px/1.4 'Noto Sans KR', sans-serif", maxWidth: "320px", boxShadow: "0 2px 8px rgba(0,0,0,.3)",
  });
  document.body.appendChild(div);
  setTimeout(() => div.remove(), 4000);
}
