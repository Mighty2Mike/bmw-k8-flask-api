import os
import time
import json
import uuid
import logging
from datetime import datetime, timezone

from flask import Flask, jsonify, request
from confluent_kafka import Producer, Consumer, KafkaError, KafkaException

from config import Config

# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)


# ---------------------------------------------------------------------------
# Kafka helpers
# ---------------------------------------------------------------------------

def _delivery_report(err, msg):
    """
    Callback fired by the Kafka producer for every message once delivery
    is confirmed (or permanently failed).  Runs in the producer's poll thread.
    """
    if err:
        logger.error(f"Kafka delivery failed | topic={msg.topic()} error={err}")
    else:
        logger.info(
            f"Kafka delivery OK | topic={msg.topic()} "
            f"partition={msg.partition()} offset={msg.offset()}"
        )


def get_producer() -> Producer:
    """
    Build a confluent-kafka Producer from config values that were injected
    into the pod as environment variables from the Kubernetes Secret
    'kafka-secrets'.  A new producer instance is created per request so the
    connection is always using the latest secret values — in production you
    would cache this and refresh on auth errors.
    """
    return Producer(Config.kafka_producer_config())


def get_consumer() -> Consumer:
    """
    Build a confluent-kafka Consumer from K8s-secret-sourced config.
    """
    return Consumer(Config.kafka_consumer_config())


# ---------------------------------------------------------------------------
# Standard routes
# ---------------------------------------------------------------------------


