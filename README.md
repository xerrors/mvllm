# vLLM Router

Intelligent load balancer for distributed vLLM server clusters

## What problem does it solve?

When you have multiple GPU servers running vLLM, you face:

- **Fragmented Resources**: Multiple independent GPUs cannot be managed unifiedly
- **Unbalanced Load**: Some servers are overloaded while others are idle
- **Poor Availability**: Single server failure affects overall service

vLLM Router provides a unified entry point that intelligently distributes requests to the best servers.

<img width="1406" height="254" alt="image" src="https://github.com/user-attachments/assets/b4b476e8-3f03-4ed4-9cdb-2818c7ca0ec1" />


## Key Advantages

### 🎯 Intelligent Load Balancing
- **Real-time Monitoring**: Direct metrics from vLLM `/metrics` endpoints
- **Smart Algorithm**: `(running + waiting * 0.5) / capacity`
- **Priority Selection**: Prefers servers with load < 50%
- **Zero Queue**: Direct forwarding without intermediate queues

### 🔄 High Availability
- **Automatic Failover**: Detects and removes unhealthy servers
- **Smart Retry**: Automatically retries failed requests on other servers
- **Hot Reload**: Configuration changes without service restart

## Quick Start

### Installation

```bash
git clone https://github.com/xerrors/mvllm.git
pip install -e .

mvllm run
```

### Configuration

Create server configuration file:

```bash
cp servers.example.toml servers.toml
```

Edit `servers.toml`:

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

### Running

```bash
# Production mode (fullscreen monitoring)
mvllm run

# Development mode (console logging)
mvllm run --console

# Custom port
mvllm run --port 8888
```

## Usage Examples

### Chat Completions

```bash
curl -X POST http://localhost:8888/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3.1:8b",
    "messages": [
      {"role": "user", "content": "Hello, please introduce yourself"}
    ]
  }'
```

### Check Load Status

```bash
curl http://localhost:8888/health
curl http://localhost:8888/load-stats
```

## API Endpoints

- `POST /v1/chat/completions` - Chat completions
- `POST /v1/completions` - Text completions
- `GET /v1/models` - Model listing
- `GET /health` - Health status
- `GET /load-stats` - Load statistics

## Deployment

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

## Configuration

### Server Configuration
- `url`: vLLM server address
- `max_concurrent_requests`: Maximum concurrent requests

### Global Configuration
- `health_check_interval`: Health check interval (seconds)
- `request_timeout`: Request timeout (seconds)
- `max_retries`: Maximum retry attempts

## Monitoring

- **Real-time Load Monitoring**: Shows running and waiting requests per server
- **Health Status**: Real-time server availability monitoring
- **Resource Utilization**: GPU cache usage and other metrics

## Chinese Version

For Chinese documentation, see [README.zh.md](README.zh.md)

## License

MIT License
