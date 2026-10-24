"""WebSocket endpoint for the interactive console.

Client → server: {type: "start", code, mainClass?} | {type: "stdin", data} | {type: "eof"} | {type: "kill"}
Server → client: {type: "stdout"|"stderr", data} | {type: "compile_error", text, errors}
    | {type: "coverage", probes, hits} | {type: "coverage", error}   (after all output, before exit; never after compile_error)
    | {type: "exit", code, durationMs}
"""

import asyncio
import json
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from config import origin_allowed
from core import interactive

router = APIRouter()


@router.websocket("/ws/run")
async def ws_run(ws: WebSocket) -> None:
    if not origin_allowed(ws.headers.get("origin"), ws.headers.get("host")):
        await ws.close(code=1008)  # policy violation: cross-site WebSocket
        return
    await ws.accept()
    proc = tmp = plan = pump_task = None
    started = 0.0

    async def emit(msg: dict) -> None:
        try:
            await ws.send_text(json.dumps(msg))
        except Exception:  # noqa: BLE001 – client went away
            pass

    async def run_and_report() -> None:
        code = await interactive.pump(proc, emit)
        cov_msg = await asyncio.to_thread(interactive.final_coverage, code, plan, tmp)
        if cov_msg:
            await emit(cov_msg)
        await emit({"type": "exit", "code": code, "durationMs": int((time.monotonic() - started) * 1000)})

    try:
        while True:
            msg = json.loads(await ws.receive_text())
            kind = msg.get("type")
            if kind == "start" and proc is None:
                started = time.monotonic()
                res = await interactive.start_session(msg.get("code", ""), msg.get("mainClass"), emit)
                if res:
                    proc, tmp, plan = res
                    pump_task = asyncio.create_task(run_and_report())
            elif kind == "stdin" and proc:
                await interactive.feed(proc, msg.get("data", ""))
            elif kind == "eof" and proc and proc.stdin:
                proc.stdin.close()
            elif kind == "kill" and proc and proc.returncode is None:
                proc.kill()
    except WebSocketDisconnect:
        pass
    finally:
        if proc and proc.returncode is None:
            proc.kill()
        if pump_task:
            await asyncio.gather(pump_task, return_exceptions=True)
        interactive.cleanup(tmp)
