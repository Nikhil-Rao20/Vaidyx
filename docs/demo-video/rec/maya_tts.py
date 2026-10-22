"""Narration with Maya1 (maya-research/maya1, Apache-2.0) on the CPU, decoded with SNAC 24 kHz.

  /data/vaidyx/venv/maya/bin/python -I maya_tts.py lines.json out_dir [--description "..."] [--seed 7] [--threads 32]

lines.json: [{"id": "c01-01", "text": "..."}]. Writes out_dir/<id>.wav (24 kHz mono) and out_dir/index.json with the durations.
A line already rendered with the same text, description and seed is skipped. Prompt format and token ids follow the model card.
"""
import argparse
import hashlib
import json
import os
import sys
import time

import numpy as np
import soundfile as sf
import torch
from snac import SNAC
from transformers import AutoModelForCausalLM, AutoTokenizer

REPO = "maya-research/maya1"
REVISION = "b1b9b38ca9decbfcfd6c98ea93dd502bfd0f9572"
CODE_START, CODE_END, CODE_OFFSET = 128257, 128258, 128266
SNAC_MIN, SNAC_MAX = 128266, 156937
SOH, EOH, SOA, TEXT_EOT = 128259, 128260, 128261, 128009
DEFAULT_DESCRIPTION = ("Female voice in her 30s with an Indian English accent. Warm, clear diction, calm and confident, "
                       "a professional narrator for a software demo. Moderate pacing, normal pitch.")


def prompt(tok, description, text):
    d = lambda i: tok.decode([i])
    return d(SOH) + tok.bos_token + f'<description="{description}"> {text}' + d(TEXT_EOT) + d(EOH) + d(SOA) + d(CODE_START)


def unpack(codes):
    frames = len(codes) // 7
    codes = codes[: frames * 7]
    l1, l2, l3 = [], [], []
    for i in range(frames):
        s = codes[i * 7:(i + 1) * 7]
        l1.append((s[0] - CODE_OFFSET) % 4096)
        l2 += [(s[1] - CODE_OFFSET) % 4096, (s[4] - CODE_OFFSET) % 4096]
        l3 += [(s[2] - CODE_OFFSET) % 4096, (s[3] - CODE_OFFSET) % 4096, (s[5] - CODE_OFFSET) % 4096, (s[6] - CODE_OFFSET) % 4096]
    return l1, l2, l3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lines")
    ap.add_argument("out")
    ap.add_argument("--description", default=DEFAULT_DESCRIPTION)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--threads", type=int, default=32)
    ap.add_argument("--temperature", type=float, default=0.4)
    a = ap.parse_args()
    torch.set_num_threads(a.threads)
    os.makedirs(a.out, exist_ok=True)
    lines = json.load(open(a.lines))
    index_path = os.path.join(a.out, "index.json")
    index = json.load(open(index_path)) if os.path.exists(index_path) else {}

    t0 = time.time()
    tok = AutoTokenizer.from_pretrained(REPO, revision=REVISION)
    model = AutoModelForCausalLM.from_pretrained(REPO, revision=REVISION, dtype=torch.bfloat16).eval()
    snac = SNAC.from_pretrained("hubertsiuzdak/snac_24khz").eval()
    print(f"loaded in {time.time() - t0:.0f} s", flush=True)

    for item in lines:
        key = hashlib.sha1(json.dumps([item["text"], a.description, a.seed, a.temperature]).encode()).hexdigest()[:12]
        wav = os.path.join(a.out, f"{item['id']}.wav")
        if index.get(item["id"], {}).get("key") == key and os.path.exists(wav):
            continue
        torch.manual_seed(a.seed)
        ids = tok(prompt(tok, a.description, item["text"]), return_tensors="pt", add_special_tokens=False)
        t = time.time()
        # roughly 85 audio tokens a second of speech; allow 2.6 words a second at the slowest, plus a margin
        budget = int(min(4000, 260 + len(item["text"].split()) * 60))
        with torch.inference_mode():
            out = model.generate(**ids, max_new_tokens=budget, min_new_tokens=28, temperature=a.temperature, top_p=0.9,
                                 repetition_penalty=1.1, do_sample=True, eos_token_id=CODE_END, pad_token_id=CODE_END)
        gen = out[0, ids["input_ids"].shape[1]:].tolist()
        ended = CODE_END in gen
        gen = gen[: gen.index(CODE_END)] if ended else gen
        codes = [g for g in gen if SNAC_MIN <= g <= SNAC_MAX]
        l1, l2, l3 = unpack(codes)
        with torch.inference_mode():
            audio = snac.decode([torch.tensor(l, dtype=torch.long).unsqueeze(0) for l in (l1, l2, l3)])[0, 0].float().numpy()
        audio = audio[2048:] if len(audio) > 4096 else audio  # the decoder's warm-up samples
        sf.write(wav, audio, 24000)
        dur = len(audio) / 24000
        index[item["id"]] = {"key": key, "text": item["text"], "seconds": round(dur, 2), "tokens": len(gen), "ended": ended}
        json.dump(index, open(index_path, "w"), indent=1)
        print(f"{item['id']}: {dur:.1f} s audio, {len(gen)} tokens in {time.time() - t:.0f} s ({len(gen) / max(1e-6, time.time() - t):.1f} tok/s)"
              f"{'' if ended else '  NOT ENDED'}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
