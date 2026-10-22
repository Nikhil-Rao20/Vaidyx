"""frame_at.py <run> <session> <mark label or epoch seconds> [offset seconds] -> prints the frame file shown at that time."""
import bisect, json, sys
run, sess, what = sys.argv[1], sys.argv[2], sys.argv[3]
off = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0
base = f"/data/vaidyx/demo_video/raw/{run}"
try:
    t = float(what)
except ValueError:
    t = [m["t"] for m in map(json.loads, open(f"{base}/marks.jsonl")) if m["label"] == what][-1]
t += off
rows = [l.rstrip("\n").split("\t") for l in open(f"{base}/{sess}/frames.tsv")]
ts = [float(r[0]) for r in rows]
i = max(0, bisect.bisect_right(ts, t) - 1)
print(f"{base}/{sess}/{rows[i][1]}")
