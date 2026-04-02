import requests
import base64
import os
import time
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

API_KEY = os.getenv("BAIDU_OCR_API_KEY")
SECRET_KEY = os.getenv("BAIDU_OCR_SECRET_KEY")

def get_access_token():
    """获取百度OCR的access_token，带重试机制"""
    url = "https://aip.baidubce.com/oauth/2.0/token"
    params = {
        "grant_type": "client_credentials",
        "client_id": API_KEY,
        "client_secret": SECRET_KEY,
    }
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(url, params=params, timeout=10)
            result = response.json()
            
            if "access_token" in result:
                logger.info(f"获取百度OCR access_token成功 (尝试 {attempt+1}/{max_retries})")
                return result.get("access_token")
            else:
                logger.warning(f"获取access_token失败: {result} (尝试 {attempt+1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(1)  # 等待1秒后重试
        except requests.exceptions.Timeout:
            logger.warning(f"获取access_token超时 (尝试 {attempt+1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(1)
        except Exception as e:
            logger.error(f"获取access_token异常: {e} (尝试 {attempt+1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(1)
    
    logger.error("获取百度OCR access_token失败，已达到最大重试次数")
    return None

def ocr_image(image_bytes, max_retries=3):
    """识别图片文字，返回字符串（带重试机制）"""
    if not API_KEY or not SECRET_KEY:
        logger.error("百度OCR API密钥未配置")
        return ""
    
    access_token = get_access_token()
    if not access_token:
        logger.error("无法获取百度OCR access_token")
        return ""
    
    url = f"https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic?access_token={access_token}"
    img_base64 = base64.b64encode(image_bytes).decode()
    data = {"image": img_base64}
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    
    for attempt in range(max_retries):
        try:
            logger.info(f"开始OCR识别 (尝试 {attempt+1}/{max_retries})")
            response = requests.post(url, data=data, headers=headers, timeout=30)  # 增加超时时间
            result = response.json()
            
            logger.info(f"OCR响应状态: {response.status_code}")
            
            if "words_result" in result:
                text = "\n".join([item["words"] for item in result["words_result"]])
                logger.info(f"OCR识别成功，文本长度: {len(text)}")
                return text
            else:
                error_msg = result.get("error_msg", "未知错误")
                logger.warning(f"OCR识别失败: {error_msg} (尝试 {attempt+1}/{max_retries})")
                
                # 如果是配额不足或频率限制，立即返回
                if "quota" in error_msg.lower() or "limit" in error_msg.lower():
                    logger.error(f"OCR配额或频率限制: {error_msg}")
                    return ""
                
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # 指数退避
                    logger.info(f"等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                    
        except requests.exceptions.Timeout:
            logger.warning(f"OCR识别超时 (尝试 {attempt+1}/{max_retries})")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logger.info(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
                
        except requests.exceptions.ConnectionError as e:
            logger.warning(f"OCR连接错误: {e} (尝试 {attempt+1}/{max_retries})")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logger.info(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
                
        except Exception as e:
            logger.error(f"OCR识别异常: {e} (尝试 {attempt+1}/{max_retries})")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logger.info(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
    
    logger.error("OCR识别失败，已达到最大重试次数")
    return ""
