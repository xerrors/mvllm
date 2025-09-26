#!/bin/bash

# vLLM Router 部署脚本集
#
# 这个脚本包含了各种部署和测试场景的示例
#
# 使用方法:
#   ./deployment-scripts.sh [command]
#

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_debug() {
    echo -e "${BLUE}[DEBUG]${NC} $1"
}

# 检查依赖
check_dependencies() {
    log_info "检查依赖..."

    # 检查 Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker 未安装"
        exit 1
    fi

    # 检查 Docker Compose
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        log_warn "Docker Compose 未安装，某些功能可能不可用"
    fi

    # 检查 curl
    if ! command -v curl &> /dev/null; then
        log_error "curl 未安装"
        exit 1
    fi

    # 检查 jq (可选，用于 JSON 处理)
    if ! command -v jq &> /dev/null; then
        log_warn "jq 未安装，某些 JSON 处理功能可能不可用"
    fi

    log_info "依赖检查完成"
}

# 创建开发环境配置
setup_dev_config() {
    log_info "创建开发环境配置..."

    cat > dev-servers.toml << EOF
[servers]
servers = [
    # 本地开发服务器
    { url = "http://localhost:8081", max_concurrent_requests = 2 },
    { url = "http://localhost:8082", max_concurrent_requests = 2 },
]

[config]
# 开发环境配置
health_check_interval = 5
health_check_timeout = 3
health_check_min_success_rate = 0.7
health_check_max_response_time = 5.0

config_reload_interval = 15
enable_active_health_check = true

request_timeout = 60
max_retries = 2
failure_threshold = 3
auto_recovery_threshold = 30
EOF

    log_info "开发配置已创建: dev-servers.toml"
}

# 创建生产环境配置
setup_prod_config() {
    log_info "创建生产环境配置..."

    cat > prod-servers.toml << EOF
[servers]
servers = [
    # 生产服务器配置示例
    { url = "http://gpu-server-1:8081", max_concurrent_requests = 8 },
    { url = "http://gpu-server-2:8081", max_concurrent_requests = 8 },
    { url = "http://gpu-server-3:8081", max_concurrent_requests = 6 },
    { url = "http://gpu-server-4:8081", max_concurrent_requests = 4 },
]

[config]
# 生产环境配置 (更严格的检查)
health_check_interval = 10
health_check_timeout = 5
health_check_min_success_rate = 0.9
health_check_max_response_time = 3.0
health_check_consecutive_failures = 2

config_reload_interval = 60
enable_active_health_check = true
failure_threshold = 2
auto_recovery_threshold = 120

request_timeout = 180
max_retries = 5
retry_delay = 0.5
EOF

    log_info "生产配置已创建: prod-servers.toml"
}

# 创建 Docker Compose 配置
setup_docker_compose() {
    log_info "创建 Docker Compose 配置..."

    mkdir -p docker

    cat > docker/docker-compose.yml << EOF
version: '3.8'

services:
  vllm-router:
    build: ..
    container_name: vllm-router
    ports:
      - "8888:8888"
    volumes:
      - ./dev-servers.toml:/app/servers.toml
      - ../logs:/app/logs
    environment:
      - LOG_TO_CONSOLE=true
      - LOG_LEVEL=INFO
      - CONFIG_PATH=/app/servers.toml
    restart: unless-stopped
    depends_on:
      - mock-vllm-1
      - mock-vllm-2

  # 模拟 vLLM 服务器 1
  mock-vllm-1:
    image: nginx:alpine
    container_name: mock-vllm-1
    ports:
      - "8081:80"
    volumes:
      - ./mock-server-config/nginx.conf:/etc/nginx/nginx.conf
      - ./mock-server-config/metrics-endpoint:/usr/share/nginx/html/metrics
    restart: unless-stopped

  # 模拟 vLLM 服务器 2
  mock-vllm-2:
    image: nginx:alpine
    container_name: mock-vllm-2
    ports:
      - "8082:80"
    volumes:
      - ./mock-server-config/nginx.conf:/etc/nginx/nginx.conf
      - ./mock-server-config/metrics-endpoint:/usr/share/nginx/html/metrics
    restart: unless-stopped

volumes:
  logs:
EOF

    # 创建模拟服务器配置
    mkdir -p docker/mock-server-config

    cat > docker/mock-server-config/nginx.conf << EOF
events {
    worker_connections 1024;
}

http {
    server {
        listen 80;

        # 模拟 /metrics 端点
        location /metrics {
            default_type "text/plain";
            return 200 'vllm:num_requests_running{engine="0",model_name="llama3.1:8b"} 1.0
vllm:num_requests_waiting{engine="0",model_name="llama3.1:8b"} 0.0
vllm:gpu_cache_usage_perc{engine="0"} 45.2
process_max_fds 65535
';
        }

        # 模拟 /v1/models 端点
        location /v1/models {
            default_type "application/json";
            return 200 '{"object":"list","data":[{"id":"llama3.1:8b","object":"model","created":1640995200}]}';
        }

        # 模拟 /v1/chat/completions 端点
        location /v1/chat/completions {
            default_type "application/json";
            return 200 '{"id":"chat-123","object":"chat.completion","created":1640995200,"choices":[{"index":0,"message":{"role":"assistant","content":"这是一个模拟的回复"},"finish_reason":"stop"}],"usage":{"prompt_tokens":10,"completion_tokens":20,"total_tokens":30}}';
        }

        # 模拟健康检查端点
        location /health {
            default_type "application/json";
            return 200 '{"status":"healthy","timestamp":"$(date +%s)"}';
        }
    }
}
EOF

    # 创建模拟的 metrics 数据
    cat > docker/mock-server-config/metrics-endpoint << EOF
vllm:num_requests_running{engine="0",model_name="llama3.1:8b"} 1.0
vllm:num_requests_waiting{engine="0",model_name="llama3.1:8b"} 0.0
vllm:gpu_cache_usage_perc{engine="0"} 45.2
process_max_fds 65535
EOF

    log_info "Docker Compose 配置已创建: docker/docker-compose.yml"
}

