# vLLM Router 部署指南

## 🚀 快速部署

### 基础环境准备

#### 系统要求
- **操作系统**: Linux (Ubuntu 20.04+), macOS 10.15+, Windows 10+
- **Python**: 3.8+
- **内存**: 最少 512MB RAM
- **磁盘**: 最少 1GB 可用空间
- **网络**: 能访问 vLLM 服务器的网络环境

#### 安装依赖

```bash
# 克隆项目
git clone https://github.com/xerrors/vllm-router.git
cd vllm-router

# 使用 uv 安装依赖 (推荐)
uv sync

# 或使用 pip 安装
pip install -r requirements.txt
```

## 📋 配置文件示例

### 基础配置 (servers.toml)

```toml
[servers]
servers = [
    # 开发环境配置
    { url = "http://localhost:8081", max_concurrent_requests = 2 },
    { url = "http://localhost:8082", max_concurrent_requests = 2 },
]

[config]
# 健康检查配置
health_check_interval = 10
health_check_timeout = 5
health_check_min_success_rate = 0.8
health_check_max_response_time = 3.0

# 配置管理
config_reload_interval = 30
enable_active_health_check = true

# 请求处理
request_timeout = 120
max_retries = 3
retry_delay = 0.1
```

### 生产环境配置

```toml
[servers]
servers = [
    # 高性能 GPU 服务器
    { url = "http://gpu-server-1:8081", max_concurrent_requests = 8 },
    { url = "http://gpu-server-2:8081", max_concurrent_requests = 8 },

    # 中等性能 GPU 服务器
    { url = "http://gpu-server-3:8081", max_concurrent_requests = 4 },
    { url = "http://gpu-server-4:8081", max_concurrent_requests = 4 },

    # 备用服务器 (较低优先级)
    { url = "http://backup-server-1:8081", max_concurrent_requests = 2 },
]

[config]
# 生产环境健康检查 (更严格)
health_check_interval = 5
health_check_timeout = 3
health_check_min_success_rate = 0.95
health_check_max_response_time = 2.0
health_check_consecutive_failures = 2

# 配置管理
config_reload_interval = 60
enable_active_health_check = true
failure_threshold = 2
auto_recovery_threshold = 120

# 请求处理 (生产环境优化)
request_timeout = 180
max_retries = 5
retry_delay = 0.5
```

## 🐳 Docker 部署

### 1. 构建 Docker 镜像

```bash
# 克隆项目
git clone https://github.com/xerrors/vllm-router.git
cd vllm-router

# 构建 Docker 镜像
docker build -t vllm-router:latest .

# 或指定版本
docker build -t vllm-router:v1.0.0 .
```

### 2. 运行容器

#### 开发环境
```bash
# 创建配置文件
cat > servers.toml << EOF
[servers]
servers = [
    { url = "http://host.docker.internal:8081", max_concurrent_requests = 3 },
    { url = "http://host.docker.internal:8082", max_concurrent_requests = 3 },
]

[config]
health_check_interval = 10
request_timeout = 60
max_retries = 3
EOF

# 运行容器 (开发模式，带控制台日志)
docker run -d \
  --name vllm-router-dev \
  -p 8888:8888 \
  -v $(pwd)/servers.toml:/app/servers.toml \
  -e LOG_TO_CONSOLE=true \
  -e LOG_LEVEL=DEBUG \
  vllm-router:latest \
  run --console
```

#### 生产环境
```bash
# 运行容器 (生产模式，无控制台日志)
docker run -d \
  --name vllm-router-prod \
  -p 8888:8888 \
  -v $(pwd)/production-servers.toml:/app/servers.toml \
  -e LOG_TO_CONSOLE=false \
  -e LOG_LEVEL=INFO \
  --restart unless-stopped \
  --memory=512m \
  --cpus=1.0 \
  vllm-router:latest
```

### 3. Docker Compose 部署

#### docker-compose.yml (基础版)
```yaml
version: '3.8'

services:
  vllm-router:
    build: .
    container_name: vllm-router
    ports:
      - "8888:8888"
    volumes:
      - ./servers.toml:/app/servers.toml
      - ./logs:/app/logs
    environment:
      - LOG_TO_CONSOLE=false
      - LOG_LEVEL=INFO
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8888/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

#### docker-compose.yml (完整版)
```yaml
version: '3.8'

services:
  vllm-router:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: vllm-router-prod
    ports:
      - "8888:8888"
    volumes:
      - ./production-servers.toml:/app/servers.toml
      - ./logs:/app/logs
      - /etc/localtime:/etc/localtime:ro
    environment:
      - LOG_TO_CONSOLE=false
      - LOG_LEVEL=INFO
      - CONFIG_PATH=/app/servers.toml
      - HOST=0.0.0.0
      - PORT=8888
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '1.0'
        reservations:
          memory: 512M
          cpus: '0.5'
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8888/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    networks:
      - vllm-network

  # 可选: Prometheus 监控
  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/etc/prometheus/console_libraries'
      - '--web.console.templates=/etc/prometheus/consoles'
      - '--storage.tsdb.retention.time=200h'
      - '--web.enable-lifecycle'
    restart: unless-stopped
    networks:
      - vllm-network

  # 可选: Grafana 可视化
  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana_data:/var/lib/grafana
      - ./monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards
      - ./monitoring/grafana/datasources:/etc/grafana/provisioning/datasources
    restart: unless-stopped
    networks:
      - vllm-network

