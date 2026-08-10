# 09 - Swift Native Code: MLX Image Bridge

## 1. Swift Module Overview

The `swift/` directory contains a single Swift Package Manager project called
**vaidyx-mlx-image-bridge**.  It produces two standalone command-line
executables that run Apple MLX machine-learning models for image processing on
Apple Silicon Macs:

| Executable | Purpose | Swift Target |
|---|---|---|
| `vaidyx-mlx-colorize` | Automatic grayscale-to-color image colorization | `VaidyxMLXColorize` |
| `vaidyx-mlx-inpaint` | Object removal / image inpainting | `VaidyxMLXInpaint` |

These executables exist because the upstream MLX model libraries
(`mlx-ddcolor-swift`, `mlx-lama-swift`) ship as Swift library packages with
only minimal smoke-test executables -- not production CLIs.  The bridge
executables wrap each library into a simple, deterministic command-line
interface that the Vaidyx Python backend can call via `subprocess`.

**Why Swift instead of Python?**  Apple's MLX framework exposes its GPU compute
kernels through Metal.  The Swift MLX bindings (`mlx-swift`) give direct,
low-overhead access to the Metal shader library (`mlx.metallib`) that ships
alongside the executables, enabling full Apple Silicon GPU acceleration for
image inference without the overhead and compatibility issues of bridging
through Python's MLX package for these specific image tasks.

### Directory Structure

```
swift/
  vaidyx-mlx-image-bridge/
    Package.swift                                        (lines 1-30)
    Sources/
      VaidyxMLXColorize/
        main.swift                                       (lines 1-80)
      VaidyxMLXInpaint/
        main.swift                                       (lines 1-88)
```

---

## 2. MLX Image Bridge -- Module Architecture

**File:** `swift/vaidyx-mlx-image-bridge/Package.swift` (lines 1-30)

### Package Declaration

```swift
// swift-tools-version: 6.2
let package = Package(
    name: "vaidyx-mlx-image-bridge",
    platforms: [.macOS(.v26)],
    ...
)
```

- **Swift Tools Version:** 6.2 (requires Xcode with Swift 6.2+ toolchain).
- **Platform:** macOS 26 minimum (Apple Silicon only; Metal GPU required).
- **Products:** Two executable products.
- **No library products** -- this package is consumed only as built binaries,
  never as a Swift dependency.

### External Dependencies

| Dependency | Branch | Provides |
|---|---|---|
| `https://github.com/xocialize/mlx-lama-swift` | `main` | `LaMa` and `MIGAN` library products |
| `https://github.com/xocialize/mlx-ddcolor-swift` | `main` | `DDColor` library product |

Both are pinned to the `main` branch, not a release tag.

### Targets

| Target | Type | Dependencies |
|---|---|---|
| `VaidyxMLXInpaint` | `.executableTarget` | `LaMa`, `MIGAN` (from mlx-lama-swift) |
| `VaidyxMLXColorize` | `.executableTarget` | `DDColor` (from mlx-ddcolor-swift) |

### Shared Architecture Pattern

Both executables follow an identical architecture:

1. **Argument parsing** -- A lightweight `Args` struct + `parseArgs()` function
   that reads CLI flags; no external argument-parsing library.
2. **Image I/O via CoreGraphics** -- `decodeCGImage()` reads any image format
   via `CGImageSource`; `encodePNG()` writes the result via
   `CGImageDestination` with `UTType.png`.
3. **Model loading** -- The upstream MLX library's `.fromPretrained()` factory
   loads SafeTensors weights into the Metal GPU.
4. **Inference** -- A single function-call operator on the model object.
5. **Error handling** -- A shared `BridgeError` enum with `.usage`, `.decode`,
   and `.encode` cases; errors are printed to stderr and the process exits with
   code 1.

---

## 3. Colorize Module -- VaidyxMLXColorize

**File:** `swift/vaidyx-mlx-image-bridge/Sources/VaidyxMLXColorize/main.swift` (lines 1-80)

