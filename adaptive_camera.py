#!/usr/bin/env python3
import cv2
import asyncio
from aiohttp import web
from aiortc import RTCPeerConnection, VideoStreamTrack, RTCSessionDescription
from aiortc.contrib.media import MediaBlackhole, MediaRecorder

# --- Webcam Track using OpenCV ---
class CameraVideoTrack(VideoStreamTrack):
    def __init__(self):
        super().__init__()
        self.cap = cv2.VideoCapture(0)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.cap.set(cv2.CAP_PROP_FPS, 30)

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        ret, frame = self.cap.read()
        if not ret:
            raise Exception("Camera read failed")
        # Convert BGR to RGB
        from av import VideoFrame
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        vframe = VideoFrame.from_ndarray(frame, format="rgb24")
        vframe.pts = pts
        vframe.time_base = time_base
        return vframe

# --- Web Server ---
pcs = set()

async def index(request):
    content = open("index.html", "r").read()
    return web.Response(content_type="text/html", text=content)

async def offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)

    pc.addTrack(CameraVideoTrack())

    @pc.on("connectionstatechange")
    async def on_state_change():
        print("Connection state:", pc.connectionState)
        if pc.connectionState == "failed" or pc.connectionState == "closed":
            await pc.close()
            pcs.discard(pc)

    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.json_response(
        {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
    )

async def on_shutdown(app):
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()

app = web.Application()
app.on_shutdown.append(on_shutdown)
app.router.add_get("/", index)
app.router.add_post("/offer", offer)
