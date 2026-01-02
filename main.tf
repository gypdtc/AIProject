# 1. 基础提供者配置
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

# 获取项目数据，用于动态构建 Job 的 URI
data "google_project" "project" {}

# 2. 基础设施：Docker 镜像仓库
resource "google_artifact_registry_repository" "stock_repo" {
  location      = "us-central1"
  repository_id = "stock-scanner-repo"
  format        = "DOCKER"
  description   = "Docker repository for AI Scanner Project"
}

# --- 3. 服务端 (Services) ---

# A. 后端 API 服务：处理插件截图
resource "google_cloud_run_v2_service" "stock_service" {
  name     = "stock-scanner-service"
  location = "us-central1"
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    containers {
      image = "us-central1-docker.pkg.dev/gen-lang-client-0486815668/stock-scanner-repo/app:latest"
      env { 
        name = "DATABASE_URL"     
        value = "placeholder" 
      }
      env { 
        name = "GEMINI_API_KEY"   
        value = "placeholder" 
      }
      env { 
        name = "INTERNAL_AUTH_KEY" 
        value = "placeholder" 
      }
    }
  }
}

# B. 前端 UI 服务：Streamlit 看板
resource "google_cloud_run_v2_service" "ui_service" {
  name     = "stock-scanner-ui"
  location = "us-central1"
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    containers {
      image   = "us-central1-docker.pkg.dev/gen-lang-client-0486815668/stock-scanner-repo/app:latest"
      command = ["streamlit", "run", "dashboard.py", "--server.port=8080", "--server.address=0.0.0.0"]
      env { 
        name = "DATABASE_URL"      
        value = "placeholder" 
      }
      env { 
        name = "DASHBOARD_PASSWORD" 
        value = "placeholder" 
      }
    }
  }
}

# 允许公众访问 API 和 UI
resource "google_cloud_run_v2_service_iam_member" "api_noauth" {
  location = google_cloud_run_v2_service.stock_service.location
  name     = google_cloud_run_v2_service.stock_service.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "ui_noauth" {
  location = google_cloud_run_v2_service.ui_service.location
  name     = google_cloud_run_v2_service.ui_service.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# --- 4. 自动化任务 (Jobs) ---

# A. 准确率分析任务
resource "google_cloud_run_v2_job" "analyst_job" {
  name     = "stock-analyst-job"
  location = "us-central1"
  template {
    template {
      containers {
        image   = "us-central1-docker.pkg.dev/gen-lang-client-0486815668/stock-scanner-repo/app:latest"
        command = ["python", "analyst_job.py"]
        env { 
          name = "DATABASE_URL" 
          value = "placeholder" 
        }
      }
    }
  }
}

# B. 期权大单扫描任务
resource "google_cloud_run_v2_job" "option_scanner_job" {
  name     = "option-scanner-job"
  location = "us-central1"
  template {
    template {
      containers {
        image   = "us-central1-docker.pkg.dev/gen-lang-client-0486815668/stock-scanner-repo/app:latest"
        command = ["python", "options_scanner.py"]
        env { 
          name = "DATABASE_URL"   
          value = "placeholder" 
        }
        env { 
          name = "GEMINI_API_KEY" 
          value = "placeholder" 
        }
      }
    }
  }
}

# --- 5. 定时触发器 (Scheduler) ---

# 每天早上 8:00 触发期权扫描
resource "google_cloud_scheduler_job" "option_scan_trigger" {
  name      = "daily-option-scan-trigger"
  schedule  = "0 8 * * *"
  region    = "us-central1"
  time_zone = "Asia/Shanghai"

  http_target {
    http_method = "POST"
    uri         = "https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${data.google_project.project.number}/jobs/option-scanner-job:run"
    oauth_token {
      service_account_email = "aiprojectadmin@gen-lang-client-0486815668.iam.gserviceaccount.com" # 换成你真实的服务账号
    }
  }
}

# 每天早上 9:00 触发准确率分析
resource "google_cloud_scheduler_job" "analyst_trigger" {
  name      = "daily-analyst-trigger"
  schedule  = "0 9 * * *"
  region    = "us-central1"
  time_zone = "Asia/Shanghai"

  http_target {
    http_method = "POST"
    uri         = "https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${data.google_project.project.number}/jobs/stock-analyst-job:run"
    oauth_token {
      service_account_email = "aiprojectadmin@gen-lang-client-0486815668.iam.gserviceaccount.com"
    }
  }
}

# --- 6. 输出 ---
output "api_url" { value = google_cloud_run_v2_service.stock_service.uri }
output "ui_url"  { value = google_cloud_run_v2_service.ui_service.uri }

# 允许该服务账号调用期权扫描 Job
resource "google_cloud_run_v2_job_iam_member" "invoke_scanner" {
  location = "us-central1"
  name     = google_cloud_run_v2_job.option_scanner_job.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:aiprojectadmin@gen-lang-client-0486815668.iam.gserviceaccount.com"
}

# 允许该服务账号调用准确率分析 Job
resource "google_cloud_run_v2_job_iam_member" "invoke_analyst" {
  location = "us-central1"
  name     = google_cloud_run_v2_job.analyst_job.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:aiprojectadmin@gen-lang-client-0486815668.iam.gserviceaccount.com"
}