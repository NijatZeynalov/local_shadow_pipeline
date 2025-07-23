from fastapi import FastAPI
import time
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI()
Instrumentator().instrument(app).expose(app)


@app.post("/predict")
def predict(data: dict):
    start_time = time.time()
    text = data.get("text", "").lower()

    # Simple rule-based "model"
    if "billing" in text or "invoice" in text:
        category = "Billing"
    else:
        category = "Technical Issue"

    latency = (time.time() - start_time) * 1000  # in ms
    return {"category": category, "confidence": 0.95, "latency_ms": latency, "model_version": "v1"}