"""Turning a journal entry into a validated mood reading.

This is the only place in the app that talks to Groq.

Design rule: **every way this can fail collapses into one exception type.**
Transport errors, bad status codes, unexpected envelopes, unparseable content,
and content that parses but is wrong all arrive at the caller as `AnalysisError`.
The caller therefore has exactly one thing to catch, and cannot accidentally let
a new failure mode through just because it's a class nobody thought of.

That matters because the previous version caught only `requests.RequestException`,
which is the exception raised by the *transport* layer. Every failure that happens
*after* the bytes arrive -- JSON parsing, key lookup, validation -- escaped and
became a 500, even though the journal entry had already been saved successfully.
"""
from __future__ import annotations

import json
from typing import Literal, get_args

import requests
from pydantic import BaseModel, Field, ValidationError, field_validator

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-20b"
TIMEOUT_SECONDS = 10

# A closed vocabulary, defined exactly once.
#
# Observed: the same entry produced 'sad', 'stressed' and 'frustrated' across
# three runs, while its mood_score stayed within one point of itself. The prompt
# *defines* the score's scale, so the model has an anchor to land on. The label
# had no defined set, so it reached for a fresh synonym each time.
#
# Closing the set buys two things:
#   1. Less variance, because the space of possible answers is small and named
#      rather than open-ended.
#   2. The label becomes *groupable*. Free-text labels cannot be counted or
#      charted -- eleven spellings of "anxious" are eleven series on a graph.
#
# The prompt text and the Pydantic type are both derived from this tuple, so
# they cannot drift apart. Adding a label here teaches the model about it and
# makes the validator accept it, in the same edit.
MoodLabel = Literal[
    "happy", "calm", "content", "motivated", "neutral", "tired",
    "anxious", "stressed", "frustrated", "sad", "angry",
]

MOOD_LABEL_VALUES = get_args(MoodLabel)

PROMPT = (
    "Read this journal entry: {entry}\n"
    "\n"
    "Return a JSON object with exactly these fields:\n"
    "\n"
    "mood_label: the single word from this list that best names the dominant "
    "emotion: " + ", ".join(MOOD_LABEL_VALUES) + ".\n"
    "mood_score: an integer from 1 to 10, where 10 represents very positive "
    "feelings and 1 represents very negative feelings, regardless of the "
    "specific mood word.\n"
    "reflection: two or three sentences addressed to the writer that name what "
    "they seem to be feeling, and may end with one open question inviting them "
    "to think further.\n"
    "\n"
    "Rules for the reflection:\n"
    "- Reflect only what is present in the entry. Do not invent details or events.\n"
    "- Do not give advice, instructions, or recommendations.\n"
    "- Do not ask a question that suggests an action, technique, or next step. A\n"
    "  question may only invite the writer to say more about what they already\n"
    "  feel. Asking 'what small step could you take?' is advice wearing a\n"
    "  question mark.\n"
    "- Do not diagnose, or mention medication, therapy, or treatment.\n"
    "- Do not claim to be a person, a therapist, or a friend, and do not say "
    "you are always available.\n"
    "- Do not use clinical or medical language.\n"
    "- If the entry suggests the writer may be in danger, keep the reflection "
    "brief and non-directive. Do not attempt to counsel them.\n"
    "\n"
    'Return a JSON object shaped exactly like this: '
    '{{"mood_label": "stressed", "mood_score": 4, "reflection": "..."}}'
)


class AnalysisError(Exception):
    """The mood analysis could not be produced.

    The journal entry is unaffected by this -- it is already saved. This
    exception is about the analysis only.
    """


class MoodAnalysis(BaseModel):
    """The shape we require of the model, enforced rather than hoped for.

    Pydantic does the work the old code did not: it coerces `"8"` to `8`, rejects
    `8.5`, rejects a score outside 1-10, rejects a missing key, and rejects an
    empty string. Anything that survives this model is safe to write to the
    database and safe to do arithmetic on later.
    """

    mood_label: MoodLabel
    mood_score: int = Field(ge=1, le=10)
    reflection: str = Field(min_length=1, max_length=1000)

    @field_validator("mood_label", mode="before")
    @classmethod
    def normalise_label(cls, value):
        # mode="before" is load-bearing. The default ("after") runs the Literal
        # membership check first, so a model returning " Stressed" -- stray
        # space or a capital -- would be rejected before anything tidied it up.
        # Normalise, then check membership.
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("reflection")
    @classmethod
    def strip_reflection(cls, value: str) -> str:
        return value.strip()


def _extract_json_object(text: str) -> str:
    """Pull the outermost {...} out of whatever the model actually returned.

    This is the honest replacement for the old
    `text.replace("```json", "")` band-aids. Those patched *one specific*
    failure (markdown fences) and were blind to every other shape. This looks
    for the structure instead of a string, so prose before the object, prose
    after it, or fences around it all survive.

    It still raises if there is no JSON object at all -- that case is not
    something to paper over, it is something to report.
    """
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end < start:
        raise AnalysisError(f"model output contained no JSON object: {text[:200]!r}")
    return text[start : end + 1]


def analyze_entry(entry_text: str, api_key: str | None) -> MoodAnalysis:
    """Ask the model to read one entry. Returns a validated MoodAnalysis.

    `api_key` is passed in rather than read from the environment here, so this
    function has no hidden dependency on global state -- and so it can be called
    equally from a request handler or from a background worker.
    """
    if not api_key:
        raise AnalysisError("GROQ_API_KEY is not set")

    try:
        response = requests.post(
            GROQ_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": PROMPT.format(entry=entry_text)}],
                "max_tokens": 1000,
                # Groq's JSON mode. The prompt is still the contract; this makes
                # the contract enforceable at the API boundary rather than only
                # after the fact.
                "response_format": {"type": "json_object"},
            },
            timeout=TIMEOUT_SECONDS,
        )
    except requests.exceptions.RequestException as e:
        raise AnalysisError(f"request failed: {e}") from e

    if response.status_code != 200:
        raise AnalysisError(f"Groq returned {response.status_code}: {response.text[:300]}")

    try:
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as e:
        # `response.json()` succeeds on error bodies too -- an error envelope is
        # valid JSON. Only status_code tells you a call failed; this is the
        # second line of defence for a 200 whose body isn't what we expected.
        raise AnalysisError(f"unexpected response envelope: {e}") from e

    try:
        return MoodAnalysis.model_validate_json(_extract_json_object(content))
    except ValidationError as e:
        raise AnalysisError(f"model output failed validation: {e}") from e
    except json.JSONDecodeError as e:
        raise AnalysisError(f"model output was not valid JSON: {e}") from e