### Purpose

Converts grayscale (or desaturated) images to full color using the DDColor
neural network, running entirely on Apple Silicon GPU via MLX.

### Imports (lines 1-6)

```swift
import Foundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers
import MLX
import DDColor
```

### Data Structures

**`Args` struct** (lines 8-13):

| Field | Type | Default | CLI Flag |
|---|---|---|---|
| `model` | `String` | `""` | `--model` |
| `image` | `String` | `""` | `--image` |
| `output` | `String` | `""` | `--output` |
| `tier` | `String` | `""` | `--tier` |

**`BridgeError` enum** (lines 51-63):

```swift
enum BridgeError: Error, CustomStringConvertible {
    case usage(String)
    case decode(String)
    case encode(String)
}
```

### Function Signatures

| Function | Signature | Lines | Purpose |
|---|---|---|---|
| `value(after:in:)` | `func value(after flag: String, in args: [String]) -> String?` | 15-18 | Extracts the value following a named flag from an argument array |
| `parseArgs()` | `func parseArgs() throws -> Args` | 20-31 | Parses `CommandLine.arguments`, validates required fields, returns populated `Args` or throws `.usage` |
| `decodeCGImage(_:)` | `func decodeCGImage(_ path: String) throws -> CGImage` | 33-40 | Loads an image file at `path` into a `CGImage` via `CGImageSource` |
| `encodePNG(_:_:)` | `func encodePNG(_ image: CGImage, _ path: String) throws` | 42-49 | Writes a `CGImage` as PNG to `path` via `CGImageDestination` |

### Main Execution Flow (lines 65-80)

```swift
do {
    let args = try parseArgs()
    let image = try decodeCGImage(args.image)
    let text = (args.tier + " " + args.model).lowercased()
    let tier: DDColorTier = text.contains("tiny") ? .tiny : .large
    let colorizer = try DDColorColorizer.fromPretrained(
        args.model,
        config: DDColorConfig(tier: tier),
        dtype: .float16
    )
    let output = colorizer(image)
    try encodePNG(output, args.output)
} catch {
    fputs("\(error)\n", stderr)
    exit(1)
}
```

**Key details:**

- **Tier detection** (line 69): The tier is determined by checking whether the
  combined string of `--tier` flag value and model path contains `"tiny"`.
  This maps to `DDColorTier.tiny` (a smaller, faster network) vs.
  `DDColorTier.large` (higher quality, more parameters).
- **Precision** (line 73): The model always loads in `float16` precision.
- **Inference** (line 75): `colorizer(image)` -- the `DDColorColorizer` type
  is callable; it takes a `CGImage` and returns a colorized `CGImage`.

### CLI Usage

```
vaidyx-mlx-colorize --model weights.safetensors --image input.png --output output.png [--tier tiny|large]
```

### Supported Models from mlx-community

| Model | Parameters | Tier | Collection |
|---|---|---|---|
| `mlx-community/DDColor-modelscope-fp16` | 227.88M | large | DDColor (MLX) |
| `mlx-community/DDColor-paper-tiny-fp16` | 55.02M | tiny | DDColor (MLX) |
| `mlx-community/DDColor-artistic-fp16` | 227.88M | large | DDColor (MLX) |

---

## 4. Inpaint Module -- VaidyxMLXInpaint

**File:** `swift/vaidyx-mlx-image-bridge/Sources/VaidyxMLXInpaint/main.swift` (lines 1-88)

### Purpose

Removes objects from images or fills masked regions using either the LaMa
(Large Mask inpainting) or MI-GAN (Mask-Informed GAN) models, running on
Apple Silicon GPU via MLX.

### Imports (lines 1-7)

```swift
import Foundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers
import MLX
import LaMa
import MIGAN
```

### Data Structures

**`Args` struct** (lines 9-15):

