"""Word boxes on the scan image for a verified quote (V1 item 8.4).

A scanned page has two independent readings: the vision model's transcription (the page text every quote, citation and fact
location points into) and the OCR engine's words with their boxes on the page image (item 8.3, page["ocr_engine"]["words"]).
This module lines the two up word by word so the UI can draw a highlight over the image where a quote was read.

It never changes the transcription and never decides anything clinical: it only says which image box shows a transcribed word.
It draws only where a token is matched, and it errs towards no box rather than a wrong box:
- tokens are compared after light normalisation (case, surrounding punctuation, table pipes, thousands commas);
- the two token sequences are aligned in order (long common runs and words that occur once on both sides first), so a repeated
  token such as "1" maps to the occurrence at the same place, not to the first "1" on the page;
- inside the stretches that differ, words that are clearly the same (high similarity) are paired, and split / merged words
  ("Ki-67" vs "Ki- 67", "IHC:" vs "IHC :") are joined only when they spell exactly the same;
- numbers must match exactly as digits ("60" never lands on a box reading "80", "7.2" never on "72");
- a stretch where the two readings disagree a lot and the pairing is ambiguous gets no boxes at all.
Coordinates are fractions (0..1) of the page image, as the engine stores them.
"""
import re
import unicodedata
from bisect import bisect_left
from difflib import SequenceMatcher

from rapidfuzz import fuzz

FUZZY_MIN = 80  # rapidfuzz ratio for two different spellings to count as the same word (one wrong letter in five)
FUZZY_MIN_LEN = 5  # shorter words must match exactly after normalisation ("ER" is not "PR")
MAX_MERGE = 3  # split / merged words: up to three pieces on either side
SMALL_GAP = 3  # a differing stretch this short on both sides is bounded tightly by matched words: pair freely in order
MAX_GAP_CELLS = 2500  # longer stretches: only pairs in a run of matches or found once on both sides; beyond this size, nothing
SUGGESTED_COVERAGE = 0.6  # suggested span_coverage threshold for showing a highlight (see tests)
MASK_TEXT = "XXXX"  # the engine's masked Aadhaar group (item 8.3)

_TOKEN = re.compile(r"[^\s|]+")  # transcription tokens: whitespace and table pipes separate words
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{2,3}(?!\d))")  # 2,45,000 and 245,000 -> 245000
_NUM = re.compile(r"\d+(?:\.\d+)?")


def _core(c):
    return c.isalnum() or unicodedata.category(c)[0] == "M"  # letters, digits and combining marks (Indic vowel signs)


def _strip(raw):
    """(lo, hi) of the token without surrounding punctuation; lo == hi when nothing is left."""
    lo, hi = 0, len(raw)
    while lo < hi and not _core(raw[lo]):
        lo += 1
    while hi > lo and not _core(raw[hi - 1]):
        hi -= 1
    return lo, hi


def _element(core):
    """Comparison form: NFKC, case-folded, thousands commas removed; inner punctuation dropped unless it sits between digits
    (Ki-67 -> ki67, but 1/2 stays 1/2 and 7.2 stays 7.2, so different numbers never compare equal)."""
    s = _THOUSANDS.sub("", unicodedata.normalize("NFKC", core).casefold())
    out = []
    for i, c in enumerate(s):
        if _core(c) or (0 < i < len(s) - 1 and s[i - 1].isdigit() and s[i + 1].isdigit()):
            out.append(c)
    return "".join(out)


class _Tok:
    __slots__ = ("el", "nums", "pos")

    def __init__(self, el, pos):
        self.el = el
        self.nums = tuple(_NUM.findall(el))
        self.pos = pos  # (start, end) offsets for the transcription; index into the word list for the engine


def _text_tokens(text):
    out = []
    for m in _TOKEN.finditer(text):
        lo, hi = _strip(m.group())
        if lo < hi:
            el = _element(m.group()[lo:hi])
            if el:
                out.append(_Tok(el, (m.start() + lo, m.start() + hi)))
    return out


def _box(w):
    x0, y0, x1, y1 = (float(v) for v in w[1:5])
    return [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]


def _word_tokens(words):
    out, boxes = [], []
    for w in words or ():
        try:
            box = _box(w)
            raw = str(w[0]).replace("|", " ")
        except (TypeError, ValueError, IndexError):
            continue
        lo, hi = _strip(raw)
        el = _element(raw[lo:hi]) if lo < hi else ""
        if el:
            out.append(_Tok(el, len(boxes)))
            boxes.append(box)
    return out, boxes


def _similar(a, b):
    """Similarity 0..1 of two single tokens, 0 when they may not be paired. Numbers must be identical as digits."""
    if a.el == b.el:
        return 1.0
    if a.nums != b.nums:
        return 0.0
    la, lb = len(a.el), len(b.el)
    if min(la, lb) < FUZZY_MIN_LEN or 2 * min(la, lb) < (FUZZY_MIN / 100) * (la + lb):
        return 0.0
    r = fuzz.ratio(a.el, b.el)
    return r / 100 if r >= FUZZY_MIN else 0.0


