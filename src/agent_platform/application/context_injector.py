from agent_platform.domain.context_rendering import RenderedContext
from agent_platform.domain.model import (
    MessageRole,
    ModelMessage,
    ModelRequest,
)


class ReferenceMessageInjector:
    @property
    def name(self) -> str:
        return "reference-message"

    @property
    def version(self) -> str:
        return "v0"

    def inject(
        self,
        request: ModelRequest,
        rendered: RenderedContext,
    ) -> ModelRequest:
        if not rendered.text:
            return request.model_copy(deep=True)

        messages = list(request.messages)
        user_index = self._last_user_message_index(messages)

        if user_index is None:
            raise ValueError(
                "ReferenceMessageInjector requires an existing user message for non-empty context."
            )

        messages.insert(
            user_index,
            ModelMessage(
                role=MessageRole.USER,
                content=rendered.text,
            ),
        )

        return request.model_copy(
            update={"messages": messages},
        )

    @staticmethod
    def _last_user_message_index(
        messages: list[ModelMessage],
    ) -> int | None:
        for index in range(len(messages) - 1, -1, -1):
            if messages[index].role is MessageRole.USER:
                return index

        return None
