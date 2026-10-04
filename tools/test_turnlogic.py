"""Unit tests for the turn-order and attribution rules (no deps needed).

    python tools/test_turnlogic.py
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))

from turnlogic import (  # noqa: E402
    counselor_took_over,
    counselor_turns,
    evaluated_party,
    next_controller,
    next_speaker,
)

results = []


def check(name, cond):
    results.append((name, cond))
    print(("  PASS  " if cond else "  FAIL  ") + name)


def msg(turn, speaker, by):
    return {"turn": turn, "speaker": speaker, "text": "x", "controlled_by": by,
            "emotion": "neutral"}


print("turn order")
check("the client always opens", next_speaker([]) == "client")
check("counsellor follows the client", next_speaker([msg(1, "client", "llm")]) == "counselor")
check("client follows the counsellor",
      next_speaker([msg(1, "client", "llm"), msg(2, "counselor", "user")]) == "client")

print("\ncontroller assignment")
check("mode A: the opening client turn is the LLM's",
      next_controller("counselor", []) == "llm")
check("mode B: the user opens as the client",
      next_controller("client", []) == "user")
check("mode C: the supervisor never holds a speaking turn",
      next_controller("supervisor", []) == "llm"
      and next_controller("supervisor", [msg(1, "client", "llm")]) == "llm")

print("\nswitching leaves nobody stranded")
t = [msg(1, "client", "llm"), msg(2, "counselor", "user"), msg(3, "client", "llm")]
check("as counsellor it is your turn", next_controller("counselor", t) == "user")
check("after switching away the LLM picks the chair up",
      next_controller("client", t) == "llm")

print("\nattribution")
mixed = t + [msg(4, "counselor", "llm"), msg(5, "client", "llm"), msg(6, "counselor", "user")]
check("chair change detected", counselor_took_over(mixed) is True)
check("single-controller session is not a takeover",
      counselor_took_over([msg(2, "counselor", "llm")]) is False)
check("user turns collected", counselor_turns(mixed, "user") == [2, 6])
check("llm turns collected", counselor_turns(mixed, "llm") == [4])
check("user is evaluated when they ever sat in the chair", evaluated_party(mixed) == "user")
check("otherwise the LLM counsellor is evaluated",
      evaluated_party([msg(1, "client", "llm"), msg(2, "counselor", "llm")]) == "llm")

bad = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(bad)} passed, {len(bad)} failed")
sys.exit(1 if bad else 0)
