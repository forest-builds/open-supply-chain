import sys
from types import SimpleNamespace


import api.chat as chat


def test_not_configured_response_is_map_safe() -> None:
    response = chat._not_configured()

    assert response["tool_used"] is None
    assert response["tool_result"] is None
    assert "AI chat is not configured" in response["response"]


def test_tool_summary_handles_geocode_success_and_error() -> None:
    assert "Nope" == chat._tool_summary("geocode", {"error": "Nope"})
    summary = chat._tool_summary(
        "geocode", {"lat": 40.7, "lon": -74.0, "display_name": "Newark, NJ"}
    )
    assert "lat=40.7" in summary
    assert "Newark" in summary


def test_tool_summary_handles_feature_collection() -> None:
    summary = chat._tool_summary(
        "ports_near", {"explanation": "Found 2 ports.", "count": 2, "features": []}
    )

    assert summary == "Found 2 ports. (2 features returned to map.)"


def test_run_tool_dispatches_known_tools(monkeypatch) -> None:
    monkeypatch.setattr(chat, "ports_near", lambda **kwargs: {"tool": "ports", "kwargs": kwargs})

    result = chat._run_tool("ports_near", {"lat": 1, "lon": 2})

    assert result == {"tool": "ports", "kwargs": {"lat": 1, "lon": 2}}


def test_run_tool_unknown_tool_returns_error() -> None:
    assert chat._run_tool("nope", {}) == {"error": "Unknown tool: nope"}


def test_geocode_returns_first_result(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return [{"lat": "40.7", "lon": "-74.0", "display_name": "Newark, NJ"}]

    monkeypatch.setattr(chat.requests, "get", lambda *args, **kwargs: FakeResponse())

    result = chat._geocode("Newark")

    assert result == {"lat": 40.7, "lon": -74.0, "display_name": "Newark, NJ"}


def test_geocode_handles_empty_and_error(monkeypatch) -> None:
    class EmptyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return []

    monkeypatch.setattr(chat.requests, "get", lambda *args, **kwargs: EmptyResponse())
    assert "No geocoding results" in chat._geocode("Atlantis")["error"]

    def broken_get(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(chat.requests, "get", broken_get)
    assert chat._geocode("Newark") == {"error": "network down"}


def test_chat_returns_not_configured_without_keys(monkeypatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    response = chat.chat(chat.ChatRequest(messages=[chat.ChatMessage(role="user", content="hi")]))

    assert response["tool_used"] is None
    assert "AI chat is not configured" in response["response"]


def test_chat_selects_openai_provider(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(
        chat, "_run_openai", lambda key, messages: {"provider": "openai", "key": key}
    )

    response = chat.chat(chat.ChatRequest(messages=[chat.ChatMessage(role="user", content="hi")]))

    assert response == {"provider": "openai", "key": "openai-key"}


def test_chat_selects_anthropic_provider(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        chat, "_run_anthropic", lambda key, messages: {"provider": "anthropic", "key": key}
    )

    response = chat.chat(chat.ChatRequest(messages=[chat.ChatMessage(role="user", content="hi")]))

    assert response == {"provider": "anthropic", "key": "anthropic-key"}


def test_run_anthropic_handles_missing_package(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "anthropic", None)

    response = chat._run_anthropic("key", [])

    assert response["response"] == "anthropic package not installed."


def test_run_openai_handles_missing_package(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "openai", None)

    response = chat._run_openai("key", [])

    assert response["response"] == "openai package not installed."


def test_run_openai_executes_tool_call(monkeypatch) -> None:
    class FakeCompletions:
        def __init__(self):
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                tool_call = SimpleNamespace(
                    id="tc-1",
                    function=SimpleNamespace(
                        name="ports_near", arguments='{"lat": 40.7, "lon": -74.0}'
                    ),
                )
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            finish_reason="tool_calls",
                            message=SimpleNamespace(content=None, tool_calls=[tool_call]),
                        )
                    ]
                )
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        finish_reason="stop",
                        message=SimpleNamespace(content="Found ports.", tool_calls=None),
                    )
                ]
            )

    completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, api_key):
            self.chat = SimpleNamespace(completions=completions)

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setattr(
        chat,
        "_run_tool",
        lambda name, args: {"tool": name, "count": 1, "explanation": "Found 1 port."},
    )

    response = chat._run_openai("key", [{"role": "user", "content": "ports near Newark"}])

    assert response["response"] == "Found ports."
    assert response["tool_used"] == "ports_near"
    assert response["tool_result"]["count"] == 1


def test_run_anthropic_executes_tool_use(monkeypatch) -> None:
    class FakeMessages:
        def __init__(self):
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return SimpleNamespace(
                    stop_reason="tool_use",
                    content=[
                        SimpleNamespace(
                            type="tool_use",
                            id="tool-1",
                            name="facilities_near",
                            input={"lat": 40.7, "lon": -74.0},
                        )
                    ],
                )
            return SimpleNamespace(
                stop_reason="end_turn",
                content=[SimpleNamespace(type="text", text="Found facilities.")],
            )

    fake_messages = FakeMessages()

    class FakeAnthropic:
        def __init__(self, api_key):
            self.messages = fake_messages

    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=FakeAnthropic))
    monkeypatch.setattr(
        chat,
        "_run_tool",
        lambda name, args: {"tool": name, "count": 2, "explanation": "Found 2 facilities."},
    )

    response = chat._run_anthropic("key", [{"role": "user", "content": "facilities"}])

    assert response["response"] == "Found facilities."
    assert response["tool_used"] == "facilities_near"
    assert response["tool_result"]["count"] == 2
