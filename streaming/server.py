"""
Live YOLOv4 streaming server.

Receives video via RTSP (or local camera/file), runs YOLOv4 inference on GPU,
and serves annotated frames as MJPEG stream viewable in a browser.

Usage:
    uvicorn streaming.server:app --host 0.0.0.0 --port 8085

    Or directly:
    python -m streaming.server --source rtsp://localhost:8554/camera
    python -m streaming.server --source /dev/video0
    python -m streaming.server --source ./examples/video.mp4
"""

import argparse
import asyncio
import collections
import math
import threading
import time
import sys
import os
from contextlib import asynccontextmanager

import cv2
import torch
import numpy as np

# Add project root to path so we can import utilities
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utilities.constants import OBJ_THRESH_DEF, SEPARATOR
from utilities.configs import parse_config, parse_names
from utilities.weights import load_weights
from utilities.devices import gpu_device_name, get_device, use_cuda
from utilities.inferencing import inference_on_image
from utilities.images import draw_detections
from utilities.detections import detections_best_class

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Shared state classes
# ---------------------------------------------------------------------------

class FrameGrabber:
    """Continuously reads from a video source in a dedicated thread,
    always keeping only the latest frame."""

    def __init__(self, source):
        self.source = source
        self.cap = None
        self.frame = None
        self.ret = False
        self.lock = threading.Lock()
        self.running = False
        self._reconnect_delay = 1.0
        self.seq = 0

    def start(self):
        self.running = True
        self._open()
        threading.Thread(target=self._grab_loop, daemon=True).start()

    def stop(self):
        self.running = False
        if self.cap is not None:
            self.cap.release()

    def _open(self):
        # Support bare integers as camera indices (e.g., --source 0)
        source = self.source
        try:
            source = int(source)
        except (ValueError, TypeError):
            pass
        self.cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def _grab_loop(self):
        while self.running:
            if self.cap is None or not self.cap.isOpened():
                self._reconnect()
                continue
            ret, frame = self.cap.read()
            if ret:
                with self.lock:
                    self.ret, self.frame = True, frame
                    self.seq += 1
                self._reconnect_delay = 1.0  # reset backoff on success
            else:
                self._reconnect()

    def _reconnect(self):
        print(f"[FrameGrabber] Connection lost. Retrying in {self._reconnect_delay:.0f}s...")
        if self.cap is not None:
            self.cap.release()
        time.sleep(self._reconnect_delay)
        self._reconnect_delay = min(self._reconnect_delay * 2, 30.0)
        self._open()

    def get_frame(self):
        with self.lock:
            return self.ret, self.frame, self.seq


class ResultHolder:
    """Holds the latest annotated frame and stats."""

    def __init__(self):
        self.frame = None
        self.lock = threading.Lock()
        self.timestamp = 0
        self.fps = 0.0
        self.latency_ms = 0.0
        self.detection_count = 0
        self.class_counts = {}

    def set_frame(self, frame, fps, latency_ms, detection_count, class_counts):
        with self.lock:
            self.frame = frame
            self.timestamp = time.time()
            self.fps = fps
            self.latency_ms = latency_ms
            self.detection_count = detection_count
            self.class_counts = class_counts

    def get_frame(self):
        with self.lock:
            return self.frame, self.timestamp

    def get_stats(self):
        with self.lock:
            return {
                "fps": round(self.fps, 1),
                "latency_ms": round(self.latency_ms, 1),
                "detection_count": self.detection_count,
                "class_counts": self.class_counts,
                "last_frame_time": self.timestamp,
                "connected": (time.time() - self.timestamp) < 5.0 if self.timestamp > 0 else False,
            }


# ---------------------------------------------------------------------------
# Inference thread
# ---------------------------------------------------------------------------

