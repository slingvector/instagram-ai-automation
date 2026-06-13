variable "project_id" { type = string }
variable "region" {
  type    = string
  default = "us-central1"
}
variable "bucket_name" {
  type    = string
  default = "modernos-relay-cdn-origin"
}
variable "relay_hostname" {
  type        = string
  description = "Hostname for the managed SSL cert, e.g. relay.example.com"
}
