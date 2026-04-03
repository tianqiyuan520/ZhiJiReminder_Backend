import requests
import json
import time

BASE_URL = "http://localhost:8003"  # 更新为端口8003
USER_ID = "test"

def test_final_fix():
    """测试最终的修复：编辑任务时图片更新和缓存破坏"""
    print("=== 测试编辑任务时图片更新和缓存破坏 ===")
    
    # 1. 创建一个带图片的任务
    print("1. 创建带图片的任务...")
    create_url = f"{BASE_URL}/api/reminder"
    test_image_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    image_data_url = f"data:image/png;base64,{test_image_base64}"
    
    create_data = {
        "user_id": USER_ID,
        "homework": {
            "course": "测试课程",
            "content": "测试作业内容",
            "deadline": "2026-12-31 23:59",
            "difficulty": "中"
        },
        "image": image_data_url
    }
    
    try:
        response = requests.post(create_url, json=create_data)
        if response.status_code != 200:
            print(f"创建任务失败: {response.status_code} - {response.text}")
            return
        
        create_result = response.json()
        reminder_id = create_result.get("reminder_id")
        print(f"创建任务成功，ID: {reminder_id}")
        
        # 2. 获取任务详情，检查图片URL
        print("\n2. 获取任务详情，检查图片URL...")
        get_url = f"{BASE_URL}/api/reminders?user_id={USER_ID}"
        
        response = requests.get(get_url)
        if response.status_code != 200:
            print(f"获取任务失败: {response.status_code} - {response.text}")
            return
        
        tasks = response.json().get("data", [])
        task = next((t for t in tasks if t["id"] == reminder_id), None)
        
        if task:
            image_url = task.get('image_url')
            print(f"初始图片URL: {image_url}")
            
            # 检查是否包含时间戳参数
            if image_url and '?t=' in image_url:
                print("✅ 初始图片URL包含时间戳参数（缓存破坏生效）")
            else:
                print("❌ 初始图片URL不包含时间戳参数")
        
        # 3. 编辑任务，更新图片
        print("\n3. 编辑任务，更新图片...")
        # 使用不同的测试图片
        test_image_base64_2 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        image_data_url_2 = f"data:image/jpeg;base64,{test_image_base64_2}"
        
        edit_data = {
            "user_id": USER_ID,
            "homework": {
                "course": "更新后的课程",
                "content": "更新后的内容",
                "deadline": "2026-12-31 23:59",
                "difficulty": "难"
            },
            "reminder_id": reminder_id,
            "image": image_data_url_2
        }
        
        response = requests.post(create_url, json=edit_data)
        if response.status_code != 200:
            print(f"编辑任务失败: {response.status_code} - {response.text}")
            return
        
        print("编辑任务成功")
        
        # 4. 再次获取任务详情，检查图片URL是否更新
        print("\n4. 检查编辑后的图片URL...")
        response = requests.get(get_url)
        if response.status_code != 200:
            print(f"获取任务失败: {response.status_code} - {response.text}")
            return
        
        tasks = response.json().get("data", [])
        task = next((t for t in tasks if t["id"] == reminder_id), None)
        
        if task:
            new_image_url = task.get('image_url')
            print(f"编辑后图片URL: {new_image_url}")
            
            # 检查是否包含时间戳参数
            if new_image_url and '?t=' in new_image_url:
                print("✅ 编辑后图片URL包含时间戳参数")
                
                # 检查时间戳是否不同（如果URL不同）
                if new_image_url != image_url:
                    print("✅ 图片URL已更新（时间戳改变）")
                else:
                    print("⚠️  图片URL没有改变")
            else:
                print("❌ 编辑后图片URL不包含时间戳参数")
            
            # 5. 测试图片访问
            print("\n5. 测试图片访问...")
            if new_image_url:
                try:
                    image_response = requests.get(new_image_url)
                    if image_response.status_code == 200:
                        print(f"✅ 图片访问成功，大小: {len(image_response.content)} bytes")
                        print(f"   内容类型: {image_response.headers.get('content-type')}")
                    else:
                        print(f"❌ 图片访问失败: {image_response.status_code}")
                except Exception as e:
                    print(f"❌ 图片访问异常: {e}")
        
        # 6. 模拟前端行为：多次获取任务，检查时间戳是否更新
        print("\n6. 模拟前端多次获取任务...")
        time.sleep(2)  # 等待2秒
        
        response = requests.get(get_url)
        if response.status_code == 200:
            tasks = response.json().get("data", [])
            task = next((t for t in tasks if t["id"] == reminder_id), None)
            
            if task:
                final_image_url = task.get('image_url')
                print(f"2秒后图片URL: {final_image_url}")
                
                # 检查时间戳是否更新
                if final_image_url and '?t=' in final_image_url:
                    # 提取时间戳
                    import urllib.parse
                    parsed_url = urllib.parse.urlparse(final_image_url)
                    query_params = urllib.parse.parse_qs(parsed_url.query)
                    final_timestamp = query_params.get('t', [None])[0]
                    
                    if new_image_url and '?t=' in new_image_url:
                        parsed_new_url = urllib.parse.urlparse(new_image_url)
                        query_new_params = urllib.parse.parse_qs(parsed_new_url.query)
                        new_timestamp = query_new_params.get('t', [None])[0]
                        
                        if final_timestamp != new_timestamp:
                            print("✅ 时间戳已更新（缓存破坏有效）")
                        else:
                            print("⚠️  时间戳没有更新")
        
        # 7. 清理测试任务
        print("\n7. 清理测试任务...")
        delete_url = f"{BASE_URL}/api/reminders/{reminder_id}"
        response = requests.delete(delete_url)
        if response.status_code == 200:
            print("测试任务已删除")
        else:
            print(f"删除任务失败: {response.status_code}")
            
        print("\n=== 测试完成 ===")
        print("总结：")
        print("1. 编辑任务时，新图片应该被保存")
        print("2. 图片URL应该包含时间戳参数防止缓存")
        print("3. 每次获取任务时，时间戳应该更新")
        print("4. 前端应该看到最新的图片")
            
    except Exception as e:
        print(f"测试过程中出现异常: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_final_fix()
