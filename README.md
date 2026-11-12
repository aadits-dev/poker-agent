# Poker Hand-History Analyst (CIS 1990 final project, solo)

An agent that answers plain-English questions about poker hand histories and returns numbers
that come from deterministic tools, not from the model's own arithmetic.

## Setup and run
```
pip install -r requirements.txt
python load_hands.py                 # builds hands.db from data/sample (3 HandHQ files, ~3k hands)
python run_dev.py --selfcheck        # checks the dev-case graders, no API key needed
export GEMINI_API_KEY=...            # free key: https://aistudio.google.com/apikey
python agent.py "What is the VPIP of player KVjLBSZKFyXvYXYB5s8NgA?"
python run_dev.py                    # runs the 3 dev cases through the agent
```

## How the pieces connect
| Step | Component | Input | Output | Feeds |
|---|---|---|---|---|
| 1 | Agent (Gemini, max 8 tool calls) | user question | chooses a tool, then writes the final answer | tools |
| 2 | `list_top_players(limit)` | a number | `[{player, hands}]` | `compute_stat` (gives it a player id) |
| 3 | `compute_stat(player, stat)` | player id, stat in `hands`, `vpip`, `pfr` | `{value, hands_counted, hands_matching}` | the answer; `lookup_hand` for evidence |
| 4 | `lookup_hand(hand_id)` | hand id | players and every action in the hand | the answer |
| 5 | `query_hands(sql)` | one SELECT | up to 50 rows | the answer (for questions `compute_stat` does not cover) |

Division of work: the tools compute every stat; the agent decides which tools to call, in what order,
checks that results make sense, says so when the data cannot answer a question, and explains the result.

## Data
Public PHH dataset (https://github.com/uoftcprg/phh-dataset, MIT license). `data/sample` holds three
obfuscated HandHQ iPoker files (no-limit hold'em, $0.50/$1 blinds, July 2009). Limits found:
`winnings` is 0 for every hand and stacks are infinite, so profit, pot size and stack questions
cannot be answered. Most hole cards are hidden.

Definitions: VPIP = % of hands where the player voluntarily called or raised preflop (a big blind
checking does not count). PFR = % of hands with a preflop raise.

## Testing
- `ground_truth.py` recomputes stats straight from the raw files (separate code path from the tools).
- `dev_cases.json`: three dev cases with intended outputs and grading rules.
- `run_dev.py --selfcheck` confirms each grader passes a right answer and fails a wrong one.
- The held-out test set will be kept separate and not used while tuning.
