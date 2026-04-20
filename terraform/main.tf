# -----------------------------------------------------------------------
# Namespace
# -----------------------------------------------------------------------
resource "kubernetes_namespace" "flask" {
  metadata {
    name = var.namespace

    labels = {
      environment = var.environment
      managed-by  = "terraform"
    }
  }
}

# -----------------------------------------------------------------------
# ConfigMap — non-sensitive application configuration
# These values are safe to store in version control
# -----------------------------------------------------------------------
resource "kubernetes_config_map" "flask_config" {
  metadata {
    name      = "flask-config"
    namespace = kubernetes_namespace.flask.metadata[0].name
  }

  data = {
    ENVIRONMENT       = var.environment
    APP_VERSION       = var.app_version
    LOG_LEVEL         = "INFO"
    DEBUG             = "false"
    STRESS_ITERATIONS = "500000"
  }
}

# -----------------------------------------------------------------------
# Secret — sensitive application configuration
# In a real pipeline these would come from Vault, AWS SSM, or SOPS.
# Terraform marks these as sensitive so they are redacted in plan output.
# -----------------------------------------------------------------------
resource "kubernetes_secret" "flask_secrets" {
  metadata {
    name      = "flask-secrets"
    namespace = kubernetes_namespace.flask.metadata[0].name
  }

  # Kubernetes automatically base64-encodes values in the `data` block
  data = {
    SECRET_KEY     = var.secret_key
    DATABASE_URL   = var.database_url
    API_KEY        = var.api_key
  }

  type = "Opaque"
}

# -----------------------------------------------------------------------
# Kafka Secret — Kafka cluster credentials stored separately so they can
# be rotated independently of the main app secret (least-privilege principle).
#
# Values flow:
#   terraform.tfvars (git-ignored)
#     → kubernetes_secret.kafka_secrets (base64 at rest in etcd)
#       → pod env vars (via envFrom.secretRef in the Helm deployment template)
#         → Config.kafka_producer/consumer_config() in config.py
#           → confluent_kafka.Producer / Consumer in main.py
# -----------------------------------------------------------------------
resource "kubernetes_secret" "kafka_secrets" {
  metadata {
    name      = "kafka-secrets"
    namespace = kubernetes_namespace.flask.metadata[0].name

    labels = {
      app        = "flask-api"
      managed-by = "terraform"
      secret-type = "kafka"
    }
  }

  data = {
    KAFKA_BOOTSTRAP_SERVERS = var.kafka_bootstrap_servers
    KAFKA_SECURITY_PROTOCOL = var.kafka_security_protocol
    KAFKA_SASL_MECHANISM    = var.kafka_sasl_mechanism
    KAFKA_SASL_USERNAME     = var.kafka_sasl_username
    KAFKA_SASL_PASSWORD     = var.kafka_sasl_password
    KAFKA_SSL_CA_LOCATION   = var.kafka_ssl_ca_location
    KAFKA_TOPIC_PRODUCE     = var.kafka_topic_produce
    KAFKA_TOPIC_CONSUME     = var.kafka_topic_consume
    KAFKA_GROUP_ID          = var.kafka_group_id
  }

  type = "Opaque"
}
