"""
Mock vLLM Server for testing the router
Simulates multiple vLLM servers with realistic response patterns

Usage:
    python mock_server.py                    # Start all mock servers
    python mock_server.py --port 8801       # Start single server on specific port
    python mock_server.py --list            # List available servers
"""

import asyncio
import json
import time
import random
import uuid
import sys
import signal
import argparse
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from loguru import logger
import os

# Mock server configurations
MOCK_SERVERS = [
    {
        "name": "MockServer-1",
        "port": 8801,
        "model": "llama3.1:8b",
        "max_tokens": 2048,
        "response_delay": 5,  # seconds
        "failure_rate": 0.05,  # 5% chance of failure
        "slow_response_rate": 0.1,  # 10% chance of slow response
    },
    {
        "name": "MockServer-2",
        "port": 8802,
        "model": "llama3.1:8b",
        "max_tokens": 1024,
        "response_delay": 3,
        "failure_rate": 0.02,
        "slow_response_rate": 0.05,
    },
    {
        "name": "MockServer-3",
        "port": 8803,
        "model": "llama3.1:8b",
        "max_tokens": 512,
        "response_delay": 8,
        "failure_rate": 0.08,
        "slow_response_rate": 0.15,
    },
]

# Global request counter for each server
request_counters = {}


def create_mock_server(server_config: Dict[str, Any]) -> FastAPI:
    """Create a mock vLLM server instance"""

    # Initialize request counter for this server
    request_counters[server_config["port"]] = 0

    app = FastAPI(
        title=f"Mock vLLM Server - {server_config['name']}",
        description=f"Mock server simulating {server_config['model']}",
        version="0.1.0",
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    async def root():
        """Root endpoint"""
        return {
            "service": f"Mock vLLM Server - {server_config['name']}",
            "model": server_config["model"],
            "port": server_config["port"],
            "status": "running",
            "requests_processed": request_counters[server_config["port"]],
        }

    @app.get("/health")
    async def health_check():
        """Health check endpoint"""
        return {"status": "healthy"}

    @app.get("/v1/models")
    async def models():
        """OpenAI-compatible models endpoint"""
        # Simulate some processing delay
        await simulate_delay(server_config)

        # Check for random failures
        if random.random() < server_config["failure_rate"]:
            raise HTTPException(status_code=500, detail="Simulated server error")

        return {
            "object": "list",
            "data": [
                {
                    "id": server_config["model"],
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "mock-server",
                }
            ],
        }

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        """OpenAI-compatible chat completions endpoint"""
        global request_counters
        request_counters[server_config["port"]] += 1

        # Simulate processing delay
        delay = server_config["response_delay"]
        if random.random() < server_config["slow_response_rate"]:
            delay *= 3  # Make it 3x slower
        await simulate_delay(server_config, delay)

        # Check for random failures
        if random.random() < server_config["failure_rate"]:
            raise HTTPException(status_code=500, detail="Simulated server error")

        # Parse request body
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")

        messages = body.get("messages", [])
        stream = body.get("stream", False)

        if not messages:
            raise HTTPException(status_code=400, detail="No messages provided")

        # Generate mock response
        response_content = generate_mock_response(messages[-1]["content"])

        response_data = {
            "id": f"chatcmpl-{uuid.uuid4().hex}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": server_config["model"],
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": response_content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": len(messages[-1]["content"].split()),
                "completion_tokens": len(response_content.split()),
                "total_tokens": len(messages[-1]["content"].split())
                + len(response_content.split()),
            },
        }

        if stream:
            # Streaming response
            async def stream_generator():
                # Send initial chunk
                chunk_data = {
                    "id": response_data["id"],
                    "object": "chat.completion.chunk",
                    "created": response_data["created"],
                    "model": response_data["model"],
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"role": "assistant", "content": ""},
                            "finish_reason": None,
                        }
                    ],
                }
                yield f"data: {json.dumps(chunk_data)}\n\n"

                # Send content chunks
                words = response_content.split()
                for i, word in enumerate(words):
                    chunk_data["choices"][0]["delta"] = {"content": word + " "}
                    chunk_data["choices"][0]["finish_reason"] = None
                    yield f"data: {json.dumps(chunk_data)}\n\n"
                    await asyncio.sleep(0.1)  # Small delay between chunks

                # Send final chunk
                chunk_data["choices"][0]["delta"] = {}
                chunk_data["choices"][0]["finish_reason"] = "stop"
                chunk_data["object"] = "chat.completion.chunk"
                yield f"data: {json.dumps(chunk_data)}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(
                stream_generator(),
                media_type="text/plain",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
            )
        else:
            # Regular response
            return JSONResponse(content=response_data)

    @app.post("/v1/completions")
    async def completions(request: Request):
        """OpenAI-compatible completions endpoint"""
        global request_counters
        request_counters[server_config["port"]] += 1

        # Simulate processing delay
        await simulate_delay(server_config)

        # Check for random failures
        if random.random() < server_config["failure_rate"]:
            raise HTTPException(status_code=500, detail="Simulated server error")

        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")

        prompt = body.get("prompt", "")
        stream = body.get("stream", False)

        if not prompt:
            raise HTTPException(status_code=400, detail="No prompt provided")

        # Generate mock response
        response_content = generate_mock_response(prompt)

        response_data = {
            "id": f"cmpl-{uuid.uuid4().hex}",
            "object": "text_completion",
            "created": int(time.time()),
            "model": server_config["model"],
            "choices": [
                {"index": 0, "text": response_content, "finish_reason": "stop"}
            ],
            "usage": {
                "prompt_tokens": len(prompt.split()),
                "completion_tokens": len(response_content.split()),
                "total_tokens": len(prompt.split()) + len(response_content.split()),
            },
        }

        if stream:
            # Streaming response
            async def stream_generator():
                chunk_data = {
                    "id": response_data["id"],
                    "object": "text_completion",
                    "created": response_data["created"],
                    "model": response_data["model"],
                    "choices": [{"index": 0, "text": "", "finish_reason": None}],
                }
                yield f"data: {json.dumps(chunk_data)}\n\n"

                # Send content chunks
                words = response_content.split()
                for i, word in enumerate(words):
                    chunk_data["choices"][0]["text"] += word + " "
                    yield f"data: {json.dumps(chunk_data)}\n\n"
                    await asyncio.sleep(0.1)

                # Send final chunk
                chunk_data["choices"][0]["finish_reason"] = "stop"
                yield f"data: {json.dumps(chunk_data)}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(
                stream_generator(),
                media_type="text/plain",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
            )
        else:
            return JSONResponse(content=response_data)

    @app.post("/v1/embeddings")
    async def embeddings(request: Request):
        """OpenAI-compatible embeddings endpoint"""
        global request_counters
        request_counters[server_config["port"]] += 1

        # Simulate processing delay
        await simulate_delay(server_config)

        # Check for random failures
        if random.random() < server_config["failure_rate"]:
            raise HTTPException(status_code=500, detail="Simulated server error")

        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")

        input_text = body.get("input", "")
        if isinstance(input_text, list):
            input_text = input_text[0] if input_text else ""
        elif isinstance(input_text, str):
            pass  # Already a string
        else:
            input_text = str(input_text)

        if not input_text:
            raise HTTPException(status_code=400, detail="No input provided")

        # Generate mock embeddings (768 dimensions for simplicity)
        embedding_vector = [random.random() for _ in range(768)]

        response_data = {
            "object": "list",
            "data": [
                {"object": "embedding", "index": 0, "embedding": embedding_vector}
            ],
            "model": server_config["model"],
            "usage": {
                "prompt_tokens": len(input_text.split()),
                "total_tokens": len(input_text.split()),
            },
        }

        return JSONResponse(content=response_data)

    return app


