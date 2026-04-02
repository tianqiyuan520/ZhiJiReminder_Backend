#!/usr/bin/env python3
"""
修复图片URL脚本
将本地URL改为生产环境URL（用于部署前准备）
"""

import os
import sqlite3
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def fix_image_urls():
    """修复数据库中的图片URL（将本地URL改为生产环境URL）"""
    
    # 使用SQLite数据库
    db_path = "zhi_ji_xia.db"
    if not os.path.exists(db_path):
        print(f"错误: 数据库文件不存在: {db_path}")
        return
    
    print(f"连接数据库: {db_path}")
    
    try:
        # 连接数据库
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 检查reminders表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reminders'")
        if not cursor.fetchone():
            print("错误: reminders表不存在")
            return
        
        # 查找所有包含本地URL的图片
        cursor.execute("""
            SELECT id, image_url 
            FROM reminders 
            WHERE image_url LIKE 'http://localhost:8002/images/%' 
               OR image_url LIKE 'http://127.0.0.1:8002/images/%'
               OR image_url LIKE 'localhost:8002/images/%'
        """)
        
        rows = cursor.fetchall()
        print(f"找到 {len(rows)} 条需要修复的记录")
        
        # 修复每条记录
        for row in rows:
            row_id = row['id']
            image_url = row['image_url']
            
            if image_url:
                # 提取文件名
                filename = image_url.split('/')[-1]
                # 生成新的生产环境URL
                new_url = f"https://zhijireminderbackend.onrender.com/images/{filename}"
                
                # 更新数据库
                cursor.execute("""
                    UPDATE reminders 
                    SET image_url = ? 
                    WHERE id = ?
                """, (new_url, row_id))
                
                print(f"修复记录 {row_id}:")
                print(f"  原URL: {image_url}")
                print(f"  新URL: {new_url}")
        
        # 提交更改
        conn.commit()
        print(f"\n成功修复 {len(rows)} 条记录")
        
        # 关闭连接
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()

def check_local_images():
    """检查本地图片文件"""
    images_dir = "images"
    if not os.path.exists(images_dir):
        print(f"错误: 图片目录不存在: {images_dir}")
        return
    
    files = os.listdir(images_dir)
    print(f"\n本地图片目录中有 {len(files)} 个文件:")
    for file in files:
        print(f"  - {file}")

def check_database_urls():
    """检查数据库中的图片URL"""
    db_path = "zhi_ji_xia.db"
    if not os.path.exists(db_path):
        print(f"错误: 数据库文件不存在: {db_path}")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 检查reminders表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reminders'")
        if not cursor.fetchone():
            print("错误: reminders表不存在")
            return
        
        # 获取所有图片URL
        cursor.execute("""
            SELECT id, course, image_url 
            FROM reminders 
            WHERE image_url IS NOT NULL AND image_url != ''
            ORDER BY id
        """)
        
        rows = cursor.fetchall()
        print(f"\n数据库中有 {len(rows)} 条包含图片URL的记录:")
        
        local_count = 0
        production_count = 0
        other_count = 0
        
        for row in rows:
            image_url = row['image_url']
            if 'localhost' in image_url or '127.0.0.1' in image_url:
                local_count += 1
                print(f"  - ID: {row['id']}, 课程: {row['course']}, URL: {image_url} [本地]")
            elif 'zhijireminderbackend.onrender.com' in image_url:
                production_count += 1
                print(f"  - ID: {row['id']}, 课程: {row['course']}, URL: {image_url} [生产]")
            else:
                other_count += 1
                print(f"  - ID: {row['id']}, 课程: {row['course']}, URL: {image_url} [其他]")
        
        print(f"\n统计:")
        print(f"  本地URL: {local_count} 条")
        print(f"  生产URL: {production_count} 条")
        print(f"  其他URL: {other_count} 条")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"检查数据库URL错误: {e}")

if __name__ == "__main__":
    print("=== 图片URL修复工具（部署准备版） ===")
    print("说明: 此工具将本地图片URL改为生产环境URL，用于部署前准备")
    
    print("\n1. 检查本地图片文件")
    check_local_images()
    
    print("\n2. 检查数据库中的图片URL")
    check_database_urls()
    
    print("\n3. 修复数据库中的图片URL（本地→生产）")
    response = input("是否开始修复？(y/n): ")
    if response.lower() == 'y':
        fix_image_urls()
    else:
        print("已取消修复操作")
    
    print("\n=== 操作完成 ===")
    print("提示: 部署后，请确保生产环境服务器上的images目录包含所有图片文件")
