import streamlit as st
import requests
import re
import json
import time
from zhipuai import ZhipuAI

ZHIPU_API_KEY = "2040bad6a4de457db8783082ea9120bc.FDSw7nPPtfv8KCaD"
CLIENT = ZhipuAI(api_key=ZHIPU_API_KEY)

# --- 核心邏輯函數 (與之前相同，略作 UI 調整) ---
def parse_google_form(form_url):
    response = requests.get(form_url)
    match = re.search(r'var FB_PUBLIC_LOAD_DATA_ = (\[.*?\]);\n', response.text, re.DOTALL)
    if not match:
        raise ValueError("無法解析表單，請確認表單權限是否為公開。")
    data = json.loads(match.group(1))
    parsed_questions = []
    for q in data[1][1]:
        try:
            parsed_questions.append({"title": q[1], "entry_id": f"entry.{q[4][0][0]}"})
        except (IndexError, TypeError):
            continue
    return parsed_questions

def generate_answers(questions, persona, count):
    questions_str = "\n".join([f"{i+1}. {q['title']}" for i, q in enumerate(questions)])
    prompt = f"你是一個自動化數據生成引擎。請根據人設：【{persona}】生成 {count} 份問卷答案。\n問卷題目：\n{questions_str}\n請以 JSON 陣列格式返回，鍵值為題目名稱，值為生成的答案。只輸出標準 JSON。"
    
    response = CLIENT.chat.completions.create(
        model="glm-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )
    result_text = response.choices[0].message.content.replace("```json", "").replace("```", "").strip()
    return json.loads(result_text)

def submit_form(form_url, parsed_questions, answers):
    post_url = form_url.replace("/viewform", "/formResponse")
    success = 0
    for answer_set in answers:
        payload = {q['entry_id']: answer_set.get(q['title'], "") for q in parsed_questions if q['title'] in answer_set}
        res = requests.post(post_url, data=payload)
        if res.status_code == 200:
            success += 1
        time.sleep(0.5)
    return success

# --- Web UI 設計 ---
st.set_page_config(page_title="自動問卷生成系統", page_icon="🤖")
st.title("🤖 Google Form 自動填寫系統")
st.markdown("輸入 Google 表單連結與目標人設，系統將自動生成並提交資料。")

with st.form("auto_form"):
    form_url = st.text_input("Google 表單連結 (必須是 /viewform 結尾)", placeholder="https://docs.google.com/forms/...")
    persona = st.text_area("填寫方向與偏好設定", placeholder="例如：就讀資工系，喜歡寫程式的大學生。專業名稱固定填寫'計算機科學'...")
    target_count = st.number_input("需要生成的問卷數量", min_value=1, max_value=500, value=5)
    
    submitted = st.form_submit_button("開始生成並提交")

if submitted:
    if not form_url:
        st.error("請輸入表單連結！")
    else:
        with st.status("任務執行中...", expanded=True) as status:
            try:
                st.write("正在解析表單結構...")
                questions = parse_google_form(form_url)
                st.write(f"成功解析出 {len(questions)} 道題目！")
                
                st.write("正在呼叫 AI 生成符合偏好的數據...")
                answers = generate_answers(questions, persona, target_count)
                st.write(f"成功生成 {len(answers)} 份模擬數據！")
                
                st.write("正在併發提交至 Google 伺服器...")
                success_count = submit_form(form_url, questions, answers)
                
                status.update(label=f"任務完成！成功提交 {success_count} 份問卷。", state="complete", expanded=False)
                st.balloons()
            except Exception as e:
                status.update(label="執行發生錯誤", state="error")
                st.error(f"錯誤詳情：{e}")
