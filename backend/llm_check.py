"""One cheap live check of gpt-6-luna WITH a tool call (no MCP, no DB).

    python -m backend.llm_check                  # chat completions + reasoning_effort='none'
    CC_LLM_API=responses python -m backend.llm_check

Prints OK if the model called the tool and answered. Costs one or two tiny requests.
"""

import asyncio

from pydantic_ai import Agent

from backend.config import MODEL_NAME
from backend.llm import LLM_API, build_model, model_settings


async def main() -> None:
    agent = Agent(build_model(), model_settings=model_settings(),
                  instructions="Use the add tool, then reply with only the number.")

    @agent.tool_plain
    def add(a: int, b: int) -> int:
        """Add two integers."""
        return a + b

    result = await agent.run("What is 2 + 3?")
    used_tool = any(getattr(p, "part_kind", "") == "tool-call"
                    for m in result.all_messages() for p in getattr(m, "parts", []))
    print(f"model={MODEL_NAME} api={LLM_API} settings={model_settings()}")
    print(f"answer={result.output!r} tool_called={used_tool}")
    print("OK" if used_tool and "5" in str(result.output) else "CHECK OUTPUT ABOVE")


if __name__ == "__main__":
    asyncio.run(main())
