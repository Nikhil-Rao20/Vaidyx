"""Narration for the demo video with Kokoro-82M (af_heart), on the CPU.

  HF_HUB_OFFLINE=1 /data/vaidyx/venv/audio/bin/python -I tts.py   (reads edit/plan.json, writes edit/voice/<line id>.wav + voice.json)

Captions keep the written form; the voice gets a spoken form (acronyms spelled, the brand name with its pronunciation).
A line already rendered with the same spoken text is skipped.
"""
import hashlib
import json
import os
import re

import numpy as np
import soundfile as sf

PLAN = "/data/vaidyx/demo_video/edit/plan.json"
OUT = "/data/vaidyx/demo_video/edit/voice"
VOICE, SPEED, SR = "af_heart", 1.0, 24000

SPOKEN = [
    (r"\bVaidyx's\b", "[Vaidyx's](/vˈIdɪksɪz/)"),
    (r"\bVaidyx\b", "[Vaidyx](/vˈIdɪks/)"),
    (r"\bUHID\b", "U H I D"),
    (r"\bOPD\b", "O P D"),
    (r"\bIHC\b", "I H C"),
    (r"\bHIS\b", "H I S"),
    (r"\bCT\b", "C T"),
    (r"\bMDT\b", "M D T"),
    (r"\bNCG\b", "N C G"),
    (r"\bPACS\b", "packs"),
    (r"\bABHA\b", "[ABHA](/ˈɑbə/)"),
    (r"\bPM-JAY\b", "P M J A Y"),
    (r"\bwalkthrough\b", "walk-through"),
    (r"\bverified\b", "[verified](/vˈɛɹɪfˌId/)"),
    (r"\bAnjali's\b", "[Anjali's](/ˈʌndʒəliz/)"),
    (r"\bER\b", "E R"),
    (r"\bPR\b", "P R"),
    (r"\bHER2\b", "her two"),
    (r"\bKi-67\b", "K I sixty-seven"),
    (r"\bAnjali\b", "[Anjali](/ˈʌndʒəli/)"),
]


def spoken(text: str) -> str:
    for pat, rep in SPOKEN:
        text = re.sub(pat, rep, text)
    return text


def main():
    os.makedirs(OUT, exist_ok=True)
    from kokoro import KPipeline
    pipe = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
    index_path = os.path.join(OUT, "voice.json")
    index = json.load(open(index_path)) if os.path.exists(index_path) else {}
    for ch in json.load(open(PLAN)):
        for seg in ch["segments"]:
            for line in seg["lines"]:
                say = spoken(line["text"])
                key = hashlib.sha1(f"{VOICE}|{SPEED}|{say}".encode()).hexdigest()[:12]
                wav = os.path.join(OUT, f"{line['id']}.wav")
                if index.get(line["id"], {}).get("key") == key and os.path.exists(wav):
                    continue
                parts = [np.asarray(a, dtype=np.float32) for _, _, a in pipe(say, voice=VOICE, speed=SPEED)]
                gap = np.zeros(int(0.12 * SR), dtype=np.float32)
                audio = np.concatenate([x for p in parts for x in (p, gap)][:-1]) if parts else np.zeros(SR // 2, np.float32)
                # trim leading and trailing silence
                nz = np.where(np.abs(audio) > 0.01)[0]
                if len(nz):
                    audio = audio[max(0, nz[0] - int(0.03 * SR)): nz[-1] + int(0.08 * SR)]
                sf.write(wav, audio, SR)
                index[line["id"]] = {"key": key, "text": line["text"], "say": say, "seconds": round(len(audio) / SR, 3)}
                json.dump(index, open(index_path, "w"), indent=1)
                print(f"{line['id']}: {len(audio) / SR:.1f} s  {line['text'][:70]}", flush=True)
    total = sum(v["seconds"] for v in index.values())
    print(f"{len(index)} lines, {total / 60:.1f} min of narration")


if __name__ == "__main__":
    main()
