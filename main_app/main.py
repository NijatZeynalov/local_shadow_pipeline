from fastapi import FastAPI, Request
from prometheus_fastapi_instrumentator import Instrumentator
import requests
import json
import uuid
import time
from kafka import KafkaProducer, errors as kafka_errors
from contextlib import asynccontextmanager

try:
KAFKA_TOPIC = "shadow-requests"
KAFKA_BOOTSTRAP_SERVERS = 'kafka:29092'
MODEL_V1_URL = "http://model_v1:8001/predict"
RETRY_DELAY = 10

app_state = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("--> [LIFESPAN] Startup event initiated...")
    producer = None
    while not producer:
        try:
            print("--> [LIFESPAN] Attempting to connect to Kafka...")
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
            print("✅ [LIFESPAN] Successfully connected to Kafka!")
        except kafka_errors.NoBrokersAvailable:
            print(f"❌ [LIFESPAN] Kafka not ready. Retrying in {RETRY_DELAY}s...")
            time.sleep(RETRY_DELAY)

    app_state["kafka_producer"] = producer
    print("--> [LIFESPAN] Kafka producer stored in app_state.")

    yield

    print("--> [LIFESPAN] Shutdown event initiated...")
    producer = app_state.get("kafka_producer")
    if producer:
        producer.close()
        print("✅ [LIFESPAN] Kafka producer connection closed.")


app = FastAPI(lifespan=lifespan)
Instrumentator().instrument(app).expose(app)


@app.post("/ticket")
async def create_ticket(request: Request):
    print("\n--- [TICKET] Request received ---")
    try:
        request_body = await request.json()
        print("[TICKET] JSON body parsed successfully.")
    except json.JSONDecodeError:
        print("❗️ [TICKET] ERROR: Invalid JSON in request body.")
        return {"error": "Invalid JSON in request body"}, 400

    request_id = str(uuid.uuid4())
    print(f"[TICKET] Assigned request_id: {request_id}")

    try:
        print(f"[TICKET] Calling production model v1 at {MODEL_V1_URL}...")
        response_v1 = requests.post(MODEL_V1_URL, json=request_body, timeout=5).json()
        print("[TICKET] Got response from v1.")
    except requests.RequestException as e:
        print(f"❗️ [TICKET] ERROR: Could not connect to model_v1: {e}")
        return {"error": "Production model service is unavailable"}, 503

    shadow_payload = {
        "request_id": request_id,
        "request_body": request_body,
        "model_v1_prediction": response_v1,
        "timestamp": time.time()
    }

    # --- THIS IS THE CRITICAL DEBUGGING SECTION ---
    print("[TICKET] Attempting to send shadow message...")
    producer = app_state.get("kafka_producer")
    if producer:
        print("[TICKET] Kafka producer found in app_state. Preparing to send...")
        try:
            producer.send(KAFKA_TOPIC,
                          value=shadow_payload)  # FIX THE TYPO            print(f"✅ [TICKET] Message for {request_id} sent to Kafka topic '{KAFKA_TOPIC}'.")
        except Exception as e:
            print(f"❗️ [TICKET] ERROR: Exception while sending to Kafka: {e}")
    else:
        # This will tell us if the producer was never created successfully
        print("❗️ [TICKET] CRITICAL ERROR: Kafka producer not found in app_state. Message was NOT sent.")

    return {
        "message": "Ticket processed by production model.",
        "request_id": request_id,
        "production_prediction": response_v1
    }