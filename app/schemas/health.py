from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    version: str
    region: str


class ReadinessResponse(BaseModel):
    ready: bool
    region: str
    detail: str | None = None
