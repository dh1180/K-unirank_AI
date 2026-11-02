# K-unirank AI

**Raspberry Pi 5용 FastAPI AI 전용 서비스**를 독립 저장소로 운영합니다.

- [K-unirank_BackEnd](https://github.com/dh1180/K-unirank_BackEnd): Spring Boot · 입결, 대학, VS, 인증
- [K-unirank_FrontEnd](https://github.com/dh1180/K-unirank_FrontEnd): Next.js + React
- [K-unirank_v2](https://github.com/dh1180/K-unirank_v2): 현재 운영 중인 Django (변경하지 않음)

> **개발 2단계:** 외부 LLM API를 이용한 **자연어→정형 검색조건 파싱**까지 추가했습니다. LLM은 답변의 입결 숫자·대학을 생성하지 않고, Spring Boot 조회 근거만 답변에 사용합니다. 모집요강 RAG·벡터 검색과 공개 채팅 화면은 아직 미구현입니다.

## 구현된 기능

- `POST /api/v1/ai/questions`: 입력한 한국어 질문에서 LLM Structured Outputs로 `grade, year, track, special, scope, region, major`만 추출 → Pydantic 검증 → 기존 Spring 입결 조회 → 근거 있는 답변 구성. `OPENAI_API_KEY`가 없으면 503, 내신 정보 없으면 422 (임의로 등급 추정 금지)
- `GET /health`: 상태 확인
- `POST /api/v1/ai/admissions/compare`: 인증된 Spring Boot 내부 호출자가 내신 등급·학과·지역·학년을 전달하면, **허용된 Spring API 1개만 호출하여** 기존 공개 입결을 조회하고 수치와 출처/학과 링크를 표시
- Pydantic으로 등급 1.0~9.0, 검색 조건, 결과 개수를 제한하며 외부에서 SQL이나 API URL을 지정할 수 없음
- `X-Internal-Service-Token`이 없거나 잘못되면 401, 미설정 시 503으로 거부
- Spring 호출 장애는 502로 처리. 빈 결과는 값이나 대학을 만들어내지 않고 '자료 없음' 명시

## 개발

Python 3.11 이상 (권장 3.12), 테스트에는 로컬 Docker나 DB가 필요하지 않습니다.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
cp .env.example .env
# .env 의 INTERNAL_SERVICE_TOKEN 을 높은 엔트로피의 실제 값으로 교체
uvicorn app.main:app --reload --port 8000
pytest -q
```

요청 예시 (실제 서비스 토큰은 명령행 이력에 노출하지 말고 비밀 관리 사용):

```http
POST /api/v1/ai/admissions/compare
X-Internal-Service-Token: <PRIVATE_SERVICE_TOKEN>
Content-Type: application/json

{"grade":"2.5","year":2026,"major":"컴퓨터","region":"서울","limit":5}
```

`SPRING_API_BASE_URL`에는 테스트용 Spring Boot API 주소를 사용하세요. 집 Raspberry Pi는 Railway의 `*.railway.internal`에 접속할 수 없습니다. **운영 API는 인증된 HTTPS 또는 검증된 네트워크 경로로만 연결**하세요. 1단계에서는 운영 DB에 직접 연결하지 않고 Spring의 공개 데이터 조회 API만 사용합니다.

## Raspberry Pi 5 / Docker

ARM64 라즈베리파이에서 `docker compose up -d --build`로 실행할 수 있도록 Dockerfile/Compose를 준비했습니다. 컨테이너는 비루트 사용자, 불필요 capability 제거, 읽기 전용 루트 FS, 로컬 루프백 포트 바인딩으로 구성합니다.

- 포트 8000은 **공유기에서 포트 포워딩하지 마세요**.
- Railway Spring Boot에서 AI를 호출할 때에는 Cloudflare Tunnel + Access 서비스 토큰 또는 이에 준하는 서비스 인증이 필요합니다.
- FastAPI의 `X-Internal-Service-Token`은 Cloudflare Access와 **별도 방어 계층**입니다.
- 가정용 인터넷/전원 장애에 대비해 Spring에서 타임아웃 및 AI 기능 fallback을 구현합니다.

## 이후 진행할 AI 작업

1. Spring Boot에서 AI 프록시/인증·시간 제한 추가 및 반환 근거 검증 테스트.
2. 모델 API 연동과 툴 호출 제한·모델 오답 검사·비용 추적.
3. 공식 모집요강 문서 파싱·연도/대학/전형 메타데이터 및 출처 페이지가 있는 RAG.
4. Raspberry Pi 5 ARM64 실기기 점검, 터널 보안, 장애·동시성·재시작 테스트.
5. 기존 Django 이전 완료 전까지 운영 사이트 연결 금지.

## 개발 규칙

[Contextory PR #10](https://github.com/kau-likelion-14th-hackathon/Contextory_BackEnd/pull/10) 형식의 `feat:` 커밋, `[Feat]` PR 제목, PR 타입·변경·테스트·참고 사항을 기록합니다.

## LLM 연동 설계

- OpenAI Chat Completions의 `response_format: json_schema` (strict) 사용. 모델은 `LLM_MODEL` 환경변수로 선택, 기본 `gpt-4.1-mini`.
- 비용: 한 질의당 최대 220 출력 토큰, 응답 타임아웃 12초. 모델 비용은 Railway와 별도이며, API 계정 설정 필요.
- 프롬프트 인젝션/모델의 잘못된 요청에도 **모델 출력은 AdmissionAsk 필드만 통과 가능**. 모델에 URL·임의 SQL·입결 값을 생성하는 도구 권한이 없습니다.
- 외부 LLM 실패/미설정일 때는 `/api/v1/ai/admissions/compare` 구조화 조회로 계속 처리 가능.
- 외부 모델 출력의 유효성은 항상 검증하고, 실제 공개 입결 데이터와 출처는 Spring Boot에서만 가져옵니다.

## 공식 모집요강 PDF 검색

**RAG 문서 검색 기반:** 관리자가 원문 출처를 직접 검증한 PDF를 Raspberry Pi 5 로컬 파일에서 색인합니다. 공개 사용자에게 URL 다운로드·파일 업로드를 허용하지 않습니다.

```bash
# 개발 PC에서는 RAG_DB_PATH=./local_docs.sqlite3 를 먼저 설정
python -m app.rag ingest ./official-admissions.pdf --university "예시대학" \
  --year 2026 --title "2026학년도 모집요강" \
  --source-url "https://admissions.example.ac.kr/guide.pdf"

python -m app.rag search "학생부종합 서류평가" --university "예시대학" --year 2026
```

`POST /api/v1/ai/docs/search` (서비스 토큰 필수): 검색어·대학·학년도 조건으로 SQLite FTS5/BM25 문서 passage 반환. 결과에는 공식 문서 링크와 PDF 페이지 번호가 포함됩니다.

**제약:** 이 단계는 문서 검색·출처 근거 보존 기능이며, 벡터 임베딩과 생성 모델의 문서 요약은 아직 구현 전입니다. 스캔 이미지 기반 PDF는 OCR을 제공하지 않으므로 텍스트를 추출할 수 없습니다. 실제 대학별 공식 문서는 아직 등록하지 않았습니다.


### 자연어 검색의 조건 해석

- 9등급제 수시 교과/종합 내신 비교를 지원합니다. 정시 백분위·5등급제는 임의 환산하지 않고 재입력을 안내합니다.
- 수도권은 서울·경기·인천, 컴공은 컴퓨터·소프트웨어·컴퓨팅 검색어로 확장하고 결과에 확장 내용을 표시합니다.
- 명시한 등급·학년도·전형·지역·대학 조건을 모델이 바꾸지 못합니다. 대학 이름 속 지역명은 지역 조건으로 사용하지 않습니다.
- 복수 지역은 OR, 대학 이름은 최대 10곳의 정확한 이름으로 전달합니다. 학과·지역·대학 조건은 서로 AND입니다.
- 모델 연결 실패 시 인식 가능한 학과/대학이 명시된 질문만 규칙으로 복구합니다. 임의의 학과나 컷을 생성하지 않습니다.
- 조건에 맞는 결과가 없어도 자동으로 전국/전체 등급으로 확대하지 않습니다. 70% 컷 우선, 없으면 50% 컷을 비교합니다.
- 제공자 요청 한도는 실제 모델 호출 직전에 소비합니다. 지원하지 않는 질문은 모델을 호출하지 않습니다.
- 회귀 테스트: `pytest -q` (외부 모델 호출 없이 해석·예외·무료 모델 제약·근거 기반 응답 검증).

대학군 약칭(건동홍·서성한·중경외시·국숭세단·광명상가·한서삼·SKY)은 명시된 대학 이름 목록으로만 확장하고 화면에 해석을 표시합니다. 약칭은 순위 판정에 사용하지 않습니다. 분리된 캠퍼스는 결과 이름으로 구분하며, 오타·상대적 대학군 조건은 확인을 요청합니다.
