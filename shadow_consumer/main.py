from kafka import KafkaConsumer, errors as kafka_errors
from elasticsearch import Elasticsearch
import json
import requests
import time

# --- Configuration ---
KAFKA_TOPIC = "shadow-requests"
KAFKA_BOOTSTRAP_SERVERS = 'kafka:29092'
MODEL_V2_URL = "http://model_v2_shadow:8002/predict"
ES_HOST = "http://elasticsearch:9200"
ES_INDEX = "model_comparison_logs"
RETRY_DELAY = 10

def main():
    """The main function to run the consumer service."""
    es = None # Initialize to None
    while not es: # Loop until Elasticsearch is connected
        try:
            print("--> [INIT] Attempting to connect to Elasticsearch...")
            es_client = Elasticsearch(hosts=[ES_HOST])
            if not es_client.ping():
                raise ConnectionError("Elasticsearch ping failed.")
            es = es_client
            print("✅ [INIT] Successfully connected to Elasticsearch!")
            if not es.indices.exists(index=ES_INDEX):
                es.indices.create(index=ES_INDEX)
                print(f"    Created Elasticsearch index: {ES_INDEX}")
        except Exception as e:
            print(f"❌ [INIT] Could not connect to Elasticsearch: {e}. Retrying in {RETRY_DELAY}s...")
            time.sleep(RETRY_DELAY)

    consumer = None # Initialize to None
    while True: # Main application loop
        try:
            if not consumer:
                consumer = KafkaConsumer(
                    KAFKA_TOPIC,
                    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                    auto_offset_reset='earliest',
                    value_deserializer=lambda x: json.loads(x.decode('utf-8')),                  # --- ADD THESE TWO LINES FOR LOW LATENCY ---
                    fetch_max_wait_ms=10,  # Wait a maximum of 10ms before fetching
                    fetch_min_bytes=0  # Fetch even if the batch has 0 bytes
                )
                print("✅ [INIT] Successfully connected to Kafka! Waiting for messages...")

            # THIS IS THE CORE LOOP, NOW WITH HYPER-LOGGING
            for message in consumer:
                payload = message.value
                req_id = payload.get("request_id", "UNKNOWN_ID")
                print(f"\n[STEP 1/5] -> Received message for request_id: {req_id}")

                try:
                    # STEP 2: Call the shadow model
                    print(f"[STEP 2/5] -- Calling v2 model at {MODEL_V2_URL} for {req_id}")
                    response_v2 = requests.post(
                        MODEL_V2_URL,
                        json=payload["request_body"],
                        timeout=5  # IMPORTANT: Add a 5-second timeout!
                    ).json()
                    print(f"[STEP 3/5] -- Got response from v2 model for {req_id}")

                    # STEP 4: Construct the log
                    comparison_log = {
                        "request_id": req_id,
                        "timestamp": payload.get("timestamp"),
                        "input_text": payload.get("request_body", {}).get("text"),
                        "model_v1_prediction": payload.get("model_v1_prediction"),
                        "model_v2_prediction": response_v2
                    }
                    comparison_log["prediction_agreed"] = (
                        comparison_log.get("model_v1_prediction", {}).get("category") ==
                        comparison_log.get("model_v2_prediction", {}).get("category")
                    )
                    print(f"[STEP 4/5] -- Constructed comparison log for {req_id}")

                    # STEP 5: Send to Elasticsearch
                    es.index(index=ES_INDEX, document=comparison_log)
                    print(f"[STEP 5/5] -- ✅ Logged comparison to Elasticsearch for {req_id}")

                except requests.exceptions.Timeout:
                    print(f"   ❗️ [ERROR] Request to v2 model TIMED OUT for {req_id}")
                except Exception as e:
                    print(f"   ❗️ [ERROR] Failed processing message {req_id}: {e}")

        except kafka_errors.NoBrokersAvailable:
            print(f"❌ [FATAL] Kafka broker not available. Resetting connection in {RETRY_DELAY}s...")
            consumer = None
            time.sleep(RETRY_DELAY)
        except Exception as e:
            print(f"❌ [FATAL] An unexpected error occurred in main loop: {e}. Restarting in {RETRY_DELAY}s...")
            consumer = None
            time.sleep(RETRY_DELAY)

if __name__ == "__main__":
    main()