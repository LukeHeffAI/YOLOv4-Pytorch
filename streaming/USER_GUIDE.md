# Live Object Detection - User Guide

This guide walks you through setting up and using the live camera detection system. By the end, you will have a browser window showing your camera feed with real-time object detection (bounding boxes labeling people, cars, animals, etc.).

No prior coding experience is needed. Just follow each step in order.

---

## What you need

- A computer with a webcam (laptop with a built-in camera works great)
- An internet connection (for downloading software and model files)
- About 2 GB of free disk space
- A web browser (Chrome, Firefox, Edge, or Safari)

If your computer has an NVIDIA GPU, detection will be fast (20+ frames per second). Without one, it will still work but will be slower (1-3 fps). The plain camera feed is always smooth regardless.

---

## Step 1: Install `uv` (the Python package manager)

`uv` is a tool that handles Python and all project dependencies for you. Installing it is one command.

**Linux/macOS:** Open a terminal and run:
```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows:** Open PowerShell and run:
```
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Close and reopen your terminal afterwards. To check it installed:
```
uv --version
```

---

## Step 2: Download the project

Open a terminal and run these commands one at a time:

```
cd ~/Desktop
```
```
git clone https://github.com/gwinndr/YOLOv4-Pytorch.git
```
```
cd YOLOv4-Pytorch
```

If `git` is not installed:
- **Ubuntu/Debian:** `sudo apt install git`
- **macOS:** It will prompt you to install it automatically.
- **Windows:** Download from https://git-scm.com/downloads

---

## Step 3: Install dependencies

Still in the `YOLOv4-Pytorch` folder, run:

```
uv sync
```

This one command creates an isolated `.venv` folder and installs everything the project needs (PyTorch, OpenCV, FastAPI, etc.). It takes a few minutes the first time and downloads about 1.5 GB.

You do not need to activate a virtual environment manually — `uv run` handles that for you in the next steps.

---

## Step 4: Download the detection model

The model file contains the "brain" of the object detector. It knows how to recognise 80 types of objects (people, cars, dogs, chairs, etc.).

Create the weights folder:

```
mkdir -p weights
```

**Option A - YOLOv4 (best quality, recommended if you have an NVIDIA GPU):** 245 MB.

- **Linux/macOS:**
  ```
  curl -L -o weights/yolov4.weights https://github.com/AlexeyAB/darknet/releases/download/darknet_yolo_v3_optimal/yolov4.weights
  ```
- **Windows (or if curl is unavailable):** Open this link in your browser:
  `https://github.com/AlexeyAB/darknet/releases/download/darknet_yolo_v3_optimal/yolov4.weights`
  When the download finishes, move the file into the `weights` folder inside `YOLOv4-Pytorch`.

**Option B - YOLOv3-tiny (smaller, faster, recommended for computers without an NVIDIA GPU):** 34 MB.

```
curl -L -o weights/yolov3-tiny.weights https://pjreddie.com/media/files/yolov3-tiny.weights
```

---

## Step 5: Start the server

In the `YOLOv4-Pytorch` folder, run the command that matches your setup.

**Linux (webcam at `/dev/video0`):**
```
uv run python -m streaming.server --source /dev/video0
```

**macOS or Windows:**
```
uv run python -m streaming.server --source 0
```

**If you downloaded YOLOv3-tiny (Option B in Step 4)**, add the config and weights flags:
```
uv run python -m streaming.server --source /dev/video0 -cfg ./configs/yolov3-tiny.cfg -weights ./weights/yolov3-tiny.weights
```
(Replace `/dev/video0` with `0` on macOS/Windows.)

**If you do NOT have an NVIDIA GPU**, add `--force_cpu`:
```
uv run python -m streaming.server --source /dev/video0 --force_cpu
```

You will see text scroll by as the model loads. When you see:

```
Server ready. Open http://0.0.0.0:8085/ in a browser.
```

the server is running. **Leave this terminal window open** — closing it stops the server.

### Troubleshooting

| Problem | Solution |
|---------|----------|
| White/blank page in browser, or "This site can't be reached" | The server is not running. Look at the terminal — if it exited or shows an error, that is the real problem. |
| `uv: command not found` | Close and reopen your terminal after installing uv in Step 1 |
| `No module named 'streaming'` | Make sure you are in the `YOLOv4-Pytorch` folder (`cd ~/Desktop/YOLOv4-Pytorch`) |
| `No such file: yolov4.weights` | Go back to Step 4 and download the weights file |
| `can't open camera`, `VIDEOIO ERROR`, or camera is black | Close any app using the camera (Zoom, Teams, etc.). On Linux, try `/dev/video1` or `/dev/video2` |
| `CUDA not available` / `AssertionError: Torch not compiled with CUDA enabled` | Add `--force_cpu` to the command |
| Port 8085 already in use | Add `--port 8090` (or any other free port); open the browser to that port instead |

---

## Step 6: Open the viewer

Open your web browser and go to:

```
http://localhost:8085
```

You should see your camera feed with a large green **Start Detection** button in the centre.

If you see a white/blank page here but the terminal still shows the server running, try:
- Hard-refresh the page (Ctrl+Shift+R on Linux/Windows, Cmd+Shift+R on macOS)
- Check you are going to the exact URL (including `http://`, not `https://`)
- If you are connecting from a different computer, use the server's IP address instead of `localhost`

---

## Step 7: Using the interface

### Starting detection

Click the green **Start Detection** button (or press the **D** key on your keyboard).

The system will begin analysing your camera feed. Within a second or two you will see:
- Coloured rectangles (bounding boxes) drawn around detected objects
- Labels showing what each object is (e.g. "person", "dog", "chair")
- The status indicator in the top-left changes from "CAMERA" to "LIVE" (green dot)
- Performance numbers appear (fps and latency)

### Stopping detection

To stop detection and return to the plain camera view:
1. Move your mouse to make the bottom controls bar appear
2. Click the red **Stop** button (or press the **D** key)

The bounding boxes disappear and you see your plain camera feed again with the **Start Detection** button.

### Adjusting sensitivity

The **Confidence** slider at the bottom controls how certain the detector must be before showing a detection:
- Slide **left** to see more detections (including less certain ones)
- Slide **right** to see fewer detections (only very confident ones)

If you see too many false boxes around things, slide it to the right. If real objects are being missed, slide it to the left.

### Other controls

| Control | What it does |
|---------|-------------|
| Pause button (&#9646;&#9646;) | Freezes the current frame on screen |
| Camera button | Saves a screenshot to your downloads folder |
| Fullscreen button | Makes the viewer fill your entire screen |

### Keyboard shortcuts

| Key | Action |
|-----|--------|
| **D** | Start or stop detection |
| **Space** | Pause or resume the video |
| **S** | Save a screenshot |
| **F** | Toggle fullscreen |
| **Escape** | Exit fullscreen |

---

## Stopping the server

When you are done, go to the terminal window where the server is running and press **Ctrl+C** (hold the Ctrl key and press C). This stops the server.

The next time you want to use it, repeat Steps 5 and 6 — you do not need to reinstall anything.

---

## Quick reference

After the first-time setup, here is the short version for daily use:

```
cd ~/Desktop/YOLOv4-Pytorch
uv run python -m streaming.server --source /dev/video0
```

Then open `http://localhost:8085` in your browser.
