#!/bin/bash
#
# Camera client: captures video from USB camera and streams via RTSP to the server.
# Requires: ffmpeg (sudo apt install ffmpeg)
# On Raspberry Pi: also requires rpicam-vid (comes with Raspberry Pi OS)
#
# Usage:
#   ./camera_client.sh <SERVER_IP> [DEVICE] [RESOLUTION] [FPS]
#
# Examples:
#   ./camera_client.sh 192.168.1.100                    # defaults: /dev/video0, 1280x720, 15fps
#   ./camera_client.sh 192.168.1.100 /dev/video1        # specify camera device
#   ./camera_client.sh 192.168.1.100 /dev/video0 640x480 30  # custom resolution and fps

set -uo pipefail

SERVER_IP="${1:?Usage: $0 <SERVER_IP> [DEVICE] [RESOLUTION] [FPS]}"
DEVICE="${2:-/dev/video0}"
RESOLUTION="${3:-1280x720}"
FPS="${4:-15}"
RTSP_PORT="${RTSP_PORT:-8554}"
STREAM_PATH="${STREAM_PATH:-camera}"

RTSP_URL="rtsp://${SERVER_IP}:${RTSP_PORT}/${STREAM_PATH}"

# Check if ffmpeg is available
if ! command -v ffmpeg &>/dev/null; then
    echo "Error: ffmpeg is not installed. Install with: sudo apt install ffmpeg"
    exit 1
fi

# Check if the camera device exists
if [ ! -e "$DEVICE" ]; then
    echo "Error: Camera device $DEVICE not found"
    echo "Available video devices:"
    ls /dev/video* 2>/dev/null || echo "  (none found)"
    exit 1
fi

# Detect if running on Raspberry Pi
is_rpi() {
    [ -f /proc/device-tree/model ] && grep -qi "raspberry" /proc/device-tree/model 2>/dev/null
}

echo "Streaming to: $RTSP_URL"
echo "Device: $DEVICE | Resolution: $RESOLUTION | FPS: $FPS"
echo "Press Ctrl+C to stop"
echo ""

RETRY_DELAY=1

while true; do
    if is_rpi && command -v rpicam-vid &>/dev/null; then
        # Raspberry Pi with rpicam-vid: hardware-accelerated H.264 encoding
        WIDTH="${RESOLUTION%x*}"
        HEIGHT="${RESOLUTION#*x}"
        echo "Using rpicam-vid (Raspberry Pi hardware encoder)"
        rpicam-vid -t 0 --width "$WIDTH" --height "$HEIGHT" --framerate "$FPS" \
            --codec h264 --profile baseline --level 4 --inline -o - | \
        ffmpeg -f h264 -i - \
            -c:v copy \
            -f rtsp -rtsp_transport tcp "$RTSP_URL"
    else
        # Generic Linux with USB camera: software H.264 encoding via ffmpeg
        echo "Using ffmpeg (software encoder)"
        ffmpeg -f v4l2 -input_format mjpeg -video_size "$RESOLUTION" -framerate "$FPS" \
            -i "$DEVICE" \
            -c:v libx264 -preset ultrafast -tune zerolatency -g "$((FPS * 2))" \
            -f rtsp -rtsp_transport tcp "$RTSP_URL"
    fi

    echo "[camera_client] Stream ended. Retrying in ${RETRY_DELAY}s..."
    sleep "$RETRY_DELAY"
    RETRY_DELAY=$((RETRY_DELAY * 2))
    if [ "$RETRY_DELAY" -gt 30 ]; then
        RETRY_DELAY=30
    fi
done
