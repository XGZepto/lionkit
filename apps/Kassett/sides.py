# -*- coding: utf-8 -*-
"""Albums as cassettes: which songs go on which side, and what length of tape they need.

An album with several discs puts one disc on each side (A, B, then a second tape's A and B).
A single-disc album is split where the two sides come out closest in length, with side A the
longer one, the way albums were sequenced for cassette."""
import math

LENGTHS = (46, 60, 90, 100, 120)     # standard cassettes: minutes for both sides together


def split(tracks):
    """tracks: dicts with "disc" and "duration" (ms), in album order. Returns a list of sides:
    {"letter", "tape", "disc", "tracks": [indexes], "duration": ms, "minutes": C-number}."""
    if not tracks:
        return []
    discs, order = {}, []
    for i, t in enumerate(tracks):
        d = t.get("disc") or 1
        if d not in discs:
            discs[d] = []
            order.append(d)
        discs[d].append(i)
    if len(order) > 1:
        groups = [discs[d] for d in order]
    elif len(tracks) < 2:
        groups = [list(range(len(tracks)))]
    else:
        lengths = [t.get("duration") or 0 for t in tracks]
        total, best, best_k, run = sum(lengths), None, 1, 0
        for k in range(1, len(tracks)):
            run += lengths[k - 1]
            gap = abs(run - (total - run))
            if best is None or gap < best or (gap == best and run >= total - run):
                best, best_k = gap, k
        groups = [list(range(best_k)), list(range(best_k, len(tracks)))]
    sides = []
    for n, g in enumerate(groups):
        sides.append({"letter": "AB"[n % 2], "tape": n // 2 + 1,
                      "disc": order[n] if len(order) > 1 else None, "tracks": g,
                      "duration": sum(tracks[i].get("duration") or 0 for i in g)})
    for tape in set(s["tape"] for s in sides):
        longest = max(s["duration"] for s in sides if s["tape"] == tape) / 60000.0
        minutes = next((L for L in LENGTHS if L / 2.0 >= longest), int(math.ceil(longest * 2)))
        for s in sides:
            if s["tape"] == tape:
                s["minutes"] = minutes
    return sides


def locate(sides, tracks, index):
    """The side holding tracks[index], and how far into that side the song starts (ms)."""
    for s in sides:
        if index in s["tracks"]:
            return s, sum(tracks[i].get("duration") or 0 for i in s["tracks"] if i < index)
    return None, 0


def heading(side, multi_disc):
    """What a side's header says in the album's track list."""
    parts = []
    if side["tape"] > 1:
        parts.append(u"Tape %d" % side["tape"])
    parts.append(u"Side %s" % side["letter"])
    if multi_disc and side.get("disc"):
        parts.append(u"Disc %d" % side["disc"])
    return u" · ".join(parts)
