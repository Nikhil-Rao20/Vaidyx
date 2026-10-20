"""Synthetic camera feeds for the meeting participants (Chromium --use-file-for-fake-video-capture): a soft moving gradient, a
round avatar with initials, the role, and 'Test camera, synthetic'. No faces. 640x360, 15 fps, 4 s loop, y4m."""
import math, subprocess, sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont
FFMPEG = sys.argv[1]
F = "/home/bharath.tangella/vaidyx/report/Inter-SemiBold.ttf"
R = "/home/bharath.tangella/vaidyx/report/Inter-Regular.ttf"
W, H, FPS, SEC = 640, 360, 15, 4
PEOPLE = {
    "mdt": ("MC", "MDT Coordinator", (14, 116, 144), (99, 102, 241)),
    "breast": ("BS", "Breast Surgery", (13, 148, 136), (14, 116, 144)),
    "rad": ("RD", "Radiology", (124, 58, 237), (37, 99, 235)),
    "path": ("PH", "Pathology", (190, 18, 60), (217, 119, 6)),
    "medonc": ("MO", "Medical Oncology", (21, 128, 61), (13, 148, 136)),
    "room": ("TB", "Tumour Board room", (30, 41, 59), (14, 116, 144)),
}
big, mid, small = ImageFont.truetype(F, 54), ImageFont.truetype(F, 22), ImageFont.truetype(R, 15)
for key, (ini, role, c1, c2) in PEOPLE.items():
    if len(sys.argv) > 2 and key not in sys.argv[2:]: continue
    out = f"/data/vaidyx/demo_video/assets/cams/{key}.y4m"
    p = subprocess.Popen([FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                          "-pix_fmt", "yuv420p", out], stdin=subprocess.PIPE)
    for i in range(FPS * SEC):
        t = i / (FPS * SEC) * 2 * math.pi
        img = Image.new("RGB", (W, H))
        d = ImageDraw.Draw(img)
        for y in range(H):
            k = y / H
            m = 0.5 + 0.5 * math.sin(t + k * 2.2)
            col = tuple(int(c1[j] * (1 - k) * (0.75 + 0.25 * m) + c2[j] * k * (0.8 + 0.2 * (1 - m))) for j in range(3))
            d.line([(0, y), (W, y)], fill=col)
        img = img.filter(ImageFilter.GaussianBlur(2))
        d = ImageDraw.Draw(img)
        cx, cy, r = W // 2, H // 2 - 22, 62 + 3 * math.sin(t * 2)
        d.ellipse([cx - r - 8, cy - r - 8, cx + r + 8, cy + r + 8], outline=(255, 255, 255, 90), width=2)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255))
        d.text((cx, cy), ini, font=big, fill=c1, anchor="mm")
        d.text((cx, cy + r + 34), role, font=mid, fill=(255, 255, 255), anchor="mm")
        d.text((W - 14, H - 14), "Test camera, synthetic", font=small, fill=(255, 255, 255), anchor="rs")
        p.stdin.write(img.tobytes())
    p.stdin.close(); p.wait()
    print(key, "ok")