async def simulate_delay(
    server_config: Dict[str, Any], custom_delay: Optional[float] = None
):
    """Simulate server processing delay"""
    delay = (
        custom_delay if custom_delay is not None else server_config["response_delay"]
    )
    await asyncio.sleep(delay)


def generate_mock_response(prompt: str) -> str:
    """Generate a mock response based on the prompt"""
    responses = [
        "这是对您查询的模拟响应。我是基于大型语言模型构建的AI助手。",
        "这是一个测试响应，用于模拟vLLM服务器的行为。您的输入已经收到。",
        "感谢您的查询！我正在模拟一个真实的语言模型响应。",
        "这是一个mock服务器的示例响应，旨在测试路由器的功能。",
        "您好！这是vLLM mock服务器的响应。我可以处理各种类型的请求。",
    ]

    # Simple keyword-based response selection
    if "你好" in prompt or "hello" in prompt.lower():
        return "您好！很高兴为您服务。请问有什么可以帮助您的吗？"
    elif "测试" in prompt or "test" in prompt.lower():
        return "这是一个测试响应。Mock服务器正在正常工作。"
    elif "模型" in prompt or "model" in prompt.lower():
        return "我使用的模型是现代化的语言模型，具有良好的理解和生成能力。"
    else:
        return random.choice(responses) + f" 您的问题是：'{prompt[:50]}...'"


