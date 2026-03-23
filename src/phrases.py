import bisect

MIN_PHRASE_LEN = 4.0
MAX_PHRASE_LEN = 14.0
SILENCE_BREAK = 0.6
BAR_SNAP_TOL = 0.2


def nearest_bar(t, bars):
    i = bisect.bisect_left(bars, t)
    candidates = []
    if i < len(bars):
        candidates.append(bars[i])
    if i > 0:
        candidates.append(bars[i - 1])
    for c in candidates:
        if abs(c - t) <= BAR_SNAP_TOL:
            return c
    return t


def segment_phrases(notes, bar_starts):
    if not notes:
        return [0.0]

    def start(n):
        return getattr(n, "time", getattr(n, "start", 0))

    def end(n):
        if hasattr(n, "sustain"):
            return n.time + n.sustain
        return getattr(n, "end", start(n))

    candidates = []

    for i in range(len(notes) - 1):
        n, nxt = notes[i], notes[i + 1]

        gap = start(nxt) - end(n)
        t = end(n)

        score = 0
        if gap >= SILENCE_BREAK:
            score += 5

        t = nearest_bar(t, bar_starts)
        candidates.append((t, score))

    phrases = [0.0]
    last = 0.0

    for t, score in sorted(candidates):
        if t - last < MIN_PHRASE_LEN:
            continue
        if score >= 4 or t - last >= MAX_PHRASE_LEN:
            phrases.append(t)
            last = t

    return sorted(set(phrases))