def inference_loop(model, frame_grabber, result_holder, class_names, network_dim, config):
    """Runs in a dedicated thread. Pulls latest frame, runs inference, publishes result."""

    # FPS tracking (rolling average over last N frames)
    frame_times = collections.deque(maxlen=30)
    last_seq = -1

    model.eval()
    with torch.no_grad():
        while frame_grabber.running:
            ret, frame, seq = frame_grabber.get_frame()
            if not ret or frame is None:
                time.sleep(0.01)
                continue

            # Skip if we already processed this frame
            if seq == last_seq:
                time.sleep(0.001)
                continue
            last_seq = seq

            # When detection is disabled, pass raw camera frames through
            if not config.get("detection_enabled", False):
                result_holder.set_frame(frame, 0, 0, 0, {})
                time.sleep(0.03)
                continue

            try:
                start = time.time()

                # Run existing inference pipeline (unchanged from detect.py)
                detections = inference_on_image(
                    model, frame, network_dim, config["obj_thresh"],
                    letterbox=config["letterbox"]
                )

                # Draw bounding boxes (unchanged from detect.py)
                annotated = draw_detections(detections, frame, class_names, verbose_output=False)

                elapsed = time.time() - start

                # Track FPS as rolling average
                frame_times.append(elapsed)
                avg_time = sum(frame_times) / len(frame_times)
                fps = 1.0 / avg_time if avg_time > 0 else 0.0

                # Count detections by class
                detection_count = len(detections)
                class_counts = {}
                if detection_count > 0:
                    _, classes = detections_best_class(detections)
                    for cls_idx in classes.cpu().numpy():
                        name = class_names[int(cls_idx)]
                        class_counts[name] = class_counts.get(name, 0) + 1

                result_holder.set_frame(annotated, fps, elapsed * 1000, detection_count, class_counts)

            except torch.cuda.OutOfMemoryError:
                print("[InferenceLoop] CUDA OOM — clearing cache")
                torch.cuda.empty_cache()
                time.sleep(0.1)
            except Exception as e:
                print(f"[InferenceLoop] Error: {e}")
                time.sleep(0.01)


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

# These are populated by init_model_and_start (called from lifespan or __main__)
frame_grabber: FrameGrabber = None
result_holder: ResultHolder = None
inference_config: dict = None
server_info: dict = {}


@asynccontextmanager
async def lifespan(app):
    """Initialize model on startup when running via uvicorn streaming.server:app."""
    global frame_grabber, result_holder, inference_config
    if frame_grabber is None:
        # Not started via __main__, so parse args from sys.argv / env vars / defaults
        args = _build_args()
        init_model_and_start(args)
    yield
    # Shutdown: stop frame grabber
    if frame_grabber is not None:
        frame_grabber.stop()


app = FastAPI(title="YOLOv4 Live Detection", lifespan=lifespan)


class ConfigUpdate(BaseModel):
    obj_thresh: float = None
    detection_enabled: bool = None


def parse_args():
    parser = argparse.ArgumentParser(description="YOLOv4 Live Streaming Server")
    parser.add_argument("--source", type=str, default="rtsp://localhost:8554/camera",
                        help="Video source: RTSP URL, device path (/dev/video0), or video file")
    parser.add_argument("-cfg", type=str, default="./configs/yolov4.cfg",
                        help="Yolo configuration file")
    parser.add_argument("-weights", type=str, default="./weights/yolov4.weights",
                        help="Yolo weights file")
    parser.add_argument("-class_names", type=str, default="./configs/coco.names",
                        help="Names for each class index")
    parser.add_argument("-obj_thresh", type=float, default=OBJ_THRESH_DEF,
                        help="Confidence threshold for filtering out predictions")
    parser.add_argument("--letterbox", action="store_true",
                        help="Turns on image input letterboxing")
    parser.add_argument("--force_cpu", action="store_true",
                        help="Forces the model to run on the cpu")
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8085)
    return parser.parse_args()


def _build_args():
    """Build args from env vars and defaults for uvicorn-managed startup.

    Checks YOLO_SOURCE, YOLO_CFG, YOLO_WEIGHTS, YOLO_CLASS_NAMES, YOLO_OBJ_THRESH,
    YOLO_LETTERBOX, YOLO_FORCE_CPU. Falls back to the same defaults as parse_args.
    Also attempts sys.argv parsing so `uvicorn streaming.server:app -- --source X` works.
    """
    try:
        return parse_args()
    except SystemExit:
        pass

    # Fallback: build from environment variables
    class Args:
        pass

    args = Args()
    args.source = os.environ.get("YOLO_SOURCE", "rtsp://localhost:8554/camera")
    args.cfg = os.environ.get("YOLO_CFG", "./configs/yolov4.cfg")
    args.weights = os.environ.get("YOLO_WEIGHTS", "./weights/yolov4.weights")
    args.class_names = os.environ.get("YOLO_CLASS_NAMES", "./configs/coco.names")
    args.obj_thresh = float(os.environ.get("YOLO_OBJ_THRESH", str(OBJ_THRESH_DEF)))
    args.letterbox = os.environ.get("YOLO_LETTERBOX", "").lower() in ("1", "true", "yes")
    args.force_cpu = os.environ.get("YOLO_FORCE_CPU", "").lower() in ("1", "true", "yes")
    args.host = os.environ.get("YOLO_HOST", "0.0.0.0")
    args.port = int(os.environ.get("YOLO_PORT", "8085"))
    return args


