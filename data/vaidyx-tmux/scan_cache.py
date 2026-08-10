import json, os, re, shutil, subprocess, urllib.request
models = []
seen = set()
BLOCKED_ROOTS = ('/sys', '/proc', '/dev', '/run', '/var/run')
def safe_path(p):
    try:
        rp = os.path.realpath(os.path.expanduser(p))
        return not any(rp == b or rp.startswith(b + os.sep) for b in BLOCKED_ROOTS)
    except Exception:
        return False
def safe_walk(top):
    if not safe_path(top): return
    for root, dirs, fns in os.walk(top, followlinks=False):
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d)) and safe_path(os.path.join(root, d))]
        yield root, dirs, fns
def gguf_role(name):
    n = name.lower()
    if n.startswith('mmproj') or 'mmproj' in n: return 'projector'
    return 'model'
def gguf_quant(name):
    m = re.search(r'(?i)(UD-)?(IQ[0-9]_[A-Z0-9_]+|Q[0-9](?:_[A-Z0-9]+)+|BF16|F16|FP16|F32|Q8_0)', name)
    return m.group(0).upper() if m else ''
def collect_ggufs(base):
    files = []
    split_groups = {}
    if not os.path.isdir(base) or not safe_path(base): return files
    for root, dirs, fns in safe_walk(base):
        for fn in sorted(fns):
            if not fn.lower().endswith('.gguf'): continue
            if fn.startswith('._'): continue  # macOS AppleDouble sidecar, not a real GGUF
            fp = os.path.join(root, fn)
            try: size = os.path.getsize(fp)
            except Exception: size = 0
            try: rel = os.path.relpath(fp, base).replace(os.sep, '/')
            except Exception: rel = fn
            sm = re.match(r'(?i)^(.+)-(\d+)-of-(\d+)\.gguf$', fn)
            if sm:
                prefix, part_s, total_s = sm.group(1), sm.group(2), sm.group(3)
                key = (root, prefix, total_s)
                g = split_groups.setdefault(key, {'name':fn,'rel_path':rel,'size_bytes':0,'role':gguf_role(fn),'quant':gguf_quant(fn),'parts':int(total_s),'split':True})
                g['size_bytes'] += size
                if int(part_s) == 1:
                    g.update({'name':fn,'rel_path':rel,'role':gguf_role(fn),'quant':gguf_quant(fn)})
                continue
            files.append({'name':fn,'rel_path':rel,'size_bytes':size,'role':gguf_role(fn),'quant':gguf_quant(fn)})
    files.extend(split_groups.values())
    files.sort(key=lambda f: (f.get('role') != 'model', f.get('rel_path', '')))
    return files
def scan_hf(cache):
    if not os.path.isdir(cache): return
    for d in sorted(os.listdir(cache)):
        if not d.startswith('models--'): continue
        rid = d.replace('models--','').replace('--','/')
        if rid in seen: continue
        seen.add(rid)
        blobs = os.path.join(cache, d, 'blobs')
        sz, nf, ic = 0, 0, False
        if os.path.isdir(blobs):
            for f in os.scandir(blobs):
                if f.is_file(): nf += 1; sz += f.stat().st_size
                if f.name.endswith('.incomplete'): ic = True
        snap = os.path.join(cache, d, 'snapshots')
        def snapshot_size():
            total, count, incomplete = 0, 0, False
            seen_real = set()
            for sd in os.listdir(snap):
                sf = os.path.join(snap, sd)
                if not os.path.isdir(sf): continue
                for root, dirs, fns in safe_walk(sf):
                    for fn in fns:
                        fp = os.path.join(root, fn)
                        if fn.endswith('.incomplete'): incomplete = True
                        try:
                            real = os.path.realpath(fp)
                            if real in seen_real: continue
                            seen_real.add(real)
                            total += os.path.getsize(real)
                            count += 1
                        except Exception:
                            pass
            return total, count, incomplete
        # Some HF caches (macOS/MLX/Xet-style) keep blobs elsewhere or expose
        # snapshot symlinks only. Size snapshots too when blob accounting is empty.
        if sz == 0 and os.path.isdir(snap):
            sz2, nf2, ic2 = snapshot_size()
            sz, nf, ic = sz2, nf2, ic or ic2
        is_video = bool(re.search(r'(?i)(^|/)Lightricks/LTX-|(^|/)LTX[-_/]|video|text-to-video|image-to-video', rid))
        is_diffusion = is_video; is_adapter = bool(re.search(r'(?i)(lora|adapter|peft|qlora|control[-_]?lora|diffusion[-_]?lora)', rid)); gguf_files = []
        if os.path.isdir(snap):
            for sd in os.listdir(snap):
                sf = os.path.join(snap, sd)
                if not os.path.isdir(sf): continue
                if os.path.exists(os.path.join(sf, 'model_index.json')): is_diffusion = True
                if os.path.exists(os.path.join(sf, 'adapter_config.json')) or os.path.exists(os.path.join(sf, 'adapter_model.safetensors')): is_adapter = True
                for _root, _dirs, _fns in safe_walk(sf):
                    for _fn in _fns:
                        _lfn = _fn.lower()
                        if _lfn.endswith('.safetensors') and re.search(r'(?i)(ltx|video|upscaler)', _lfn): is_video = True; is_diffusion = True
                        if _lfn in ('adapter_config.json','adapter_model.safetensors','pytorch_lora_weights.safetensors') or 'lora' in _lfn:
                            is_adapter = True
                for f in collect_ggufs(sf): f['rel_path'] = sd + '/' + f['rel_path']; gguf_files.append(f)
        models.append({'repo_id':rid,'size_bytes':sz,'nb_files':nf,'has_incomplete':ic,'path':cache,'is_diffusion':is_diffusion,'is_video':is_video,'is_adapter':is_adapter,'is_gguf':bool(gguf_files),'gguf_files':gguf_files})
