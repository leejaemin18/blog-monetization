# 제휴 글 초안 어시스턴트 (크롬 확장 프로토타입)

시중의 "자동 글쓰기 프로그램"을 **크롬 확장으로 만들 수 있는지** 검토하며 만든 **동작 골격**입니다.
타당성 분석은 → [`../docs/23-자동글쓰기-크롬확장-타당성.md`](../docs/23-자동글쓰기-크롬확장-타당성.md)

> ⚠️ **학습·검토용**입니다. 실사용 전 프록시 인증·요금 상한·정책을 반드시 점검하세요.
> **자동 발행 기능은 의도적으로 없습니다** — 초안을 에디터에 넣는 것까지만. 발행은 사람이 검수 후 수동.

## 무엇을 하나
1. 사이드패널에 **제목·키워드·니치·제휴처·채널**을 입력
2. 백엔드 프록시가 **스타일 가이드를 system 프롬프트로 주입**해 Claude(`claude-opus-5`) 호출
3. 광고표시 문구 + 이미지 자리표시자 + 링크 **자리표시자**가 포함된 초안 생성
4. "에디터에 삽입" 또는 "복사" → 사람이 검수·수정·발행

## 구조
```
extension/
  manifest.json      MV3
  background.js      서비스워커(프록시 호출·메시지 라우팅)
  content.js         에디터에 초안 삽입(워드프레스/네이버/일반)
  sidepanel.html/js  입력·생성·복사 UI
  proxy/
    server.js        ★ API 키를 쥐는 백엔드(Anthropic SDK)
    package.json
```

## 실행법

### 1) 프록시 서버 (API 키는 여기만)
```bash
cd extension/proxy
npm install
export ANTHROPIC_API_KEY=sk-ant-...   # 절대 깃/코드에 넣지 말 것
npm start                              # http://localhost:8787
```

### 2) 크롬에 확장 로드
1. `chrome://extensions` → 우상단 **개발자 모드** 켜기
2. **압축해제된 확장 프로그램을 로드** → `extension/` 폴더 선택
3. 워드프레스/네이버 글쓰기 페이지를 열고, 툴바의 확장 아이콘 클릭 → 사이드패널
4. 입력 후 **초안 생성** → 검수 → **에디터에 삽입**

## 보안 원칙 (중요)
- **API 키를 확장에 넣지 않는다.** 확장 코드는 누구나 열람 가능 → 키 유출.
- 키는 **프록시 서버**만 보관. 배포 시:
  - 프록시에 **인증**(내 확장/내 계정만 허용), **rate limit**, **비용 상한**, **HTTPS** 추가
  - `manifest.json`의 `host_permissions`를 실제 프록시 도메인으로 좁히기
- MV3는 원격 코드 로딩 금지 — 로직은 확장에 내장, 비밀만 프록시.

## 하지 않는 것 (권장)
- 🚫 네이버 자동 포스팅/매크로 (약관 위반·저품질·제재)
- 🚫 사람 검수 없는 무인 대량 발행 (스팸 정책 위반)
- 🚫 API 키 확장 내장

## 발행 전 검수
생성 초안은 저장소의 검사기로 한 번 더 확인하세요.
```bash
# 초안을 파일로 저장한 뒤
python3 ../tools/compliance.py drafts/내초안.md
```
그리고 [`../checklists/발행전-체크리스트.md`](../checklists/발행전-체크리스트.md).

## 참고
- Chrome 확장(MV3): https://developer.chrome.com/docs/extensions
- 쿠팡 파트너스 Open API(딥링크·이미지, 선택): https://developers.coupangcorp.com/
- Claude 모델·API: 저장소의 claude-api 스킬 / Anthropic 공식 문서
