from enum import StrEnum
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ProviderErrorCode(StrEnum):
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_STRUCTURED_OUTPUT = "INVALID_STRUCTURED_OUTPUT"
    REFUSED = "REFUSED"
    INCOMPLETE_RESPONSE = "INCOMPLETE_RESPONSE"


class LLMApiStyle(StrEnum):
    RESPONSES = "responses"


class StructuredOutputMode(StrEnum):
    JSON_SCHEMA = "json_schema"


class ProviderCapabilities(BaseModel):
    """Only capabilities that affect the current extraction adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    supports_responses_api: bool = True
    supports_json_schema: bool = True
    supports_usage: bool = True


class LLMProviderConfig(BaseModel):
    """Provider-neutral connection and protocol configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    provider_id: str = Field(min_length=1, max_length=128)
    base_url: str = Field(min_length=1, max_length=2048)
    api_key: str = Field(min_length=1, repr=False)
    model: str = Field(min_length=1, max_length=255)
    api_style: LLMApiStyle = LLMApiStyle.RESPONSES
    structured_output: StructuredOutputMode = StructuredOutputMode.JSON_SCHEMA
    timeout_seconds: float = Field(default=60.0, gt=0)
    max_retries: int = Field(default=2, ge=0, le=10)
    capabilities: ProviderCapabilities = Field(default_factory=ProviderCapabilities)

    @field_validator("provider_id", "model")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("provider identifiers must not be blank")
        return normalized

    @field_validator("api_key")
    @classmethod
    def normalize_api_key(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("api_key must not be blank")
        return normalized

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        normalized = value.strip()
        parsed = urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an absolute http or https URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("base_url must not contain credentials, query, or fragment")
        path = parsed.path.rstrip("/")
        return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))

    @model_validator(mode="after")
    def validate_capabilities(self) -> "LLMProviderConfig":
        if self.api_style != LLMApiStyle.RESPONSES:
            raise ValueError("only the Responses API style is supported")
        if self.structured_output != StructuredOutputMode.JSON_SCHEMA:
            raise ValueError("only JSON Schema structured output is supported")
        if not self.capabilities.supports_responses_api:
            raise ValueError("provider does not support the Responses API")
        if not self.capabilities.supports_json_schema:
            raise ValueError("provider does not support JSON Schema structured output")
        return self


class LLMProviderError(RuntimeError):
    """Provider-neutral error semantics exposed to the processing layer."""

    def __init__(
        self,
        message: str,
        *,
        code: ProviderErrorCode,
        retryable: bool,
        provider: str,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.retryable = retryable
        self.provider = provider