def hf_cache_paths():
    candidates = []
    def add(p):
        if not p: return
        p = os.path.expanduser(p)
        if p not in candidates: candidates.append(p)
    add(os.environ.get('HUGGINGFACE_HUB_CACHE'))
    hf_home = os.environ.get('HF_HOME')
    if hf_home: add(os.path.join(hf_home, 'hub'))
    add('~/.cache/huggingface/hub')
    # Docker images mount ./data/huggingface at /app/.cache/huggingface.
    # When HOME is /root, expanduser() misses that persisted cache.
    add('/app/.cache/huggingface/hub')

    return candidates
def normalize_model_dir(p):
    p = os.path.expanduser((p or '').strip())
    if not p: return p
    if os.path.isdir(p) or os.path.isabs(p): return p
    # Users often paste Linux absolute paths without the leading slash.
    # Treat home/<user>/... as /home/<user>/... so remote scans work.
    if p.startswith(('home/', 'mnt/', 'media/', 'data/', 'opt/', 'srv/', 'var/')):
        prefixed = '/' + p
        if os.path.isdir(prefixed): return prefixed
    return p
def scan_dir(p):
    p = normalize_model_dir(p)
    if not os.path.isdir(p) or not safe_path(p): return
    for d in sorted(os.listdir(p)):
        if d.startswith('.'): continue
        if d.startswith('models--'): continue
        fp = os.path.join(p, d)
        if not os.path.isdir(fp) or os.path.islink(fp) or not safe_path(fp): continue
        if d in seen: continue
        is_model = False; is_adapter = bool(re.search(r'(?i)(lora|adapter|peft|qlora|control[-_]?lora|diffusion[-_]?lora)', d)); gguf_files = []
        for root, dirs, fns in safe_walk(fp):
            for fn in fns:
                if fn.lower().endswith('.gguf'): is_model = True
                elif fn == 'config.json' or fn.endswith('.safetensors') or fn.endswith('.bin'): is_model = True
                if fn in ('adapter_config.json','adapter_model.safetensors','pytorch_lora_weights.safetensors') or 'lora' in fn.lower(): is_adapter = True
            if is_model: break
        if not is_model: continue
        gguf_files = collect_ggufs(fp)
        seen.add(d)
        sz, nf = 0, 0
        for dp, _, fns in safe_walk(fp):
            for fn in fns:
                try: nf += 1; sz += os.path.getsize(os.path.join(dp, fn))
                except Exception: pass
        is_diff = os.path.exists(os.path.join(fp, 'model_index.json'))
        models.append({'repo_id':d,'size_bytes':sz,'nb_files':nf,'has_incomplete':False,'path':p,'is_local_dir':True,'is_diffusion':is_diff,'is_adapter':is_adapter,'is_gguf':bool(gguf_files),'gguf_files':gguf_files})
def parse_size(num, unit):
    try: n = float(num)
    except Exception: return 0
    u = (unit or '').upper()
    if u.startswith('TB'): return int(n * 1024 ** 4)
    if u.startswith('GB'): return int(n * 1024 ** 3)
    if u.startswith('MB'): return int(n * 1024 ** 2)
    if u.startswith('KB'): return int(n * 1024)
    return int(n)
def scan_ollama():
    if any(m.get('is_ollama') for m in models): return
    if os.name == 'nt' and not os.environ.get('VAIDYX_ALLOW_OLLAMA_CLI_SCAN'): return
    if not shutil.which('ollama'): return
    try:
        p = subprocess.run(['ollama', 'list'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=6)
    except Exception:
        return
    if p.returncode != 0: return
    for line in (p.stdout or '').splitlines()[1:]:
        parts = line.split()
        if len(parts) < 4: continue
        name = parts[0]
        if not name or name in seen: continue
        size_bytes = parse_size(parts[2], parts[3])
        seen.add(name)
        models.append({'repo_id':name,'size_bytes':size_bytes,'nb_files':1,'has_incomplete':False,'path':'ollama','backend':'ollama','is_ollama':True})
def scan_ollama_api():
    urls = ['http://127.0.0.1:11434/api/tags', 'http://localhost:11434/api/tags', 'http://host.docker.internal:11434/api/tags']
    for url in urls:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                data = json.loads(r.read().decode('utf-8', 'replace'))
        except Exception:
            continue
        for item in data.get('models', []):
            name = item.get('name') or item.get('model')
            if not name or name in seen: continue
            size_bytes = int(item.get('size') or item.get('size_bytes') or 0)
            seen.add(name)
            models.append({'repo_id':name,'size_bytes':size_bytes,'nb_files':1,'has_incomplete':False,'path':'ollama','backend':'ollama','is_ollama':True})
        return
for _hf_cache in hf_cache_paths(): scan_hf(_hf_cache)
scan_ollama_api()
scan_ollama()
print(json.dumps(models))
