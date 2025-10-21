# vLLM Router

智能负载均衡器，用于分布式 vLLM 服务器集群

## 解决什么问题？

当你有多个 GPU 服务器运行 vLLM 时，会面临：

- **资源分散**：多个独立的 GPU 无法统一管理
- **负载不均**：有的服务器过载，有的空闲
- **可用性差**：单个服务器故障影响整体服务

vLLM Router 提供统一的入口，智能分配请求到最佳服务器。

## 核心优势

### 🎯 智能负载均衡
- **实时监控**：直接获取 vLLM 的 `/metrics` 指标
- **智能算法**：`(running + waiting * 0.5) / capacity`
- **优先级选择**：优先选择负载 < 50% 的服务器
- **零队列**：直接转发，无中间队列

### 🔄 高可用性
- **自动故障转移**：检测并剔除不健康的服务器
- **智能重试**：请求失败时自动重试其他服务器
- **热重载**：配置修改无需重启服务

### 🌐 OpenAI 兼容
- **无缝集成**：完全兼容 OpenAI API
- **通用客户端**：支持任何 OpenAI 兼容的客户端

## 快速开始

### 安装

```bash
git clone https://github.com/xerrors/mvllm.git
pip install -e .

mvllm run
```

### 配置

创建服务器配置文件：

```bash
cp servers.example.toml servers.toml
```

编辑 `servers.toml`：

```toml
[servers]
servers = [
    { url = "http://gpu-server-1:8081", max_concurrent_requests = 3 },
    { url = "http://gpu-server-2:8088", max_concurrent_requests = 5 },
    { url = "http://gpu-server-3:8089", max_concurrent_requests = 4 },
]

[config]
health_check_interval = 10
request_timeout = 120
max_retries = 3
```

### 运行

```bash
# 生产模式（全屏监控）
mvllm run

# 开发模式（控制台日志）
mvllm run --console

# 自定义端口
mvllm run --port 8888
```

## 使用示例

### 聊天完成

```bash
curl -X POST http://localhost:8888/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3.1:8b",
    "messages": [
      {"role": "user", "content": "你好，请介绍一下自己"}
    ]
  }'
```

### 查看负载状态

```bash
curl http://localhost:8888/health
curl http://localhost:8888/load-stats
```

## API 端点

- `POST /v1/chat/completions` - 聊天完成
- `POST /v1/completions` - 文本完成
- `GET /v1/models` - 模型列表
- `GET /health` - 健康状态
- `GET /load-stats` - 负载统计

## 部署

### Docker

```bash
docker build -t mvllm .
docker run -d -p 8888:8888 -v $(pwd)/servers.toml:/app/servers.toml mvllm
```

### Docker Compose

```yaml
version: '3.8'
services:
  mvllm:
    build: .
    ports:
      - "8888:8888"
    volumes:
      - ./servers.toml:/app/servers.toml
```

## 配置说明

### 服务器配置
- `url`: vLLM 服务器地址
- `max_concurrent_requests`: 最大并发请求数

### 全局配置
- `health_check_interval`: 健康检查间隔（秒）
- `request_timeout`: 请求超时时间（秒）
- `max_retries`: 最大重试次数

## 监控

- **实时负载监控**：显示每个服务器的运行和等待请求数
- **健康状态**：实时监控服务器可用性
- **资源利用率**：GPU 缓存使用率等指标

## English Version

For English documentation, see [README.md](README.md)

## 许可证

MIT License