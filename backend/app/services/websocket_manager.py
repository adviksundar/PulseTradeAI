from fastapi import WebSocket

from app.services.cache import to_ws_payload


class WebSocketManager:
    def __init__(self) -> None:
        self.active_connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.discard(websocket)

    async def broadcast(self, event: str, data: object) -> None:
        payload = to_ws_payload(event, data)
        stale: list[WebSocket] = []
        for connection in self.active_connections:
            try:
                await connection.send_text(payload)
            except Exception:
                stale.append(connection)
        for connection in stale:
            self.disconnect(connection)

