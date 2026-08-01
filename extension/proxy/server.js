// 백엔드 프록시 (Node.js). API 키를 여기서만 쥔다 — 확장/브라우저에 노출 금지.
// 확장이 이 서버를 호출하면, 서버가 스타일 가이드를 system 프롬프트로 주입해 Claude를 호출한다.
//
// 실행:
//   cd extension/proxy
//   npm install
//   export ANTHROPIC_API_KEY=sk-ant-...      # 절대 코드/깃에 넣지 말 것
//   node server.js                            # http://localhost:8787
//
// ⚠️ 학습·검토용 최소 예제. 실제 배포 시: 인증(내 확장만 허용), 요청 제한(rate limit),
//    HTTPS, 비용 상한, 로깅을 반드시 추가할 것.

import http from "node:http";
import Anthropic from "@anthropic-ai/sdk";

const PORT = process.env.PORT || 8787;
const client = new Anthropic(); // ANTHROPIC_API_KEY 환경변수에서 읽음

// 우리 스타일 가이드(docs/20, templates/제휴글-스타일가이드)를 압축한 system 프롬프트.
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

const server = http.createServer(async (req, res) => {
  // CORS (개발용). 배포 시 확장 ID로 제한할 것.
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  if (req.method === "OPTIONS") { res.writeHead(204); return res.end(); }

  if (req.method === "POST" && req.url === "/generate") {
    try {
      const body = await readJson(req);
      if (!body?.title) {
        res.writeHead(400, { "Content-Type": "application/json" });
        return res.end(JSON.stringify({ error: "title required" }));
      }
      const message = await client.messages.create({
        model: "claude-opus-5",
        max_tokens: 8000,
        system: SYSTEM_PROMPT,
        messages: [{ role: "user", content: buildUserPrompt(body) }],
      });
      const draft = message.content
        .filter((b) => b.type === "text")
        .map((b) => b.text)
        .join("\n");
      res.writeHead(200, { "Content-Type": "application/json" });
      return res.end(JSON.stringify({ draft }));
    } catch (err) {
      res.writeHead(500, { "Content-Type": "application/json" });
      return res.end(JSON.stringify({ error: String(err?.message || err) }));
    }
  }

  res.writeHead(404, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ error: "not found" }));
});

function readJson(req) {
  return new Promise((resolve, reject) => {
    let data = "";
    req.on("data", (c) => (data += c));
    req.on("end", () => {
      try { resolve(data ? JSON.parse(data) : {}); } catch (e) { reject(e); }
    });
    req.on("error", reject);
  });
}

server.listen(PORT, () => {
  console.log(`제휴 글 프록시 실행: http://localhost:${PORT}  (POST /generate)`);
  if (!process.env.ANTHROPIC_API_KEY) {
    console.warn("경고: ANTHROPIC_API_KEY 미설정. export ANTHROPIC_API_KEY=... 후 재실행하세요.");
  }
});
