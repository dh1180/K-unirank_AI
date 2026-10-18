"""A fixed read-only backend tool; never accept arbitrary URLs or SQL from users."""
import httpx
from pydantic import ValidationError

from app.config import Settings
from app.models import AdmissionAsk, SpringComparison


class SpringToolFailure(Exception):
    pass


class SpringAdmissionTool:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def compare(self, req: AdmissionAsk) -> SpringComparison:
        params: dict[str, str | int] = {
            "grade": str(req.grade),
            "track": req.track,
            "special": req.special,
            "scope": req.scope,
            "page": 0,
            "size": req.limit,
        }
        if req.year is not None:
            params["year"] = req.year
        if req.region:
            params["region"] = req.region
        if req.major:
            params["q"] = req.major
        try:
            async with httpx.AsyncClient(
                base_url=self.settings.spring_api_base_url.rstrip("/") + "/",
                timeout=self.settings.spring_api_timeout_seconds,
                follow_redirects=False,
            ) as client:
                response = await client.get("api/v1/admissions/compare", params=params)
                response.raise_for_status()
                return SpringComparison.model_validate(response.json())
        except (httpx.HTTPError, ValueError, ValidationError) as exc:
            raise SpringToolFailure("Spring Boot 입결 API 연결 또는 응답 검증 실패") from exc
