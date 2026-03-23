def cluster_notes(notes, max_gap=0.18):
    clusters = []
    current = [notes[0]]

    for n in notes[1:]:
        if n.time - current[-1].time <= max_gap:
            current.append(n)
        else:
            clusters.append(current)
            current = [n]
    clusters.append(current)
    return clusters


def simplify(notes, level):
    if not notes:
        return []

    clusters = cluster_notes(notes)
    result = []

    for c in clusters:
        if len(c) == 1:
            result.append(c[0])
            continue

        if level == 0:
            result.append(c[0])  # easiest
        elif level == 1:
            result.append(c[len(c)//2])
        else:
            result.extend(c)

    return sorted(result, key=lambda n: n.time)


def generate_levels(full_notes):
    return [
        simplify(full_notes, 0),
        simplify(full_notes, 1),
        full_notes
    ]