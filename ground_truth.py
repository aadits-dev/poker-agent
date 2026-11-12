"""Independent ground truth for dev/test cases.

Reads the raw .phhs files directly (no SQLite, no code from load_hands.py or tools.py)
so a bug in the agent's tools is not silently shared with the answer key.
"""
import glob
import tomllib


def _hands(sample_dir="data/sample"):
    for path in sorted(glob.glob(f"{sample_dir}/*.phhs")):
        with open(path, "rb") as f:
            yield from tomllib.load(f).values()


def stats_for(player, sample_dir="data/sample"):
    dealt = vpip = pfr = 0
    for h in _hands(sample_dir):
        if player not in h["players"]:
            continue
        dealt += 1
        me = h["players"].index(player) + 1
        # money each seat has in front of it this street; forced blinds count as already in
        put = {i + 1: float(b) for i, b in enumerate(h["blinds_or_straddles"])}
        to_call = max(put.values())
        did_vpip = did_raise = False
        for a in h["actions"]:
            if a.startswith("d "):
                if a.startswith("d db"):
                    break  # first board card ends preflop
                continue
            seat, kind, *rest = a.split()
            seat = int(seat[1:])
            if kind == "cbr":
                put[seat] = float(rest[0])
                to_call = put[seat]
                if seat == me:
                    did_vpip = did_raise = True
            elif kind == "cc":
                if seat == me and put[seat] < to_call:
                    did_vpip = True
                put[seat] = to_call
        vpip += did_vpip
        pfr += did_raise
    return {"hands": dealt, "vpip": round(100 * vpip / dealt, 2) if dealt else None,
            "pfr": round(100 * pfr / dealt, 2) if dealt else None}


def top_players(n=5, sample_dir="data/sample"):
    counts = {}
    for h in _hands(sample_dir):
        for p in h["players"]:
            counts[p] = counts.get(p, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:n]


if __name__ == "__main__":
    for p, n in top_players(3):
        print(p, n, stats_for(p))