@app.route("/", methods=["GET"])
def hello():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>WELCOME TO THE BMW GROUP!</title>
        <style>
            body {
                margin: 0;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            }
            .card {
                background: white;
                border-radius: 16px;
                padding: 60px 80px;
                text-align: center;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            }
            h1 { font-size: 3rem; color: #4a4a8a; margin: 0 0 12px; }
            p  { color: #888; font-size: 1.1rem; margin: 0; }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>WELCOME TO THE BMW GROUP! 👋</h1>
            <p>Flask API Assessment by Michael Nthodi running on Kubernetes via Helm</p>
        </div>
    </body>
    </html>
    """

@app.route("/health", methods=["GET"])
def health():
    """Liveness probe endpoint."""
    return jsonify({"status": "healthy"}), 200


@app.route("/ready", methods=["GET"])
def ready():
    """Readiness probe endpoint."""
    return jsonify({"status": "ready"}), 200


@app.route("/api/v1/data", methods=["GET"])
def get_data():
    """Main API endpoint - simulates work under load."""
    start = time.time()
    time.sleep(0.05)
    duration = round((time.time() - start) * 1000, 2)
    logger.info(f"GET /api/v1/data processed in {duration}ms")
    return jsonify({
        "message":     "Success",
        "environment": app.config["ENVIRONMENT"],
        "app_version": app.config["APP_VERSION"],
        "duration_ms": duration,
    }), 200


@app.route("/api/v1/stress", methods=["GET"])
def stress():
    """CPU-intensive endpoint to trigger HPA scaling."""
    result = 0
    for i in range(int(app.config.get("STRESS_ITERATIONS", 500000))):
        result += i * i
    logger.info("Stress endpoint hit")
    return jsonify({"result": result % 1000000}), 200


# ---------------------------------------------------------------------------
# Kafka routes
# ---------------------------------------------------------------------------

@app.route("/api/v1/kafka/produce", methods=["POST"])
def kafka_produce():
    """
    Publish a message to the Kafka topic defined by KAFKA_TOPIC_PRODUCE.

    The Kafka connection is established using credentials injected from the
    Kubernetes Secret 'kafka-secrets' via environment variables:
        KAFKA_BOOTSTRAP_SERVERS, KAFKA_SASL_USERNAME, KAFKA_SASL_PASSWORD, ...

    Request body (JSON):
        {
            "event_type": "order.created",   # required
            "payload":    { ... }            # any JSON object
        }

    Returns 202 Accepted — delivery confirmation is asynchronous via the
    _delivery_report callback.
    """
    body = request.get_json(silent=True)
    if not body or "event_type" not in body:
        return jsonify({
            "error": "Request body must be JSON with an 'event_type' field"
        }), 400

    event = {
        "event_id":    str(uuid.uuid4()),
        "event_type":  body["event_type"],
        "payload":     body.get("payload", {}),
        "produced_at": datetime.now(timezone.utc).isoformat(),
        "source":      "flask-api",
    }

    topic = Config.KAFKA_TOPIC_PRODUCE

    try:
        producer = get_producer()

        producer.produce(
            topic       = topic,
            key         = event["event_id"].encode("utf-8"),
            value       = json.dumps(event).encode("utf-8"),
            on_delivery = _delivery_report,
        )

        # poll(0) flushes the delivery-report callback queue without blocking
        producer.poll(0)

        # flush(timeout) blocks until all messages are delivered or timeout
        undelivered = producer.flush(timeout=10)
        if undelivered > 0:
            logger.warning(f"{undelivered} message(s) not delivered within timeout")

        logger.info(f"Produced event {event['event_id']} to topic '{topic}'")

        return jsonify({
            "status":   "accepted",
            "event_id": event["event_id"],
            "topic":    topic,
        }), 202

    except KafkaException as exc:
        logger.error(f"Kafka produce error: {exc}")
        return jsonify({"error": "Failed to produce message", "detail": str(exc)}), 503

    except Exception as exc:
        logger.error(f"Unexpected error during produce: {exc}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/v1/kafka/consume", methods=["GET"])
def kafka_consume():
    """
    Poll the Kafka topic defined by KAFKA_TOPIC_CONSUME and return up to
    `max_messages` messages (default 10).

    The Kafka connection credentials come from the Kubernetes Secret
    'kafka-secrets' via environment variables — the same secret that drives
    the producer route above.

    Query params:
        max_messages  int    Maximum messages to return (default 10, max 100)
        timeout       float  Poll timeout in seconds (default 3.0)

    This is a synchronous poll — suitable for an assessment demo.
    In production, consumers would run in a background thread or separate
    consumer service, committing offsets after successful processing.
    """
    max_messages = min(int(request.args.get("max_messages", 10)), 100)
    poll_timeout = float(request.args.get("timeout", 3.0))

    topic    = Config.KAFKA_TOPIC_CONSUME
    messages = []

    try:
        consumer = get_consumer()
        consumer.subscribe([topic])
        logger.info(f"Subscribed to topic '{topic}', polling for {poll_timeout}s")

        deadline = time.time() + poll_timeout

        while len(messages) < max_messages and time.time() < deadline:
            remaining = deadline - time.time()
            msg = consumer.poll(timeout=min(1.0, remaining))

            if msg is None:
                continue

            if msg.error():
                # End-of-partition is informational, not a fatal error
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    logger.debug(
                        f"End of partition {msg.topic()}/{msg.partition()}"
                    )
                    break
                raise KafkaException(msg.error())

            try:
                value = json.loads(msg.value().decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                value = msg.value().decode("utf-8", errors="replace")

            messages.append({
                "topic":     msg.topic(),
                "partition": msg.partition(),
                "offset":    msg.offset(),
                "key":       msg.key().decode("utf-8") if msg.key() else None,
                "value":     value,
                "timestamp": msg.timestamp()[1],
            })

            # Manual commit after successful processing (reliable delivery)
            consumer.commit(msg)

        return jsonify({
            "topic":         topic,
            "messages_read": len(messages),
            "messages":      messages,
        }), 200

    except KafkaException as exc:
        logger.error(f"Kafka consume error: {exc}")
        return jsonify({"error": "Failed to consume messages", "detail": str(exc)}), 503

    except Exception as exc:
        logger.error(f"Unexpected error during consume: {exc}")
        return jsonify({"error": "Internal server error"}), 500

    finally:
        # Always close the consumer to release group membership & committed offsets
        try:
            consumer.close()
        except Exception:
            pass


@app.route("/api/v1/kafka/status", methods=["GET"])
def kafka_status():
    """
    Probe Kafka cluster reachability using credentials from the Kubernetes
    Secret 'kafka-secrets'.  Returns broker metadata if reachable.

    Useful as an integration health check — callable from monitoring or
    a readiness probe extension.
    """
    try:
        producer = get_producer()

        # list_topics() performs a metadata fetch — confirms connectivity
        metadata = producer.list_topics(timeout=5)

        brokers = [
            {"id": b.id, "host": b.host, "port": b.port}
            for b in metadata.brokers.values()
        ]
        topics = list(metadata.topics.keys())

        return jsonify({
            "status":            "connected",
            "bootstrap_servers": Config.KAFKA_BOOTSTRAP_SERVERS,
            "security_protocol": Config.KAFKA_SECURITY_PROTOCOL,
            "brokers":           brokers,
            "visible_topics":    topics,
        }), 200

    except KafkaException as exc:
        logger.error(f"Kafka status check failed: {exc}")
        return jsonify({
            "status":            "unreachable",
            "bootstrap_servers": Config.KAFKA_BOOTSTRAP_SERVERS,
            "error":             str(exc),
        }), 503


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(
        host  = "0.0.0.0",
        port  = int(os.environ.get("PORT", 5000)),
        debug = app.config["DEBUG"],
    )
