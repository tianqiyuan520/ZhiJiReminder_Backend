import requests
import base64
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("BAIDU_OCR_API_KEY")
SECRET_KEY = os.getenv("BAIDU_OCR_SECRET_KEY")

def get_access_token():
    url = "https://aip.baidubce.com/oauth/2.0/token"
    params = {
        "grant_type": "client_credentials",
        "client_id": API_KEY,
        "client_secret": SECRET_KEY,
    }
    response = requests.post(url, params=params)
    return response.json().get("access_token")

def ocr_image(image_bytes):
    """识别图片文字，返回字符串"""
    access_token = get_access_token()
    url = f"https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic?access_token={access_token}"
    img_base64 = base64.b64encode(image_bytes).decode()
    data = {"image": img_base64}
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(url, data=data, headers=headers)
    result = response.json()
    
    # 打印OCR结果到控制台
    print("=== OCR识别结果 ===")
    print(f"响应状态: {response.status_code}")
    print(f"完整响应: {result}")
    
    if "words_result" in result:
        text = "\n".join([item["words"] for item in result["words_result"]])
        print(f"识别到的文本:\n{text}")
        print("==================")
        return text
    else:
        print(f"OCR识别失败: {result}")
        print("==================")
        return ""
