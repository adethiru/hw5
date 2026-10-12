"""Shared definition of an agent role on the Campus Customs team."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Type

from pydantic import BaseModel

from backend.config import PROMPTS_DIR


@dataclass(frozen=True)
class AgentSpec:
    name: str                 # boss | inventory | accounting | facilities | customer_service
    title: str                # human-readable role
    description: str          # one line shown to other agents for delegation
    prompt_file: str          # file in backend/prompts/
    output_type: Type[BaseModel]

    def instructions(self) -> str:
        return (PROMPTS_DIR / self.prompt_file).read_text(encoding="utf-8")
