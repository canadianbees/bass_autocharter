from statistics import median


WINDOW = 1.5
MIN_SHIFT = 2
MIN_TIME = 0.75


def get_window(notes, t):
    return [n for n in notes if abs(n.time - t) <= WINDOW]


def compute_anchor(window):
    frets = [n.fret for n in window if n.fret > 0]
    if not frets:
        return 1
    return max(1, int(median(frets)))


def smooth_anchors(notes):
    if not notes:
        return [(0.0, 1)]

    anchors = []
    current = None
    last_time = -999

    for n in notes:
        window = get_window(notes, n.time)
        target = compute_anchor(window)

        if current is None:
            current = target
            anchors.append((n.time, current))
            continue

        if abs(target - current) >= MIN_SHIFT and (n.time - last_time) > MIN_TIME:
            current = target
            anchors.append((n.time, current))
            last_time = n.time

    return anchors