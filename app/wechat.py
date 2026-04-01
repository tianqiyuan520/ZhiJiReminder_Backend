"""
微信订阅消息模块
处理订阅消息的发送和管理
"""

import logging
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import requests

from app.database import db_config

logger = logging.getLogger(__name__)


class WeChatSubscribeMessage:
    """微信订阅消息处理类"""
    
    def __init__(self):
        import os
        
        # 微信小程序配置（从环境变量获取）
        self.app_id = os.getenv("WECHAT_APP_ID", "wx1234567890abcdef")  # 微信小程序AppID
        self.app_secret = os.getenv("WECHAT_APP_SECRET", "your_app_secret_here")  # 微信小程序AppSecret
        self.access_token = None
        self.token_expire_time = 0
        
        # 订阅消息模板ID（从环境变量获取）
        self.template_ids = {
            "reminder_due": os.getenv("WECHAT_TEMPLATE_REMINDER_DUE", "SmeggOOCYnQ8841WNG5w9eeiZWYGMzGfOBCEEJpH9_8"),
            "reminder_urgent": os.getenv("WECHAT_TEMPLATE_REMINDER_URGENT", "SmeggOOCYnQ8841WNG5w9eeiZWYGMzGfOBCEEJpH9_8"),
        }
        
        # 检查配置
        if self.app_id == "wx1234567890abcdef" or self.app_secret == "your_app_secret_here":
            logger.warning("微信配置未设置，订阅消息功能将无法正常工作")
            logger.warning("请设置环境变量：WECHAT_APP_ID, WECHAT_APP_SECRET")
    
    def get_access_token(self) -> Optional[str]:
        """获取微信Access Token"""
        # 如果token未过期，直接返回
        if self.access_token and time.time() < self.token_expire_time:
            return self.access_token
        
        # 从微信API获取新的token
        url = f"https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={self.app_id}&secret={self.app_secret}"
        
        try:
            response = requests.get(url, timeout=10)
            result = response.json()
            
            if "access_token" in result:
                self.access_token = result["access_token"]
                self.token_expire_time = time.time() + result.get("expires_in", 7200) - 300  # 提前5分钟过期
                logger.info("微信Access Token获取成功")
                return self.access_token
            else:
                logger.error(f"获取微信Access Token失败: {result}")
                return None
        except Exception as e:
            logger.error(f"获取微信Access Token异常: {e}")
            return None
    
    def send_subscribe_message(self, openid: str, template_id: str, data: Dict, 
                              page: str = "pages/reminder/reminder") -> bool:
        """发送订阅消息"""
        access_token = self.get_access_token()
        if not access_token:
            logger.error("无法获取Access Token，发送订阅消息失败")
            return False
        
        url = f"https://api.weixin.qq.com/cgi-bin/message/subscribe/send?access_token={access_token}"
        
        payload = {
            "touser": openid,
            "template_id": template_id,
            "page": page,
            "data": data
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            result = response.json()
            
            if result.get("errcode") == 0:
                logger.info(f"订阅消息发送成功: openid={openid}, template={template_id}")
                return True
            else:
                logger.error(f"订阅消息发送失败: {result}")
                return False
        except Exception as e:
            logger.error(f"发送订阅消息异常: {e}")
            return False
    
    def send_reminder_due_message(self, user_id: str, reminder_info: Dict) -> bool:
        """发送提醒到期消息"""
        # 获取用户的openid
        query = "SELECT openid FROM users WHERE user_id = %s"
        users_data = db_config.execute_query(query, (user_id,))
        
        if not users_data or not users_data[0].get("openid"):
            logger.warning(f"用户 {user_id} 没有openid，无法发送订阅消息")
            return False
        
        openid = users_data[0]["openid"]
        
        # 构建消息数据
        data = {
            "thing1": {"value": reminder_info.get("course", "未知课程")[:20]},  # 课程名称
            "thing2": {"value": reminder_info.get("content", "未知作业")[:20]},  # 作业内容
            "time3": {"value": reminder_info.get("deadline", "未知时间")},  # 截止时间
            "thing4": {"value": self._get_urgency_level(reminder_info.get("deadline"))}  # 紧急程度
        }
        
        # 根据紧急程度选择模板
        urgency = self._get_urgency_level(reminder_info.get("deadline"))
        template_id = self.template_ids["reminder_urgent"] if urgency == "非常紧急" else self.template_ids["reminder_due"]
        
        return self.send_subscribe_message(openid, template_id, data)
    
    def _get_urgency_level(self, deadline_str: str) -> str:
        """根据截止时间计算紧急程度"""
        if not deadline_str:
            return "未知"
        
        try:
            deadline = datetime.strptime(deadline_str, '%Y-%m-%d %H:%M')
            now = datetime.now()
            time_diff = deadline - now
            
            if time_diff.total_seconds() <= 0:
                return "已过期"
            elif time_diff.total_seconds() <= 24 * 3600:  # 24小时内
                return "非常紧急"
            elif time_diff.total_seconds() <= 3 * 24 * 3600:  # 3天内
                return "紧急"
            elif time_diff.total_seconds() <= 7 * 24 * 3600:  # 7天内
                return "一般"
            else:
                return "不紧急"
        except Exception as e:
            logger.error(f"计算紧急程度失败: {e}, deadline_str={deadline_str}")
            return "未知"


# 全局微信订阅消息实例
wechat_message = WeChatSubscribeMessage()


def check_due_reminders():
    """检查即将到期的提醒并发送订阅消息"""
    logger.info("开始检查即将到期的提醒...")
    
    try:
        # 查询所有待处理且即将到期的提醒
        # 提前1天、3小时、1小时发送提醒
        now = datetime.now()
        
        # 1天后到期的提醒
        one_day_later = now + timedelta(days=1)
        one_day_query = """
        SELECT r.id, r.user_id, r.course, r.content, r.deadline, u.openid
        FROM reminders r
        JOIN users u ON r.user_id = u.user_id
        WHERE r.status = 'pending' 
        AND r.deadline BETWEEN %s AND %s
        AND (r.last_notified IS NULL OR r.last_notified < %s)
        """
        
        # 3小时后到期的提醒
        three_hours_later = now + timedelta(hours=3)
        three_hours_query = """
        SELECT r.id, r.user_id, r.course, r.content, r.deadline, u.openid
        FROM reminders r
        JOIN users u ON r.user_id = u.user_id
        WHERE r.status = 'pending' 
        AND r.deadline BETWEEN %s AND %s
        AND (r.last_notified IS NULL OR r.last_notified < %s)
        """
        
        # 1小时后到期的提醒
        one_hour_later = now + timedelta(hours=1)
        one_hour_query = """
        SELECT r.id, r.user_id, r.course, r.content, r.deadline, u.openid
        FROM reminders r
        JOIN users u ON r.user_id = u.user_id
        WHERE r.status = 'pending' 
        AND r.deadline BETWEEN %s AND %s
        AND (r.last_notified IS NULL OR r.last_notified < %s)
        """
        
        # 格式化时间字符串
        time_format = '%Y-%m-%d %H:%M'
        
        # 检查1天后到期的提醒
        one_day_start = now.strftime(time_format)
        one_day_end = one_day_later.strftime(time_format)
        one_day_reminders = db_config.execute_query(
            one_day_query, 
            (one_day_start, one_day_end, now.strftime(time_format))
        )
        
        # 检查3小时后到期的提醒
        three_hours_start = now.strftime(time_format)
        three_hours_end = three_hours_later.strftime(time_format)
        three_hours_reminders = db_config.execute_query(
            three_hours_query,
            (three_hours_start, three_hours_end, now.strftime(time_format))
        )
        
        # 检查1小时后到期的提醒
        one_hour_start = now.strftime(time_format)
        one_hour_end = one_hour_later.strftime(time_format)
        one_hour_reminders = db_config.execute_query(
            one_hour_query,
            (one_hour_start, one_hour_end, now.strftime(time_format))
        )
        
        all_reminders = one_day_reminders + three_hours_reminders + one_hour_reminders
        sent_count = 0
        
        for reminder in all_reminders:
            try:
                reminder_info = {
                    "id": reminder["id"],
                    "course": reminder["course"],
                    "content": reminder["content"],
                    "deadline": reminder["deadline"]
                }
                
                # 发送订阅消息
                success = wechat_message.send_reminder_due_message(
                    reminder["user_id"], 
                    reminder_info
                )
                
                if success:
                    # 更新最后通知时间
                    update_query = "UPDATE reminders SET last_notified = %s WHERE id = %s"
                    db_config.execute_query(update_query, (now.strftime(time_format), reminder["id"]))
                    sent_count += 1
                    logger.info(f"已发送提醒通知: {reminder['user_id']} - {reminder['course']}")
                
            except Exception as e:
                logger.error(f"处理提醒 {reminder.get('id')} 失败: {e}")
        
        logger.info(f"检查完成，共发送 {sent_count} 条订阅消息")
        return sent_count
        
    except Exception as e:
        logger.error(f"检查到期提醒失败: {e}")
        return 0


def add_last_notified_column():
    """在reminders表中添加last_notified列（如果不存在）"""
    try:
        # 检查列是否存在（SQLite和PostgreSQL语法不同）
        if db_config.db_type == "sqlite":
            check_query = "PRAGMA table_info(reminders)"
            columns = db_config.execute_query(check_query)
            column_names = [col["name"] for col in columns]
            
            if "last_notified" not in column_names:
                alter_query = "ALTER TABLE reminders ADD COLUMN last_notified TEXT"
                db_config.execute_query(alter_query)
                logger.info("已添加last_notified列到reminders表")
        else:
            # PostgreSQL
            check_query = """
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'reminders' AND column_name = 'last_notified'
            """
            result = db_config.execute_query(check_query)
            
            if not result:
                alter_query = "ALTER TABLE reminders ADD COLUMN last_notified TEXT"
                db_config.execute_query(alter_query)
                logger.info("已添加last_notified列到reminders表")
                
    except Exception as e:
        logger.error(f"添加last_notified列失败: {e}")
