#!/usr/bin/env python3
"""
智记侠后端服务启动脚本
自动检测可用端口并启动FastAPI服务
"""

import os
import sys
import socket
import subprocess
import time
from datetime import datetime

def check_port_available(port):
    """检查端口是否可用"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        return result != 0  # 如果连接失败，说明端口可用
    except:
        return False

def find_available_port(start_port=8000, max_attempts=10):
    """查找可用的端口"""
    for port in range(start_port, start_port + max_attempts):
        if check_port_available(port):
            return port
    return None

def print_banner():
    """打印启动横幅"""
    banner = """
╔══════════════════════════════════════════════════════════╗
║                智记侠后端服务启动器                      ║
║                ZhiJiReminder Server Starter              ║
╚══════════════════════════════════════════════════════════╝
    """
    print(banner)
    print(f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"工作目录: {os.getcwd()}")
    print("-" * 60)

def check_dependencies():
    """检查依赖是否安装"""
    print("检查依赖...")
    dependencies = ['fastapi', 'uvicorn', 'sqlite3']
    
    for dep in dependencies:
        try:
            if dep == 'sqlite3':
                # sqlite3是Python标准库
                import sqlite3
            else:
                __import__(dep)
            print(f"  ✓ {dep}")
        except ImportError:
            print(f"  ✗ {dep} 未安装")
            if dep != 'sqlite3':
                print(f"    请运行: pip install {dep}")
            return False
    return True

def start_server(port=8000, reload=False):
    """启动FastAPI服务器"""
    print(f"\n启动服务器在端口 {port}...")
    
    # 构建命令
    cmd = [
        sys.executable, '-m', 'uvicorn',
        'app.main:app',
        '--host', 'localhost',
        '--port', str(port)
    ]
    
    if reload:
        cmd.append('--reload')
        print("启用热重载模式")
    
    print(f"命令: {' '.join(cmd)}")
    print("-" * 60)
    
    try:
        # 启动服务器
        process = subprocess.Popen(cmd)
        
        print(f"服务器已启动! PID: {process.pid}")
        print(f"API地址: http://localhost:{port}")
        print(f"API文档: http://localhost:{port}/docs")
        print(f"首页: http://localhost:{port}/")
        
        # 启动定时任务调度器
        print("\n启动定时任务调度器...")
        try:
            # 导入并启动调度器
            sys.path.insert(0, os.getcwd())
            from app.scheduler import init_scheduler
            scheduler = init_scheduler()
            print("✓ 定时任务调度器已启动")
            print(f"  检查间隔: {scheduler.check_interval_minutes}分钟")
            print(f"  定时检查即将到期的提醒并发送微信订阅消息")
        except Exception as e:
            print(f"✗ 启动定时任务调度器失败: {e}")
            print("  定时任务功能将不可用")
        
        print("\n按 Ctrl+C 停止服务器")
        print("-" * 60)
        
        # 等待进程结束
        process.wait()
        
    except KeyboardInterrupt:
        print("\n\n收到停止信号，正在关闭服务器...")
        if process:
            process.terminate()
        print("服务器已停止")
    except Exception as e:
        print(f"启动服务器时出错: {e}")
        return False
    
    return True

def main():
    """主函数"""
    print_banner()
    
    # 检查依赖
    if not check_dependencies():
        print("\n依赖检查失败，请先安装缺失的依赖")
        print("建议运行: pip install fastapi uvicorn python-multipart")
        return
    
    # 查找可用端口
    print("\n查找可用端口...")
    port = find_available_port(8002)
    
    if port is None:
        print("错误: 未找到可用端口 (8000-8009)")
        print("请关闭占用端口的程序或手动指定端口")
        port = 8000  # 仍然尝试8000
    
    print(f"使用端口: {port}")
    
    # 检查是否启用热重载
    reload_mode = '--reload' in sys.argv or '-r' in sys.argv
    
    # 启动服务器
    start_server(port, reload_mode)

if __name__ == "__main__":
    main()
