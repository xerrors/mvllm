# vLLM Router

A FastAPI-based load balancer for vLLM servers with OpenAI-compatible API.

## Features

- **Real-time Load Monitoring**: Direct server load retrieval via `/metrics` endpoint
- **Smart Load Balancing**: Dynamic server selection based on actual load
- **Health Checks**: Automatic server health monitoring and failover
- **Configuration Hot Reload**: Live configuration updates without restart
- **OpenAI Compatible**: Full compatibility with OpenAI API format
- **Monitoring**: Built-in load and health statistics endpoints
- **High Performance**: Direct request forwarding without queue bottlenecks

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/xerrors/vllm-router.git
cd vllm-router

# Install dependencies
uv sync
```

### Configuration

1. Copy the example configuration:
```bash
cp servers.example.toml servers.toml
```

2. Edit `servers.toml` to configure your vLLM servers:
```toml
[servers]
servers = [
    { url = "http://172.19.13.5:8081", max_concurrent_requests = 3 },
    { url = "http://172.19.13.6:8088", max_concurrent_requests = 3 },
]

[config]
health_check_interval = 30
config_reload_interval = 60
request_timeout = 150
health_check_timeout = 5
max_retries = 3
```

### Running the Server

#### Option 1: CLI (Recommended)
```bash
# Basic run - no console output
vllm-router run

# With console logging
vllm-router run --console

# Custom host and port
vllm-router run --host 0.0.0.0 --port 8888 --console

# With auto-reload for development
vllm-router run --reload --console

# Custom config file
vllm-router run --config custom-servers.toml --console
```

#### Option 2: Direct Execution
```bash
uv run python3 run.py
```

#### Option 3: Docker
```bash
# Build the image
docker build -t vllm-router .

# Run with Docker
docker run -p 8888:8888 -v $(pwd)/servers.toml:/app/servers.toml vllm-router
```

#### Option 4: Docker Compose
```bash
docker-compose up -d
```

The server will start on `http://localhost:8888` by default.

## API Endpoints

### OpenAI Compatible Endpoints

- `POST /v1/chat/completions` - Chat completions
- `POST /v1/completions` - Text completions
- `GET /v1/models` - List available models
- `POST /v1/embeddings` - Create embeddings

### Management Endpoints

- `GET /` - Service information
- `GET /health` - Health status and server statistics
- `GET /load-stats` - Real-time load statistics and server utilization

### CLI Commands

```bash
# Show help
vllm-router --help

# Run server with options
vllm-router run --help

# Check configuration
vllm-router check-config

# Show version
vllm-router version
```

#### CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--console`, `-c` | Enable console logging output | `false` |
| `--host`, `-h` | Host to bind to | `0.0.0.0` |
| `--port`, `-p` | Port to bind to | `8888` |
| `--config` | Path to configuration file | `servers.toml` |
| `--reload` | Enable auto-reload for development | `false` |
| `--log-level` | Logging level | `INFO` |

## Usage Examples

### Chat Completions

```bash
curl -X POST http://localhost:8888/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3.1:8b",
    "messages": [
      {"role": "user", "content": "Hello, how are you?"}
    ]
  }'
```

### Health Check

```bash
curl http://localhost:8888/health
```

## Testing

```bash
# Run basic tests
uv run python3 test.py

# Run OpenAI client test
uv run python3 openai_test.py

# Test health endpoint
curl http://localhost:8888/health

# Test API endpoints
curl -X POST http://localhost:8888/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "llama3.1:8b", "messages": [{"role": "user", "content": "Hello!"}]}'
```

## Monitoring and Logging

### Health Check
```bash
curl http://localhost:8888/health
```

### Logs
- Application logs are printed to console
- Health check logs show server status
- Request logs show forwarded requests

### Metrics
The health endpoint provides:
- Total number of servers
- Number of healthy servers
- Individual server status
- Last check time for each server

## Production Deployment

### Environment Variables
```bash
# Configuration file path
export CONFIG_PATH=/path/to/servers.toml

# Log level
export LOG_LEVEL=INFO

# Server port
export PORT=8888

# Host binding
export HOST=0.0.0.0
```

### Docker Deployment
```bash
# Build and run with custom configuration
docker build -t vllm-router .
docker run -d \
  --name vllm-router \
  -p 8888:8888 \
  -v /path/to/servers.toml:/app/servers.toml \
  -e LOG_LEVEL=INFO \
  vllm-router
```

### Kubernetes Deployment
See `k8s/` directory for Kubernetes deployment examples.

## Performance Tuning

### Load Balancing
- Adjust server weights based on capacity
- Monitor server health and response times
- Use appropriate timeouts for your use case

### Configuration Optimization
- Increase `health_check_interval` for less frequent checks
- Adjust `request_timeout` based on model complexity
- Tune `max_retries` for reliability vs performance

### Scaling
- Add more vLLM servers for increased throughput
- Use multiple router instances for high availability
- Consider geographic distribution for global applications

## Troubleshooting

### Common Issues

**Server not starting**
- Check port availability (default: 8888)
- Verify configuration file syntax
- Check vLLM server connectivity

**High latency**
- Review network connectivity between router and vLLM servers
- Check vLLM server resource usage
- Adjust timeout values

**Servers marked unhealthy**
- Verify vLLM servers are running and accessible
- Check vLLM server health endpoints
- Review firewall settings

### Debug Mode
```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
uv run python3 run.py
```

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

This project is open source and available under the [MIT License](LICENSE).

## Support

- 📖 [Documentation](README.md)
- 🐛 [Issue Tracker](https://github.com/your-username/vllm-router/issues)
- 💬 [Discussions](https://github.com/your-username/vllm-router/discussions)