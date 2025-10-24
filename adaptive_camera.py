#!/usr/bin/env python3
import cv2
import asyncio
from aiohttp import web
from aiortc import RTCPeerConnection, VideoStreamTrack, RTCSessionDescription
from av import VideoFrame

# --- Webcam Video Track ---
class CameraVideoTrack(VideoStreamTrack):
    def __init__(self):
        super().__init__()
        self.cap = None
        for device in [0, 1, 2, 3]:
            cap = cv2.VideoCapture(device)
            if cap.isOpened():
                self.cap = cap
                print(f"[INFO] ✅ Camera opened at /dev/video{device}")
                break
        if self.cap is None:
            raise RuntimeError("❌ No available camera detected")

        # Force supported capture format
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.cap.set(cv2.CAP_PROP_FPS, 30)

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        ret, frame = self.cap.read()
        if not ret:
            await asyncio.sleep(0.1)
            return await self.recv()

        # Convert to YUV for WebRTC (better compatibility)
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2YUV_I420)
        vframe = VideoFrame.from_ndarray(frame, format="yuv420p")
        vframe.pts = pts
        vframe.time_base = time_base
        return vframe


# --- Web Server ---
pcs = set()

async def index(request):
    content = open("index.html", "r").read()
    return web.Response(content_type="text/html", text=content)

async def offer(request):
    try:
        params = await request.json()
        offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

        pc = RTCPeerConnection()
        pcs.add(pc)

        # Attach camera
        video = CameraVideoTrack()
        pc.addTrack(video)

        @pc.on("connectionstatechange")
        async def on_state_change():
            print(f"[INFO] Connection state: {pc.connectionState}")
            if pc.connectionState in ["failed", "closed"]:
                await pc.close()
                pcs.discard(pc)

        await pc.setRemoteDescription(offer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        print("[INFO] ✅ Offer processed successfully")
        return web.json_response(
            {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        )

    except Exception as e:
        print("[ERROR] Offer handling failed:", e)
        return web.json_response({"error": str(e)}, status=500)


async def on_shutdown(app):
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()


# --- App Setup ---
app = web.Application()
app.on_shutdown.append(on_shutdown)
app.router.add_get("/", index)
app.router.add_post("/offer", offer)

# --- Run Server ---
if __name__ == "__main__":
    print("[INFO] Starting WebRTC server on port 8080...")
    web.run_app(app, port=8080)