volumes:
  prometheus_data:
  grafana_data:

networks:
  vllm-network:
    driver: bridge
```

## ☸️ Kubernetes 部署

### 1. 基础 Kubernetes 配置

#### ConfigMap
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: vllm-router-config
  namespace: vllm-system
data:
  servers.toml: |
    [servers]
    servers = [
      { url = "http://vllm-server-1.vllm-system.svc.cluster.local:8081", max_concurrent_requests = 8 },
      { url = "http://vllm-server-2.vllm-system.svc.cluster.local:8081", max_concurrent_requests = 8 },
      { url = "http://vllm-server-3.vllm-system.svc.cluster.local:8081", max_concurrent_requests = 4 },
    ]

    [config]
    health_check_interval = 10
    health_check_timeout = 5
    health_check_min_success_rate = 0.9
    health_check_max_response_time = 3.0

    config_reload_interval = 60
    enable_active_health_check = true

    request_timeout = 120
    max_retries = 3
```

#### Deployment
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vllm-router
  namespace: vllm-system
  labels:
    app: vllm-router
spec:
  replicas: 3  # 高可用部署
  selector:
    matchLabels:
      app: vllm-router
  template:
    metadata:
      labels:
        app: vllm-router
    spec:
      containers:
      - name: vllm-router
        image: vllm-router:latest
        imagePullPolicy: Always
        ports:
        - containerPort: 8888
          name: http
        env:
        - name: CONFIG_PATH
          value: "/etc/vllm-router/servers.toml"
        - name: LOG_TO_CONSOLE
          value: "false"
        - name: LOG_LEVEL
          value: "INFO"
        volumeMounts:
        - name: config
          mountPath: "/etc/vllm-router"
        - name: logs
          mountPath: "/app/logs"
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8888
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /health
            port: 8888
          initialDelaySeconds: 5
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 1
      volumes:
      - name: config
        configMap:
          name: vllm-router-config
      - name: logs
        emptyDir: {}
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              labelSelector:
                matchExpressions:
                - key: app
                  operator: In
                  values:
                  - vllm-router
              topologyKey: kubernetes.io/hostname
```

#### Service
```yaml
apiVersion: v1
kind: Service
metadata:
  name: vllm-router-service
  namespace: vllm-system
  labels:
    app: vllm-router
spec:
  selector:
    app: vllm-router
  ports:
  - name: http
    port: 8888
    targetPort: 8888
  type: ClusterIP
```

#### Ingress
```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: vllm-router-ingress
  namespace: vllm-system
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  tls:
  - hosts:
    - vllm-router.yourdomain.com
    secretName: vllm-router-tls
  rules:
  - host: vllm-router.yourdomain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: vllm-router-service
            port:
              number: 8888
```

### 2. Helm Chart 部署

#### 创建 Helm Chart
```bash
# 创建 Chart 结构
helm create vllm-router-chart
cd vllm-router-chart

# 编辑 values.yaml
cat > values.yaml << EOF
replicaCount: 3

image:
  repository: vllm-router
  tag: latest
  pullPolicy: Always

service:
  type: ClusterIP
  port: 8888

ingress:
  enabled: true
  hosts:
    - host: vllm-router.yourdomain.com
      paths: ["/"]
  tls: []

config:
  servers:
    - url: "http://vllm-server-1:8081"
      max_concurrent_requests: 8
    - url: "http://vllm-server-2:8081"
      max_concurrent_requests: 8

resources:
  limits:
    cpu: 500m
    memory: 512Mi
  requests:
    cpu: 250m
    memory: 256Mi

autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 10
  targetCPUUtilizationPercentage: 80
  targetMemoryUtilizationPercentage: 80
EOF

# 安装 Chart
helm install vllm-router ./vllm-router-chart -n vllm-system --create-namespace
```

## 🔄 生产环境最佳实践

### 1. 高可用配置

#### 多区域部署
```yaml
# 使用 Kubernetes 部署多区域实例
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vllm-router-us-east
  namespace: vllm-system
spec:
  replicas: 3
  template:
    spec:
      nodeSelector:
        topology.kubernetes.io/region: us-east
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vllm-router-us-west
  namespace: vllm-system
spec:
  replicas: 3
  template:
    spec:
      nodeSelector:
        topology.kubernetes.io/region: us-west
