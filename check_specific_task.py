import requests
import json

BASE_URL = "http://localhost:8002"
USER_ID = "test"
TASK_ID = "d81a2cd8-4110-4ef8-bc9f-14082521cb73"  # 从日志中看到的任务ID

def check_task_image():
    """检查特定任务的图片状态"""
    print(f"=== 检查任务 {TASK_ID} 的图片状态 ===")
    
    # 1. 获取任务详情
    print("1. 获取任务详情...")
    get_url = f"{BASE_URL}/api/reminders?user_id={USER_ID}"
    
    try:
        response = requests.get(get_url)
        if response.status_code != 200:
            print(f"获取任务失败: {response.status_code} - {response.text}")
            return
        
        tasks = response.json().get("data", [])
        task = next((t for t in tasks if t["id"] == TASK_ID), None)
        
        if not task:
            print(f"任务 {TASK_ID} 不存在")
            return
        
        print(f"任务详情:")
        print(f"  - ID: {task.get('id')}")
        print(f"  - 课程: {task.get('course')}")
        print(f"  - 内容: {task.get('content')}")
        print(f"  - 图片URL: {task.get('image_url')}")
        print(f"  - 状态: {task.get('status')}")
        print(f"  - 创建时间: {task.get('created_at')}")
        
        # 2. 检查图片URL
        image_url = task.get('image_url')
        if image_url:
            print(f"\n2. 检查图片URL: {image_url}")
            
            # 尝试访问图片
            try:
                image_response = requests.get(image_url)
                if image_response.status_code == 200:
                    print(f"  - 图片访问成功")
                    print(f"  - 图片大小: {len(image_response.content)} bytes")
                    print(f"  - 内容类型: {image_response.headers.get('content-type')}")
                    
                    # 检查是否是有效的图片
                    content_type = image_response.headers.get('content-type', '')
                    if 'image' in content_type:
                        print("  - ✅ 是有效的图片文件")
                    else:
                        print(f"  - ⚠️  不是图片文件: {content_type}")
                        print(f"  - 前100字节: {image_response.content[:100]}")
                else:
                    print(f"  - 图片访问失败: {image_response.status_code}")
                    print(f"  - 响应: {image_response.text[:200]}")
            except Exception as e:
                print(f"  - 图片访问异常: {e}")
        else:
            print("\n2. 任务没有图片URL")
            
        # 3. 直接访问图片API
        print(f"\n3. 直接访问图片API...")
        direct_image_url = f"{BASE_URL}/api/images/{TASK_ID}"
        print(f"  - 直接URL: {direct_image_url}")
        
        try:
            direct_response = requests.get(direct_image_url)
            if direct_response.status_code == 200:
                print(f"  - 直接访问成功")
                print(f"  - 图片大小: {len(direct_response.content)} bytes")
                print(f"  - 内容类型: {direct_response.headers.get('content-type')}")
            elif direct_response.status_code == 404:
                print(f"  - 直接访问失败: 404 - 图片不存在")
            else:
                print(f"  - 直接访问失败: {direct_response.status_code}")
                print(f"  - 响应: {direct_response.text[:200]}")
        except Exception as e:
            print(f"  - 直接访问异常: {e}")
            
        # 4. 检查数据库中的图片数据
        print(f"\n4. 检查数据库状态...")
        # 这里可以添加SQL查询，但需要数据库访问权限
        # 暂时跳过
            
    except Exception as e:
        print(f"检查过程中出现异常: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_task_image()
