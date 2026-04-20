# -----------------------------------------------------------------------
# Helm Release — deploys the Flask API chart onto Minikube
# -----------------------------------------------------------------------
resource "helm_release" "flask_api" {
  name      = "flask-api"
  chart     = "${path.module}/../charts/bmw-k8-flask-api"
  namespace = kubernetes_namespace.flask.metadata[0].name

  # Wait for all pods to be ready before Terraform marks apply as complete
  wait    = true
  timeout = 300

  # -----------------------------------------------------------------------
  # Non-sensitive values passed directly into chart values
  # -----------------------------------------------------------------------
  set {
    name  = "image.repository"
    value = "michaelnthodidocker/bmw-flask-k8-assessment"
  }

  set {
    name  = "image.tag"
    value = var.app_version
  }

  set {
    name  = "image.pullPolicy"
    value = "Never" # Use local Minikube image; change to Always for remote registry
  }

  set {
    name  = "replicaCount"
    value = var.min_replicas
  }

  set {
    name  = "hpa.minReplicas"
    value = var.min_replicas
  }

  set {
    name  = "hpa.maxReplicas"
    value = var.max_replicas
  }

  set {
    name  = "environment"
    value = var.environment
  }

  # -----------------------------------------------------------------------
  # Reference the K8s Secret created by Terraform above
  # The chart reads env vars from this secret — values never appear in
  # Helm values or Terraform state in plaintext
  # -----------------------------------------------------------------------
  set {
    name  = "existingSecret"
    value = kubernetes_secret.flask_secrets.metadata[0].name
  }

  set {
    name  = "existingConfigMap"
    value = kubernetes_config_map.flask_config.metadata[0].name
  }

  # Pass the Kafka secret name into the chart so the deployment can mount it
  set {
    name  = "existingKafkaSecret"
    value = kubernetes_secret.kafka_secrets.metadata[0].name
  }

  depends_on = [
    kubernetes_namespace.flask,
    kubernetes_config_map.flask_config,
    kubernetes_secret.flask_secrets,
    kubernetes_secret.kafka_secrets,
  ]
}
