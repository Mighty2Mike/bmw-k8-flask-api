variable "namespace" {
  description = "Kubernetes namespace for the Flask application"
  type        = string
  default     = "bmw-k8-flask-api"
}

variable "app_version" {
  description = "Docker image tag to deploy"
  type        = string
  default     = "latest"
}

variable "environment" {
  description = "Deployment environment (development | staging | production)"
  type        = string
  default     = "development"

  # validation {
  #   condition     = contains(["development", "staging", "production"], var.environment)
  #   error_message = "environment must be one of: development, staging, production"
  # }
}

# -----------------------------------------------------------------------
# Sensitive variables — passed in via terraform.tfvars (git-ignored) or
# environment variables: TF_VAR_secret_key, TF_VAR_database_url, etc.
# Never hardcode real secrets here.
# -----------------------------------------------------------------------
variable "secret_key" {
  description = "Flask SECRET_KEY — must be cryptographically random in production"
  type        = string
  sensitive   = true
}

variable "database_url" {
  description = "Full database connection string"
  type        = string
  sensitive   = true
  default     = "sqlite:///dev.db"
}

variable "api_key" {
  description = "External API key consumed by the Flask app"
  type        = string
  sensitive   = true
  default     = "dev-api-key"
}

variable "min_replicas" {
  description = "Minimum HPA replica count"
  type        = number
  default     = 2
}

variable "max_replicas" {
  description = "Maximum HPA replica count"
  type        = number
  default     = 10
}

# -----------------------------------------------------------------------
# Kafka variables — all sensitive, sourced from terraform.tfvars (git-ignored)
# or via TF_VAR_kafka_* environment variables in a CI/CD pipeline.
# -----------------------------------------------------------------------
variable "kafka_bootstrap_servers" {
  description = "Comma-separated Kafka broker list, e.g. broker1:9092,broker2:9092"
  type        = string
  sensitive   = true
  default     = "localhost:9092"
}

variable "kafka_security_protocol" {
  description = "Kafka security protocol: PLAINTEXT | SSL | SASL_PLAINTEXT | SASL_SSL"
  type        = string
  default     = "PLAINTEXT"
}

variable "kafka_sasl_mechanism" {
  description = "SASL mechanism: PLAIN | SCRAM-SHA-256 | SCRAM-SHA-512"
  type        = string
  default     = "PLAIN"
}

variable "kafka_sasl_username" {
  description = "Kafka SASL username"
  type        = string
  sensitive   = true
  default     = ""
}

variable "kafka_sasl_password" {
  description = "Kafka SASL password"
  type        = string
  sensitive   = true
  default     = ""
}

variable "kafka_ssl_ca_location" {
  description = "Path to CA certificate file (mounted via K8s secret volume)"
  type        = string
  default     = ""
}

variable "kafka_topic_produce" {
  description = "Kafka topic the Flask API publishes events to"
  type        = string
  default     = "flask-api-events"
}

variable "kafka_topic_consume" {
  description = "Kafka topic the Flask API reads events from"
  type        = string
  default     = "flask-api-events"
}

variable "kafka_group_id" {
  description = "Kafka consumer group ID"
  type        = string
  default     = "flask-api-consumer-group"
}
