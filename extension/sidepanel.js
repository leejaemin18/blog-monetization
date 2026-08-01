const $ = (id) => document.getElementById(id);

// ── 설정(API 키·모델·프록시) 로드/저장 ─────────────────────────────
async function loadSettings() {
  const s = await chrome.storage.local.get(["apiKey", "model", "proxyUrl"]);
  $("apiKey").value = s.apiKey || "";
  $("model").value = s.model || "claude-opus-5";
  $("proxyUrl").value = s.proxyUrl || "";
  // 키가 없으면 설정 패널을 펼쳐서 먼저 입력하도록 유도.
  if (!s.apiKey && !s.proxyUrl) $("settings").open = true;
}

$("saveSettings").addEventListener("click", async () => {
  await chrome.storage.local.set({
    apiKey: $("apiKey").value.trim(),
    model: $("model").value,
    proxyUrl: $("proxyUrl").value.trim(),
  });
  $("settingsStatus").textContent = "저장했습니다.";
  setTimeout(() => ($("settingsStatus").textContent = ""), 2000);
});

$("toggleSettings").addEventListener("click", () => {
  $("settings").open = !$("settings").open;
});

loadSettings();

$("gen").addEventListener("click", async () => {
  const payload = {
    title: $("title").value.trim(),
    keywords: $("keywords").value.trim(),
    niche: $("niche").value.trim(),
    program: $("program").value,
    channel: $("channel").value,
  };
  if (!payload.title) {
    setStatus("제목을 입력하세요.");
    return;
  }
  setBusy(true, "생성 중… (수 초~수십 초)");
  try {
    const resp = await chrome.runtime.sendMessage({ type: "GENERATE_DRAFT", payload });
    if (!resp?.ok) throw new Error(resp?.error || "알 수 없는 오류");
    $("out").value = resp.draft || "";
    setStatus("완료. 검수 후 사용하세요.");
  } catch (e) {
    setStatus("오류: " + (e?.message || e));
  } finally {
    setBusy(false);
  }
});

$("insert").addEventListener("click", async () => {
  const markdown = $("out").value.trim();
  if (!markdown) { setStatus("삽입할 초안이 없습니다."); return; }
  try {
    const resp = await chrome.runtime.sendMessage({ type: "INSERT_INTO_EDITOR", markdown });
    if (!resp?.ok) throw new Error(resp?.error || "삽입 실패");
    setStatus("에디터에 삽입 요청 완료.");
  } catch (e) {
    setStatus("오류: " + (e?.message || e));
  }
});

$("copy").addEventListener("click", async () => {
  const text = $("out").value;
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    setStatus("복사했습니다.");
  } catch {
    setStatus("복사 실패. 수동으로 선택해 복사하세요.");
  }
});

function setStatus(msg) { $("status").textContent = msg; }
function setBusy(busy, msg) {
  $("gen").disabled = busy;
  if (msg) setStatus(msg);
}
