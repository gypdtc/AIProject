# 1. 基础配置 (Terraform & Provider)
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

# 2. 镜像仓库 (保持不变)
resource "google_artifact_registry_repository" "my_repo" {
  location      = "us-central1"
  repository_id = "stock-scanner-repo"
  format        = "DOCKER"
}

# 3. 核心任务 (改用 Job)
resource "google_cloud_run_v2_job" "stock_scanner_job" {
  name     = "stock-scanner-job"
  location = "us-central1"

  template {
    template {
      containers {
        #image = "us-central1-docker.pkg.dev/gen-lang-client-0486815668/stock-scanner-repo/app:latest"
        image = "us-docker.pkg.dev/cloudrun/container/hello"
        env {
          name  = "DATABASE_URL"
          value = "placeholder"
        }
        env {
          name  = "GEMINI_API_KEY"
          value = "placeholder"
        }
      }
    }
  }
}