| Field | Type | Default | CLI Flag |
|---|---|---|---|
| `model` | `String` | `""` | `--model` |
| `image` | `String` | `""` | `--image` |
| `mask` | `String` | `""` | `--mask` |
| `output` | `String` | `""` | `--output` |
| `mode` | `String` | `""` | `--mode` |

The `mask` field is the critical difference from the colorize module -- inpainting
requires a mask image where white pixels indicate regions to fill.

**`BridgeError` enum** (lines 54-66): Identical to the colorize module.

### Function Signatures

| Function | Signature | Lines | Purpose |
|---|---|---|---|
| `value(after:in:)` | `func value(after flag: String, in args: [String]) -> String?` | 17-19 | Same as colorize module |
| `parseArgs()` | `func parseArgs() throws -> Args` | 21-34 | Parses args; requires `--model`, `--image`, `--mask`, and `--output` |
| `decodeCGImage(_:)` | `func decodeCGImage(_ path: String) throws -> CGImage` | 36-41 | Same as colorize module |
| `encodePNG(_:_:)` | `func encodePNG(_ image: CGImage, _ path: String) throws` | 43-52 | Same as colorize module |

### Main Execution Flow (lines 68-88)

```swift
do {
    let args = try parseArgs()
    let source = try decodeCGImage(args.image)
    let mask = try decodeCGImage(args.mask)
    let lower = args.model.lowercased()
    let mode = args.mode.lowercased()
    let output: CGImage

    if lower.contains("mi-gan") || lower.contains("migan") || mode == "fast" {
        let resolution = lower.contains("512") ? 512 : 256
        let inpainter = try MIGANInpainter.fromPretrained(args.model, resolution: resolution, dtype: .float16)
        output = inpainter(source, mask: mask)
    } else {
        let inpainter = try LaMaInpainter.fromPretrained(args.model, dtype: .bfloat16)
        output = inpainter(source, mask: mask)
    }
    try encodePNG(output, args.output)
} catch {
    fputs("\(error)\n", stderr)
    exit(1)
}
```

**Key details:**

- **Model selection** (line 76): The executable supports two distinct model
  architectures in a single binary.  Selection is automatic based on the model
  path name or the `--mode` flag:
  - If the model path contains `"mi-gan"` or `"migan"`, or `--mode fast` is
    specified, the MI-GAN model is used.
  - Otherwise, the LaMa model is used (default / `--mode best`).
- **MI-GAN resolution** (line 77): Resolution is auto-detected from the model
  path -- 512 if the path contains `"512"`, otherwise 256.
- **MI-GAN precision** (line 78): `float16`.
- **LaMa precision** (line 81): `bfloat16` (note: different from MI-GAN).
- **Inference** (lines 79, 82): Both `MIGANInpainter` and `LaMaInpainter` are
  callable types taking `(CGImage, mask: CGImage) -> CGImage`.

### CLI Usage

```
vaidyx-mlx-inpaint --model weights.safetensors --image input.png --mask mask.png --output output.png [--mode best|fast]
```

### Supported Models from mlx-community

| Model | Parameters | Engine | Resolution | Collection |
|---|---|---|---|---|
| `mlx-community/MI-GAN-256-places2-fp16` | 6.29M | MI-GAN | 256 | Inpainting (MLX) |
| `mlx-community/MI-GAN-256-ffhq-fp16` | 6.29M | MI-GAN | 256 | Inpainting (MLX) |
| `mlx-community/LaMa-bf16` | 51.06M | LaMa | any | Inpainting (MLX) |

---

## 5. Build System

### Package.swift Configuration

**File:** `swift/vaidyx-mlx-image-bridge/Package.swift`

The package uses Swift Package Manager (SPM) with the following constraints:

- **swift-tools-version: 6.2** -- Requires a Swift 6.2+ toolchain (ships with
  Xcode 27 or later standalone Swift toolchain).
- **platforms: [.macOS(.v26)]** -- macOS 26 (Tahoe) minimum deployment target.
  This is required because the MLX Swift framework and the dependent model
  libraries use APIs available only on this or newer macOS versions.

