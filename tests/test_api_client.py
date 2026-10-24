import asyncio
from types import SimpleNamespace

import httpx2 as httpx  # SDK openai 3.x работает на httpx2
import openai
import pytest

from api_client import AIClient, AIError

MESSAGES = [{"role": "user", "content": "привет"}]


class FakeCompletions:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


def make_client(result=None, error=None, tokens_param="max_completion_tokens"):
    completions = FakeCompletions(result, error)
    fake = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return AIClient(client=fake, tokens_param=tokens_param), completions


def ok_response(text="ответ", finish="stop"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason=finish)],
        usage=SimpleNamespace(prompt_tokens=20, completion_tokens=7),
        model="gpt-test", _request_id="req_1",
    )


def status_error(cls, code, body=None):
    response = httpx.Response(code, request=httpx.Request("POST", "https://example.test/v1/chat/completions"))
    return cls("error", response=response, body=body)


def run(coro):
    return asyncio.run(coro)


def test_system_goes_first_and_params_are_mapped():
    client, fake = make_client(ok_response())
    result = run(client.complete(MESSAGES, "профиль канала", "gpt-test", 500,
                                 effort="low", temperature=0.3))
    sent = fake.calls[0]
    assert sent["messages"][0] == {"role": "system", "content": "профиль канала"}
    assert sent["messages"][1:] == MESSAGES
    assert sent["max_completion_tokens"] == 500 and "max_tokens" not in sent
    assert sent["reasoning_effort"] == "low"
    assert sent["temperature"] == 0.3
    assert result.text == "ответ"
    assert (result.input_tokens, result.output_tokens) == (20, 7)
    assert result.stop_reason == "end_turn"
    assert result.request_id == "req_1"


def test_default_request_has_no_optional_params():
    client, fake = make_client(ok_response(), tokens_param="max_tokens")
    run(client.complete(MESSAGES, None, "gpt-test", 100))
    sent = fake.calls[0]
    assert sent["max_tokens"] == 100
    assert "reasoning_effort" not in sent and "temperature" not in sent
    assert sent["messages"] == MESSAGES


def test_temperature_zero_is_not_dropped():
    client, fake = make_client(ok_response())
    run(client.complete(MESSAGES, None, "gpt-test", 100, temperature=0.0))
    assert fake.calls[0]["temperature"] == 0.0


def test_length_finish_maps_to_max_tokens_and_empty_content():
    client, _ = make_client(ok_response(text=None, finish="length"))
    result = run(client.complete(MESSAGES, None, "gpt-test", 10))
    assert result.stop_reason == "max_tokens"
    assert result.text == ""


def test_bad_request_detail_is_extracted():
    body = {"error": {"message": "Unsupported parameter: 'temperature'"}}
    client, _ = make_client(error=status_error(openai.BadRequestError, 400, body))
    with pytest.raises(AIError) as info:
        run(client.complete(MESSAGES, None, "gpt-test", 10, temperature=1.0))
    assert info.value.kind == "bad_request"
    assert info.value.status == 400
    assert "temperature" in info.value.user_message


@pytest.mark.parametrize("cls,code,kind", [
    (openai.RateLimitError, 429, "rate_limit"),
    (openai.AuthenticationError, 401, "auth"),
    (openai.NotFoundError, 404, "not_found"),
    (openai.InternalServerError, 500, "api_error"),
])
def test_status_errors_are_mapped(cls, code, kind):
    client, _ = make_client(error=status_error(cls, code))
    with pytest.raises(AIError) as info:
        run(client.complete(MESSAGES, None, "gpt-test", 100))
    assert info.value.kind == kind


def test_timeout_is_mapped():
    request = httpx.Request("POST", "https://example.test/v1/chat/completions")
    client, _ = make_client(error=openai.APITimeoutError(request=request))
    with pytest.raises(AIError) as info:
        run(client.complete(MESSAGES, None, "gpt-test", 100))
    assert info.value.kind == "timeout"