def _joins(toks, i, k):
    """Element and numbers of toks[i:i+k] read as one word."""
    part = toks[i:i + k]
    return "".join(t.el for t in part), tuple(n for t in part for n in t.nums)


def _gap_pairs(A, B, alo, ahi, blo, bhi):
    """Best in-order pairing inside a differing stretch (dynamic programme). Pairs are (a indices, b indices)."""
    n, m = ahi - alo, bhi - blo
    W = m + 1
    score = [0.0] * ((n + 1) * W)
    move = [None] * ((n + 1) * W)
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            best, mv = score[(i + 1) * W + j], (1, 0)
            if score[i * W + j + 1] > best:
                best, mv = score[i * W + j + 1], (0, 1)
            s = _similar(A[alo + i], B[blo + j])
            if s and s + score[(i + 1) * W + j + 1] > best:
                best, mv = s + score[(i + 1) * W + j + 1], (1, 1)
            b_el, b_nums = B[blo + j].el, B[blo + j].nums
            a_el, a_nums = A[alo + i].el, A[alo + i].nums
            for k in range(2, MAX_MERGE + 1):  # many transcription tokens -> one engine word ("Ki-" "67" -> "Ki-67")
                if i + k <= n and _joins(A, alo + i, k) == (b_el, b_nums) and k + score[(i + k) * W + j + 1] > best:
                    best, mv = k + score[(i + k) * W + j + 1], (k, 1)
            for k in range(2, MAX_MERGE + 1):  # one transcription token -> several engine words
                if j + k <= m and _joins(B, blo + j, k) == (a_el, a_nums) and 1 + score[(i + 1) * W + j + k] > best:
                    best, mv = 1 + score[(i + 1) * W + j + k], (1, k)
            score[i * W + j], move[i * W + j] = best, mv
    pairs, i, j = [], 0, 0
    while i < n and j < m:
        di, dj = move[i * W + j]
        if di and dj:
            pairs.append((list(range(alo + i, alo + i + di)), list(range(blo + j, blo + j + dj))))
        i, j = i + di, j + dj
    return pairs


def _in_run(pairs, a_el, b_el, ca, cb):
    """Keep pairs that sit next to another pair on both sides, or whose words occur only once in the stretch on both sides."""
    keep = []
    for x, p in enumerate(pairs):
        a, b = p
        distinctive = all(ca[a_el[i]] == 1 for i in a) and all(cb[b_el[j]] == 1 for j in b)
        prev_ok = x > 0 and pairs[x - 1][0][-1] + 1 == a[0] and pairs[x - 1][1][-1] + 1 == b[0]
        next_ok = x + 1 < len(pairs) and a[-1] + 1 == pairs[x + 1][0][0] and b[-1] + 1 == pairs[x + 1][1][0]
        if prev_ok or next_ok or distinctive:
            keep.append(p)
    return keep


def _lis(pairs):
    """Longest run of (a, b) pairs increasing in both (pairs sorted by a)."""
    tails, tails_idx, back = [], [], [None] * len(pairs)
    for x, (_, b) in enumerate(pairs):
        k = bisect_left(tails, b)
        back[x] = tails_idx[k - 1] if k else None
        if k == len(tails):
            tails.append(b)
            tails_idx.append(x)
        else:
            tails[k], tails_idx[k] = b, x
    out, x = [], tails_idx[-1] if tails_idx else None
    while x is not None:
        out.append(pairs[x])
        x = back[x]
    return out[::-1]


def _count(seq, lo, hi, sub):
    k, c = len(sub), 0
    for i in range(lo, hi - k + 1):
        if seq[i:i + k] == sub:
            c += 1
            if c > 1:
                break
    return c


def _align(A, B):
    """In-order alignment of transcription tokens A to engine tokens B: list of (a indices, b indices)."""
    a, b = [t.el for t in A], [t.el for t in B]
    sm = SequenceMatcher(None, a, b, autojunk=False)
    out, stack = [], [(0, len(a), 0, len(b))]
    while stack:
        alo, ahi, blo, bhi = stack.pop()
        if alo >= ahi or blo >= bhi:
            continue
        i, j, k = sm.find_longest_match(alo, ahi, blo, bhi)
        if k >= 4 or (k >= 2 and _count(a, alo, ahi, a[i:i + k]) == 1 and _count(b, blo, bhi, a[i:i + k]) == 1):
            out.extend(([i + d], [j + d]) for d in range(k))  # a long common run, or a short one found once on both sides
            stack += [(alo, i, blo, j), (i + k, ahi, j + k, bhi)]
            continue
        ca, cb = {}, {}
        for x in range(alo, ahi):
            ca[a[x]] = ca.get(a[x], 0) + 1
        for y in range(blo, bhi):
            cb[b[y]] = cb.get(b[y], 0) + 1
        where = {b[y]: y for y in range(blo, bhi) if cb[b[y]] == 1}
        anchors = _lis([(x, where[a[x]]) for x in range(alo, ahi) if ca[a[x]] == 1 and a[x] in where])
        if anchors:  # words that occur exactly once on both sides, in the same order (patience alignment)
            out.extend(([x], [y]) for x, y in anchors)
            pa, pb = alo, blo
            for x, y in anchors:
                stack.append((pa, x, pb, y))
                pa, pb = x + 1, y + 1
            stack.append((pa, ahi, pb, bhi))
            continue
        n, m = ahi - alo, bhi - blo
        if n <= SMALL_GAP and m <= SMALL_GAP:
            out.extend(_gap_pairs(A, B, alo, ahi, blo, bhi))
        elif n * m <= MAX_GAP_CELLS:
            out.extend(_in_run(_gap_pairs(A, B, alo, ahi, blo, bhi), a, b, ca, cb))
        # larger ambiguous stretches: no boxes rather than possibly wrong ones
    return out


