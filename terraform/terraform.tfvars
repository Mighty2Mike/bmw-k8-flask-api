# Copy this file to terraform.tfvars and fill in real values.
# terraform.tfvars is git-ignored — NEVER commit real secrets.

environment  = "development"
app_version  = "latest"
min_replicas = 2
max_replicas = 10

# Secrets — use strong random values in staging/production
secret_key     = "XXXXXXXXXXXXX"
database_url   = "sqlite:///dev.db"
api_key        = "XXXXXX_API_KEY_XXXXXXX"

# ---------------------------------------------------------------------------
# Kafka secrets
# For local Minikube dev, spin up a local Kafka with:
#   docker run -d --name kafka -p 9092:9092 \
#     -e KAFKA_CFG_ADVERTISED_LISTENERS=PLAINTEXT://127.0.0.1:9092 \
#     bitnami/kafka:latest
# Then use the values below as-is.
#
# For a secured cluster (Confluent Cloud, MSK, etc.) set the SASL/SSL fields.
# ---------------------------------------------------------------------------
kafka_bootstrap_servers = "localhost:9092"
kafka_security_protocol = "PLAINTEXT"   # Change to SASL_SSL for production
kafka_sasl_mechanism    = "PLAIN"
kafka_sasl_username     = ""            # Required when SASL_* protocol is used
kafka_sasl_password     = ""            # Required when SASL_* protocol is used
kafka_ssl_ca_location   = ""            # Path to CA cert, e.g. /etc/ssl/kafka-ca.pem
kafka_topic_produce     = "bmw-flask-api-events"
kafka_topic_consume     = "bmw-flask-api-events"
kafka_group_id          = "bmw-flask-api-consumer-group"
