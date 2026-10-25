"""FastAPI entry point for Java Blueprints."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import state
from config import ALLOWED_ORIGINS
from api import analyze, decompose, files, generate, graph, parse, run, ws, ai

app = FastAPI(title="Java Blueprints API", version="1.0.0")



@app.middleware("http")
async def session_middleware(request: Request, call_next):
    """Pick the per-tab session from X-Session-Id (none → shared default; non-UUID → 400)."""
    try:
        sid = state.parse_sid(request.headers.get("x-session-id"))
    except ValueError:
        return JSONResponse(status_code=400, content={"detail": "Некорректный заголовок X-Session-Id: нужен UUID"})
    token = state.use(sid)
    try:
        return await call_next(request)
    finally:
        state.reset(token)


# added after the session middleware, so CORS is outermost and also decorates the 400
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(ALLOWED_ORIGINS),
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (parse, graph, analyze, generate, run, decompose, files, ws, ai):
    app.include_router(module.router, prefix="/api")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
