# Live Detection via SSH (Surface laptop → GPU server)

Quick reference for running live YOLOv4 detection when the camera is on the Surface laptop and the GPU is on a remote Linux server. Everything passes through SSH — no public ports, no exposed services.

## Architecture

```
[Surface camera] → [ffmpeg] → [mediamtx RTSP on server] → [YOLOv4 server] → [browser on Surface]
```

## What runs where

| Machine | Terminal | Command |
|---------|----------|---------|
| Server  | SSH #2 | Command 1 |
| Server  | SSH #3 | Command 2 |
| Surface | PowerShell #1 | Command 3 |
| Surface | PowerShell #2 | Command 4 |
| Surface | Browser | Command 5 |

---

## Command 1 — Start mediamtx (RTSP relay) on the server

First-time setup (download mediamtx):

```bash
cd ~
mkdir -p mediamtx && cd mediamtx
curl -L -o mediamtx.tar.gz https://github.com/bluenviron/mediamtx/releases/download/v1.8.4/mediamtx_v1.8.4_linux_amd64.tar.gz
tar xzf mediamtx.tar.gz
```

Every time:

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

Leave it running. It will retry until Command 4 starts pushing frames, then pick them up automatically. Listens on `:8085`.

---

## Command 3 — SSH port forwarding from Surface to server

In PowerShell on the Surface:

```powershell
ssh -L 8554:localhost:8554 -L 8085:localhost:8085 <your-ssh-user>@<server-address>
```

The `-L` flag syntax is `-L <LAPTOP_PORT>:localhost:<SERVER_PORT>`. The `localhost` here is interpreted **on the server side** — it means "once this traffic reaches the server, deliver it to the server's own localhost." Breakdown of the two forwards:

| Forward | Laptop port (what you connect to locally) | Server port (where it lands) | Direction of traffic | Purpose |
|---------|-------------------------------------------|------------------------------|----------------------|---------|
| `-L 8554:localhost:8554` | `localhost:8554` on Surface | `localhost:8554` on server (mediamtx) | Surface → server | ffmpeg push reaches mediamtx |
| `-L 8085:localhost:8085` | `localhost:8085` on Surface | `localhost:8085` on server (YOLOv4 viewer) | Surface → server | Browser loads the viewer page |

The port numbers happen to match on both ends here, but they don't have to — if port 8554 is taken on your Surface, use e.g. `-L 9554:localhost:8554` and then point ffmpeg at `rtsp://localhost:9554/camera` in Command 4.

Leave the session open. No command needed inside it.

---

## Command 4 — Push the Surface camera to the server

First, find your camera name (one-time):

```powershell
ffmpeg -list_devices true -f dshow -i dummy
```

Copy the exact camera name from the output. Then, every time:

```powershell
ffmpeg -f dshow -framerate 15 -video_size 640x480 -i video="YOUR CAMERA NAME" -c:v libx264 -preset ultrafast -tune zerolatency -f rtsp -rtsp_transport tcp rtsp://localhost:8554/camera
```

Replace `YOUR CAMERA NAME` with what `-list_devices` showed (keep the quotes). Leave it running. Stop with `Ctrl+C` when done.

---

## Command 5 — Open the viewer

In the Surface browser:

```
http://localhost:8085
```

You should see your Surface camera feed with a **Start Detection** button. Press it (or the `D` key) to toggle YOLOv4 bounding boxes.

---

## Stopping everything

In reverse order: Ctrl+C the ffmpeg push (Command 4), close the SSH forward window (Command 3), Ctrl+C the YOLOv4 server (Command 2), Ctrl+C mediamtx (Command 1).

## First-time prerequisites

- **Server:** `uv sync` has been run in the project (one time); yolov4 weights exist in `./weights/`
- **Surface:** ffmpeg installed (`winget install ffmpeg`), then reopen PowerShell
