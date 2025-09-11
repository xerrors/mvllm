#!/usr/bin/env python3
"""
使用OpenAI客户端测试vLLM Router的示例脚本
"""

import openai
import json

# 配置OpenAI客户端连接到vLLM Router
client = openai.OpenAI(
    api_key="not-needed",  # vLLM不需要真实的API key
    base_url="http://localhost:8888/v1",
    timeout=30.0
)

def test_chat_completion():
    """测试chat completion功能"""
    print("🤖 测试Chat Completion...")
    
    try:
        response = client.chat.completions.create(
            model="llama3.1:8b",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "请用中文介绍一下vLLM Router的功能"}
            ],
            max_tokens=200,
            temperature=0.7,
            stream=False
        )
        
        print("✅ Chat Completion成功！")
        print(f"模型: {response.model}")
        print(f"回复: {response.choices[0].message.content}")
        print(f"使用token: {response.usage.total_tokens}")
        print("-" * 50)
        
    except Exception as e:
        print(f"❌ Chat Completion失败: {e}")

def test_list_models():
    """测试列出模型"""
    print("📋 测试列出模型...")
    
    try:
        models = client.models.list()
        print("✅ 获取模型列表成功！")
        for model in models.data:
            print(f"  - {model.id} (最大长度: {model.max_model_len})")
        print("-" * 50)
        
    except Exception as e:
        print(f"❌ 获取模型列表失败: {e}")

def test_multiple_requests():
    """测试多次请求以验证负载均衡"""
    print("🔄 测试负载均衡（多次请求）...")
    
    for i in range(3):
        try:
            response = client.chat.completions.create(
                model="llama3.1:8b",
                messages=[{"role": "user", "content": f"负载均衡测试 {i+1}"}],
                max_tokens=50,
                temperature=0.7
            )
            print(f"✅ 请求 {i+1} 成功: {response.choices[0].message.content[:30]}...")
            
        except Exception as e:
            print(f"❌ 请求 {i+1} 失败: {e}")
    
    print("-" * 50)

def main():
    """主函数"""
    print("🚀 vLLM Router OpenAI客户端测试")
    print("=" * 50)
    
    # 测试各种功能
    test_list_models()
    test_chat_completion()
    test_multiple_requests()
    
    print("🎉 测试完成！")

if __name__ == "__main__":
    main()