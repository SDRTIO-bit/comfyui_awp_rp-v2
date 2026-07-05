"""awp_rp_runtime_v2 — ComfyUI RP Runtime V2."""

__version__ = "0.1.0"

from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

# Register management API routes (only when ComfyUI server is available)
try:
    from .runtime import management_api  # noqa: F401
except Exception:
    pass

# ── Auto-start standalone management server ─────────────────────────────
# Starts on port 8189 in a background daemon thread.
# Frontend: http://localhost:8189/awp/
# This avoids SSE buffering issues with ComfyUI's aiohttp server.
import os as _os
import threading as _threading


def _start_standalone_server():
    try:
        from aiohttp import web as _web
        from .scripts.awp_server import create_app
        app = create_app()
        runner = _web.AppRunner(app)
        import asyncio as _asyncio

        async def _run():
            await runner.setup()
            site = _web.TCPSite(runner, "127.0.0.1", 8189)
            await site.start()
            print("[AWP] Management panel: http://127.0.0.1:8189/awp/")

        loop = _asyncio.new_event_loop()
        _asyncio.set_event_loop(loop)
        loop.run_until_complete(_run())
        loop.run_forever()
    except Exception as e:
        print(f"[AWP] Standalone server failed to start: {e}")


_server_thread = _threading.Thread(target=_start_standalone_server, daemon=True)
_server_thread.start()

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
