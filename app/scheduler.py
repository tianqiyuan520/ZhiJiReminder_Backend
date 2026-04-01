"""
定时任务调度模块
定期检查即将到期的提醒并发送订阅消息
"""

import logging
import time
import threading
from datetime import datetime, timedelta
import schedule
import requests

from app.wechat import check_due_reminders

logger = logging.getLogger(__name__)


class ReminderScheduler:
    """提醒调度器"""
    
    def __init__(self, check_interval_minutes=30):
        """
        初始化调度器
        
        Args:
            check_interval_minutes: 检查间隔（分钟）
        """
        self.check_interval_minutes = check_interval_minutes
        self.scheduler_thread = None
        self.running = False
        
    def check_due_reminders_job(self):
        """检查到期提醒的定时任务"""
        logger.info(f"定时任务执行: 检查即将到期的提醒")
        try:
            sent_count = check_due_reminders()
            logger.info(f"定时任务完成: 发送了 {sent_count} 条订阅消息")
        except Exception as e:
            logger.error(f"定时任务执行失败: {e}")
    
    def start(self):
        """启动定时任务调度器"""
        if self.running:
            logger.warning("调度器已经在运行中")
            return
        
        logger.info(f"启动提醒调度器，检查间隔: {self.check_interval_minutes}分钟")
        
        # 设置定时任务
        schedule.every(self.check_interval_minutes).minutes.do(self.check_due_reminders_job)
        
        # 立即执行一次
        self.check_due_reminders_job()
        
        # 启动调度器线程
        self.running = True
        self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.scheduler_thread.start()
        
        logger.info("提醒调度器已启动")
    
    def _run_scheduler(self):
        """运行调度器的主循环"""
        while self.running:
            try:
                schedule.run_pending()
                time.sleep(60)  # 每分钟检查一次
            except Exception as e:
                logger.error(f"调度器运行异常: {e}")
                time.sleep(60)
    
    def stop(self):
        """停止定时任务调度器"""
        if not self.running:
            return
        
        logger.info("停止提醒调度器")
        self.running = False
        
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        
        schedule.clear()
        logger.info("提醒调度器已停止")
    
    def trigger_manual_check(self):
        """手动触发检查"""
        logger.info("手动触发检查即将到期的提醒")
        return self.check_due_reminders_job()


def start_scheduler():
    """启动定时任务调度器（用于应用启动时调用）"""
    # 根据环境配置检查间隔
    # 开发环境：每30分钟检查一次
    # 生产环境：每10分钟检查一次
    import os
    is_production = os.environ.get("RENDER", "").lower() == "true"
    check_interval = 10 if is_production else 30
    
    scheduler = ReminderScheduler(check_interval_minutes=check_interval)
    scheduler.start()
    return scheduler


# 全局调度器实例
_scheduler_instance = None


def get_scheduler():
    """获取全局调度器实例"""
    global _scheduler_instance
    return _scheduler_instance


def init_scheduler():
    """初始化调度器"""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = start_scheduler()
    return _scheduler_instance


def stop_scheduler():
    """停止调度器"""
    global _scheduler_instance
    if _scheduler_instance:
        _scheduler_instance.stop()
        _scheduler_instance = None


# API端点调用函数（用于手动触发）
def trigger_check_via_api():
    """通过API手动触发检查"""
    try:
        # 获取当前服务的URL
        import os
        base_url = os.environ.get("BASE_URL", "http://localhost:8000")
        
        # 调用API端点
        response = requests.get(f"{base_url}/api/check-due-reminders", timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"API触发检查成功: {result.get('message')}")
            return result
        else:
            logger.error(f"API触发检查失败: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logger.error(f"API触发检查异常: {e}")
        return None


if __name__ == "__main__":
    # 直接运行此脚本进行测试
    logging.basicConfig(level=logging.INFO)
    logger.info("测试定时任务调度器...")
    
    # 创建并启动调度器
    test_scheduler = ReminderScheduler(check_interval_minutes=1)  # 1分钟间隔用于测试
    test_scheduler.start()
    
    try:
        # 运行5分钟进行测试
        logger.info("调度器运行中，等待5分钟...")
        time.sleep(300)  # 5分钟
        
        # 手动触发一次检查
        logger.info("手动触发检查...")
        test_scheduler.trigger_manual_check()
        
        # 再等待2分钟
        time.sleep(120)
        
    except KeyboardInterrupt:
        logger.info("收到中断信号")
    finally:
        # 停止调度器
        test_scheduler.stop()
        logger.info("测试完成")
