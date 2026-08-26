import streamlit as st
import requests
import re
import json
import time
import random
import html
from zhipuai import ZhipuAI

# ================= 配置區 =================
ZHIPU_API_KEY = "2040bad6a4de457db8783082ea9120bc.FDSw7nPPtfv8KCaD"
CLIENT = ZhipuAI(api_key=ZHIPU_API_KEY)

# ================= 模組一：自動解析表單結構 =================
def parse_google_form(form_url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8'
    }
    
    response = requests.get(form_url, headers=headers)
    if response.status_code != 200:
        raise ValueError(f"連線失敗！Google 回傳狀態碼：{response.status_code}")

    match = re.search(r'var FB_PUBLIC_LOAD_DATA_ = (\[.*?\]);\n', response.text, re.DOTALL)
    if not match:
         match = re.search(r'var FB_PUBLIC_LOAD_DATA_ = (\[.*?\]);</script>', response.text, re.DOTALL)
    if not match:
        raise ValueError("找不到表單資料，可能被防爬蟲機制擋下。")

    data = json.loads(match.group(1))
    parsed_questions = []
    
    try:
        questions_data = data[1][1]
        for q in questions_data:
            try:
                item_type = q[3]
                if item_type == 8: continue
                    
                main_title = q[1]
                if len(q) > 4 and isinstance(q[4], list):
                    for sub_q in q[4]:
                        if not isinstance(sub_q, list) or len(sub_q) == 0: continue
                        
                        entry_id = f"entry.{sub_q[0]}"
                        
                        sub_title = main_title
                        if len(sub_q) >= 4 and isinstance(sub_q[3], list) and len(sub_q[3]) > 0:
                            sub_title = sub_q[3][0]
                        elif len(q) > 5 and isinstance(q[5], list) and len(q[5]) > 0:
                            sub_title = f"{main_title}_{sub_q[0]}"

                        final_title = f"{main_title} - {sub_title}" if sub_title and sub_title != main_title else main_title
                        
                        options = []
                        if len(sub_q) > 1 and isinstance(sub_q[1], list):
                            for opt in sub_q[1]:
                                if isinstance(opt, list) and len(opt) > 0:
                                    val = str(opt[0])
                                    if val and "其他" not in val and "__other_option__" not in val:
                                        options.append(val)
                        
                        parsed_questions.append({
                            "title": final_title,
                            "entry_id": entry_id,
                            "options": options
                        })
            except (IndexError, TypeError):
                continue
    except (IndexError, TypeError) as e:
        raise ValueError(f"解析題目結構失敗：{e}")
        
    return parsed_questions

# ================= 模組二：智譜 API (強制數量截斷與邏輯版) =================
def generate_answers(questions, persona, total_count):
    all_answers = []
    batch_size = 1 
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i in range(0, total_count, batch_size):
        current_count = min(batch_size, total_count - i)
        status_text.text(f"⏳ 正在與 AI 溝通生成數據... (目前進度: {i+1}/{total_count})")
        
        prompt = f"""
        你現在是一個自動化數據生成引擎。請根據以下人設：【{persona}】
        為我生成 {current_count} 份 JSON 格式的基本資料。
        
        【極度嚴格限制】：
        1. 你 **只能** 輸出以下 5 個 Key：
        - "姓名（不用填寫姓名最後一個字，如陳大X）"
        - "大學學科全名"
        - "大學學系編號"
        - "入學年份"
        - "年級"
        
        請只輸出這 5 個欄位的 JSON 陣列。
        """
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = CLIENT.chat.completions.create(
                    model="glm-4-flash",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.9, 
                    max_tokens=8192
                )
                
                result_text = response.choices[0].message.content
                result_text = result_text.replace("```json", "").replace("
