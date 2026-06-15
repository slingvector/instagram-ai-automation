# ModernOS Content Relay — Method 1 edge: GCS origin + HTTPS LB + Cloud CDN.
# `terraform apply` with your own GCP creds. Point a DNS A record for
# var.relay_hostname at google_compute_global_address.relay.address.

terraform {
  required_providers {
    google = { source = "hashicorp/google", version = "~> 5.0" }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# --- Origin bucket -----------------------------------------------------------
resource "google_storage_bucket" "origin" {
  name                        = var.bucket_name
  location                    = "US"
  uniform_bucket_level_access = true
  cors {
    origin          = ["*"]
    method          = ["GET", "HEAD"]
    response_header = ["*"]
    max_age_seconds = 3600
  }
}

# Public read on HLS objects (use signed URLs instead if assets are private).
resource "google_storage_bucket_iam_member" "public_read" {
  bucket = google_storage_bucket.origin.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

# --- CDN-backed backend ------------------------------------------------------
resource "google_compute_backend_bucket" "relay" {
  name        = "modernos-relay-backend"
  bucket_name = google_storage_bucket.origin.name
  enable_cdn  = true
  cdn_policy {
    cache_mode  = "CACHE_ALL_STATIC"
    default_ttl = 3600
    max_ttl     = 86400
    # Long TTL for immutable .ts segments; serve the .m3u8 with a short
    # Cache-Control (set at upload) so playlists refresh.
  }
}

# --- HTTPS front end ---------------------------------------------------------
resource "google_compute_global_address" "relay" {
  name = "modernos-relay-ip"
}

resource "google_compute_managed_ssl_certificate" "relay" {
  name = "modernos-relay-cert"
  managed { domains = [var.relay_hostname] }
}

resource "google_compute_url_map" "relay" {
  name            = "modernos-relay-urlmap"
  default_service = google_compute_backend_bucket.relay.id
}

resource "google_compute_target_https_proxy" "relay" {
  name             = "modernos-relay-https-proxy"
  url_map          = google_compute_url_map.relay.id
  ssl_certificates = [google_compute_managed_ssl_certificate.relay.id]
}

resource "google_compute_global_forwarding_rule" "relay" {
  name       = "modernos-relay-fr"
  target     = google_compute_target_https_proxy.relay.id
  port_range = "443"
  ip_address = google_compute_global_address.relay.address
}
