"""Bounded browser-reported model timings; no user, device, URL, or error text."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Milliseconds = Annotated[float, Field(ge=0, le=86400000, allow_inf_nan=False)]


class ModelLoadMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    view: Literal["preview", "scenario", "demo"] = "preview"
    scene: Literal["ball", "duo", "carry", "skills", "rollers", "table", "seated"] | None = None
    result: Literal["ready", "failed"]
    cache: Literal["network", "http", "persistent", "memory", "unknown"]
    elapsed_ms: Milliseconds
    navigation_ms: Milliseconds
    manifest_ms: Milliseconds = 0
    asset_ms: Milliseconds = 0
    parse_ms: Milliseconds = 0
    assemble_ms: Milliseconds = 0
    first_frame_ms: Milliseconds = 0
    transfer_bytes: int = Field(default=0, ge=0, le=64 * 1024 * 1024)
    encoded_bytes: int = Field(default=0, ge=0, le=32 * 1024 * 1024)
    decoded_bytes: int = Field(default=0, ge=0, le=32 * 1024 * 1024)
