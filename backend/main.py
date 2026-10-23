"""FastAPI entry point for Java Blueprints."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import ALLOWED_ORIGINS
from api import analyze, decompose, generate, graph, parse, run, ws, ai

app = FastAPI(title="Java Blueprints API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(ALLOWED_ORIGINS),
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (parse, graph, analyze, generate, run, decompose, ws, ai):
    app.include_router(module.router, prefix="/api")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