```

#### 负载均衡配置
```nginx
# Nginx 负载均衡配置
upstream vllm_router_backend {
    least_conn;
    server vllm-router-1:8888 weight=3;
    server vllm-router-2:8888 weight=3;
    server vllm-router-3:8888 weight=2;

    # 健康检查
    keepalive 32;
    keepalive_requests 1000;
    keepalive_timeout 60s;
}

server {
    listen 80;
    server_name vllm-router.yourdomain.com;

    location / {
        proxy_pass http://vllm_router_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 超时配置
        proxy_connect_timeout 5s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;

        # 健康检查
        proxy_next_upstream error timeout invalid_header http_500 http_502 http_503 http_504;
        proxy_next_upstream_tries 3;
    }
}
```

### 2. 监控和日志

#### Prometheus 配置
```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'vllm-router'
    static_configs:
      - targets: ['vllm-router:8888']
    metrics_path: '/metrics'
    scrape_interval: 10s
    scrape_timeout: 5s

  - job_name: 'vllm-servers'
    static_configs:
      - targets:
        - 'vllm-server-1:8081'
        - 'vllm-server-2:8081'
        - 'vllm-server-3:8081'
    metrics_path: '/metrics'
    scrape_interval: 15s
```

#### 日志配置
```bash
# 日志轮转配置
cat > logrotate.conf << EOF
/var/log/vllm-router/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 vllm-router vllm-router
    postrotate
        /usr/bin/docker exec vllm-router kill -USR1 $(cat /var/run/vllm-router.pid)
    endscript
}
EOF
```

### 3. 安全配置

#### 网络安全
```yaml
# NetworkPolicy 配置
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: vllm-router-network-policy
  namespace: vllm-system
spec:
  podSelector:
    matchLabels:
      app: vllm-router
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: ingress-nginx
    ports:
    - protocol: TCP
      port: 8888
  egress:
  - to: []
    ports:
    - protocol: TCP
      port: 8081  # vLLM 服务器端口
```

#### 环境变量安全
```bash
# 使用 Kubernetes Secrets
kubectl create secret generic vllm-router-secrets \
  --from-literal=api-key=your-api-key \
  --from-literal=database-url=your-database-url \
  -n vllm-system

# 在部署中引用
env:
  - name: API_KEY
    valueFrom:
      secretKeyRef:
        name: vllm-router-secrets
        key: api-key
```

## 🧪 测试和验证

### 1. 健康检查测试

```bash
# 测试健康检查端点
curl -f http://localhost:8888/health || echo "Health check failed"

# 测试负载统计
curl -s http://localhost:8888/load-stats | jq .

# 测试模型列表
curl -s http://localhost:8888/v1/models | jq .
```

### 2. 性能测试

```bash
# 使用 wrk 进行压力测试
wrk -t12 -c400 -d30s http://localhost:8888/health

# 使用 ab 进行基准测试
ab -n 1000 -c 50 http://localhost:8888/health

# 自定义测试脚本
cat > test_load_balancing.py << EOF
import asyncio
import aiohttp
import json

async def test_chat_completion():
    url = "http://localhost:8888/v1/chat/completions"
    payload = {
        "model": "llama3.1:8b",
        "messages": [{"role": "user", "content": "Hello!"}],
        "max_tokens": 50
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as response:
            return await response.json()

async def run_tests():
    tasks = [test_chat_completion() for _ in range(100)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    success_count = sum(1 for r in results if not isinstance(r, Exception))
    print(f"Success rate: {success_count}/{len(results)}")

asyncio.run(run_tests())
EOF
```

### 3. 故障转移测试

```bash
# 模拟服务器故障
docker stop vllm-server-1

# 观察路由器行为
curl -s http://localhost:8888/health | jq '.servers[] | select(.healthy == false)'

# 恢复服务器
docker start vllm-server-1

# 验证自动恢复
sleep 30
curl -s http://localhost:8888/health | jq '.servers[] | select(.url | contains("server-1"))'
```

## 📚 故障排除

### 常见问题

1. **连接超时**
   ```bash
   # 检查网络连接
   telnet vllm-server-1 8081

   # 检查防火墙设置
   sudo ufw status
   sudo iptables -L
   ```

2. **配置文件错误**
   ```bash
   # 验证配置文件
   vllm-router check-config --config servers.toml

   # 检查 TOML 语法
   python -c "import toml; toml.load('servers.toml')"
   ```

3. **内存不足**
   ```bash
   # 检查内存使用
   free -h

   # 监控 Docker 容器
   docker stats vllm-router

   # 调整内存限制
   docker update --memory 1g vllm-router
   ```

### 日志分析

```bash
# 查看实时日志
docker logs -f vllm-router

# 过滤错误日志
docker logs vllm-router 2>&1 | grep ERROR

# 分析结构化日志
cat logs/vllm-router-structured.log | jq '.time + " " + .level + " " + .message'
```

这个部署指南提供了从开发到生产的完整部署方案，包括 Docker、Kubernetes、监控配置、安全设置和故障排除等内容。