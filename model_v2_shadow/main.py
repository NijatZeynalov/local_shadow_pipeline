from fastapi import FastAPI
import time
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI()
Instrumentator().instrument(app).expose(app)


@app.post("/predict")
def predict(data: dict):
    start_time = time.time()
    text = data.get("text", "").lower()

    # More "advanced" rule-based model
    if "billing" in text and "upgrade" in text:
        category = "Billing::Subscription-Upgrade"
    elif "billing" in text or "invoice" in text:
        category = "Billing::General"
    elif "slow" in text or "error" in text:
        category = "Technical Issue::Performance"
    else:
        category = "Technical Issue::General"

    time.sleep(0.05)  # Simulate a heavier model
    latency = (time.time() - start_time) * 1000  # in ms
    return {"category": category, "confidence": 0.91, "latency_ms": latency, "model_version": "v2"}