# 开发环境部署
deploy_dev() {
    log_info "部署开发环境..."

    check_dependencies
    setup_dev_config
    setup_docker_compose

    cd docker

    # 启动服务
    log_info "启动 Docker 服务..."
    docker-compose up -d

    # 等待服务启动
    log_info "等待服务启动..."
    sleep 10

    # 检查服务状态
    log_info "检查服务状态..."
    if curl -f http://localhost:8888/health > /dev/null 2>&1; then
        log_info "vLLM Router 启动成功！"
        log_info "访问地址: http://localhost:8888"
        log_info "健康检查: http://localhost:8888/health"
        log_info "负载统计: http://localhost:8888/load-stats"
    else
        log_error "vLLM Router 启动失败"
        docker-compose logs vllm-router
        exit 1
    fi
}

# 生产环境部署
deploy_prod() {
    log_info "部署生产环境..."

    check_dependencies
    setup_prod_config

    # 构建生产镜像
    log_info "构建 Docker 镜像..."
    docker build -t vllm-router:latest .

    # 创建生产环境目录
    mkdir -p production/{logs,config}

    # 复制配置文件
    cp prod-servers.toml production/config/servers.toml

    # 运行生产容器
    log_info "启动生产容器..."
    docker run -d \
        --name vllm-router-prod \
        -p 8888:8888 \
        -v $(pwd)/production/config/servers.toml:/app/servers.toml \
        -v $(pwd)/production/logs:/app/logs \
        -e LOG_TO_CONSOLE=false \
        -e LOG_LEVEL=INFO \
        --restart unless-stopped \
        --memory=1g \
        --cpus=1.0 \
        vllm-router:latest

    # 等待服务启动
    log_info "等待服务启动..."
    sleep 30

    # 检查服务状态
    log_info "检查服务状态..."
    if curl -f http://localhost:8888/health > /dev/null 2>&1; then
        log_info "vLLM Router 生产环境启动成功！"
    else
        log_error "vLLM Router 启动失败"
        docker logs vllm-router-prod
        exit 1
    fi
}

# 运行测试
run_tests() {
    log_info "运行测试..."

    # 等待服务完全启动
    sleep 5

    # 健康检查测试
    log_info "测试健康检查端点..."
    curl -s http://localhost:8888/health | jq . || curl -s http://localhost:8888/health

    # 负载统计测试
    log_info "测试负载统计端点..."
    curl -s http://localhost:8888/load-stats | jq . || curl -s http://localhost:8888/load-stats

    # 模型列表测试
    log_info "测试模型列表端点..."
    curl -s http://localhost:8888/v1/models | jq . || curl -s http://localhost:8888/v1/models

    # 聊天补全测试
    log_info "测试聊天补全端点..."
    curl -s -X POST http://localhost:8888/v1/chat/completions \
        -H "Content-Type: application/json" \
        -d '{
            "model": "llama3.1:8b",
            "messages": [{"role": "user", "content": "Hello!"}],
            "max_tokens": 50
        }' | jq . || curl -s -X POST http://localhost:8888/v1/chat/completions \
        -H "Content-Type: application/json" \
        -d '{
            "model": "llama3.1:8b",
            "messages": [{"role": "user", "content": "Hello!"}],
            "max_tokens": 50
        }'

    log_info "基本测试完成"
}