def init_model_and_start(args):
    """Initialize model, frame grabber, and inference thread. Mirrors detect.py's setup."""
    global frame_grabber, result_holder, inference_config, server_info

    if args.force_cpu:
        print("----- WARNING: Model is using the CPU (--force_cpu) -----")
        use_cuda(False)

    print("Parsing config into model...")
    model = parse_config(args.cfg)
    if model is None:
        raise RuntimeError("Failed to parse config")

    model = model.to(get_device())
    model.eval()

    if model.net_block.width != model.net_block.height:
        raise RuntimeError("Width and height must match in [net]")
    network_dim = model.net_block.width

    print("Parsing class names...")
    class_names = parse_names(args.class_names)
    if class_names is None:
        raise RuntimeError("Failed to parse class names")

    print("Loading weights...")
    load_weights(model, args.weights)

    print("")
    print(SEPARATOR)
    print("YOLOv4 STREAMING SERVER")
    print("GPU:", gpu_device_name())
    print("Config:", args.cfg)
    print("Weights:", args.weights)
    print("Network Dim:", network_dim)
    print("Letterbox:", args.letterbox)
    print("Source:", args.source)
    print(SEPARATOR)
    print("")

    # Shared config (mutable at runtime)
    inference_config = {
        "obj_thresh": args.obj_thresh,
        "letterbox": args.letterbox,
        "detection_enabled": False,
    }

    server_info.update({
        "model": os.path.basename(args.cfg).replace(".cfg", ""),
        "network_dim": network_dim,
        "source": args.source,
    })

    # Start frame grabber
    frame_grabber = FrameGrabber(args.source)
    frame_grabber.start()

    # Start result holder
    result_holder = ResultHolder()

    # Start inference thread
    threading.Thread(
        target=inference_loop,
        args=(model, frame_grabber, result_holder, class_names, network_dim, inference_config),
        daemon=True
    ).start()

    print(f"Server ready. Open http://{args.host}:{args.port}/ in a browser.")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def viewer():
    """Serve the viewer HTML page."""
    viewer_path = os.path.join(os.path.dirname(__file__), "viewer.html")
    with open(viewer_path, "r") as f:
        return HTMLResponse(content=f.read())


@app.get("/stream")
async def stream():
    """MJPEG video stream of annotated frames."""
    async def generate():
        last_ts = 0
        while True:
            frame, ts = result_holder.get_frame()
            if frame is None or ts == last_ts:
                await asyncio.sleep(0.03)
                continue
            last_ts = ts
            _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n")

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/stats")
async def stats():
    """JSON stats: fps, latency, detection count, connection status."""
    s = result_holder.get_stats()
    s.update(server_info)
    s["obj_thresh"] = inference_config["obj_thresh"]
    s["detection_enabled"] = inference_config.get("detection_enabled", False)
    return JSONResponse(content=s)


@app.post("/config")
async def update_config(update: ConfigUpdate):
    """Update runtime configuration (e.g. confidence threshold)."""
    if update.detection_enabled is not None:
        inference_config["detection_enabled"] = bool(update.detection_enabled)
    if update.obj_thresh is not None:
        if not math.isfinite(update.obj_thresh):
            return JSONResponse(
                status_code=400,
                content={"error": "obj_thresh must be a finite number"}
            )
        clamped = max(0.05, min(0.95, update.obj_thresh))
        inference_config["obj_thresh"] = clamped
    return inference_config


# ---------------------------------------------------------------------------
# Main entry point (python -m streaming.server)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    args = parse_args()
    init_model_and_start(args)
    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    finally:
        if frame_grabber is not None:
            frame_grabber.stop()
