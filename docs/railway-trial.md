# Railway 한 달 운영

- AI 서비스는 public domain 없이 `ai.railway.internal:8000`에서 실행합니다.
- `LLM_PROVIDER=openrouter`, `LLM_MODEL=openrouter/free` 또는 검증한 `:free` 모델만 허용합니다.
- 키는 Railway `OPENROUTER_API_KEY`에만 설정합니다. Spring·브라우저에는 제공하지 않습니다.
- 모든 OpenRouter 요청에 `provider.max_price.prompt=0`, `completion=0`을 지정합니다. 유료 대체 모델을 지정하지 않습니다.
- 단일 replica/worker에서 하루 40회, 동시 2회로 제한합니다. 실패한 호출도 한도에 포함됩니다. 프로세스 재시작 시 로컬 한도는 초기화되며 공급자 한도는 별도로 적용됩니다.
- `/health`는 프로세스, `/ready`는 키·서비스 토큰·무료 모델 설정을 확인합니다. 모델의 현재 가용성은 실제 질문 smoke test로 확인합니다.
- 질문은 외부 AI 공급자로 전달되므로 개인정보를 입력하지 않도록 화면에 안내합니다. 질문을 요청 로그로 남기지 않습니다.
- 모델은 검색 조건만 해석하며 등급컷·학교명·모집단위는 Spring의 실제 조회 결과를 사용합니다.
- LLM 추론비와 별개로 Railway CPU/RAM/network 비용이 발생합니다. 월말 실사용 비용으로 판단합니다.