# 性能测试
run_performance_test() {
    log_info "运行性能测试..."

    # 安装 wrk（如果可用）
    if command -v wrk &> /dev/null; then
        log_info "使用 wrk 进行压力测试..."
        wrk -t4 -c100 -d30s http://localhost:8888/health
    else
        log_warn "wrk 未安装，使用 curl 进行简单测试..."

        # 简单的并发测试
        log_info "发送 100 个并发请求..."
        start_time=$(date +%s)

        for i in {1..100}; do
            curl -s http://localhost:8888/health > /dev/null &
            if [ $((i % 10)) -eq 0 ]; then
                log_info "已发送 $i 个请求"
            fi
        done

        wait

        end_time=$(date +%s)
        duration=$((end_time - start_time))
        log_info "完成 100 个请求，耗时 ${duration} 秒"
        log_info "平均 QPS: $(echo "scale=2; 100 / $duration" | bc)"
    fi
}

# 监控测试
monitor_system() {
    log_info "监控系统状态..."

    # 监控 60 秒
    for i in {1..60}; do
        echo "=== 监控第 $i/60 秒 ==="

        # 获取健康状态
        health=$(curl -s http://localhost:8888/health 2>/dev/null || echo '{"status":"error"}')
        echo "健康状态: $(echo $health | jq -r '.status' 2>/dev/null || echo 'unknown')"

        # 获取负载统计
        load_stats=$(curl -s http://localhost:8888/load-stats 2>/dev/null || echo '{"summary":{"overall_utilization_percent":0}}')
        echo "总体利用率: $(echo $load_stats | jq -r '.summary.overall_utilization_percent' 2>/dev/null || echo 'unknown')%"

        # 显示服务器状态
        echo "服务器状态:"
        echo $load_stats | jq -r '.servers[] | "  \(.url): \(.current_load)/\(.max_capacity) (\(.utilization_percent|round)%)"' 2>/dev/null || echo "  无法获取服务器状态"

        echo ""
        sleep 1
    done
}

# 停止服务
stop_services() {
    log_info "停止所有服务..."

    # 停止 Docker Compose 服务
    if [ -f docker/docker-compose.yml ]; then
        cd docker
        docker-compose down
        cd ..
    fi

    # 停止生产容器
    docker stop vllm-router-prod 2>/dev/null || true
    docker rm vllm-router-prod 2>/dev/null || true

    log_info "所有服务已停止"
}

# 清理环境
cleanup() {
    log_info "清理环境..."

    # 停止服务
    stop_services

    # 删除镜像
    docker rmi vllm-router:latest 2>/dev/null || true

    # 删除配置文件
    rm -f dev-servers.toml prod-servers.toml
    rm -rf docker production

    # 删除日志
    rm -rf logs

    log_info "环境清理完成"
}

# 显示帮助
show_help() {
    echo "vLLM Router 部署脚本"
    echo ""
    echo "用法: $0 [命令]"
    echo ""
    echo "可用命令:"
    echo "  dev         - 部署开发环境"
    echo "  prod        - 部署生产环境"
    echo "  test        - 运行测试"
    echo "  performance - 运行性能测试"
    echo "  monitor     - 监控系统状态"
    echo "  stop        - 停止所有服务"
    echo "  cleanup     - 清理环境"
    echo "  help        - 显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 dev              # 部署开发环境"
    echo "  $0 test             # 运行测试"
    echo "  $0 stop             # 停止服务"
    echo "  $0 cleanup          # 清理环境"
}

# 主函数
main() {
    case "${1:-}" in
        "dev")
            deploy_dev
            ;;
        "prod")
            deploy_prod
            ;;
        "test")
            run_tests
            ;;
        "performance")
            run_performance_test
            ;;
        "monitor")
            monitor_system
            ;;
        "stop")
            stop_services
            ;;
        "cleanup")
            cleanup
            ;;
        "help"|"-h"|"--help")
            show_help
            ;;
        "")
            log_error "请指定命令"
            show_help
            exit 1
            ;;
        *)
            log_error "未知命令: $1"
            show_help
            exit 1
            ;;
    esac
}

# 运行主函数
main "$@"