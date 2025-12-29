# main.tf

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project     = "gen-lang-client-0486815668" # ⬅️ 替换为你真实的 GCP Project ID
  region      = "us-central1"
  credentials = file("service-account-key.json") # ⬅️ 确保这个JSON文件也在该目录下
}

# 1. 创建存放 Docker 镜像的仓库
resource "google_artifact_registry_repository" "my_repo" {
  location      = "us-central1"
  repository_id = "stock-scanner-repo"
  description   = "Docker repository for Reddit Stock Scanner"
  format        = "DOCKER"
}

# 2. 创建 Cloud Run 服务
resource "google_cloud_run_v2_service" "default" {
  name     = "stock-scanner-service"
  location = "us-central1"
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    containers {
      # 初始先用一个简单的镜像，后续由 GitHub Actions 更新为你的 Python 代码
      image = "us-docker.pkg.dev/cloudrun/container/hello"
      
      # 环境变量（这些会被 GitHub Actions 的配置覆盖，但在这里初始化比较安全）
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

# 3. 允许公开访问（方便测试 URL）
resource "google_cloud_run_v2_service_iam_member" "noauth" {
  location = google_cloud_run_v2_service.default.location
  name     = google_cloud_run_v2_service.default.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}