"""Load PHH hand files (.phhs) into a SQLite database.

Usage: python load_hands.py [sample_dir] [db_path]

Tables
  hands(hand_id, source, n_players, sb, bb, year, month, day)
  hand_players(hand_id, idx, player)            idx is 1..n, matching p1..pn in actions
  actions(hand_id, seq, street, player, kind, amount, voluntary)
      kind: f = fold, cc = check/call, cbr = bet/raise
      voluntary: preflop only, 1 if the player put money in beyond a forced blind
"""
import glob
import os
import sqlite3
import sys
import tomllib

SCHEMA = """
DROP TABLE IF EXISTS hands;
DROP TABLE IF EXISTS hand_players;
DROP TABLE IF EXISTS actions;
CREATE TABLE hands(hand_id INTEGER PRIMARY KEY, source TEXT, n_players INTEGER,
                   sb REAL, bb REAL, year INTEGER, month INTEGER, day INTEGER);
CREATE TABLE hand_players(hand_id INTEGER, idx INTEGER, player TEXT);
CREATE TABLE actions(hand_id INTEGER, seq INTEGER, street TEXT, player TEXT,
                     kind TEXT, amount REAL, voluntary INTEGER);
CREATE INDEX idx_actions_player ON actions(player);
CREATE INDEX idx_actions_hand ON actions(hand_id);
CREATE INDEX idx_players_player ON hand_players(player);
"""


def parse_actions(hand):
    """Yield (seq, street, player, kind, amount, voluntary) for each player action."""
    players = hand["players"]
    commit = {i + 1: float(b) for i, b in enumerate(hand["blinds_or_straddles"])}
    current_bet = max(commit.values())
    street_names = ["preflop", "flop", "turn", "river"]
    street = 0
    seq = 0
    for a in hand["actions"]:
        parts = a.split()
        if parts[0] == "d":
            if parts[1] == "db":  # board cards dealt, new street
                street += 1
                commit = {i: 0.0 for i in commit}
                current_bet = 0.0
            continue
        idx = int(parts[0][1:])
        kind = parts[1]
        if kind not in ("f", "cc", "cbr"):  # e.g. 'sm' show/muck lines are not betting actions
            continue
        amount = float(parts[2]) if len(parts) > 2 else None
        voluntary = None
        if street == 0:
            if kind == "cbr":
                voluntary = 1
            elif kind == "cc":
                voluntary = 1 if commit[idx] < current_bet else 0  # call vs. check
            else:
                voluntary = 0
        if kind == "cbr":
            commit[idx] = amount
            current_bet = amount
        elif kind == "cc":
            commit[idx] = current_bet
        seq += 1
        yield seq, street_names[min(street, 3)], players[idx - 1], kind, amount, voluntary


def load(sample_dir, db_path):
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    n_hands = 0
    for path in sorted(glob.glob(os.path.join(sample_dir, "*.phhs"))):
        with open(path, "rb") as f:
            data = tomllib.load(f)
        source = os.path.basename(path)
        for h in data.values():
            if h.get("variant") != "NT":
                continue
            hid = int(h["hand"])
            blinds = [b for b in h["blinds_or_straddles"] if b]
            con.execute(
                "INSERT OR IGNORE INTO hands VALUES (?,?,?,?,?,?,?,?)",
                (hid, source, len(h["players"]), blinds[0], blinds[1] if len(blinds) > 1 else blinds[0],
                 h["year"], h["month"], h["day"]),
            )
            con.executemany(
                "INSERT INTO hand_players VALUES (?,?,?)",
                [(hid, i + 1, p) for i, p in enumerate(h["players"])],
            )
            con.executemany(
                "INSERT INTO actions VALUES (?,?,?,?,?,?,?)",
                [(hid, *row) for row in parse_actions(h)],
            )
            n_hands += 1
    con.commit()
    con.close()
    return n_hands


if __name__ == "__main__":
    sample = sys.argv[1] if len(sys.argv) > 1 else "data/sample"
    db = sys.argv[2] if len(sys.argv) > 2 else "hands.db"
    print(f"loaded {load(sample, db)} hands into {db}")