### Build Commands

```bash
cd swift/vaidyx-mlx-image-bridge
swift build -c release
```

The resulting binaries are placed at:
```
.build/release/vaidyx-mlx-colorize
.build/release/vaidyx-mlx-inpaint
```

### Runtime Requirement: mlx.metallib

The built executables require `mlx.metallib` (or `default.metallib`) to be
present in the same directory as the binary at runtime.  This Metal shader
library contains the GPU compute kernels used by the MLX framework.  The
Vaidyx dependency-management system (in `routes/shell_routes.py` and
`routes/cookbook_routes.py`) explicitly checks for this file and reports an
error if it is missing.

The metallib file is typically copied from the Python MLX package's installation
directory during the dependency install step managed by the Cookbook UI.

### Dependency Graph

```
vaidyx-mlx-image-bridge
  |
  +-- VaidyxMLXInpaint (executable)
  |     +-- LaMa    (from mlx-lama-swift)
  |     +-- MIGAN   (from mlx-lama-swift)
  |           +-- MLX (Apple's mlx-swift)
  |                 +-- Metal / mlx.metallib
  |
  +-- VaidyxMLXColorize (executable)
        +-- DDColor (from mlx-ddcolor-swift)
              +-- MLX (Apple's mlx-swift)
                    +-- Metal / mlx.metallib
```

---

## 6. Integration with Python

The Swift executables are called from the Python backend via `subprocess.run()`.
The integration layer lives in `scripts/mlx_image_server.py`, a FastAPI
micro-server that exposes an OpenAI-compatible image API.

### Call Chain

```
Browser/Client
    |
    v
Vaidyx Python Backend (app.py / routes)
    |
    v
scripts/mlx_image_server.py  (FastAPI, port 8100)
    |
    v  subprocess.run(...)
vaidyx-mlx-colorize  or  vaidyx-mlx-inpaint
    |
    v  MLX Metal GPU inference
result.png
```

### Bridge Resolution

**File:** `scripts/mlx_image_server.py`, function `_resolve_bridge()` (lines 137-142)

The server locates the Swift executables by searching PATH and the Python
environment's bin directory.  Each bridge accepts fallback binary names:

| Primary Name | Fallback Name |
|---|---|
| `vaidyx-mlx-colorize` | `mlx-ddcolor-serve` |
| `vaidyx-mlx-inpaint` | `mlx-lama-serve` |

```python
def _resolve_bridge(names: list[str]) -> str:
    for name in names:
        found = _resolve_cli(name)
        if found:
            return found
    return ""
```

If neither binary is found on PATH, the server returns an HTTP 503 with an
error message directing the user to build the bridge from
`swift/vaidyx-mlx-image-bridge`.

### DDColor Bridge Invocation

**File:** `scripts/mlx_image_server.py`, function `_run_ddcolor_bridge()` (lines 214-229)

```python
def _run_ddcolor_bridge(model: str, image_raw: bytes, out_path: Path) -> None:
    bridge = _resolve_bridge(["vaidyx-mlx-colorize", "mlx-ddcolor-serve"])
    ...
    _run_bridge([
        bridge,
        "--model", str(weights),
        "--image", str(inp),
        "--output", str(out_path),
        "--tier", tier,
    ])
```

Steps:
1. Resolve the bridge binary.
2. Write the input image bytes to a temporary PNG file.
3. Locate model weights via `_weights_path()` (local path or Hugging Face
   snapshot download).
4. Determine tier (`"tiny"` or `"large"`) from the model name.
5. Execute the Swift binary and wait for completion.
6. Read the output PNG from the path the Swift binary wrote to.

### Inpaint Bridge Invocation

**File:** `scripts/mlx_image_server.py`, function `_run_inpaint_bridge()` (lines 232-255)

