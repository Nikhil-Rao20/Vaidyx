// AI provider logo SVGs — regex-based matching for self-hosted model names
// Uses official logos from Simple Icons where available, custom minimal SVGs otherwise
// All SVGs use viewBox="0 0 24 24" fill="currentColor"

const _PROVIDERS = [
  // Ollama
  [/ollama|:11434/i,
    '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2.5c-3.1 0-5.65 2.43-5.86 5.48A6.62 6.62 0 0 0 3 13.62C3 18 6.8 21.5 12 21.5s9-3.5 9-7.88a6.62 6.62 0 0 0-3.14-5.64C17.65 4.93 15.1 2.5 12 2.5Zm-2.7 8.25a1.15 1.15 0 1 1 0 2.3 1.15 1.15 0 0 1 0-2.3Zm5.4 0a1.15 1.15 0 1 1 0 2.3 1.15 1.15 0 0 1 0-2.3Zm-5.15 5.15c.75.7 1.55 1.04 2.45 1.04s1.7-.34 2.45-1.04c.26-.24.66-.23.9.03.24.26.23.66-.03.9-.98.91-2.08 1.37-3.32 1.37s-2.34-.46-3.32-1.37a.64.64 0 0 1-.03-.9.64.64 0 0 1 .9-.03Z"/></svg>'],

  // Anthropic — Claude (official Simple Icons)
  [/anthropic|claude/i,
    '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M17.3041 3.541h-3.6718l6.696 16.918H24Zm-10.6082 0L0 20.459h3.7442l1.3693-3.5527h7.0052l1.3693 3.5528h3.7442L10.5363 3.5409Zm-.3712 10.2232 2.2914-5.9456 2.2914 5.9456Z"/></svg>'],

  // Google Gemini (official Simple Icons)
  [/google|gemini|gemma/i,
    '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M11.04 19.32Q12 21.51 12 24q0-2.49.93-4.68.96-2.19 2.58-3.81t3.81-2.55Q21.51 12 24 12q-2.49 0-4.68-.93a12.3 12.3 0 0 1-3.81-2.58 12.3 12.3 0 0 1-2.58-3.81Q12 2.49 12 0q0 2.49-.96 4.68-.93 2.19-2.55 3.81a12.3 12.3 0 0 1-3.81 2.58Q2.49 12 0 12q2.49 0 4.68.96 2.19.93 3.81 2.55t2.55 3.81"/></svg>'],

  // Meta — Llama models (official Simple Icons). Exclude the llama.cpp / llama-cpp
  // / llamacpp inference engine — that's an independent project (ggml), not Meta.
  [/meta|llama(?![.\-_ ]?cpp)/i,
    '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6.915 4.03c-1.968 0-3.683 1.28-4.871 3.113C.704 9.208 0 11.883 0 14.449c0 .706.07 1.369.21 1.973a6.624 6.624 0 0 0 .265.86 5.297 5.297 0 0 0 .371.761c.696 1.159 1.818 1.927 3.593 1.927 1.497 0 2.633-.671 3.965-2.444.76-1.012 1.144-1.626 2.663-4.32l.756-1.339.186-.325c.061.1.121.196.183.3l2.152 3.595c.724 1.21 1.665 2.556 2.47 3.314 1.046.987 1.992 1.22 3.06 1.22 1.075 0 1.876-.355 2.455-.843a3.743 3.743 0 0 0 .81-.973c.542-.939.861-2.127.861-3.745 0-2.72-.681-5.357-2.084-7.45-1.282-1.912-2.957-2.93-4.716-2.93-1.047 0-2.088.467-3.053 1.308-.652.57-1.257 1.29-1.82 2.05-.69-.875-1.335-1.547-1.958-2.056-1.182-.966-2.315-1.303-3.454-1.303zm10.16 2.053c1.147 0 2.188.758 2.992 1.999 1.132 1.748 1.647 4.195 1.647 6.4 0 1.548-.368 2.9-1.839 2.9-.58 0-1.027-.23-1.664-1.004-.496-.601-1.343-1.878-2.832-4.358l-.617-1.028a44.908 44.908 0 0 0-1.255-1.98c.07-.109.141-.224.211-.327 1.12-1.667 2.118-2.602 3.358-2.602zm-10.201.553c1.265 0 2.058.791 2.675 1.446.307.327.737.871 1.234 1.579l-1.02 1.566c-.757 1.163-1.882 3.017-2.837 4.338-1.191 1.649-1.81 1.817-2.486 1.817-.524 0-1.038-.237-1.383-.794-.263-.426-.464-1.13-.464-2.046 0-2.221.63-4.535 1.66-6.088.454-.687.964-1.226 1.533-1.533a2.264 2.264 0 0 1 1.088-.285z"/></svg>'],

  // Mistral AI (official Simple Icons). Match Mixtral and Ministral too.
  [/mi[sx]tral|ministral/i,
    '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M17.143 3.429v3.428h-3.429v3.429h-3.428V6.857H6.857V3.43H3.43v13.714H0v3.428h10.286v-3.428H6.857v-3.429h3.429v3.429h3.429v-3.429h3.428v3.429h-3.428v3.428H24v-3.428h-3.43V3.429z"/></svg>'],

  // Qwen (Tongyi Qianwen) — official geometric hexagonal logo
  [/qwen|alibaba/i,
    '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12.604 1.34c.393.69.784 1.382 1.174 2.075a.18.18 0 00.157.091h5.552c.174 0 .322.11.446.327l1.454 2.57c.19.337.24.478.024.837-.26.43-.513.864-.76 1.3l-.367.658c-.106.196-.223.28-.04.512l2.652 4.637c.172.301.111.494-.043.77-.437.785-.882 1.564-1.335 2.34-.159.272-.352.375-.68.37-.777-.016-1.552-.01-2.327.016a.099.099 0 00-.081.05 575.097 575.097 0 01-2.705 4.74c-.169.293-.38.363-.725.364-.997.003-2.002.004-3.017.002a.537.537 0 01-.465-.271l-1.335-2.323a.09.09 0 00-.083-.049H4.982c-.285.03-.553-.001-.805-.092l-1.603-2.77a.543.543 0 01-.002-.54l1.207-2.12a.198.198 0 000-.197 550.951 550.951 0 01-1.875-3.272l-.79-1.395c-.16-.31-.173-.496.095-.965.465-.813.927-1.625 1.387-2.436.132-.234.304-.334.584-.335a338.3 338.3 0 012.589-.001.124.124 0 00.107-.063l2.806-4.895a.488.488 0 01.422-.246c.524-.001 1.053 0 1.583-.006L11.704 1c.341-.003.724.032.9.34zm-3.432.403a.06.06 0 00-.052.03L6.254 6.788a.157.157 0 01-.135.078H3.253c-.056 0-.07.025-.041.074l5.81 10.156c.025.042.013.062-.034.063l-2.795.015a.218.218 0 00-.2.116l-1.32 2.31c-.044.078-.021.118.068.118l5.716.008c.046 0 .08.02.104.061l1.403 2.454c.046.081.092.082.139 0l5.006-8.76.783-1.382a.055.055 0 01.096 0l1.424 2.53a.122.122 0 00.107.062l2.763-.02a.04.04 0 00.035-.02.041.041 0 000-.04l-2.9-5.086a.108.108 0 010-.113l.293-.507 1.12-1.977c.024-.041.012-.062-.035-.062H9.2c-.059 0-.073-.026-.043-.077l1.434-2.505a.107.107 0 000-.114L9.225 1.774a.06.06 0 00-.053-.031zm6.29 8.02c.046 0 .058.02.034.06l-.832 1.465-2.613 4.585a.056.056 0 01-.05.029.058.058 0 01-.05-.029L8.498 9.841c-.02-.034-.01-.052.028-.054l.216-.012 6.722-.012z"/></svg>'],

  // DeepSeek (official whale logo from LobeHub icons)
  [/deepseek/i,
    '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M23.748 4.482c-.254-.124-.364.113-.512.234-.051.039-.094.09-.137.136-.372.397-.806.657-1.373.626-.829-.046-1.537.214-2.163.848-.133-.782-.575-1.248-1.247-1.548-.352-.156-.708-.311-.955-.65-.172-.241-.219-.51-.305-.774-.055-.16-.11-.323-.293-.35-.2-.031-.278.136-.356.276-.313.572-.434 1.202-.422 1.84.027 1.436.633 2.58 1.838 3.393.137.093.172.187.129.323-.082.28-.18.552-.266.833-.055.179-.137.217-.329.14a5.526 5.526 0 01-1.736-1.18c-.857-.828-1.631-1.742-2.597-2.458a11.365 11.365 0 00-.689-.471c-.985-.957.13-1.743.388-1.836.27-.098.093-.432-.779-.428-.872.004-1.67.295-2.687.684a3.055 3.055 0 01-.465.137 9.597 9.597 0 00-2.883-.102c-1.885.21-3.39 1.102-4.497 2.623C.082 8.606-.231 10.684.152 12.85c.403 2.284 1.569 4.175 3.36 5.653 1.858 1.533 3.997 2.284 6.438 2.14 1.482-.085 3.133-.284 4.994-1.86.47.234.962.327 1.78.397.63.059 1.236-.03 1.705-.128.735-.156.684-.837.419-.961-2.155-1.004-1.682-.595-2.113-.926 1.096-1.296 2.746-2.642 3.392-7.003.05-.347.007-.565 0-.845-.004-.17.035-.237.23-.256a4.173 4.173 0 001.545-.475c1.396-.763 1.96-2.015 2.093-3.517.02-.23-.004-.467-.247-.588zM11.581 18c-2.089-1.642-3.102-2.183-3.52-2.16-.392.024-.321.471-.235.763.09.288.207.486.371.739.114.167.192.416-.113.603-.673.416-1.842-.14-1.897-.167-1.361-.802-2.5-1.86-3.301-3.307-.774-1.393-1.224-2.887-1.298-4.482-.02-.386.093-.522.477-.592a4.696 4.696 0 011.529-.039c2.132.312 3.946 1.265 5.468 2.774.868.86 1.525 1.887 2.202 2.891.72 1.066 1.494 2.082 2.48 2.914.348.292.625.514.891.677-.802.09-2.14.11-3.054-.614zm1-6.44a.306.306 0 01.415-.287.302.302 0 01.2.288.306.306 0 01-.31.307.303.303 0 01-.304-.308zm3.11 1.596c-.2.081-.399.151-.59.16a1.245 1.245 0 01-.798-.254c-.274-.23-.47-.358-.552-.758a1.73 1.73 0 01.016-.588c.07-.327-.008-.537-.239-.727-.187-.156-.426-.199-.688-.199a.559.559 0 01-.254-.078c-.11-.054-.2-.19-.114-.358.028-.054.16-.186.192-.21.356-.202.767-.136 1.146.016.352.144.618.408 1.001.782.391.451.462.576.685.914.176.265.336.537.445.848.067.195-.019.354-.25.452z"/></svg>'],

  // Nous Research / Hermes
  [/nous|hermes/i,
    '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" stroke-width="1.5" fill="none"/></svg>'],

  // Microsoft / Phi (four squares)
  [/microsoft|phi-/i,
    '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M1 1h10v10H1zm12 0h10v10H13zM1 13h10v10H1zm12 0h10v10H13z"/></svg>'],

  // Zhipu AI — GLM, ChatGLM (official Z logo)
  [/zhipu|glm|chatglm/i,
    '<svg viewBox="0 0 24 24" fill="currentColor"><polygon points="19.44,5.68 10.51,18.32 4.56,18.32 13.49,5.68"/><path d="M12.38 5.68l-1.04 1.48a.86.86 0 0 1-.72.38H4.93V5.68h7.45z"/><path d="M11.62 18.32l1.05-1.49a.86.86 0 0 1 .72-.37h5.68v1.86h-7.45z"/></svg>'],

  // MiniMax
  [/minimax/i,
    '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M4 4h4v16H4zm6 4h4v12h-4zm6-4h4v16h-4z"/></svg>'],

  // Kimi / Moonshot AI (crescent moon)
  [/kimi|moonshot/i,
    '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2A10 10 0 0 0 2 12a10 10 0 0 0 10 10 10 10 0 0 0 0-20zm0 2a8 8 0 0 1 0 16A6.5 6.5 0 0 0 12 4z"/></svg>'],

  // NVIDIA / Nemotron (official Simple Icons)
  [/nvidia|nemotron/i,
    '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8.948 8.798v-1.43a6.7 6.7 0 0 1 .424-.018c3.922-.124 6.493 3.374 6.493 3.374s-2.774 3.851-5.75 3.851c-.398 0-.787-.062-1.158-.185v-4.346c1.528.185 1.837.857 2.747 2.385l2.04-1.714s-1.492-1.952-4-1.952a6.016 6.016 0 0 0-.796.035m0-4.735v2.138l.424-.027c5.45-.185 9.01 4.47 9.01 4.47s-4.08 4.964-8.33 4.964c-.37 0-.733-.035-1.095-.097v1.325c.3.035.61.062.91.062 3.957 0 6.82-2.023 9.593-4.408.459.371 2.34 1.263 2.73 1.652-2.633 2.208-8.772 3.984-12.253 3.984-.335 0-.653-.018-.971-.053v1.864H24V4.063zm0 10.326v1.131c-3.657-.654-4.673-4.46-4.673-4.46s1.758-1.944 4.673-2.262v1.237H8.94c-1.528-.186-2.73 1.245-2.73 1.245s.68 2.412 2.739 3.11M2.456 10.9s2.164-3.197 6.5-3.533V6.201C4.153 6.59 0 10.653 0 10.653s2.35 6.802 8.948 7.42v-1.237c-4.84-.6-6.492-5.936-6.492-5.936z"/></svg>'],
];

