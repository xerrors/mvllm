#!/usr/bin/env python3
"""
持续发送completions请求测试脚本
每隔1秒发送一次背诵静夜思的请求，连续20次后间隔10秒，然后继续
"""

import asyncio
import random
import httpx
import time
from loguru import logger

# 配置
BASE_URL = "http://localhost:8888/v1"
MODEL = "llama3.1:8b"
BATCH_SIZE = 30
SHORT_INTERVAL = 1  # 1秒
LONG_INTERVAL = 10.0  # 10秒

# 静夜诗内容
POEM_CONTENT = f"{random.randint(1, 1000000)}请背诵一下《{random.choice(['出师表', '静夜思', '将进酒', '登高'])}》前{random.randint(1, 100)}句"


async def send_completion_request(
    client: httpx.AsyncClient, request_num: int, batch_num: int
) -> bool:
    """发送单个completion请求"""
    try:
        payload = {
            "model": MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": f"[第{batch_num}批-第{request_num}次] {POEM_CONTENT}",
                }
            ],
            "max_tokens": 500,
            "temperature": 0.7,
            "stream": False,
        }

        start_time = time.time()
        response = await client.post(
            f"{BASE_URL}/chat/completions",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30.0,
        )
        end_time = time.time()

        if response.status_code == 200:
            # result = response.json()
            logger.info(
                f"✅ 请求成功 [第{batch_num}批-第{request_num}次] 耗时: {end_time - start_time:.2f}s"
            )
            return True
        else:
            logger.error(
                f"❌ 请求失败 [第{batch_num}批-第{request_num}次] HTTP {response.status_code}: {response.text}"
            )
            return False

    except Exception as e:
        logger.error(f"❌ 请求异常 [第{batch_num}批-第{request_num}次]: {e}")
        return False


async def run_batch(client: httpx.AsyncClient, batch_num: int):
    """运行一个批次的请求 - 每1秒异步发送一个请求"""
    logger.info(f"🚀 开始第 {batch_num} 批请求，共 {BATCH_SIZE} 次")

    tasks = []
    for i in range(1, BATCH_SIZE + 1):
        # 创建异步任务，不等待完成
        task = asyncio.create_task(send_completion_request(client, i, batch_num))
        tasks.append(task)

        # 等待1秒再发送下一个请求
        await asyncio.sleep(SHORT_INTERVAL)

    # 等待所有任务完成
    results = await asyncio.gather(*tasks, return_exceptions=True)

    success_count = sum(1 for result in results if result is True)
    logger.info(f"📊 第 {batch_num} 批完成: 成功 {success_count}/{BATCH_SIZE}")
    return success_count


async def main():
    """主函数"""
    logger.info("🌙 开始静夜思连续请求测试...")
    logger.info(
        f"配置: 模型={MODEL}, 批次大小={BATCH_SIZE}, 短间隔={SHORT_INTERVAL}s, 长间隔={LONG_INTERVAL}s"
    )

    batch_num = 1
    total_success = 0
    total_requests = 0

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                # 运行一个批次
                batch_success = await run_batch(client, batch_num)
                total_success += batch_success
                total_requests += BATCH_SIZE

                # 显示统计信息
                success_rate = (
                    (total_success / total_requests) * 100 if total_requests > 0 else 0
                )
                logger.info(
                    f"📈 总体统计: 成功 {total_success}/{total_requests} ({success_rate:.1f}%)"
                )

                # 等待10秒（除了第一次）
                if batch_num > 0:
                    logger.info(f"⏰ 等待 {LONG_INTERVAL} 秒后开始下一批...")
                    await asyncio.sleep(LONG_INTERVAL)

                batch_num += 1

    except KeyboardInterrupt:
        logger.info("⏹️ 测试被用户中断")
        logger.info(
            f"📊 最终统计: 成功 {total_success}/{total_requests} ({success_rate:.1f}%)"
        )
    except Exception as e:
        logger.error(f"💥 测试过程中发生错误: {e}")
        logger.info(
            f"📊 最终统计: 成功 {total_success}/{total_requests} ({success_rate:.1f}%)"
        )


if __name__ == "__main__":
    # 配置日志
    logger.add(
        "poem_test.log",
        rotation="10 MB",
        retention="1 day",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    )

    # 运行测试
    asyncio.run(main())
