#!/usr/bin/env python3
"""
vLLM Router 使用示例集

这个文件包含了各种场景下使用 vLLM Router 的实际示例，
包括基本的 API 调用、错误处理、性能测试等。
"""

import asyncio
import aiohttp
import json
import time
import random
from typing import List, Dict, Any, Optional

class VLLMRouterClient:
    """vLLM Router 客户端封装类"""

    def __init__(self, base_url: str = "http://localhost:8888"):
        self.base_url = base_url.rstrip('/')
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=300)
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def health_check(self) -> Dict[str, Any]:
        """检查路由器健康状态"""
        async with self.session.get(f"{self.base_url}/health") as response:
            return await response.json()

    async def get_load_stats(self) -> Dict[str, Any]:
        """获取负载统计信息"""
        async with self.session.get(f"{self.base_url}/load-stats") as response:
            return await response.json()

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = "llama3.1:8b",
        temperature: float = 0.7,
        max_tokens: int = 500,
        stream: bool = False
    ) -> Dict[str, Any]:
        """聊天补全"""
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream
        }

        async with self.session.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload
        ) as response:
            return await response.json()

    async def text_completion(
        self,
        prompt: str,
        model: str = "llama3.1:8b",
        temperature: float = 0.7,
        max_tokens: int = 500
    ) -> Dict[str, Any]:
        """文本补全"""
        payload = {
            "model": model,
            "prompt": prompt,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        async with self.session.post(
            f"{self.base_url}/v1/completions",
            json=payload
        ) as response:
            return await response.json()

    async def embeddings(
        self,
        input_text: str,
        model: str = "llama3.1:8b"
    ) -> Dict[str, Any]:
        """获取文本嵌入向量"""
        payload = {
            "model": model,
            "input": input_text
        }

        async with self.session.post(
            f"{self.base_url}/v1/embeddings",
            json=payload
        ) as response:
            return await response.json()

    async def list_models(self) -> Dict[str, Any]:
        """列出可用模型"""
        async with self.session.get(f"{self.base_url}/v1/models") as response:
            return await response.json()


async def example_1_basic_usage():
    """示例 1: 基本使用方法"""
    print("=== 示例 1: 基本使用方法 ===")

    async with VLLMRouterClient() as client:
        # 检查健康状态
        health = await client.health_check()
        print(f"路由器状态: {health['status']}")
        print(f"健康服务器数: {health['healthy_servers']}/{health['total_servers']}")

        # 获取负载统计
        stats = await client.get_load_stats()
        print(f"总利用率: {stats['summary']['overall_utilization_percent']:.1f}%")

        # 简单聊天
        messages = [
            {"role": "system", "content": "你是一个有用的助手。"},
            {"role": "user", "content": "用一句话介绍人工智能。"}
        ]

        response = await client.chat_completion(messages)
        print(f"AI 回复: {response['choices'][0]['message']['content']}")


async def example_2_concurrent_requests():
    """示例 2: 并发请求测试"""
    print("\n=== 示例 2: 并发请求测试 ===")

    async with VLLMRouterClient() as client:
        # 准备多个请求
        questions = [
            "什么是机器学习？",
            "解释深度学习的基本概念",
            "神经网络是如何工作的？",
            "什么是自然语言处理？",
            "计算机视觉的应用有哪些？"
        ]

        # 并发发送请求
        tasks = []
        for question in questions:
            messages = [
                {"role": "user", "content": question}
            ]
            tasks.append(client.chat_completion(messages, max_tokens=100))

        # 等待所有请求完成
        start_time = time.time()
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        end_time = time.time()

        # 分析结果
        success_count = sum(1 for r in responses if not isinstance(r, Exception))
        total_time = end_time - start_time

        print(f"完成请求数: {success_count}/{len(questions)}")
        print(f"总耗时: {total_time:.2f}秒")
        print(f"平均每请求: {total_time/len(questions):.2f}秒")

        # 显示部分结果
        for i, (question, response) in enumerate(zip(questions, responses)):
            if not isinstance(response, Exception):
                answer = response['choices'][0]['message']['content']
                print(f"{i+1}. Q: {question}")
                print(f"   A: {answer[:50]}...")
                print()


async def example_3_error_handling():
    """示例 3: 错误处理和重试"""
    print("\n=== 示例 3: 错误处理和重试 ===")

    async with VLLMRouterClient() as client:
        # 测试不同的错误情况
        test_cases = [
            {
                "name": "正常请求",
                "messages": [{"role": "user", "content": "你好"}]
            },
            {
                "name": "空消息",
                "messages": []
            },
            {
                "name": "超长消息",
                "messages": [{"role": "user", "content": "A" * 10000}]
            },
            {
                "name": "无效模型",
                "messages": [{"role": "user", "content": "测试"}],
                "model": "invalid-model"
            }
        ]

        for case in test_cases:
            try:
                response = await client.chat_completion(
                    messages=case["messages"],
                    model=case.get("model", "llama3.1:8b"),
                    max_tokens=50
                )
                print(f"✅ {case['name']}: 成功")

            except Exception as e:
                print(f"❌ {case['name']}: {str(e)}")


async def example_4_performance_benchmark():
    """示例 4: 性能基准测试"""
    print("\n=== 示例 4: 性能基准测试 ===")

    async with VLLMRouterClient() as client:
        # 测试参数
        concurrent_levels = [1, 5, 10, 20, 50]
        requests_per_level = 20

        results = []

        for concurrent in concurrent_levels:
            print(f"测试并发级别: {concurrent}")

            # 准备请求
            tasks = []
            for i in range(requests_per_level):
                messages = [
                    {"role": "user", "content": f"生成一个随机数字: {random.randint(1, 1000)}"}
                ]
                tasks.append(client.chat_completion(messages, max_tokens=20))

            # 执行并发请求
            start_time = time.time()
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            end_time = time.time()

            # 统计结果
            success_count = sum(1 for r in responses if not isinstance(r, Exception))
            total_time = end_time - start_time
            qps = success_count / total_time if total_time > 0 else 0

            result = {
                "concurrent": concurrent,
                "total_requests": requests_per_level,
                "success_count": success_count,
                "total_time": total_time,
                "qps": qps,
                "success_rate": success_count / requests_per_level * 100
            }
            results.append(result)

            print(f"  成功率: {result['success_rate']:.1f}%")
            print(f"  QPS: {result['qps']:.2f}")
            print(f"  总耗时: {total_time:.2f}秒")
            print()

        # 显示最佳性能
        best_result = max(results, key=lambda x: x['qps'])
        print(f"🏆 最佳性能: 并发 {best_result['concurrent']} 时达到 {best_result['qps']:.2f} QPS")


async def example_5_load_balancing_test():
    """示例 5: 负载均衡测试"""
    print("\n=== 示例 5: 负载均衡测试 ===")

    async with VLLMRouterClient() as client:
        # 获取初始负载状态
        initial_stats = await client.get_load_stats()
        print("初始负载状态:")
        for server in initial_stats['servers']:
            print(f"  {server['url']}: {server['current_load']}/{server['max_capacity']} ({server['utilization_percent']:.1f}%)")

        # 发送一系列请求观察负载变化
        print("\n发送 50 个请求...")
        for i in range(50):
            messages = [
                {"role": "user", "content": f"测试消息 {i+1}: 这是负载均衡测试"}
            ]
            try:
                await client.chat_completion(messages, max_tokens=10)
                if (i + 1) % 10 == 0:
                    print(f"已完成 {i+1} 个请求")
            except Exception as e:
                print(f"请求 {i+1} 失败: {e}")

        # 等待负载更新
        await asyncio.sleep(5)

        # 获取最终负载状态
        final_stats = await client.get_load_stats()
        print("\n最终负载状态:")
        for server in final_stats['servers']:
            print(f"  {server['url']}: {server['current_load']}/{server['max_capacity']} ({server['utilization_percent']:.1f}%)")


async def example_6_embeddings_and_similarity():
    """示例 6: 嵌入向量和相似度计算"""
    print("\n=== 示例 6: 嵌入向量和相似度计算 ===")

    async with VLLMRouterClient() as client:
        # 测试文本
        texts = [
            "人工智能是计算机科学的一个分支",
            "机器学习是人工智能的子领域",
            "深度学习使用神经网络",
            "今天天气很好",
            "我喜欢编程"
        ]

        # 获取嵌入向量
        embeddings = []
        for text in texts:
            try:
                response = await client.embeddings(text)
                embedding = response['data'][0]['embedding']
                embeddings.append(embedding)
                print(f"✅ 获取嵌入向量: {text[:30]}...")
            except Exception as e:
                print(f"❌ 获取嵌入向量失败: {e}")
                embeddings.append(None)

        # 计算相似度（简单示例）
        print("\n文本相似度矩阵:")
        print("   " + " ".join(f"{i:2d}" for i in range(len(texts))))

        for i in range(len(texts)):
            if embeddings[i] is None:
                continue
            row = []
            for j in range(len(texts)):
                if embeddings[j] is None:
                    row.append(" N/A")
                    continue

                # 计算余弦相似度
                import numpy as np
                vec1 = np.array(embeddings[i])
                vec2 = np.array(embeddings[j])

                similarity = np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
                row.append(f"{similarity:3.2f}")

            print(f"{i:2d} " + " ".join(row))


async def example_7_streaming_chat():
    """示例 7: 流式聊天"""
    print("\n=== 示例 7: 流式聊天 ===")

    # 注意：这个示例需要修改客户端以支持流式响应
    print("流式聊天功能需要额外的客户端支持，这里演示基本概念。")

    async with VLLMRouterClient() as client:
        messages = [
            {"role": "user", "content": "请写一个关于技术的小故事"}
        ]

        try:
            response = await client.chat_completion(
                messages,
                max_tokens=200,
                stream=False  # 当前客户端不支持真正的流式
            )

            content = response['choices'][0]['message']['content']
            print(f"完整回复: {content}")

            # 模拟流式输出
            print("\n模拟流式输出:")
            words = content.split()
            for i, word in enumerate(words):
                if i > 0 and i % 5 == 0:
                    print()
                print(word + " ", end="", flush=True)
                await asyncio.sleep(0.1)  # 模拟打字效果
            print()

        except Exception as e:
            print(f"流式聊天失败: {e}")


async def example_8_model_comparison():
    """示例 8: 模型比较"""
    print("\n=== 示例 8: 模型比较 ===")

    async with VLLMRouterClient() as client:
        # 获取可用模型
        try:
            models_response = await client.list_models()
            available_models = [model['id'] for model in models_response['data']]
            print(f"可用模型: {available_models}")
        except Exception as e:
            print(f"获取模型列表失败: {e}")
            # 使用默认模型
            available_models = ["llama3.1:8b"]

        # 测试问题
        test_question = "什么是量子计算？请用简单的语言解释。"

        # 使用不同模型回答
        for model in available_models[:2]:  # 只测试前两个模型
            print(f"\n使用模型: {model}")
            print("-" * 50)

            try:
                start_time = time.time()
                response = await client.chat_completion(
                    [{"role": "user", "content": test_question}],
                    model=model,
                    max_tokens=150
                )
                end_time = time.time()

                answer = response['choices'][0]['message']['content']
                tokens_used = response['usage']['total_tokens']

                print(f"回复: {answer}")
                print(f"耗时: {end_time - start_time:.2f}秒")
                print(f"使用 tokens: {tokens_used}")

            except Exception as e:
                print(f"模型 {model} 测试失败: {e}")


async def main():
    """运行所有示例"""
    print("vLLM Router 使用示例集")
    print("=" * 50)

    examples = [
        example_1_basic_usage,
        example_2_concurrent_requests,
        example_3_error_handling,
        example_4_performance_benchmark,
        example_5_load_balancing_test,
        example_6_embeddings_and_similarity,
        example_7_streaming_chat,
        example_8_model_comparison
    ]

    for example in examples:
        try:
            await example()
        except Exception as e:
            print(f"示例运行失败: {e}")
            print("请确保 vLLM Router 正在运行，并且有健康的后端服务器。")

        # 示例之间添加间隔
        await asyncio.sleep(1)

    print("\n" + "=" * 50)
    print("所有示例运行完成！")


if __name__ == "__main__":
    # 运行示例
    asyncio.run(main())