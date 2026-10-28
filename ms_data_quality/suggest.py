import json
import os
import re
import subprocess
import urllib.request
from collections import Counter
from difflib import SequenceMatcher
from typing import Protocol

from ms_data_quality.detect import LEGAL_FORMS

BACKENDS = ("rules", "ollama", "anthropic", "claude-cli")


class Backend(Protocol):
    name: str

    def complete(self, prompt: str) -> str: ...


def rules_choice(variants: Counter) -> str:
    """No model: the most frequent spelling, preferring one with a legal form and normal casing."""

    def rank(item: tuple[str, int]) -> tuple:
        name, count = item
        has_form = any(t in LEGAL_FORMS for t in re.sub(r"[^a-z ]", "", name.casefold()).split())
        return (count, has_form, not (name.islower() or name.isupper()), len(name))

    return max(variants.items(), key=rank)[0]


def build_prompt(variants: Counter) -> str:
    lines = "\n".join(f"- {name} ({count}x)" for name, count in variants.most_common())
    return (
        "The following are different spellings of the same company name found in a customer "
        "list, with how often each occurs:\n"
        f"{lines}\n\n"
        "Reply with the single best canonical name: correctly spelled, with its legal form if one "
        "of the spellings has it. Prefer one of the spellings above; only fix an obvious typo. "
        "Reply with the name only, no quotes and no explanation."
    )


def accept_model_answer(answer: str, variants: Counter) -> str | None:
    """Guard against invented names: the answer must be (close to) one of the real spellings."""
    cleaned = answer.strip().splitlines()[0].strip().strip("\"'`") if answer.strip() else ""
    if not cleaned or len(cleaned) > 100:
        return None
    best = max(
        variants, key=lambda v: SequenceMatcher(None, cleaned.casefold(), v.casefold()).ratio()
    )
    if SequenceMatcher(None, cleaned.casefold(), best.casefold()).ratio() < 0.8:
        return None
    return cleaned


class OllamaBackend:
    name = "ollama"

    def __init__(self) -> None:
        self.url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
        self.model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")

    def complete(self, prompt: str) -> str:
        body = json.dumps(
            {
                "model": self.model,
                "stream": False,
                "options": {"temperature": 0},
                "messages": [{"role": "user", "content": prompt}],
            }
        ).encode()
        request = urllib.request.Request(
            f"{self.url}/api/chat", body, {"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.load(response)["message"]["content"]


class AnthropicBackend:
    name = "anthropic"

    def __init__(self) -> None:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        try:
            from anthropic import Anthropic
        except ImportError as error:
            raise RuntimeError("Install the extra first: pip install .[anthropic]") from error
        self.client = Anthropic(api_key=key)
        self.model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")

    def complete(self, prompt: str) -> str:
        response = self.client.messages.create(
            model=self.model, max_tokens=100, messages=[{"role": "user", "content": prompt}]
        )
        return "".join(block.text for block in response.content if block.type == "text")


class ClaudeCliBackend:
    """Owner-only: uses the local `claude` CLI with the owner's own login."""

    name = "claude-cli"

    def complete(self, prompt: str) -> str:
        result = subprocess.run(
            ["claude", "-p"], input=prompt, capture_output=True, text=True, timeout=120, check=False
        )
        if result.returncode != 0:
            raise RuntimeError("claude CLI failed")
        return result.stdout


def get_backend(name: str) -> Backend | None:
    if name == "rules":
        return None
    if name == "ollama":
        return OllamaBackend()
    if name == "anthropic":
        return AnthropicBackend()
    if name == "claude-cli":
        return ClaudeCliBackend()
    raise ValueError(f"Unknown backend '{name}'. Choose from: {', '.join(BACKENDS)}")


def choose_canonical(variants: Counter, backend: Backend | None) -> tuple[str, str]:
    """Return (canonical name, source) where source is rules, model or rules-fallback."""
    if backend is None:
        return rules_choice(variants), "rules"
    try:
        answer = accept_model_answer(backend.complete(build_prompt(variants)), variants)
    except Exception:  # a model failure must never block cleaning
        answer = None
    if answer is None:
        return rules_choice(variants), "rules-fallback"
    return answer, "model"
