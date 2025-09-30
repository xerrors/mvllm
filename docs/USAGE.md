# vLLM Router Usage Guide

## Command Line Interface

### Basic Usage

```bash
# Start server without console output (logs only to files)
mvllm run

# Start server with console logging
mvllm run --console

# Start with custom host and port
mvllm run --host 0.0.0.0 --port 9999 --console

# Development mode with auto-reload
mvllm run --reload --console

# Custom configuration file
mvllm run --config production-servers.toml --console
```

### Management Commands

```bash
# Check configuration syntax
mvllm check-config

# Check custom configuration
mvllm check-config --config custom.toml

# Show version
mvllm version

# Show help
mvllm --help
mvllm run --help
```

### Log Management

The router provides comprehensive logging:

- **Console Output**: Only shown when `--console` flag is used
- **File Logging**: Always enabled
  - `logs/mvllm.log` - General application logs
  - `logs/mvllm-error.log` - Error logs only
  - `logs/mvllm-structured.log` - Structured logs for analytics

### Log Levels

```bash
# Set log level (DEBUG, INFO, WARNING, ERROR)
mvllm run --log-level DEBUG --console
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_TO_CONSOLE` | Enable console logging | `false` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `CONFIG_PATH` | Configuration file path | `servers.toml` |

### Server Configuration Example

```toml
[servers]
servers = [
    { url = "http://172.19.13.5:8081", max_concurrent_requests = 3 },
    { url = "http://172.19.13.6:8088", max_concurrent_requests = 5 },
]

[config]
health_check_interval = 10
config_reload_interval = 30
request_timeout = 120
max_retries = 3
```

## Real-time Load Monitoring

The router monitors server load in real-time via the `/metrics` endpoint on each server. It parses vLLM's native Prometheus metrics to extract the actual number of running requests.

### Load Statistics API

```bash
curl http://localhost:8888/load-stats
```

Example response:
```json
{
  "servers": [
    {
      "url": "http://172.19.13.5:8081",
      "current_load": 1,
      "max_capacity": 3,
      "available_capacity": 2,
      "utilization_percent": 33.3,
      "status": true,
      "last_updated": "2024-01-15T10:30:00"
    }
  ],
  "summary": {
    "total_servers": 2,
    "healthy_servers": 2,
    "total_active_load": 3,
    "total_capacity": 8,
    "overall_utilization_percent": 37.5
  }
}
```

### Console Display

When running with `--console`, you'll see a real-time status panel:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                     vLLM Router - 实时负载监控                               │
│               健康度: 2/2 | 全部健康 | 总利用率: 37.5%                   │
├──────────────────────────────────────────────────────────────────────────────┤
│ 时间    │ 服务器    │ 负载 │ 容量 │ 利用率 │ 状态                          │
├──────────────────────────────────────────────────────────────────────────────┤
│ 10:30:05 │ 172.19.13.5 │ 1   │ 3    │ 33.3% │ ✅                           │
│ 10:30:05 │ 172.19.13.6 │ 2   │ 5    │ 40.0% │ ✅                           │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Status Indicators

- ✅ **Healthy**: Server is healthy and has low utilization
- 🟡 **Warning**: Server is healthy but has high utilization (70%+)
- 🔴 **Critical**: Server is healthy but has very high utilization (90%+)
- ❌ **Unhealthy**: Server is marked as unhealthy (shown with strikethrough)

## Load Balancing Strategy

The router uses a smart load balancing algorithm:

1. **Health Check**: Only considers healthy servers
2. **Load Analysis**: Gets real-time load from each server's `/metrics` endpoint
3. **Metrics Parsing**: Extracts `vllm:num_requests_running` from Prometheus metrics
4. **Utilization Calculation**: Considers both current load and capacity
5. **Optimal Selection**: Chooses server with best load-to-capacity ratio

### Server Selection Criteria

- Primary: Current server load (lower is better)
- Secondary: Server utilization percentage (lower is better)
- Fallback: Random selection among equally loaded servers

## Docker Usage

### Basic Docker Run

```bash
# Build image
docker build -t mvllm .

# Run without console logs
docker run -p 8888:8888 -v $(pwd)/servers.toml:/app/servers.toml mvllm

# Run with console logs (for debugging)
docker run -p 8888:8888 -v $(pwd)/servers.toml:/app/servers.toml mvllm run --console
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
    environment:
      - LOG_TO_CONSOLE=true
      - LOG_LEVEL=INFO
```

## Development

### Setup Development Environment

```bash
# Clone and install dependencies
git clone <repository>
cd mvllm
pip install -e .

# Run in development mode
mvllm run --reload --console
```

### Testing

```bash
# Check configuration
mvllm check-config

# Test with different log levels
mvllm run --log-level DEBUG --console

# Test with custom config
mvllm run --config test-servers.toml --console
```

## Troubleshooting

### Common Issues

1. **No console output**: Use `--console` flag to enable logging
2. **Server not starting**: Check configuration with `mvllm check-config`
3. **High load**: Monitor with `/load-stats` endpoint
4. **Connection issues**: Check server health with `/health` endpoint

### Debug Mode

```bash
# Enable debug logging
mvllm run --log-level DEBUG --console

# Check detailed server status
curl http://localhost:8888/health
```

### Log Files

- `logs/mvllm.log` - Main application logs
- `logs/mvllm-error.log` - Error logs only
- `logs/mvllm-structured.log` - Machine-readable logs