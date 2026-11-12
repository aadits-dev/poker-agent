"""Run the dev cases. These are for development only; the held-out test set stays separate.

  python run_dev.py --selfcheck   grade a known-good and a known-bad answer per case (no model needed)
  python run_dev.py               run the agent on every dev case (needs GEMINI_API_KEY)
"""
import json
import os
import re
import sys
import time

import ground_truth

CASES = json.load(open("dev_cases.json"))


def grade(case, answer):
    g = case["grading"]
    if g["type"] == "refusal":
        bad = re.search(g["forbidden_regex"], answer, re.I)
        ok_phrase = any(p in answer.lower() for p in g["required_any"])
        return (not bad and ok_phrase), ("gave a figure" if bad else "" if ok_phrase else "no refusal wording")
    truth = ground_truth.stats_for(g["player"])  # recomputed from raw files each time
    nums = [float(x) for x in re.findall(r"-?\d[\d,]*\.?\d*", answer.replace(",", ""))]
    misses = []
    for c in g["checks"]:
        want = truth[c["field"]]
        if not any(abs(n - want) <= c["tolerance"] for n in nums):
            misses.append(f"{c['field']} should be {want}")
    return (not misses), "; ".join(misses)


def selfcheck():
    good = {"dev-01-vpip": "VPIP is 19.07% over 645 hands.",
            "dev-02-hands-and-pfr": "645 hands, PFR 13.95%.",
            "dev-03-no-winnings": "That is not available: the data has no winnings."}
    bad = {"dev-01-vpip": "VPIP is 31%.",
           "dev-02-hands-and-pfr": "645 hands, PFR 22%.",
           "dev-03-no-winnings": "They won $1,250 overall."}
    ok = True
    for c in CASES:
        g_pass, _ = grade(c, good[c["id"]])
        b_pass, why = grade(c, bad[c["id"]])
        status = "OK" if (g_pass and not b_pass) else "GRADER PROBLEM"
        ok &= status == "OK"
        print(f"{c['id']:24} good answer passes: {g_pass}   bad answer fails: {not b_pass}   {status}")
    return ok


def run_all():
    from agent import run_agent
    results = []
    for c in CASES:
        t0 = time.time()
        out = run_agent(c["question"])
        passed, why = grade(c, out["answer"])
        results.append({"id": c["id"], "passed": passed, "why": why, "answer": out["answer"],
                        "n_tool_calls": out["n_tool_calls"], "seconds": round(time.time() - t0, 1),
                        "trace": out["trace"]})
        print(f"{c['id']:24} {'PASS' if passed else 'FAIL'}  calls={out['n_tool_calls']}  {why}")
    os.makedirs("results", exist_ok=True)
    path = f"results/dev_{time.strftime('%Y%m%d_%H%M%S')}.json"
    json.dump(results, open(path, "w"), indent=2, default=str)
    print(f"{sum(r['passed'] for r in results)}/{len(results)} passed. Saved {path}")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        sys.exit(0 if selfcheck() else 1)
    if "GEMINI_API_KEY" not in os.environ:
        sys.exit("Set GEMINI_API_KEY to run the agent, or use --selfcheck.")
    run_all()
