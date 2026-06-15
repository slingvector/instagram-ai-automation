output "cdn_ip" {
  value       = google_compute_global_address.relay.address
  description = "Point a DNS A record for relay_hostname at this IP."
}
output "cdn_base_url" {
  value = "https://${var.relay_hostname}"
}
output "origin_bucket" {
  value = google_storage_bucket.origin.name
}