def _same_line(r, s):
    """Two boxes on one text line: their vertical extents overlap by at least half the smaller height."""
    ov = min(r[3], s[3]) - max(r[1], s[1])
    return ov > 0 and ov >= 0.5 * min(r[3] - r[1], s[3] - s[1])


def _line_groups(boxes):
    """Union rectangle per text line, top to bottom."""
    groups = []
    for bx in sorted(boxes, key=lambda r: ((r[1] + r[3]) / 2, r[0])):
        for g in groups:
            if _same_line(g, bx):
                g[0], g[1], g[2], g[3] = min(g[0], bx[0]), min(g[1], bx[1]), max(g[2], bx[2]), max(g[3], bx[3])
                break
        else:
            groups.append(list(bx))
    return sorted(groups, key=lambda g: (g[1], g[0]))


def _r(v):
    return round(min(1.0, max(0.0, v)), 4)


def _padded(r, pad):
    return [_r(r[0] - pad), _r(r[1] - pad), _r(r[2] + pad), _r(r[3] + pad)]


def token_map(text, words):
    """Transcription tokens matched to engine word boxes: [[start, end, x0, y0, x1, y1], ...] in order of start.

    start / end are offsets into text (the token without surrounding punctuation). A token whose engine counterpart is split
    over several words gets one entry per text line it covers. Tokens that cannot be matched get no entry."""
    if not text or not words:
        return []
    A = _text_tokens(text)
    B, boxes = _word_tokens(words)
    if not A or not B:
        return []
    out = []
    for ai, bj in _align(A, B):
        bxs = [boxes[B[y].pos] for y in bj]
        rects = _line_groups(bxs) if len(bxs) > 1 else bxs
        for x in ai:
            s, e = A[x].pos
            for r in rects:
                out.append([s, e, _r(r[0]), _r(r[1]), _r(r[2]), _r(r[3])])
    out.sort(key=lambda t: (t[0], t[3], t[2]))
    return out


def _overlapping(tmap, start, end):
    """Entries of a token map whose token overlaps [start, end) (tmap is sorted by start; tokens do not overlap each other)."""
    i = bisect_left(tmap, [start])
    while i > 0 and tmap[i - 1][1] > start:
        i -= 1
    for t in tmap[i:]:
        if t[0] >= end:
            break
        if t[1] > start:
            yield t


def boxes_for_span(tmap, start, end, pad=0.003):
    """Highlight rectangles for the text span [start, end): one per text line, padded slightly, clipped to 0..1."""
    if not tmap or end <= start:
        return []
    return [_padded(g, pad) for g in _line_groups([t[2:6] for t in _overlapping(tmap, start, end)])]


def span_coverage(tmap, text, start, end):
    """Share (0..1) of the span's word tokens (with a letter or digit) that have a box. 0.0 when the span has none."""
    if not text or end <= start:
        return 0.0
    covered = total = 0
    hits = list(_overlapping(tmap or [], start, end))
    for m in _TOKEN.finditer(text, max(0, start), min(len(text), end)):
        lo, hi = _strip(m.group())
        if lo >= hi:
            continue
        ts, te = m.start() + lo, m.start() + hi
        total += 1
        covered += any(t[0] < te and t[1] > ts for t in hits)
    return covered / total if total else 0.0


def masked_boxes(words, pad=0.003, indices=None):
    """Boxes of the words that held masked Aadhaar digits, padded, for blacking out the page preview: the words at `indices` (the
    engine records which words it masked, item 8.3), else, for pages read before it did, every word containing "XXXX" ("XXXX",
    "(XXXX", "XXXX-XXXX-2200", "Aadhaar:XXXX"). The whole word box is filled: over-masking is safe, under-masking is not."""
    out, words = [], list(words or ())
    pick = sorted({i for i in indices if isinstance(i, int) and 0 <= i < len(words)}) if indices is not None else \
        [i for i, w in enumerate(words) if isinstance(w, (list, tuple)) and w and MASK_TEXT in str(w[0])]
    for i in pick:
        try:
            out.append(_padded(_box(words[i]), pad))
        except (TypeError, ValueError, IndexError):
            continue
    return out
