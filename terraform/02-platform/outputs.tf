output "traefik_release" {
  value = "${helm_release.traefik.name} (chart ${helm_release.traefik.version}) in namespace ${helm_release.traefik.namespace}"
}

output "app_url" {
  value = "http://localhost/api/stats"
}
