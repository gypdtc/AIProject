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

# 创建定时触发器
resource "google_cloud_scheduler_job" "stock_scanner_scheduler" {
  name             = "reddit-stock-scanner-hourly"
  description      = "Every hour, trigger the stock scanner AI job"
  schedule         = "0 * * * *"        # 每小时运行一次
  time_zone        = "Asia/Shanghai"    # 设置时区
  attempt_deadline = "320s"

  retry_config {
    retry_count = 1
  }

  http_target {
    http_method = "POST"
    # 这里动态获取你定义的 Cloud Run Job 的执行 URL
    uri         = "https://${google_cloud_run_v2_job.stock_scanner_job.location}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${google_cloud_run_v2_job.stock_scanner_job.project}/jobs/${google_cloud_run_v2_job.stock_scanner_job.name}:run"

    oauth_token {
      service_account_email = data.google_compute_default_service_account.default.email
    }
  }
}

# 获取默认的服务账号，用于授权调度器运行 Job
data "google_compute_default_service_account" "default" {}