async def start_mock_server(server_config: Dict[str, Any]):
    """Start a single mock server"""
    app = create_mock_server(server_config)

    logger.info(f"Starting {server_config['name']} on port {server_config['port']}")

    config = uvicorn.Config(
        app=app, host="0.0.0.0", port=server_config["port"], log_level="info"
    )

    server = uvicorn.Server(config)
    await server.serve()


async def main():
    """Main function to start all mock servers"""
    logger.info("Starting Mock vLLM Servers...")

    # Create tasks for all servers
    tasks = []
    for server_config in MOCK_SERVERS:
        task = asyncio.create_task(start_mock_server(server_config))
        tasks.append(task)

    # Wait for all servers to start
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.info("Shutting down mock servers...")
    except Exception as e:
        logger.error(f"Error running mock servers: {e}")


def setup_logging():
    """Setup logging for mock servers"""
    logger.remove()
    logger.add(
        os.sys.stdout,
        format="<green>{time:MM-DD HH:mm:ss}</green> | <cyan>{name}</cyan>:<cyan>{function}:{line}</cyan> - <level>{message}</level>",
        level="INFO",
        colorize=True,
    )


def signal_handler(signum, frame):
    """Handle signals for graceful shutdown"""
    print("\n正在关闭Mock服务器...")
    sys.exit(0)


def list_servers():
    """List all available mock servers"""
    print("可用的Mock服务器配置:")
    for i, server in enumerate(MOCK_SERVERS, 1):
        print(f"  {i}. {server['name']}:")
        print(f"     端口: {server['port']}")
        print(f"     模型: {server['model']}")
        print(f"     最大Token: {server['max_tokens']}")
        print(f"     响应延迟: {server['response_delay']}秒")
        print(f"     失败率: {server['failure_rate'] * 100}%")
        print()


def start_single_server(port: int):
    """Start a single mock server on the specified port"""
    # Find server config for the specified port
    server_config = None
    for config in MOCK_SERVERS:
        if config["port"] == port:
            server_config = config
            break

    if not server_config:
        print(f"错误: 未找到端口 {port} 的服务器配置")
        print("使用 --list 查看可用的服务器")
        sys.exit(1)

    # Setup signal handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print(f"启动单个Mock服务器: {server_config['name']} (端口: {port})")
    print(f"模型: {server_config['model']}")
    print("按 Ctrl+C 停止服务器\n")

    # Start the server
    setup_logging()
    asyncio.run(start_mock_server(server_config))


def start_all_servers():
    """Start all mock servers"""
    # Setup signal handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("启动所有Mock vLLM服务器...")
    print("服务器配置:")
    for server in MOCK_SERVERS:
        print(
            f"- {server['name']}: http://localhost:{server['port']} ({server['model']})"
        )
    print("\n按 Ctrl+C 停止所有服务器\n")

    # Setup logging and start servers
    setup_logging()
    asyncio.run(main())


def main_cli():
    """Main command-line interface"""
    parser = argparse.ArgumentParser(
        description="启动Mock vLLM服务器用于测试路由器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python mock_server.py              # 启动所有服务器
  python mock_server.py --port 8801  # 启动单个服务器
  python mock_server.py --list       # 列出所有服务器
        """,
    )

    parser.add_argument(
        "--port",
        type=int,
        choices=[8801, 8802, 8803],
        help="启动单个服务器 (端口: 8801, 8802, 8803)",
    )

    parser.add_argument("--list", action="store_true", help="列出所有可用的服务器配置")

    args = parser.parse_args()

    if args.list:
        list_servers()
    elif args.port:
        start_single_server(args.port)
    else:
        start_all_servers()


if __name__ == "__main__":
    main_cli()
