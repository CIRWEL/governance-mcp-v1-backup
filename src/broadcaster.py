from starlette.websockets import WebSocket
import logging
import asyncio
import time
from collections import deque

logger = logging.getLogger(__name__)

# Activity history entry: (timestamp_epoch, verdict_action)
ACTIVITY_HISTORY_MAX = 720  # ~1 hour at 5s intervals, generous buffer

class EISVBroadcaster:
    def __init__(self):
        self.connections: list[WebSocket] = []
        self.last_update: dict = None
        self._lock = asyncio.Lock()
        self.activity_history: deque = deque(maxlen=ACTIVITY_HISTORY_MAX)

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

    def get_activity_buckets(self, window_minutes=60, bucket_minutes=5):
        """Return check-in counts grouped by 5-min bucket + verdict for sparkline."""
        now = time.time()
        cutoff = now - (window_minutes * 60)
        bucket_size = bucket_minutes * 60

        # Initialize buckets covering the window
        num_buckets = window_minutes // bucket_minutes
        # Align to bucket boundaries
        current_bucket_start = int(now // bucket_size) * bucket_size
        bucket_starts = [current_bucket_start - (i * bucket_size) for i in range(num_buckets - 1, -1, -1)]

        buckets = []
        for bs in bucket_starts:
            buckets.append({
                "ts": bs,
                "proceed": 0,
                "guide": 0,
                "pause": 0,
            })

        # Fill from history
        for ts, action in self.activity_history:
            if ts < cutoff:
                continue
            bucket_idx = int((ts - bucket_starts[0]) // bucket_size)
            if 0 <= bucket_idx < len(buckets):
                if action in ("guide",):
                    buckets[bucket_idx]["guide"] += 1
                elif action in ("pause", "reject"):
                    buckets[bucket_idx]["pause"] += 1
                else:
                    buckets[bucket_idx]["proceed"] += 1

        return buckets

    async def broadcast(self, data: dict):
        self.last_update = data

        # Track activity for sparkline
        decision = data.get("decision", {})
        action = decision.get("action", "proceed") if isinstance(decision, dict) else "proceed"
        self.activity_history.append((time.time(), action))

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