```python
def _run_inpaint_bridge(model: str, image_raw: bytes, mask_raw: bytes | None, out_path: Path) -> None:
    ...
    mode = "fast" if ("mi-gan" in model.lower() or "migan" in model.lower()) else "best"
    _run_bridge([
        bridge,
        "--model", str(weights),
        "--image", str(inp),
        "--mask", str(mask),
        "--output", str(out_path),
        "--mode", mode,
    ])
```

Steps:
1. Validate that a mask image was provided (HTTP 422 if not).
2. Resolve the bridge binary.
3. Write both the input image and mask to temporary PNG files.
   - Mask processing (line 194-201): If the mask has an RGBA alpha channel,
     the Python side converts it using the OpenAI convention -- transparent
     pixels become white (region to inpaint), opaque pixels become black (keep).
4. Determine mode (`"fast"` for MI-GAN, `"best"` for LaMa) from the model name.
5. Execute the Swift binary and wait for completion.

### Subprocess Execution

**File:** `scripts/mlx_image_server.py`, function `_run_bridge()` (lines 205-211)

```python
def _run_bridge(cmd: list[str]) -> None:
    env = os.environ.copy()
    proc = subprocess.run(cmd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "MLX Swift bridge failed").strip()
        logger.error("MLX Swift bridge failed (%s): %s\n%s", proc.returncode, " ".join(cmd), detail[-4000:])
        raise HTTPException(500, detail[-4000:])
```

The bridge runs synchronously (blocking the request handler).  stdout and
stderr are captured; on failure, up to 4000 characters of error output are
returned in the HTTP 500 response.

### API Endpoints That Use the Swift Bridge

All endpoints are in `scripts/mlx_image_server.py`:

| Endpoint | Method | Lines | Bridge Used |
|---|---|---|---|
| `/v1/images/edits` | POST | 386-417 | DDColor or Inpaint (multipart upload) |
| `/v1/images/harmonize` | POST | 420-443 | DDColor or Inpaint (base64 JSON) |
| `/v1/images/generations` | POST | 328-383 | Returns 503 for DDColor/Inpaint models (generation not applicable) |

### Dependency Detection from the UI

The Vaidyx Cookbook UI checks whether the Swift bridge binaries are installed
on the target Apple Silicon Mac. This logic lives in `routes/shell_routes.py`:

**Binary probing** (lines 397-411): The remote probe script searches PATH for
the bridge binaries and checks for `mlx.metallib` / `default.metallib` next to
them.

**Installation status check** (lines 182-191):

```python
if name == "mlx_lama_swift":
    return bool(
        (binaries.get("vaidyx-mlx-inpaint") or binaries.get("mlx-lama-serve"))
        and (files.get("mlx.metallib") or files.get("default.metallib"))
    )
if name == "mlx_ddcolor_swift":
    return bool(
        (binaries.get("vaidyx-mlx-colorize") or binaries.get("mlx-ddcolor-serve"))
        and (files.get("mlx.metallib") or files.get("default.metallib"))
    )
```

Both the binary AND the Metal shader library must be present for the dependency
to be considered satisfied.

### Error Recovery

**File:** `routes/cookbook_helpers.py` (lines 1342-1351)

If the MLX image server emits an error referencing the Swift bridge, the
Cookbook error-recovery system matches it via regex and offers the user a
one-click action to install the missing dependency:

```python
(
    r"mlx-lama-swift|vaidyx-mlx-inpaint|mlx-lama-serve|LaMa / MI-GAN MLX inpainting models require",
    "LaMa / MI-GAN MLX inpainting requires an Vaidyx-compatible mlx-lama-swift bridge ...",
    [{"label": "build mlx-lama-swift bridge ...", "op": "dependency", "package": "mlx_lama_swift"}],
),
```

### Preflight Checks in Cookbook Runner Scripts

**File:** `routes/cookbook_routes.py` (lines 2579-2618)

When the Cookbook generates a launch script for an MLX image model, it includes
shell-level preflight checks that verify the Swift bridge binary is on PATH
and that `mlx.metallib` is present beside it, aborting with a clear error
message if either is missing.
