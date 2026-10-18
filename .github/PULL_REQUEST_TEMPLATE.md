### PR 타입(하나 이상의 PR 타입을 선택해주세요)

* [ ] 기능 추가
* [ ] 기능 삭제
* [ ] 버그 수정
* [ ] 의존성, 환경 변수, 빌드 관련 코드 업데이트
* [ ] 리팩터링

### 반영 브랜치

`feature/example -> main`

### 변경 사항

1. **변경 내용**
   * 구현 및 안전성 검증 설명

### 주요 API

| 기능 | Method | Endpoint | 인증 |
|---|---|---|---|
| 예시 | POST | `/api/v1/ai/...` | 서비스 토큰 |

### 테스트 결과

* [ ] pytest
* [ ] GitHub Actions 성공
* [ ] Raspberry Pi 5 ARM64 동작 검증 (별도)

### 참고 사항

* Railway 운영 DB·기존 Django 영향
* Cloudflare 인증·LLM 비용·모델 오류 대처
