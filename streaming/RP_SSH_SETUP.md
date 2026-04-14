# Live Detection via SSH (Raspberry Pi camera → GPU server, viewed on Surface)

Quick reference for running live YOLOv4 detection when the USB camera is on a headless Raspberry Pi (same LAN as the Surface), the GPU is on a remote server on a different network, and the Surface is used only to drive the Pi and view the output.

## Architecture

```
[USB camera on Pi] → [ffmpeg on Pi] ─SSH tunnel─► [mediamtx RTSP on server] → [YOLOv4 server]
                                                                                      │
[Surface browser] ◄───────────────── SSH tunnel ──────────────────────────────────────┘
```

Both the Pi and the Surface open their own SSH tunnel to the server. They don't talk to each other at the app layer — the server is the meeting point.

## What runs where

| Machine | Terminal | Command |
|---------|----------|---------|
| Server  | SSH #1 | (chat / general work — no command needed) |
| Server  | SSH #2 | Command 1 |
| Server  | SSH #3 | Command 2 |
| Surface | PowerShell #1 (SSH'd into Pi) | Command 3 |
| Pi (inside the SSH'd session) | — | Command 4 (nested SSH to server) |
| Pi (second shell) | — | Command 5 |
| Surface | PowerShell #2 (SSH'd into server) | Command 6 |
| Surface | Browser | Command 7 |

One-time prerequisites are listed at the bottom.

---

## Command 1 — Start mediamtx (RTSP relay) on the server

```bash
cd ~/mediamtx
./mediamtx
```

Leave it running. Listens on `:8554`.

---

## Command 2 — Start the YOLOv4 server

```bash
cd ~/Documents/GitHub/YOLOv4-Pytorch
uv run python -m streaming.server --source rtsp://localhost:8554/camera
```

Leave it running. It will retry until Command 5 starts pushing frames, then pick them up. Listens on `:8085`.

---

## Command 3 — SSH from Surface to Pi

In PowerShell on the Surface:

```powershell
ssh <pi-user>@<pi-address>
```

Default Pi OS user is often `pi`. The address is typically something like `raspberrypi.local` (mDNS) or an IP like `192.168.1.42`. Leave this session open — the next two commands run inside it.

---

## Command 4 — From Pi, open an SSH tunnel to the server

From within the Pi shell (i.e. inside the SSH session opened by Command 3):

```bash
ssh -N -L 8554:localhost:8554 <server-user>@<server-address>
```

The `-L` syntax is `-L <PI_PORT>:localhost:<SERVER_PORT>` — the `localhost` is interpreted on the server side.

| Forward | Pi port (ffmpeg pushes here) | Server port (lands here) | Direction | Purpose |
|---------|------------------------------|--------------------------|-----------|---------|
| `-L 8554:localhost:8554` | `localhost:8554` on Pi | `localhost:8554` on server (mediamtx) | Pi → server | Camera push reaches mediamtx |

`-N` means "don't run a remote shell, just hold the tunnel open." The terminal will appear idle — that's correct. Leave it open.

---

## Command 5 — Push the USB camera from Pi to the tunnel

Open a **second SSH session to the Pi** from your Surface (repeat Command 3 in a new PowerShell window). Then, on the Pi:

First, confirm the capture device (one-time check):

```bash
v4l2-ctl --list-devices
```

USB webcams often expose multiple `/dev/videoN` nodes — only one is the capture stream. Pick the first `videoN` under your camera's name (commonly `/dev/video0`).

Then, push with **hardware** encoding (preferred on Pi 3B+):

```bash
ffmpeg -f v4l2 -framerate 15 -video_size 640x480 -i /dev/video0 -c:v h264_v4l2m2m -b:v 1M -f rtsp -rtsp_transport tcp rtsp://localhost:8554/camera
```

If ffmpeg errors with "Unknown encoder 'h264_v4l2m2m'" or the stream fails silently, fall back to **software** encoding:

```bash
ffmpeg -f v4l2 -framerate 15 -video_size 640x480 -i /dev/video0 -c:v libx264 -preset ultrafast -tune zerolatency -b:v 1M -f rtsp -rtsp_transport tcp rtsp://localhost:8554/camera
```

Software encoding is CPU-heavy on a Pi 3B+; if it can't keep up (frame drops, `frame=... fps=<<15`), drop to `-framerate 10 -video_size 480x360`.

Leave it running. You should see `frame= NN fps=15 ...` scrolling. In the YOLOv4 server terminal on the server, the retry messages should stop.

---

## Command 6 — SSH tunnel from Surface to server (for the viewer page)

In a **new** PowerShell window on the Surface:

```powershell
ssh -N -L 8085:localhost:8085 <server-user>@<server-address>
```

| Forward | Surface port (browser connects here) | Server port (lands here) | Direction | Purpose |
|---------|---------------------------------------|--------------------------|-----------|---------|
| `-L 8085:localhost:8085` | `localhost:8085` on Surface | `localhost:8085` on server (YOLOv4 viewer) | Surface → server | Browser loads the viewer page |

Leave open.

---

## Command 7 — Open the viewer

In the Surface browser:

```
http://localhost:8085
```

You should see the Pi's camera feed with a **Start Detection** button. Press it (or the `D` key) to toggle YOLOv4 bounding boxes.

Expect higher latency than the Surface-direct setup — the frames travel Pi → server (internet) → back to Surface (internet). At 640×480/15fps over a decent connection, round-trip is usually 200–500 ms.

---

## Stopping everything

In reverse order:
1. Ctrl+C ffmpeg on the Pi (Command 5)
2. Close the Surface SSH tunnel window (Command 6)
3. Ctrl+C the Pi→server tunnel (Command 4)
4. Close the Surface→Pi SSH sessions (Command 3)
5. Ctrl+C the YOLOv4 server on the server (Command 2)
6. Ctrl+C mediamtx on the server (Command 1)

---

## First-time prerequisites

### On the server

- `uv sync` run once in the project
- YOLOv4 weights present in `./weights/yolov4.weights`
- mediamtx downloaded to `~/mediamtx/` (see `SSH_SETUP.md` Command 1 for the download commands)
- SSH access open from the Pi and Surface (typically via public key; password auth works but you'll be prompted for each tunnel)

### On the Pi

```bash
sudo apt update
sudo apt install -y ffmpeg v4l-utils openssh-client
```

Then confirm the camera works (optional sanity check):

```bash
v4l2-ctl --list-devices
ffmpeg -f v4l2 -i /dev/video0 -frames:v 1 /tmp/test.jpg && echo OK
```

Copy SSH key to the server so Command 4 doesn't prompt for a password each time:

```bash
ssh-keygen -t ed25519   # if you don't already have a key
ssh-copy-id <server-user>@<server-address>
```

### On the Surface

- OpenSSH client enabled in Windows (Settings → Apps → Optional features → "OpenSSH Client")
- Optional: copy an SSH key to both the Pi and the server so logins are password-less:
  ```powershell
  ssh-keygen -t ed25519
  type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh <pi-user>@<pi-address> "cat >> ~/.ssh/authorized_keys"
  type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh <server-user>@<server-address> "cat >> ~/.ssh/authorized_keys"
  ```

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---------|--------------------|
| `ssh: connect to host ... Connection refused` (to Pi) | Pi not powered / not on network / SSH not enabled. Enable via `sudo raspi-config` → Interface Options → SSH, or place an empty `ssh` file on the boot partition |
| `Unknown encoder 'h264_v4l2m2m'` | Use the `libx264` fallback command in Command 5 |
| ffmpeg reports `Device busy` on `/dev/video0` | Another process is holding the camera. `sudo fuser -k /dev/video0` to free it |
| ffmpeg pushes but YOLOv4 server still retries | The Pi→server tunnel (Command 4) dropped. Reopen it. Confirm with `ss -tln \| grep 8554` on the Pi — should show `127.0.0.1:8554 LISTEN` |
| High fps on Pi but viewer is choppy | Upstream bandwidth limit. Lower to `-framerate 10 -video_size 480x360 -b:v 500k` |
| Viewer shows "CAMERA" but no image | mediamtx isn't receiving frames. Check the mediamtx terminal for "publisher connected on path camera" |
