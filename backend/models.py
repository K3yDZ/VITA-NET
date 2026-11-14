"""Pydantic models. Field bounds double as input validation — a
malformed or malicious request (e.g. a heart rate of -1 or 999999) is
rejected by FastAPI before it ever reaches application logic. This is a
big chunk of what "secure against attacks" means for an API this small.
"""

import re
from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional, List


def _sanitize_html(s: str) -> str:
    """Strip HTML/script tags and their content to prevent XSS in reflected contexts."""
    # Remove script tags and their content
    s = re.sub(r"<script[^>]*>.*?</script>", "", s, flags=re.IGNORECASE | re.DOTALL)
    # Remove other HTML tags
    return re.sub(r"<[^>]*>", "", s)


class Astronaut(BaseModel):
    id: str
    name: str
    role: str

    @field_validator("id")
    @classmethod
    def id_alphanumeric(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", v):
            raise ValueError("id must be alphanumeric with optional _ or -")
        return v

    @field_validator("name")
    @classmethod
    def name_no_html(cls, v: str) -> str:
        return _sanitize_html(v).strip()


class VitalsReading(BaseModel):
    model_config = ConfigDict(extra="ignore")

    heartRate: float = Field(ge=20, le=220, description="beats per minute")
    bpSys: float = Field(ge=50, le=260, description="systolic mmHg")
    bpDia: float = Field(ge=30, le=180, description="diastolic mmHg")
    spo2: float = Field(ge=50, le=100, description="oxygen saturation %")
    tempC: float = Field(ge=30, le=43, description="body temperature, Celsius")
    stressIndex: float = Field(ge=0, le=100, description="simulated composite index")
    radiationMSv: float = Field(default=0, ge=0, le=2000, description="cumulative mission dose, mSv")
    hrv: Optional[float] = Field(default=None, ge=0, le=200)



class AdviceRequest(BaseModel):
    astronaut: Astronaut
    vitals: VitalsReading
    radiationMSv: float = Field(ge=0, le=2000)
    alerts: List[str] = Field(default_factory=list, max_length=20)


class AdviceResponse(BaseModel):
    advice: str
    source: str  # "local" | "llm"
