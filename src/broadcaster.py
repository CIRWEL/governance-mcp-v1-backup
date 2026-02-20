from starlette.websockets import WebSocket
import logging
import asyncio

logger = logging.getLogger(__name__)

class EISVBroadcaster:
    def __init__(self):
        self.connections: list[WebSocket] = []
        self.last_update: dict = None
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.connections.append(websocket)
        logger.info(f"[WS] Dashboard client connected ({len(self.connections)} active)")

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            if websocket in self.connections:
                self.connections.remove(websocket)
        logger.info(f"[WS] Dashboard client disconnected")

    async def broadcast(self, data: dict):
        self.last_update = data
        
        async with self._lock:
            if not self.connections:
                return
            conns = list(self.connections)
            
        dead = []
        for ws in conns:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
                
        if dead:
            async with self._lock:
                for ws in dead:
                    if ws in self.connections:
                        self.connections.remove(ws)
            logger.info(f"[WS] Removed {len(dead)} dead connections")

broadcaster_instance = EISVBroadcaster()
