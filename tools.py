"""Tools the agent can call. Each takes and returns plain JSON-serializable data.

Relationships (what feeds what):
  list_top_players -> gives player ids  -> compute_stat(player, stat)
  compute_stat     -> gives numbers (and the hands counted) -> lookup_hand(hand_id) to show evidence
  query_hands      -> read-only SQL for questions the stat tool does not cover
Stats come from deterministic code here, never from the model's own arithmetic.
"""
import json
import re
import sqlite3

DB_PATH = "hands.db"
STATS = ("hands", "vpip", "pfr")


def _con():
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)  # read-only connection


def list_top_players(limit: int = 5):
    """Players with the most hands in the database."""
    limit = max(1, min(int(limit), 20))
    with _con() as c:
        rows = c.execute(
            "SELECT player, COUNT(*) n FROM hand_players GROUP BY player ORDER BY n DESC, player LIMIT ?",
            (limit,),
        ).fetchall()
    return [{"player": p, "hands": n} for p, n in rows]


def compute_stat(player: str, stat: str):
    """hands = hands dealt in; vpip = % hands with a voluntary preflop call or raise;
    pfr = % hands with a preflop raise."""
    if stat not in STATS:
        return {"error": f"unknown stat '{stat}'. Supported: {', '.join(STATS)}"}
    with _con() as c:
        hands = c.execute("SELECT COUNT(*) FROM hand_players WHERE player=?", (player,)).fetchone()[0]
        if hands == 0:
            return {"error": f"no hands found for player '{player}'"}
        if stat == "hands":
            return {"player": player, "stat": "hands", "value": hands, "hands_counted": hands}
        if stat == "vpip":
            n = c.execute(
                "SELECT COUNT(DISTINCT hand_id) FROM actions WHERE player=? AND street='preflop' AND voluntary=1",
                (player,),
            ).fetchone()[0]
        else:
            n = c.execute(
                "SELECT COUNT(DISTINCT hand_id) FROM actions WHERE player=? AND street='preflop' AND kind='cbr'",
                (player,),
            ).fetchone()[0]
    return {"player": player, "stat": stat, "value": round(100.0 * n / hands, 2),
            "unit": "percent", "hands_counted": hands, "hands_matching": n}


def lookup_hand(hand_id: int):
    with _con() as c:
        h = c.execute("SELECT hand_id, n_players, sb, bb, year, month, day FROM hands WHERE hand_id=?",
                      (int(hand_id),)).fetchone()
        if not h:
            return {"error": f"hand {hand_id} not found"}
        players = c.execute("SELECT idx, player FROM hand_players WHERE hand_id=? ORDER BY idx", (h[0],)).fetchall()
        acts = c.execute("SELECT seq, street, player, kind, amount FROM actions WHERE hand_id=? ORDER BY seq",
                         (h[0],)).fetchall()
    return {"hand_id": h[0], "n_players": h[1], "sb": h[2], "bb": h[3], "date": f"{h[4]}-{h[5]:02d}-{h[6]:02d}",
            "players": [{"seat": i, "player": p} for i, p in players],
            "actions": [{"seq": s, "street": st, "player": p, "kind": k, "amount": a} for s, st, p, k, a in acts]}


_SELECT_ONLY = re.compile(r"^\s*select\b", re.I)


def query_hands(sql: str):
    """Read-only SQL over hands, hand_players, actions. One SELECT statement, 50 rows max."""
    s = sql.strip().rstrip(";")
    if ";" in s or not _SELECT_ONLY.match(s):
        return {"error": "only a single SELECT statement is allowed"}
    try:
        with _con() as c:  # connection is read-only, so writes fail even if the check above missed something
            cur = c.execute(s)
            cols = [d[0] for d in cur.description]
            rows = cur.fetchmany(50)
    except sqlite3.Error as e:
        return {"error": f"sql error: {e}"}
    return {"columns": cols, "rows": rows, "truncated_at": 50}


REGISTRY = {
    "list_top_players": list_top_players,
    "compute_stat": compute_stat,
    "lookup_hand": lookup_hand,
    "query_hands": query_hands,
}


def call_tool(name: str, args: dict):
    fn = REGISTRY.get(name)
    if fn is None:
        return {"error": f"unknown tool '{name}'"}
    try:
        return fn(**args)
    except TypeError as e:
        return {"error": f"bad arguments: {e}"}
    except Exception as e:  # never crash the agent loop on a tool failure
        return {"error": f"{type(e).__name__}: {e}"}


if __name__ == "__main__":
    top = list_top_players(1)[0]
    print(json.dumps(top))
    print(json.dumps(compute_stat(top["player"], "vpip")))
