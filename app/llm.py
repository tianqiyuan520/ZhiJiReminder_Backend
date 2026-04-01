import os
import httpx
import json
from dotenv import load_dotenv

load_dotenv()

ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY")
ZHIPU_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

async def parse_homework_info(text):
    """使用大模型从OCR文本中提取课程、作业内容、截止时间"""
    # 打印OCR文本到控制台
    print("=== AI解析的OCR文本 ===")
    print(text)
    print("=====================")
    
    prompt = f"""
你是一个作业信息提取助手。请从以下文本中提取出：
- 课程名 (course)：课程的名称，如"高等数学"、"计算机导论"等
- 作业内容 (content)：具体的作业要求、题目或任务描述
- 截止时间 (deadline，格式为 YYYY-MM-DD HH:MM，如无法确定时间则返回 "未指定")

注意：如果文本中包含多个课程或作业，请提取最主要的一个。
如果截止时间不明确，尝试从"截止"、"提交"、"due"、"deadline"等关键词附近提取时间信息。

只返回一个JSON对象，不要有其他内容。
文本：
{text}
"""
    headers = {
        "Authorization": f"Bearer {ZHIPU_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "glm-4-flash",
        "messages": [
            {"role": "system", "content": "你是一个智能提取助手。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(ZHIPU_API_URL, headers=headers, json=payload, timeout=30)
        result = resp.json()
        content = result["choices"][0]["message"]["content"]
        
        # 打印AI解析结果到控制台
        print("=== AI解析结果 ===")
        print(f"AI返回内容: {content}")
        
        # 解析返回的JSON
        try:
            import re
            # 提取JSON部分
            json_str = re.search(r'\{.*\}', content, re.S).group()
            info = json.loads(json_str)
            print(f"解析后的JSON: {info}")
        except Exception as e:
            print(f"JSON解析失败: {e}")
            info = {"course": "未知", "content": "无法识别", "deadline": "未指定"}
        
        print("==================")
        return info

async def analyze_homework(homework_info):
    """分析作业，提供拖延风险预测和微习惯拆解"""
    prompt = f"""
你是一个学习规划助手。请分析以下作业：
- 课程：{homework_info.get('course')}
- 内容：{homework_info.get('content')}
- 截止时间：{homework_info.get('deadline')}
- 难度：{homework_info.get('difficulty', '中')}

请提供：
1. 拖延风险（高/中/低），基于剩余时间、作业难度和内容复杂度
2. 微习惯拆解：将作业拆解为每天2-5分钟的微型任务，持续3-7天
3. 个性化建议：如何高效完成作业

返回JSON格式：
{{
  "procrastination_risk": "高/中/低",
  "micro_tasks": [
    {{"day": 1, "task": "具体任务描述", "duration_minutes": 3}},
    {{"day": 2, "task": "具体任务描述", "duration_minutes": 5}},
    ...
  ],
  "suggestion": "个性化建议文本"
}}
"""
    headers = {
        "Authorization": f"Bearer {ZHIPU_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "glm-4-flash",
        "messages": [
            {"role": "system", "content": "你是一个学习规划专家。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(ZHIPU_API_URL, headers=headers, json=payload, timeout=30)
        result = resp.json()
        content = result["choices"][0]["message"]["content"]
        try:
            import re
            json_str = re.search(r'\{.*\}', content, re.S).group()
            analysis = json.loads(json_str)
        except:
            # 默认分析
            analysis = {
                "procrastination_risk": "中",
                "micro_tasks": [
                    {"day": 1, "task": "阅读作业要求，明确目标", "duration_minutes": 5},
                    {"day": 2, "task": "收集相关资料", "duration_minutes": 5},
                    {"day": 3, "task": "完成第一部分", "duration_minutes": 5}
                ],
                "suggestion": "建议每天固定时间完成微任务，避免拖延。"
            }
        return analysis
