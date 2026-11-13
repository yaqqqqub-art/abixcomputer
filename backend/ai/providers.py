"""Model providers. A provider turns a message list into text. New models = a new class here."""
import json, os, urllib.request, urllib.error


class ProviderError(Exception):
    pass


class Provider:
    name = "base"

    def complete(self, messages, max_tokens=800):
        raise NotImplementedError


class FakeProvider(Provider):
    """For tests only: replays a fixed list of answers. Never used in production."""
    name = "fake"

    def __init__(self, answers):
        self.answers, self.calls = list(answers), []

    def complete(self, messages, max_tokens=800):
        self.calls.append(messages)
        if not self.answers:
            raise ProviderError("fake provider has no more answers")
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a


class LocalProvider(Provider):
    """Talks to your own model server through the OpenAI-compatible /v1/chat/completions route
    (llama.cpp llama-server offers it). The URL comes from ABIX_AI_URL; no key is needed."""
    name = "local"

    def __init__(self, url=None, model=None, timeout=300):
        self.url = (url or os.environ.get("ABIX_AI_URL", "")).rstrip("/")
        self.model = model or os.environ.get("ABIX_AI_MODEL", "abix-local")
        self.timeout = timeout
        if not self.url.startswith(("http://", "https://")):
            raise ProviderError("ABIX_AI_URL is not set (example: http://host.docker.internal:8081)")

    def complete(self, messages, max_tokens=800):
        body = json.dumps({"model": self.model, "messages": messages, "temperature": 0.2,
                           "max_tokens": max_tokens, "stream": False}).encode()
        req = urllib.request.Request(self.url + "/v1/chat/completions", data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
        except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError) as e:
            raise ProviderError("model server error: %s" % e)
