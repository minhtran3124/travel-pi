"""PoC (evaluation-only, MIN-61) — chứng minh PIIMiddleware chạy ở version pin.

Throwaway: KHÔNG import `app`, KHÔNG network. Dựng một `create_agent` với model
"capturing" tự viết (ghi lại đúng message model NHẬN được) để chứng minh
PIIMiddleware redact/mask input TRƯỚC khi tới model.

Run (từ repo root):
    .venv/bin/python specs/agent-middleware-spike/poc/pii_middleware_poc.py
"""

from __future__ import annotations

from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import PIIMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class CapturingModel(BaseChatModel):
    """Ghi lại nội dung message model nhận được, trả lời cố định. Zero network."""

    captured: list[str] = []

    @property
    def _llm_type(self) -> str:
        return "capturing"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Any = None,
        run_manager: Any = None,
        **kw: Any,
    ) -> ChatResult:
        # Ghi nội dung mọi human message model thực sự nhìn thấy.
        for m in messages:
            if m.__class__.__name__ == "HumanMessage":
                self.captured.append(str(m.content))
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="ok"))])


def main() -> None:
    model = CapturingModel()
    agent = create_agent(
        model=model,
        tools=[],
        middleware=[
            PIIMiddleware("email", strategy="redact", apply_to_input=True),
            PIIMiddleware("credit_card", strategy="mask", apply_to_input=True),
        ],
    )

    raw = "My email is john.doe@example.com and my card is 5105-1051-0510-5100"
    print("INPUT (user gõ):    ", raw)

    result = agent.invoke({"messages": [{"role": "user", "content": raw}]})

    seen_by_model = (
        model.captured[-1] if model.captured else "<model nhận không có human msg>"
    )
    print("MODEL NHẬN:         ", seen_by_model)

    final_human = next(
        (
            m.content
            for m in reversed(result["messages"])
            if m.__class__.__name__ == "HumanMessage"
        ),
        "<none>",
    )
    print("STATE human cuối:   ", final_human)

    # Assertions — chứng minh redaction/masking đã xảy ra trước model.
    assert "john.doe@example.com" not in seen_by_model, "email KHÔNG bị redact!"
    assert "5105-1051-0510-5100" not in seen_by_model, "credit card KHÔNG bị mask!"
    print("\n✅ PASS — email redacted + credit card masked TRƯỚC khi tới model.")
    print("   Kết luận: PIIMiddleware hoạt động ở langchain 1.3.x với create_agent.")


if __name__ == "__main__":
    main()
