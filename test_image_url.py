#!/usr/bin/env python3
"""
测试图片URL生成逻辑
"""

import os
import sys

# 模拟不同的环境变量设置
test_cases = [
    {
        "name": "本地开发环境（默认）",
        "env_vars": {
            "RENDER": "false",
            "FRONTEND_BASE_URL": ""
        },
        "expected_base_url": "http://localhost:8002"
    },
    {
        "name": "生产环境（通过RENDER变量）",
        "env_vars": {
            "RENDER": "true",
            "FRONTEND_BASE_URL": ""
        },
        "expected_base_url": "https://zhijireminderbackend.onrender.com"
    },
    {
        "name": "自定义FRONTEND_BASE_URL",
        "env_vars": {
            "RENDER": "false",
            "FRONTEND_BASE_URL": "https://custom.example.com"
        },
        "expected_base_url": "https://custom.example.com"
    },
    {
        "name": "生产环境但使用自定义URL",
        "env_vars": {
            "RENDER": "true",
            "FRONTEND_BASE_URL": "https://myproduction.com"
        },
        "expected_base_url": "https://myproduction.com"
    }
]

def test_image_url_generation():
    """测试图片URL生成逻辑"""
    print("=== 测试图片URL生成逻辑 ===\n")
    
    all_passed = True
    
    for test_case in test_cases:
        print(f"测试: {test_case['name']}")
        print(f"  环境变量: {test_case['env_vars']}")
        
        # 设置环境变量
        for key, value in test_case['env_vars'].items():
            os.environ[key] = value
        
        # 模拟upload_image_only函数中的逻辑
        base_url = os.getenv("FRONTEND_BASE_URL", "")
        
        if not base_url:
            # 如果没有设置FRONTEND_BASE_URL，根据RENDER环境变量判断
            render_env = os.getenv("RENDER", "false").lower() == "true"
            if render_env:
                base_url = "https://zhijireminderbackend.onrender.com"
            else:
                base_url = "http://localhost:8002"
        
        # 生成图片URL
        image_filename = "test-uuid.jpg"
        image_url = f"{base_url.rstrip('/')}/images/{image_filename}"
        
        expected_url = f"{test_case['expected_base_url'].rstrip('/')}/images/{image_filename}"
        
        print(f"  生成的base_url: {base_url}")
        print(f"  生成的图片URL: {image_url}")
        print(f"  期望的图片URL: {expected_url}")
        
        if image_url == expected_url:
            print("  结果: ✓ 通过\n")
        else:
            print("  结果: ✗ 失败\n")
            all_passed = False
        
        # 清理环境变量
        for key in test_case['env_vars'].keys():
            if key in os.environ:
                del os.environ[key]
    
    # 测试实际环境变量
    print("=== 测试当前实际环境 ===\n")
    
    actual_render = os.getenv("RENDER", "未设置")
    actual_frontend_base_url = os.getenv("FRONTEND_BASE_URL", "未设置")
    
    print(f"当前RENDER环境变量: {actual_render}")
    print(f"当前FRONTEND_BASE_URL环境变量: {actual_frontend_base_url}")
    
    # 根据当前环境生成URL
    base_url = os.getenv("FRONTEND_BASE_URL", "")
    
    if not base_url:
        render_env = os.getenv("RENDER", "false").lower() == "true"
        if render_env:
            base_url = "https://zhijireminderbackend.onrender.com"
        else:
            base_url = "http://localhost:8002"
    
    print(f"\n当前环境将使用的base_url: {base_url}")
    print(f"图片URL示例: {base_url.rstrip('/')}/images/test-uuid.jpg")
    
    if all_passed:
        print("\n=== 所有测试通过 ===")
    else:
        print("\n=== 部分测试失败 ===")
        sys.exit(1)

if __name__ == "__main__":
    test_image_url_generation()
