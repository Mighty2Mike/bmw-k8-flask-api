output "namespace" {
  description = "Kubernetes namespace the app is deployed into"
  value       = kubernetes_namespace.flask.metadata[0].name
}

# output "helm_release_status" {
#   description = "Helm release status"
#   value       = helm_release.flask_api.status
# }

output "config_map_name" {
  description = "Name of the ConfigMap holding non-sensitive config"
  value       = kubernetes_config_map.flask_config.metadata[0].name
}

output "secret_name" {
  description = "Name of the K8s Secret holding sensitive config"
  value       = kubernetes_secret.flask_secrets.metadata[0].name
  sensitive   = true
}
