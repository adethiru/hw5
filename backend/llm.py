"""Model factory. Every agent gets its model from here, so there is exactly one
place a model is configured: config.MODEL_NAME ("gpt-6-luna") via Portkey.

Azure's gpt-6-luna rejects function tools on /v1/chat/completions unless
reasoning_effort is 'none' ("Function tools with reasoning_effort are not
supported ... set reasoning_effort to 'none'"). Our agents always use tools
(MCP + delegate_task), so:

  * default  (CC_LLM_API=chat):      chat completions + reasoning_effort='none'
  * optional (CC_LLM_API=responses): the /v1/responses API, which allows tools
                                     together with the model's default reasoning

No temperature or other sampling overrides are set.
"""

from __future__ import annotations

import os

from pydantic_ai.providers.openai import OpenAIProvider

try:  # pydantic-ai >= 1.0
    from pydantic_ai.models.openai import OpenAIChatModel as _ChatModel
except ImportError:  # older pydantic-ai
    from pydantic_ai.models.openai import OpenAIModel as _ChatModel

from backend.config import MODEL_NAME, PORTKEY_BASE_URL, get_api_key

ALLOWED_MODEL = "gpt-6-luna"
LLM_API = os.environ.get("CC_LLM_API", "chat").lower()  # "chat" | "responses"


def _provider() -> OpenAIProvider:
    return OpenAIProvider(base_url=PORTKEY_BASE_URL, api_key=get_api_key())


def build_model():
    if MODEL_NAME != ALLOWED_MODEL:
        raise RuntimeError(f"Only {ALLOWED_MODEL} is allowed in this homework (got {MODEL_NAME!r}).")
    if LLM_API == "responses":
        from pydantic_ai.models.openai import OpenAIResponsesModel
        return OpenAIResponsesModel(MODEL_NAME, provider=_provider())
    return _ChatModel(MODEL_NAME, provider=_provider())


def model_settings() -> dict:
    """Per-agent model settings (passed to every Agent)."""
    if LLM_API == "responses":
        return {}
    # Required by Azure gpt-6-luna for tool calling on chat completions.
    return {"openai_reasoning_effort": "none"}
