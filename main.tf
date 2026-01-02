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

# --- 新增：定义 Docker 仓库 ---
resource "google_artifact_registry_repository" "stock_repo" {
  location      = "us-central1"
  repository_id = "stock-scanner-repo"
  description   = "Docker repository for AI Scanner"
  format        = "DOCKER"
}

# 2. 修改为 Cloud Run Service
resource "google_cloud_run_v2_service" "stock_service" {
  name     = "stock-scanner-service"
  location = "us-central1"
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    containers {
      # 保持使用 hello 镜像作为初始占位，直到 GitHub Actions 推送真正的镜像
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
  
  # 确保仓库先创建好
  depends_on = [google_artifact_registry_repository.stock_repo]
}

# 3. 允许公开访问
resource "google_cloud_run_v2_service_iam_member" "noauth" {
  location = google_cloud_run_v2_service.stock_service.location
  name     = google_cloud_run_v2_service.stock_service.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}


resource "google_cloud_run_v2_job" "analyst_job" {
  name     = "stock-analyst-job"
  location = "us-central1"

  template {
    template {
      containers {
        image = "us-central1-docker.pkg.dev/gen-lang-client-0486815668/stock-scanner-repo/app:latest"
        # 重点：运行这个特定的分析脚本，而不是 main.py
        command = ["python", "analyst_job.py"] 
        env {
          name  = "DATABASE_URL"
          value = "你的_DATABASE_URL"
        }
      }
    }
  }
}



