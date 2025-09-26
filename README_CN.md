# vLLM Router

<div align="center">

**🚀 企业级分布式 vLLM 服务器负载均衡器**

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Stars](https://img.shields.io/github/stars/xerrors/vllm-router?style=social)](https://github.com/xerrors/vllm-router)

**通过智能负载均衡解决分布式 vLLM 实例的 GPU 碎片化问题**

[快速开始](#快速开始) • [核心功能](#核心功能) • [架构设计](#架构设计) • [文档](#文档)

</div>

---

## 🎯 问题背景：LLM 部署中的 GPU 碎片化

现代大语言模型（如 Llama 3.1-8B）需要大量 GPU 资源，但组织通常面临以下挑战：

- **分散的 GPU 资源**：多台机器上的独立 GPU 无法整合使用
- **资源利用率低**：部分 GPU 过载而其他 GPU 空闲
- **管理复杂性**：需要手动协调多个 vLLM 实例
- **可用性挑战**：单个节点维护时服务中断

**vLLM Router 通过统一入口点智能分配请求到您的 vLLM 集群来解决这些挑战。**

---

## 🚀 核心功能

### 🔀 智能多端点负载均衡
- **实时指标**：直接集成 vLLM `/metrics` 端点
- **容量感知路由**：同时考虑当前负载和服务器容量
- **加权分配**：智能算法：`(运行中 * 3 + 等待中) / 容量`
- **零队列瓶颈**：直接请求转发，无中间队列

### 📊 高级监控与可视化
- **实时仪表板**：使用 Rich 控制台界面的实时负载监控
- **全屏模式**：控制台日志禁用时的专用监控视图
- **详细指标**：运行中请求、等待队列、GPU 缓存使用率、文件描述符
- **健康状态**：自动健康检查和故障转移检测

### ⚡ 高可用性与可靠性
- **自动故障转移**：即时检测和移除不健康服务器
- **断路器机制**：智能重试逻辑防止级联故障
- **优雅降级**：部分故障期间继续提供服务
- **可配置超时**：精细的超时和重试策略

### 🔧 配置管理
- **热重载**：服务不中断的配置更新
- **TOML 配置**：人类可读的配置文件
- **环境变量**：灵活的部署选项
- **动态扩展**：无需重启即可添加/移除服务器

### 🌐 OpenAI API 兼容性
- **无缝集成**：OpenAI API 端点的直接替代品
- **完整覆盖**：聊天补全、文本补全、嵌入、模型列表
- **客户端无关**：适用于任何 OpenAI 兼容的客户端库

---

## 🏗️ 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                    客户端应用程序                            │
├─────────────────────────────────────────────────────────────┤
│                   vLLM Router (负载均衡器)                    │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │   负载管理器    │  │  健康监控器     │  │ 配置管理器      │ │
│  │  - 实时指标     │  │  - 自动修复     │  │  - 热重载       │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                    vLLM 服务器集群                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │
│  │ vLLM 节点 1 │  │ vLLM 节点 2 │  │ vLLM 节点 N │           │
│  │ GPU: 1xRTX │  │ GPU: 2x4090 │  │ GPU: 1xA100 │           │
│  │ Llama-3.1-8B│  │ Llama-3.1-8B│  │ Mixtral-8x7B│           │
│  └─────────────┘  └─────────────┘  └─────────────┘           │
└─────────────────────────────────────────────────────────────┘
```

### 核心组件

1. **负载管理器**：实时负载监控和服务器选择
2. **健康监控器**：持续健康检查和自动故障转移
3. **配置管理器**：动态配置管理和验证
4. **请求路由器**：带重试逻辑的智能请求分配

---

## 🚀 快速开始

### 前置要求

- Python 3.8+
- 多台不同机器上运行的 vLLM 服务器
- 路由器和 vLLM 服务器之间的网络连通性

### 安装

```bash
# 克隆仓库
git clone https://github.com/xerrors/vllm-router.git
cd vllm-router

# 安装依赖
uv sync
```

### 配置

创建您的服务器配置：

```bash
cp servers.example.toml servers.toml
```

编辑 `servers.toml` 来定义您的 vLLM 集群：

```toml
[servers]
servers = [
    { url = "http://gpu-server-1:8081", max_concurrent_requests = 3 },
    { url = "http://gpu-server-2:8088", max_concurrent_requests = 5 },
    { url = "http://gpu-server-3:8089", max_concurrent_requests = 4 },
]

[config]
health_check_interval = 10
config_reload_interval = 30
request_timeout = 120
health_check_timeout = 5
max_retries = 3
```

### 运行路由器

#### 生产模式（全屏监控）
```bash
# 专用监控视图，无控制台日志
vllm-router run
```

#### 开发模式（控制台日志）
```bash
# 控制台输出与监控混合
vllm-router run --console
```

#### 高级选项
```bash
# 自定义主机和端口
vllm-router run --host 0.0.0.0 --port 8888

# 开发环境自动重载
vllm-router run --reload --console

# 自定义配置
vllm-router run --config production-servers.toml
```

---

## 📡 API 端点

### OpenAI 兼容端点

所有端点完全兼容 OpenAI API 规范：

```bash
# 聊天补全
POST /v1/chat/completions

# 文本补全
POST /v1/completions

# 模型列表
GET /v1/models

# 嵌入向量
POST /v1/embeddings
```

### 管理与监控端点

```bash
# 服务信息
GET /

# 健康状态和集群统计
GET /health

# 实时负载指标和利用率
GET /load-stats
```

---

## 💻 使用示例

### 聊天补全

```bash
curl -X POST http://localhost:8888/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3.1:8b",
    "messages": [
      {"role": "system", "content": "你是一个有用的助手。"},
      {"role": "user", "content": "用简单的术语解释量子计算。"}
    ],
    "temperature": 0.7,
    "max_tokens": 500
  }'
```

### 负载统计

```bash
curl -s http://localhost:8888/load-stats | jq '.'
```

**响应：**
```json
{
  "servers": [
    {
      "url": "http://gpu-server-1:8081",
      "current_load": 2,
      "max_capacity": 3,
      "available_capacity": 1,
      "utilization_percent": 66.7,
      "status": true,
      "detailed_metrics": {
        "num_requests_running": 2,
        "num_requests_waiting": 0,
        "gpu_cache_usage_perc": 78.5,
        "process_max_fds": 65535
      }
    }
  ],
  "summary": {
    "total_servers": 3,
    "healthy_servers": 3,
    "total_active_load": 5,
    "total_capacity": 12,
    "overall_utilization_percent": 41.7
  }
}
```

---

## 🐳 部署选项

### Docker 部署

```bash
# 构建镜像
docker build -t vllm-router .

# 生产模式运行，带监控
docker run -d \
  --name vllm-router \
  -p 8888:8888 \
  -v $(pwd)/servers.toml:/app/servers.toml \
  vllm-router

# 开发模式运行，带控制台
docker run -d \
  --name vllm-router \
  -p 8888:8888 \
  -v $(pwd)/servers.toml:/app/servers.toml \
  -e LOG_TO_CONSOLE=true \
  vllm-router run --console
```

### Docker Compose

```yaml
version: '3.8'
services:
  vllm-router:
    build: .
    ports:
      - "8888:8888"
    volumes:
      - ./servers.toml:/app/servers.toml
    environment:
      - LOG_LEVEL=INFO
    depends_on:
      - vllm-server-1
      - vllm-server-2

  vllm-server-1:
    image: vllm/vllm-openai:latest
    # ... vLLM 服务器配置 ...

  vllm-server-2:
    image: vllm/vllm-openai:latest
    # ... vLLM 服务器配置 ...
```

### Kubernetes 部署

请参阅 `k8s/` 目录获取完整的 Kubernetes 部署示例，包括：

- 便于部署的 Helm charts
- 水平 Pod 自动扩展配置
- 服务网格集成示例
- 多区域部署策略

---

## 🔧 配置

### 服务器配置

```toml
[servers]
servers = [
    # 每个服务器可以有不同的容量
    { url = "http://server1:8081", max_concurrent_requests = 3 },
    { url = "http://server2:8088", max_concurrent_requests = 8 },
    { url = "http://server3:8089", max_concurrent_requests = 5 },
]

[config]
# 健康检查设置
health_check_interval = 10          # 每 10 秒检查一次
health_check_timeout = 5             # 5 秒超时
health_check_min_success_rate = 0.8 # 需要 80% 成功率
health_check_max_response_time = 2.0 # 最大 2 秒响应时间

# 配置管理
config_reload_interval = 30          # 每 30 秒检查配置变更
enable_active_health_check = true    # 启用主动健康监控

# 请求处理
request_timeout = 120                # 2 分钟超时
max_retries = 3                     # 最多重试 3 次
retry_delay = 0.1                   # 重试间隔 100ms
```

### 环境变量

```bash
# 基本配置
CONFIG_PATH=/path/to/servers.toml    # 配置文件路径
LOG_LEVEL=INFO                       # 日志级别 (DEBUG, INFO, WARNING, ERROR)
LOG_TO_CONSOLE=false                 # 启用控制台日志
HOST=0.0.0.0                        # 绑定主机
PORT=8888                           # 绑定端口

# 高级设置
HEALTH_CHECK_INTERVAL=10             # 健康检查间隔（秒）
CONFIG_RELOAD_INTERVAL=30            # 配置重载间隔（秒）
REQUEST_TIMEOUT=120                  # 请求超时（秒）
```

---

## 📊 监控与可观测性

### 实时监控

路由器提供全面的监控功能：

**全屏模式**（当 `LOG_TO_CONSOLE=false` 时）：
- 专用监控界面
- 实时负载统计
- 服务器健康状态可视化
- 清晰专业的显示

**控制台模式**（当 `LOG_TO_CONSOLE=true` 时）：
- 混合控制台日志和监控
- 传统日志体验
- 开发友好的输出

### 指标收集

- **vLLM 集成**：直接从 `/metrics` 端点获取指标
- **请求跟踪**：成功率、延迟、错误分布
- **资源监控**：GPU 使用率、内存、文件描述符
- **健康状态**：服务器可用性、响应时间、成功率

### 日志记录

```bash
# 控制台输出（启用时）
LOG_TO_CONSOLE=true vllm-router run

# 文件日志（始终启用）
logs/vllm-router.log          # 一般应用日志
logs/vllm-router-error.log    # 仅错误日志
logs/vllm-router-structured.log # 机器可读日志
```

---

## ⚡ 性能调优

### 负载均衡优化

智能负载均衡算法考虑以下因素：

```python
# 分数计算：(running * 3 + waiting * 1) / capacity
# 分数越低 = 下一个请求的更好候选
```

**调优建议**：
- **高性能集群**：在强大节点上增加 `max_concurrent_requests`
- **混合环境**：为较旧/较弱的 GPU 设置较低容量
- **稳定性重点**：减少 `max_retries` 并增加 `health_check_interval`

### 配置优化

```toml
# 高吞吐量配置
[config]
health_check_interval = 5           # 频繁健康检查
request_timeout = 60                # 较低超时以更快故障转移
max_retries = 2                     # 较少重试以更快响应

# 高可靠性配置
[config]
health_check_interval = 15          # 较少频繁检查
request_timeout = 180               # 复杂模型的较高超时
max_retries = 5                     # 更多重试以提高可靠性
```

### 扩展策略

- **水平扩展**：添加更多 vLLM 服务器以提高吞吐量
- **垂直扩展**：增加现有服务器的 `max_concurrent_requests`
- **地理分布**：在更靠近用户区域的部署路由器
- **多层架构**：为不同模型类型/大小使用分离的路由器

---

## 🛠️ 开发

### 设置开发环境

```bash
# 克隆和安装
git clone https://github.com/xerrors/vllm-router.git
cd vllm-router
uv sync

# 安装开发依赖
uv add --dev pytest pytest-asyncio httpx black isort flake8

# 运行测试
uv run pytest

# 代码质量检查
black --check app/
isort --check-only app/
flake8 app/
```

### 运行测试

```bash
# 所有测试
uv run pytest

# 带覆盖率
uv run pytest --cov=app --cov-report=html

# 特定测试类别
uv run pytest tests/test_load_balancing.py
uv run pytest tests/test_health_monitoring.py
```

### 贡献

我们欢迎贡献！请参阅 [CONTRIBUTING.md](CONTRIBUTING.md) 获取指南。

---

## 🏛️ 生产最佳实践

### 高可用部署

1. **多个路由器实例**：在多个 vLLM Router 实例前使用负载均衡器
2. **健康监控**：实施带自动故障转移的外部健康检查
3. **数据库支持**：将配置和指标存储在数据库中以实现持久化
4. **告警**：为高错误率或服务器不可用设置告警

### 安全考虑

```bash
# 生产安全设置
export LOG_LEVEL=WARNING               # 减少日志详细程度
export REQUEST_TIMEOUT=60              # 较低超时以提高安全性
export HEALTH_CHECK_INTERVAL=5         # 频繁健康检查
# 启用 HTTPS（推荐）
# 配置防火墙规则
# 实施身份验证/授权
```

### 监控栈集成

- **Prometheus**：导出指标用于监控
- **Grafana**：为负载和性能可视化创建仪表板
- **AlertManager**：设置智能告警
- **ELK Stack**：集中式日志记录和分析

---

## 🤝 社区与支持

### 获取帮助

- 📖 **文档**：[README.md](README.md)、[USAGE.md](USAGE.md)
- 🐛 **错误报告**：[GitHub Issues](https://github.com/xerrors/vllm-router/issues)
- 💬 **讨论**：[GitHub Discussions](https://github.com/xerrors/vllm-router/discussions)
- 📧 **邮件支持**：创建 issue 并标记 "question" 标签

### 贡献

我们鼓励社区贡献！无论您是：

- 🐛 **报告错误**
- 💡 **建议功能**
- 📝 **改进文档**
- 👨‍💻 **提交拉取请求**

每个贡献都有助于让 vLLM Router 变得更好。

### 路线图

- [ ] **v1.1**：自定义负载均衡算法的插件系统
- [ ] **v1.2**：配置和监控的 Web UI
- [ ] **v1.3**：高级分析和报告
- [ ] **v1.4**：多协议支持（gRPC、WebSocket）
- [ ] **v2.0**：分布式路由器集群

---

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件。

### 第三方许可证

- **FastAPI**：MIT 许可证
- **Rich**：MIT 许可证
- **aiohttp**：Apache 2.0 许可证
- **Click**：BSD 许可证

---

## 🙏 致谢

- [vLLM](https://github.com/vllm-project/vllm) 提供出色的 LLM 推理引擎
- [FastAPI](https://fastapi.tiangolo.com/) 提供现代 Web 框架
- [Rich](https://github.com/Textualize/rich) 提供美观的终端应用程序
- 开源社区提供的灵感和反馈

---

<div align="center">

**⭐ 如果 vLLM Router 帮助您解决了 GPU 碎片化挑战，请给我们一个星标！**

[![GitHub Stars](https://img.shields.io/github/stars/xerrors/vllm-router?style=social)](https://github.com/xerrors/vllm-router)

</div>