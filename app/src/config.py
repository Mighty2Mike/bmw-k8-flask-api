import os


class Config:
    """
    Application configuration loaded from environment variables.

    In Kubernetes:
    - Non-sensitive values come from ConfigMap (injected as env vars)
    - Sensitive values come from Secrets (injected as env vars)

    Locally for development, use a .env file with python-dotenv.
    Never hardcode secrets in source code.
    """

    # -------------------------------------------------------------------------
    # Non-sensitive config — sourced from Kubernetes ConfigMap
    # -------------------------------------------------------------------------
    ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")
    APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
    STRESS_ITERATIONS = int(os.environ.get("STRESS_ITERATIONS", 500000))

    # -------------------------------------------------------------------------
    # Sensitive config — sourced from Kubernetes Secret
    # These would be base64-encoded in the K8s Secret manifest and injected
    # as environment variables at pod startup. Never commit real values.
    # -------------------------------------------------------------------------
    DATABASE_URL   = os.environ.get("DATABASE_URL", "")
    SECRET_KEY     = os.environ.get("SECRET_KEY", "dev-only-insecure-key")
    API_KEY        = os.environ.get("API_KEY", "")

    # -------------------------------------------------------------------------
    # Kafka config — sourced from Kubernetes Secret (kafka-secrets)
    #
    # KAFKA_BOOTSTRAP_SERVERS  — comma-separated broker list
    #                            e.g. "broker1:9092,broker2:9092"
    # KAFKA_SECURITY_PROTOCOL  — PLAINTEXT | SSL | SASL_PLAINTEXT | SASL_SSL
    # KAFKA_SASL_MECHANISM     — PLAIN | SCRAM-SHA-256 | SCRAM-SHA-512
    # KAFKA_SASL_USERNAME      — SASL username (sensitive)
    # KAFKA_SASL_PASSWORD      — SASL password (sensitive)
    # KAFKA_SSL_CA_LOCATION    — path to CA cert file mounted via K8s secret
    # KAFKA_TOPIC_PRODUCE      — topic the API publishes events to
    # KAFKA_TOPIC_CONSUME      — topic the API reads events from
    # KAFKA_GROUP_ID           — consumer group ID
    # -------------------------------------------------------------------------
    KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    KAFKA_SECURITY_PROTOCOL = os.environ.get("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")
    KAFKA_SASL_MECHANISM    = os.environ.get("KAFKA_SASL_MECHANISM", "PLAIN")
    KAFKA_SASL_USERNAME     = os.environ.get("KAFKA_SASL_USERNAME", "")
    KAFKA_SASL_PASSWORD     = os.environ.get("KAFKA_SASL_PASSWORD", "")
    KAFKA_SSL_CA_LOCATION   = os.environ.get("KAFKA_SSL_CA_LOCATION", "")
    KAFKA_TOPIC_PRODUCE     = os.environ.get("KAFKA_TOPIC_PRODUCE", "flask-api-events")
    KAFKA_TOPIC_CONSUME     = os.environ.get("KAFKA_TOPIC_CONSUME", "flask-api-events")
    KAFKA_GROUP_ID          = os.environ.get("KAFKA_GROUP_ID", "flask-api-consumer-group")

    @classmethod
    def validate(cls):
        """Fail fast on startup if required secrets are missing in production."""
        if cls.ENVIRONMENT == "production":
            required = ["DATABASE_URL", "SECRET_KEY", "API_KEY", "KAFKA_BOOTSTRAP_SERVERS"]
            missing = [k for k in required if not getattr(cls, k)]
            if missing:
                raise EnvironmentError(
                    f"Missing required environment variables: {missing}"
                )

    @classmethod
    def kafka_producer_config(cls) -> dict:
        """
        Build the confluent-kafka producer config dict from environment.
        Constructed at call-time so values are always fresh from the env.
        """
        cfg = {
            "bootstrap.servers":  cls.KAFKA_BOOTSTRAP_SERVERS,
            "security.protocol":  cls.KAFKA_SECURITY_PROTOCOL,
            "client.id":          "flask-api-producer",
            # Delivery guarantees
            "acks":               "all",     # wait for all ISR replicas
            "retries":            5,
            "retry.backoff.ms":   300,
        }
        if cls.KAFKA_SECURITY_PROTOCOL in ("SASL_PLAINTEXT", "SASL_SSL"):
            cfg["sasl.mechanism"] = cls.KAFKA_SASL_MECHANISM
            cfg["sasl.username"]  = cls.KAFKA_SASL_USERNAME
            cfg["sasl.password"]  = cls.KAFKA_SASL_PASSWORD
        if cls.KAFKA_SECURITY_PROTOCOL in ("SSL", "SASL_SSL") and cls.KAFKA_SSL_CA_LOCATION:
            cfg["ssl.ca.location"] = cls.KAFKA_SSL_CA_LOCATION
        return cfg

    @classmethod
    def kafka_consumer_config(cls) -> dict:
        """
        Build the confluent-kafka consumer config dict from environment.
        """
        cfg = {
            "bootstrap.servers":  cls.KAFKA_BOOTSTRAP_SERVERS,
            "security.protocol":  cls.KAFKA_SECURITY_PROTOCOL,
            "group.id":           cls.KAFKA_GROUP_ID,
            "auto.offset.reset":  "earliest",
            "enable.auto.commit": False,     # manual commit for reliability
        }
        if cls.KAFKA_SECURITY_PROTOCOL in ("SASL_PLAINTEXT", "SASL_SSL"):
            cfg["sasl.mechanism"] = cls.KAFKA_SASL_MECHANISM
            cfg["sasl.username"]  = cls.KAFKA_SASL_USERNAME
            cfg["sasl.password"]  = cls.KAFKA_SASL_PASSWORD
        if cls.KAFKA_SECURITY_PROTOCOL in ("SSL", "SASL_SSL") and cls.KAFKA_SSL_CA_LOCATION:
            cfg["ssl.ca.location"] = cls.KAFKA_SSL_CA_LOCATION
        return cfg