// Returns an SVG string for the given model ID, or null if no match
export function providerLogo(modelId) {
  if (!modelId) return null;
  for (const [re, svg] of _PROVIDERS) {
    if (re.test(modelId)) return svg;
  }
  return null;
}

// Host suffix → friendly provider label (cloud labels removed — local-only mode).
const _ENDPOINT_LABELS = [];

/**
 * Friendly label for the endpoint that served a model, from its URL.
 * Returns "Local" for loopback/LAN hosts, a known provider name when matched,
 * else the bare host. Null when no URL is available.
 */
export function providerLabel(endpointUrl) {
  if (!endpointUrl || typeof endpointUrl !== "string") return null;
  let host, port;
  try {
    const u = new URL(endpointUrl);
    host = u.hostname;
    port = u.port;
  } catch (_) {
    const stripped = endpointUrl.replace(/^[a-z]+:\/\//i, "").split("/")[0];
    const colonIdx = stripped.lastIndexOf(":");
    host = colonIdx >= 0 ? stripped.slice(0, colonIdx) : stripped;
    port = colonIdx >= 0 ? stripped.slice(colonIdx + 1) : "";
  }
  if (!host) return null;
  const isLoopback = /^(localhost|127\.|0\.0\.0\.0|::1)/.test(host);
  if (isLoopback) {
    if (port === "11434") return "Ollama";
    return "Local";
  }
  if (/^(192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.)/i.test(host)) {
    return "Local";
  }
  // Unknown host — show bare hostname
  return host.replace(/^api\./i, "");
}

// Map endpoint URL → logo SVG using the same model-id regex catalog.
// Tests host + port + path so loopback servers (e.g. Ollama on
// localhost:11434) still match by port. Falls back to null when nothing
// recognises the URL, so callers can render a neutral placeholder.
export function providerLogoFromUrl(url) {
  if (!url) return null;
  let host = '', port = '', path = '';
  try {
    const u = new URL(url);
    host = u.hostname; port = u.port; path = u.pathname || '';
  } catch (_) {
    const raw = String(url).replace(/^[a-z]+:\/\//i, '');
    const slashIdx = raw.indexOf('/');
    const hostport = slashIdx >= 0 ? raw.slice(0, slashIdx) : raw;
    path = slashIdx >= 0 ? raw.slice(slashIdx) : '';
    const colon = hostport.lastIndexOf(':');
    host = colon >= 0 ? hostport.slice(0, colon) : hostport;
    port = colon >= 0 ? hostport.slice(colon + 1) : '';
  }
  // Build candidate strings to test against the provider catalog.
  const candidates = [host, port ? `${host}:${port}` : '', port ? `:${port}` : '', path].filter(Boolean);
  for (const [re, svg] of _PROVIDERS) {
    if (candidates.some(c => re.test(c))) return svg;
  }
  return null;
}

export default { providerLogo, providerLabel, providerLogoFromUrl };
