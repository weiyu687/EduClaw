"""OpenAI-compatible transport; custom providers implement async complete()."""
import asyncio
import json
import os
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # A provider redirect must never forward an application's API credential.
        return None


class OpenAICompatibleModel:
    def __init__(self, *, name, base_url, api_key_env, timeout=60):
        url = urlsplit(base_url)
        if url.scheme not in ("http", "https") or not url.netloc or url.username or url.password or url.query or url.fragment:
            raise ValueError("Invalid model base_url.")
        if url.scheme != "https" and url.hostname not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("Remote model endpoints must use HTTPS.")
        self.name, self.url, self.timeout = name, base_url.rstrip("/") + "/chat/completions", timeout
        self.api_key = os.environ.get(api_key_env)
        if not name or not self.api_key:
            raise ValueError(f"Set model name and application credential environment variable {api_key_env}.")

    async def complete(self, messages, tools):
        payload = {"model": self.name, "messages": messages}
        if tools:
            payload["tools"] = tools
        def request():
            req = Request(self.url, data=json.dumps(payload).encode(), headers={
                "Authorization": "Bearer " + self.api_key, "Content-Type": "application/json"})
            with build_opener(_NoRedirect()).open(req, timeout=self.timeout) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError("Model response exceeds size limit.")
            return json.loads(raw)["choices"][0]["message"]
        return await asyncio.to_thread(request)


class DemoModel:
    """Explicit offline transport for scaffolds and smoke tests, not an LLM."""
    async def complete(self, messages, tools):
        return {"role": "assistant", "content": "[offline demo] " + messages[-1]["content"]}


def configured_model(settings):
    settings = dict(settings)
    provider = settings.pop("provider", "openai-compatible")
    if provider == "demo":
        return DemoModel()
    if provider != "openai-compatible":
        raise ValueError("Inject a model object for custom providers.")
    return OpenAICompatibleModel(**settings)
