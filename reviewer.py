"""Multi-pass code reviewer with evidence verification.

The hard problem is not finding issues - a model will always find some. It is
staying quiet about the ones that do not matter. A reviewer that comments on
everything gets muted, and a muted reviewer catches nothing.

Baseline (single generic prompt): 65 comments across 5 clean commits.
This: 0. Most of the reduction comes from three mechanisms below.
"""
import json
import re
from openai import OpenAI

from diff_parser import review_scope, chunk_by_file, touches_tests

MODEL = "gpt-4o-mini"
MIN_CONFIDENCE = 0.6
MAX_ATTEMPTS = 3

# Coverage gaps are never urgent. Without this the tests pass reported
# "untested behaviour" at the same severity as an injection flaw.
SEVERITY_CAP = {"tests": "low"}
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

REQUIRED_FIELDS = {"file", "line", "severity", "confidence", "issue", "evidence"}

SHARED_RULES = """
Output JSON: {"findings": [{"file": str, "line": int, "severity": "high"|"medium"|"low",
"confidence": 0.0-1.0, "issue": str, "evidence": str}]}

RULES:
- Only comment on lines listed as in scope. Never on unchanged or removed code.
- "evidence" MUST be copied verbatim from the diff. If you cannot quote it, do not report it.
- "confidence" is how certain you are FROM THIS DIFF ALONE. You cannot see the rest of the file,
  the tests, or the callers. If your finding depends on code you cannot see, confidence is below 0.5.
- "issue" is one sentence. No preamble, no suggested rewrite.
- Most changes have no issues in your category. Returning {"findings": []} is the correct and
  expected answer. Do not invent findings to appear thorough.
- Maximum 3 findings.
"""

# One prompt asking for "any issues" makes the model do four jobs shallowly.
# The DO NOT REPORT lines do most of the work - generic advice only goes away
# when you name it explicitly.
PASSES = {
    "security": """You review code changes for SECURITY defects only.

REPORT: injection (SQL, command, path), hardcoded secrets, unsafe deserialisation,
missing authentication or authorisation checks, unvalidated external input reaching a sink,
unsafe SSL/TLS handling, secrets written to logs.

JavaScript/TypeScript-specific: eval() or new Function() on external input, innerHTML or
dangerouslySetInnerHTML with unsanitised data (XSS), prototype pollution via unguarded
object merges (Object.assign, spread with user input), ReDoS-prone regex patterns.

DO NOT REPORT: general hardening advice, dependency versions, anything requiring knowledge of
code outside this diff, "consider validating input" without a concrete reachable path.
""" + SHARED_RULES,

    "correctness": """You review code changes for CORRECTNESS and ERROR HANDLING defects only.

REPORT: null or undefined dereference visible in the diff, unhandled exception or unhandled
Promise rejection from a call on a changed line, resource left unclosed, off-by-one, inverted
condition, wrong variable used, swallowed exception, mutable default argument.

JavaScript/TypeScript-specific: missing await on an async call whose result is used, an unhandled
rejected Promise, == used where === was intended in a way that changes behaviour, a callback whose
error-first argument is never checked.

DO NOT REPORT: style, naming, type-annotation preferences, "consider adding error handling" with no
specific failure path, performance, anything about language version or syntax features.
""" + SHARED_RULES,

    "tests": """You review code changes for MISSING TEST COVERAGE only.

REPORT: only when the diff changes behaviour AND contains no corresponding test change. Name the
specific untested behaviour.

DO NOT REPORT: "add more edge case tests" or "consider more scenarios" - these are unfalsifiable.
If the diff touches any test file (including *.test.js, *.spec.ts), assume coverage exists and
return no findings. Documentation, version bumps and type annotations need no tests.
""" + SHARED_RULES,
}


def _normalise(text):
    return re.sub(r"\s+", " ", str(text)).strip().lower()


def evidence_present(evidence, diff):
    """Check the quoted evidence actually appears in the diff.

    This is the anti-hallucination mechanism. A model can assert anything in prose
    - the naive version confidently claimed TypeIs was not a standard type hint -
    but it cannot fake a quote that has to appear in the source.

    Whitespace is normalised and a substantial fragment counts, because exact
    reproduction of indentation is a needlessly strict bar.
    """
    needle, haystack = _normalise(evidence), _normalise(diff)
    if len(needle) < 8:
        return False
    if needle in haystack:
        return True
    return any(needle[i:i + 20] in haystack
               for i in range(0, max(len(needle) - 20, 1), 5))


class Reviewer:
    def __init__(self, api_key=None, model=MODEL, min_confidence=MIN_CONFIDENCE):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.min_confidence = min_confidence
        self.spend = {"calls": 0, "in": 0, "out": 0, "usd": 0.0}

    def _chat(self, system, user):
        response = self.client.chat.completions.create(
            model=self.model, temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
        )
        usage = response.usage
        self.spend["calls"] += 1
        self.spend["in"] += usage.prompt_tokens
        self.spend["out"] += usage.completion_tokens
        self.spend["usd"] += usage.prompt_tokens * 0.15e-6 + usage.completion_tokens * 0.60e-6
        return response.choices[0].message.content

    def _ask(self, system, user):
        """Call the model, validate the shape, retry on malformed output.

        json_object mode guarantees valid JSON, not the right shape - a field can
        still be missing. Retrying and then degrading to an empty result matters
        in CI: one malformed response should not take down the whole review.
        """
        for attempt in range(MAX_ATTEMPTS):
            try:
                data = json.loads(self._chat(system, user))
                findings = data.get("findings", [])
                if not isinstance(findings, list):
                    raise ValueError("findings is not a list")
                return [f for f in findings
                        if isinstance(f, dict) and REQUIRED_FIELDS <= set(f)]
            except Exception:
                continue
        return []

    def _filter(self, findings, diff):
        kept, rejected = [], {"evidence": 0, "confidence": 0}
        for finding in findings:
            if not evidence_present(finding["evidence"], diff):
                rejected["evidence"] += 1
                continue
            try:
                confidence = float(finding["confidence"])
            except (TypeError, ValueError):
                confidence = 0.0
            if confidence < self.min_confidence:
                rejected["confidence"] += 1
                continue
            kept.append(finding)
        return kept, rejected

    def review(self, commit):
        findings, rejected = [], {"evidence": 0, "confidence": 0}
        skip_tests = touches_tests(commit)

        for chunk in chunk_by_file(commit):
            diff, scope = review_scope(chunk)
            if not scope:
                continue
            user = (f"DIFF:\n{diff}\n\n"
                    f"LINES IN SCOPE (only these may be commented on):\n" + "\n".join(scope))

            for name, system in PASSES.items():
                if name == "tests" and skip_tests:
                    continue
                kept, rej = self._filter(self._ask(system, user), diff)
                for item in kept:
                    item["pass"] = name
                    cap = SEVERITY_CAP.get(name)
                    if cap:
                        item["severity"] = cap
                findings += kept
                for key in rejected:
                    rejected[key] += rej[key]

        # Passes overlap - an unhandled exception is plausibly both a correctness
        # and a security finding. Same file and line means the same problem.
        seen, deduped = set(), []
        for finding in findings:
            key = (str(finding["file"]), finding["line"])
            if key not in seen:
                seen.add(key)
                deduped.append(finding)

        deduped.sort(key=lambda f: SEVERITY_ORDER.get(str(f["severity"]).lower(), 3))
        return deduped, rejected
