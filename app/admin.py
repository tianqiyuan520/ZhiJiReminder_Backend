"""
后台管理模块
提供数据库管理界面
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Request, Form, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import os

from app.database import db_config

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(prefix="/management", tags=["management"])

# 模板目录
templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
os.makedirs(templates_dir, exist_ok=True)
templates = Jinja2Templates(directory=templates_dir)


# 基本认证（简单实现，生产环境应使用更安全的认证）
def check_admin_auth(request: Request):
    """检查管理员权限（简单实现）"""
    # 这里可以添加更复杂的认证逻辑
    # 例如检查cookie、session或token
    return True  # 暂时允许所有访问


@router.get("/", response_class=HTMLResponse)
async def management_home(request: Request, auth: bool = Depends(check_admin_auth)):
    """管理首页"""
    try:
        # 获取统计信息
        stats = {
            "user_count": 0,
            "reminder_count": 0,
            "pending_count": 0,
            "completed_count": 0
        }
        
        # 用户总数
        user_query = "SELECT COUNT(*) as count FROM users"
        user_result = db_config.execute_query(user_query)
        if user_result:
            stats["user_count"] = user_result[0].get("count", 0)
        
        # 提醒总数
        reminder_query = "SELECT COUNT(*) as count FROM reminders"
        reminder_result = db_config.execute_query(reminder_query)
        if reminder_result:
            stats["reminder_count"] = reminder_result[0].get("count", 0)
        
        # 待处理提醒数
        pending_query = "SELECT COUNT(*) as count FROM reminders WHERE status = 'pending'"
        pending_result = db_config.execute_query(pending_query)
        if pending_result:
            stats["pending_count"] = pending_result[0].get("count", 0)
        
        # 已完成提醒数
        completed_query = "SELECT COUNT(*) as count FROM reminders WHERE status = 'completed'"
        completed_result = db_config.execute_query(completed_query)
        if completed_result:
            stats["completed_count"] = completed_result[0].get("count", 0)
        
        return templates.TemplateResponse(
            "management.html",
            {
                "request": request,
                "stats": stats,
                "page": "home"
            }
        )
    except Exception as e:
        logger.error(f"管理首页加载失败: {e}")
        raise HTTPException(500, f"管理页面加载失败: {str(e)}")


@router.get("/users", response_class=HTMLResponse)
async def manage_users(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    auth: bool = Depends(check_admin_auth)
):
    """用户管理页面"""
    try:
        # 计算偏移量
        offset = (page - 1) * page_size
        
        # 获取用户列表
        users_query = """
        SELECT user_id, openid, nick_name, avatar_url, created_at
        FROM users 
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
        """
        
        users = db_config.execute_query(users_query, (page_size, offset))
        
        # 获取用户总数
        count_query = "SELECT COUNT(*) as count FROM users"
        count_result = db_config.execute_query(count_query)
        total_count = count_result[0].get("count", 0) if count_result else 0
        
        # 计算总页数
        total_pages = (total_count + page_size - 1) // page_size
        
        return templates.TemplateResponse(
            "management.html",
            {
                "request": request,
                "users": users,
                "page": "users",
                "current_page": page,
                "page_size": page_size,
                "total_count": total_count,
                "total_pages": total_pages
            }
        )
    except Exception as e:
        logger.error(f"用户管理页面加载失败: {e}")
        raise HTTPException(500, f"用户管理页面加载失败: {str(e)}")


@router.get("/reminders", response_class=HTMLResponse)
async def manage_reminders(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    auth: bool = Depends(check_admin_auth)
):
    """提醒管理页面"""
    try:
        # 计算偏移量
        offset = (page - 1) * page_size
        
        # 构建查询条件
        where_clauses = []
        params = []
        
        if status:
            where_clauses.append("status = %s")
            params.append(status)
        
        if user_id:
            where_clauses.append("user_id = %s")
            params.append(user_id)
        
        where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        
        # 获取提醒列表
        reminders_query = f"""
        SELECT r.id, r.user_id, r.course, r.content, r.start_time, 
               r.deadline, r.difficulty, r.status, r.created_at,
               u.nick_name as user_nick_name
        FROM reminders r
        LEFT JOIN users u ON r.user_id = u.user_id
        {where_sql}
        ORDER BY r.created_at DESC
        LIMIT %s OFFSET %s
        """
        
        params.extend([page_size, offset])
        reminders = db_config.execute_query(reminders_query, tuple(params) if params else None)
        
        # 获取提醒总数
        count_query = f"SELECT COUNT(*) as count FROM reminders r {where_sql}"
        count_params = params[:-2] if len(params) > 2 else []  # 移除LIMIT和OFFSET参数
        count_result = db_config.execute_query(count_query, tuple(count_params) if count_params else None)
        total_count = count_result[0].get("count", 0) if count_result else 0
        
        # 计算总页数
        total_pages = (total_count + page_size - 1) // page_size
        
        # 获取状态统计
        status_stats_query = """
        SELECT status, COUNT(*) as count 
        FROM reminders 
        GROUP BY status
        """
        status_stats = db_config.execute_query(status_stats_query)
        
        return templates.TemplateResponse(
            "management.html",
            {
                "request": request,
                "reminders": reminders,
                "page": "reminders",
                "current_page": page,
                "page_size": page_size,
                "total_count": total_count,
                "total_pages": total_pages,
                "status": status,
                "user_id": user_id,
                "status_stats": status_stats
            }
        )
    except Exception as e:
        logger.error(f"提醒管理页面加载失败: {e}")
        raise HTTPException(500, f"提醒管理页面加载失败: {str(e)}")


@router.post("/reminders/{reminder_id}/delete")
async def delete_reminder(
    reminder_id: str,
    request: Request,
    auth: bool = Depends(check_admin_auth)
):
    """删除提醒"""
    try:
        delete_query = "DELETE FROM reminders WHERE id = %s"
        rowcount = db_config.execute_query(delete_query, (reminder_id,))
        
        if rowcount == 0:
            raise HTTPException(404, "提醒不存在")
        
        # 重定向回提醒管理页面
        return RedirectResponse(url="/management/reminders", status_code=303)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除提醒失败: {e}")
        raise HTTPException(500, f"删除提醒失败: {str(e)}")


@router.post("/reminders/{reminder_id}/toggle-status")
async def toggle_reminder_status(
    reminder_id: str,
    request: Request,
    auth: bool = Depends(check_admin_auth)
):
    """切换提醒状态（pending/completed）"""
    try:
        # 先获取当前状态
        get_query = "SELECT status FROM reminders WHERE id = %s"
        reminder_data = db_config.execute_query(get_query, (reminder_id,))
        
        if not reminder_data:
            raise HTTPException(404, "提醒不存在")
        
        current_status = reminder_data[0].get("status", "pending")
        new_status = "completed" if current_status == "pending" else "pending"
        
        # 更新状态
        update_query = "UPDATE reminders SET status = %s WHERE id = %s"
        db_config.execute_query(update_query, (new_status, reminder_id))
        
        # 重定向回提醒管理页面
        return RedirectResponse(url="/management/reminders", status_code=303)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"切换提醒状态失败: {e}")
        raise HTTPException(500, f"切换提醒状态失败: {str(e)}")


@router.post("/users/{user_id}/delete")
async def delete_user(
    user_id: str,
    request: Request,
    auth: bool = Depends(check_admin_auth)
):
    """删除用户（同时删除其所有提醒）"""
    try:
        # 先删除用户的提醒
        delete_reminders_query = "DELETE FROM reminders WHERE user_id = %s"
        db_config.execute_query(delete_reminders_query, (user_id,))
        
        # 删除用户
        delete_user_query = "DELETE FROM users WHERE user_id = %s"
        rowcount = db_config.execute_query(delete_user_query, (user_id,))
        
        if rowcount == 0:
            raise HTTPException(404, "用户不存在")
        
        # 重定向回用户管理页面
        return RedirectResponse(url="/management/users", status_code=303)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除用户失败: {e}")
        raise HTTPException(500, f"删除用户失败: {str(e)}")


@router.get("/database", response_class=HTMLResponse)
async def database_info(
    request: Request,
    show_data: bool = Query(False),
    table_name: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=1000),
    auth: bool = Depends(check_admin_auth)
):
    """数据库信息页面"""
    try:
        # 获取数据库信息
        db_info = {
            "type": db_config.db_type,
            "path": db_config.sqlite_path if db_config.db_type == "sqlite" else "PostgreSQL",
            "tables": [],
            "current_table": table_name,
            "show_data": show_data,
            "limit": limit
        }
        
        # 获取表信息（SQLite和PostgreSQL语法不同）
        if db_config.db_type == "sqlite":
            tables_query = "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        else:
            tables_query = """
            SELECT table_name as name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name
            """
        
        tables = db_config.execute_query(tables_query)
        
        # 获取每个表的行数和列信息
        for table in tables:
            table_name = table["name"]
            count_query = f"SELECT COUNT(*) as count FROM {table_name}"
            try:
                count_result = db_config.execute_query(count_query)
                row_count = count_result[0].get("count", 0) if count_result else 0
                
                # 获取表结构信息
                if db_config.db_type == "sqlite":
                    structure_query = f"PRAGMA table_info({table_name})"
                else:
                    structure_query = f"""
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_name = '{table_name}'
                    ORDER BY ordinal_position
                    """
                
                structure_result = db_config.execute_query(structure_query)
                columns = []
                for col in structure_result:
                    if db_config.db_type == "sqlite":
                        columns.append({
                            "name": col.get("name", ""),
                            "type": col.get("type", ""),
                            "nullable": col.get("notnull", 0) == 0
                        })
                    else:
                        columns.append({
                            "name": col.get("column_name", ""),
                            "type": col.get("data_type", ""),
                            "nullable": col.get("is_nullable", "NO") == "YES"
                        })
                
                db_info["tables"].append({
                    "name": table_name,
                    "row_count": row_count,
                    "columns": columns
                })
                
                # 如果请求查看特定表的数据
                if show_data and table_name == table_name:
                    try:
                        data_query = f"SELECT * FROM {table_name} LIMIT %s"
                        if db_config.db_type != "postgresql":
                            data_query = data_query.replace("%s", "?")
                        
                        table_data = db_config.execute_query(data_query, (limit,))
                        db_info["table_data"] = table_data
                        db_info["data_columns"] = list(table_data[0].keys()) if table_data else []
                    except Exception as data_error:
                        logger.warning(f"获取表 {table_name} 数据失败: {data_error}")
                        db_info["table_data"] = []
                        db_info["data_error"] = str(data_error)
                        
            except Exception as e:
                logger.warning(f"获取表 {table_name} 信息失败: {e}")
                db_info["tables"].append({
                    "name": table_name,
                    "row_count": "未知",
                    "columns": []
                })
        
        return templates.TemplateResponse(
            "management.html",
            {
                "request": request,
                "db_info": db_info,
                "page": "database"
            }
        )
    except Exception as e:
        logger.error(f"数据库信息页面加载失败: {e}")
        raise HTTPException(500, f"数据库信息页面加载失败: {str(e)}")


@router.post("/database/switch")
async def switch_database(
    request: Request,
    db_type: str = Form(...),
    auth: bool = Depends(check_admin_auth)
):
    """切换数据库类型"""
    try:
        if db_type not in ["sqlite", "postgresql"]:
            raise HTTPException(400, "不支持的数据库类型")
        
        # 更新环境变量（仅对当前进程有效）
        import os
        os.environ["DB_TYPE"] = db_type
        
        # 重新初始化数据库连接
        from app.database import db_config
        db_config.db_type = db_type
        db_config._connection = None
        
        # 重定向回数据库信息页面
        return RedirectResponse(url="/management/database", status_code=303)
    except Exception as e:
        logger.error(f"切换数据库失败: {e}")
        raise HTTPException(500, f"切换数据库失败: {str(e)}")
