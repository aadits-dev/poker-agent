"""Poker hand-history analyst: an LLM that decides which tools to call, with a hard step limit.

Usage:
  export GEMINI_API_KEY=...        (free key from Google AI Studio)
  python agent.py "What is the VPIP of player KVjLBSZKFyXvYXYB5s8NgA?"

The model never computes stats itself. It picks tools, reads the results, and explains them.
"""
import json
import os
import sys

import tools

MAX_TOOL_CALLS = 8
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

SYSTEM = """You answer questions about poker hand histories stored in a database.
Rules:
- Get every number from a tool. Never calculate or estimate a stat yourself.
- Use compute_stat for hands, vpip and pfr. Use query_hands only for things compute_stat cannot do.
- Player ids are opaque strings. If the user does not give one, call list_top_players first.
- The data has actions only. It has NO winnings, profits, pot results or stack sizes. If asked for
  something the data cannot show, say it is not available instead of guessing.
- Include the player id and the number of hands counted in your answer."""


_client = None


def gemini_step(contents):
    """One model turn. Returns (model_content, tool_calls, text). Isolated so tests can swap it out."""
    global _client
    from google import genai
    from google.genai import types

    if _client is None:  # one shared client, kept alive for the whole run
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    cfg = types.GenerateContentConfig(
        system_instruction=SYSTEM,
        tools=list(tools.REGISTRY.values()),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),  # we run the loop
        temperature=0,
    )
    for attempt in range(5):
        try:
            resp = _client.models.generate_content(model=MODEL, contents=contents, config=cfg)
            break
        except genai.errors.ServerError:  # 503 overloaded: wait and retry
            if attempt == 4:
                raise
            time.sleep(2 ** attempt * 3)
    calls = [(c.name, dict(c.args or {})) for c in (resp.function_calls or [])]
    return resp.candidates[0].content, calls, (resp.text or "") if not calls else ""

def run_agent(question, step=gemini_step, max_calls=MAX_TOOL_CALLS):
    """Returns {"answer", "trace", "n_tool_calls", "stopped"}; trace lists every tool call and result."""
    from google.genai import types

    contents = [types.Content(role="user", parts=[types.Part.from_text(text=question)])]
    trace = []
    while True:
        content, calls, text = step(contents)
        if not calls:
            return {"answer": text, "trace": trace, "n_tool_calls": len(trace), "stopped": "answered"}
        contents.append(content)
        parts = []
        for name, args in calls:
            if len(trace) >= max_calls:  # step limit: stop runaway loops
                return {"answer": "Stopped: reached the tool-call limit before finishing.",
                        "trace": trace, "n_tool_calls": len(trace), "stopped": "limit"}
            result = tools.call_tool(name, args)
            trace.append({"tool": name, "args": args, "result": result})
            parts.append(types.Part.from_function_response(name=name, response={"result": result}))
        contents.append(types.Content(role="user", parts=parts))


if __name__ == "__main__":
    if "GEMINI_API_KEY" not in os.environ:
        sys.exit("Set GEMINI_API_KEY first (free key: https://aistudio.google.com/apikey).")
    q = " ".join(sys.argv[1:]) or "Who are the top 3 players by hands played, and what is each one's VPIP?"
    out = run_agent(q)
    for i, t in enumerate(out["trace"], 1):
        print(f"[{i}] {t['tool']}({json.dumps(t['args'])}) -> {json.dumps(t['result'])[:200]}")
    print("\nANSWER:", out["answer"])
