# 1. 基础配置保持不变
terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project     = "gen-lang-client-0486815668"
  region      = "us-central1"
  credentials = file("service-account-key.json")
}

# 2. 修改为 Cloud Run Service
resource "google_cloud_run_v2_service" "stock_service" {
  name     = "stock-scanner-service"
  location = "us-central1"
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    containers {
      # 临时改用这个，保证能创建成功
      image = "us-docker.pkg.dev/cloudrun/container/hello"
      #image = "us-central1-docker.pkg.dev/gen-lang-client-0486815668/stock-scanner-repo/app:latest"
      env {
        name  = "DATABASE_URL"
        value = "placeholder" # 部署时由 GitHub Actions 填充
      }
      env {
        name  = "GEMINI_API_KEY"
        value = "placeholder"
      }
    }
  }
}

# 3. 必须允许公开访问（以便插件调用）
resource "google_cloud_run_v2_service_iam_member" "noauth" {
  location = google_cloud_run_v2_service.stock_service.location
  name     = google_cloud_run_v2_service.stock_service.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

output "service_url" {
  value = google_cloud_run_v2_service.stock_service.uri
}