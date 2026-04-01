"""
数据库连接配置模块
支持SQLite（本地开发）和PostgreSQL（生产环境）的自动切换
"""

import os
import logging
from typing import Optional, Union
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


class DatabaseConfig:
    """数据库配置类"""
    
    def __init__(self):
        self.db_type = os.environ.get("DB_TYPE", "sqlite").lower()
        self._connection = None
        
        # PostgreSQL配置
        self.pg_internal_url = os.environ.get(
            "POSTGRES_INTERNAL_URL",
            "postgresql://zhi_ji_xia_user:biPoDHMdRoOoqQUrLFD7zIiZKolhxop7@dpg-d76cfmhaae7s73c21lig-a/zhi_ji_xia"
        )
        self.pg_external_url = os.environ.get(
            "POSTGRES_EXTERNAL_URL",
            "postgresql://zhi_ji_xia_user:biPoDHMdRoOoqQUrLFD7zIiZKolhxop7@dpg-d76cfmhaae7s73c21lig-a.singapore-postgres.render.com/zhi_ji_xia"
        )
        
        # SQLite配置
        self.sqlite_path = os.environ.get("SQLITE_PATH", "zhi_ji_xia.db")
    
    def get_connection(self):
        """获取数据库连接"""
        # 对于SQLite，每个线程需要自己的连接
        if self.db_type == "sqlite":
            # 为当前线程创建连接
            import threading
            thread_id = threading.get_ident()
            
            # 检查是否已经有当前线程的连接
            if not hasattr(self, '_thread_connections'):
                self._thread_connections = {}
            
            if thread_id not in self._thread_connections:
                self._thread_connections[thread_id] = self._create_sqlite_connection()
            
            return self._thread_connections[thread_id]
        else:
            # PostgreSQL使用共享连接
            if self._connection is None:
                self._connection = self._create_connection()
            elif self._connection.closed:
                # PostgreSQL连接已关闭，重新创建
                self._connection = self._create_connection()
            return self._connection
    
    def _create_connection(self):
        """创建数据库连接"""
        if self.db_type == "postgresql":
            return self._create_postgresql_connection()
        else:
            return self._create_sqlite_connection()
    
    def _create_postgresql_connection(self):
        """创建PostgreSQL连接"""
        try:
            # 判断环境：如果在Render部署环境，使用内部URL；否则使用外部URL
            is_render = os.environ.get("RENDER", "").lower() == "true"
            db_url = self.pg_internal_url if is_render else self.pg_external_url
            
            logger.info(f"连接PostgreSQL数据库，环境: {'Render生产环境' if is_render else '本地/外部环境'}")
            conn = psycopg2.connect(
                db_url,
                cursor_factory=RealDictCursor
            )
            conn.autocommit = False
            logger.info("PostgreSQL连接成功")
            return conn
        except Exception as e:
            logger.error(f"PostgreSQL连接失败: {e}")
            raise
    
    def _create_sqlite_connection(self):
        """创建SQLite连接"""
        try:
            logger.info(f"连接SQLite数据库: {self.sqlite_path}")
            conn = sqlite3.connect(self.sqlite_path)
            conn.row_factory = sqlite3.Row
            logger.info("SQLite连接成功")
            return conn
        except Exception as e:
            logger.error(f"SQLite连接失败: {e}")
            raise
    
    def close(self):
        """关闭数据库连接"""
        if self._connection:
            try:
                self._connection.close()
                logger.info("数据库连接已关闭")
            except Exception as e:
                logger.error(f"关闭数据库连接失败: {e}")
            finally:
                self._connection = None
    
    def execute_query(self, query: str, params: tuple = None):
        """执行查询并返回结果"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # 转换参数占位符：PostgreSQL使用%s，SQLite使用?
            if self.db_type != "postgresql":
                # 将%s替换为?（仅当有参数时）
                if params:
                    query = query.replace("%s", "?")
            
            # 如果是SQLite，需要处理INSERT OR REPLACE语法
            if self.db_type != "postgresql" and "INSERT OR REPLACE" in query.upper():
                # 转换为SQLite的INSERT OR REPLACE语法
                cursor.execute(query, params or ())
            else:
                cursor.execute(query, params or ())
            
            # 如果是SELECT查询，获取结果
            if query.strip().upper().startswith("SELECT"):
                result = cursor.fetchall()
                
                # 转换为字典列表
                if self.db_type == "postgresql":
                    return [dict(row) for row in result]
                else:
                    return [dict(row) for row in result]
            else:
                conn.commit()
                return cursor.rowcount
                
        except Exception as e:
            conn.rollback()
            logger.error(f"查询执行失败: {e}, 查询: {query}")
            raise
        finally:
            cursor.close()
    
    def execute_many(self, query: str, params_list: list):
        """批量执行查询"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.executemany(query, params_list)
            conn.commit()
            return cursor.rowcount
        except Exception as e:
            conn.rollback()
            logger.error(f"批量查询执行失败: {e}")
            raise
        finally:
            cursor.close()


# 全局数据库配置实例
db_config = DatabaseConfig()


def init_database():
    """初始化数据库表"""
    logger.info("开始初始化数据库...")
    
    # 用户表
    create_users_table = """
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        openid TEXT UNIQUE,
        nick_name TEXT,
        avatar_url TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
    
    # 提醒表
    create_reminders_table = """
    CREATE TABLE IF NOT EXISTS reminders (
        id TEXT PRIMARY KEY,
        user_id TEXT,
        course TEXT NOT NULL,
        content TEXT NOT NULL,
        start_time TEXT,
        deadline TEXT NOT NULL,
        difficulty TEXT DEFAULT '中',
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_notified TEXT,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    """
    
    try:
        # 创建用户表
        db_config.execute_query(create_users_table)
        logger.info("用户表创建/检查完成")
        
        # 创建提醒表
        db_config.execute_query(create_reminders_table)
        logger.info("提醒表创建/检查完成")
        
        # 创建默认用户 "test"（如果不存在）
        create_default_user_query = """
        INSERT INTO users (user_id, openid, nick_name, avatar_url)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id) DO NOTHING
        """
        
        if db_config.db_type != "postgresql":
            create_default_user_query = create_default_user_query.replace("%s", "?")
        
        default_user_params = (
            "test",
            "test_openid",
            "测试用户",
            ""
        )
        
        try:
            db_config.execute_query(create_default_user_query, default_user_params)
            logger.info("默认用户 'test' 创建/检查完成")
        except Exception as user_error:
            logger.warning(f"创建默认用户失败: {user_error}")
        
        logger.info("数据库初始化完成")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        raise


def get_db():
    """获取数据库连接（用于依赖注入）"""
    return db_config.get_connection()


def close_db():
    """关闭数据库连接"""
    db_config.close()
