from fastapi import FastAPI
from prometheus_client import make_asgi_app
from app.routes import router

app = FastAPI(title="Day27 FAQ Bot")

# API routes
app.include_router(router)

# Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

@app.get("/healthz")
def healthz():
    return {"status": "ok"}
