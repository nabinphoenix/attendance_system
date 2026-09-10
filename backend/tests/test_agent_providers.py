from app.modules.agent.providers import FallbackModelClient, ProviderFailure, ProviderReply


class FakeProvider:
    def __init__(self, name: str, reply: ProviderReply | None = None, failure: ProviderFailure | None = None):
        self.name = name
        self.reply = reply
        self.failure = failure

    def configured(self) -> bool:
        return True

    def complete(self, messages, tools):
        if self.failure:
            raise self.failure
        return self.reply


def test_rate_limited_primary_falls_back_to_next_provider():
    client = FallbackModelClient()
    client.order = ["groq", "openrouter"]
    client.providers = {
        "groq": FakeProvider("groq", failure=ProviderFailure("groq", "rate limited", retryable=True)),
        "openrouter": FakeProvider("openrouter", reply=ProviderReply("openrouter", "Hello", [])),
    }

    reply, attempts = client.complete([], [])

    assert reply.provider == "openrouter"
    assert reply.content == "Hello"
    assert attempts == ["groq: temporarily unavailable", "openrouter: selected"]


def test_unavailable_primary_still_tries_the_next_configured_provider():
    client = FallbackModelClient()
    client.order = ["groq", "gemini"]
    client.providers = {
        "groq": FakeProvider("groq", failure=ProviderFailure("groq", "bad model")),
        "gemini": FakeProvider("gemini", reply=ProviderReply("gemini", "Fallback answer", [])),
    }

    reply, attempts = client.complete([], [])

    assert reply.provider == "gemini"
    assert attempts == ["groq: unavailable", "gemini: selected"]
