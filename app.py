import streamlit as st
import requests
import re
import json
import time
from zhipuai import ZhipuAI

# ================= 配置區 =================
# 填入你的智譜 API Key
ZHIPU_API_KEY = "2040bad6a4de457db8783082ea9120bc.FDSw7nPPtfv8KCaD"
CLIENT = ZhipuAI(api_key=ZHIPU_API_KEY)

# ================= 模組一：自動解析表單 (加入反爬蟲偽裝) =================
def parse_google_form(form_url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7'
    }
    
    response = requests.get(form_url, headers=headers)
    if response.status_code != 200:
        raise ValueError(f"連線失敗！Google 回傳狀態碼：{response.status_code}")

    match = re.search(r'var FB_PUBLIC_LOAD_DATA_ = (\[.*?\]);\n', response.text, re.DOTALL)
    if not match:
         match = re.search(r'var FB_PUBLIC_LOAD_DATA_ = (\[.*?\]);</script>', response.text, re.DOTALL)
         
    if not match:
        error_preview = response.text[:200].replace('\n', ' ')
        raise ValueError(f"找不到表單資料，可能被防爬蟲機制擋下。伺服器實際回傳內容為：{error_preview}")

    data = json.loads(match.group(1))
    parsed_questions = []
    
    try:
        questions_data = data[1][1]
        for q in questions_data:
            try:
                title = q[1]
                entry_id = f"entry.{q[4][0][0]}"
                parsed_questions.append({"title": title, "entry_id": entry_id})
            except (IndexError, TypeError):
                continue
    except (IndexError, TypeError) as e:
        raise ValueError(f"解析題目結構失敗，表單結構可能不受支援。錯誤：{e}")
        
    return parsed_questions

# ================= 模組二：智譜 API 策略引擎 (分批 + 邏輯關聯版) =================
def generate_answers(questions, persona, total_count):
    all_answers = []
    batch_size = 5 
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i in range(0, total_count, batch_size):
        current_count = min(batch_size, total_count - i)
        status_text.text(f"⏳ 正在與 AI 溝通生成數據... (目前進度: {i}/{total_count})")
        
        questions_str = "\n".join([f"- {q['title']}" for q in questions])
        
        prompt = f"""
        你現在是一個自動化數據生成引擎。
        我需要填寫一份問卷，請根據以下設定的方向/人設：【{persona}】
        為我生成 {current_count} 份不同的問卷答案。
        
        問卷題目如下：
        {questions_str}
        
        【填寫邏輯規則】：
        1. 保持人設一致：對於選擇題或判斷題，請根據你已經設定的背景資訊（如專業、年齡、對特定工具的看法）來推斷並填寫最合理的選項文字。
        2. 無關題目隨機化：如果該題與設定的方向或之前填寫的資訊無關，請直接隨機生成一個常理下合理的答案或選項。
        3. 鍵值匹配：返回的 JSON 鍵值(Key)必須「完全等於」上述列表中的題目名稱，一字不差，絕對不要自己縮寫或加上題號。
        
        請以 JSON 陣列格式返回，每個元素代表一份問卷的答案。絕對不要輸出任何解釋文字，只需輸出標準的 JSON 陣列格式。
        """
        
        try:
            # 使用 glm-4-flash 極速版模型
            response = CLIENT.chat.completions.create(
                model="glm-4-flash",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.8
            )
            
            result_text = response.choices[0].message.content
            result_text = result_text.replace("```json", "").replace("```", "").strip()
            
            batch_answers = json.loads(result_text)
            
            if isinstance(batch_answers, list):
                all_answers.extend(batch_answers)
            else:
                st.warning(f"第 {i+1} 批次資料格式有誤，已略過。")
                
        except Exception as e:
            st.warning(f"第 {i+1} 批次生成發生錯誤，略過... ({str(e)})")
            
        current_progress = min(1.0, (i + current_count) / total_count)
        progress_bar.progress(current_progress)
        time.sleep(1) 
        
    status_text.text(f"✅ AI 數據生成完畢！共準備好 {len(all_answers)} 份資料。")
    return all_answers

# ================= 模組三：並發提交模組 (智慧容錯防空缺版) =================
def submit_form(form_url, parsed_questions, answers):
    post_url = form_url.replace("/viewform", "/formResponse")
    success_count = 0
    
    for answer_set in answers:
        payload = {}
        for q in parsed_questions:
            q_title = q['title']
            
            if q_title in answer_set:
                payload[q['entry_id']] = answer_set[q_title]
            else:
                # 模糊匹配：去除標點與空白後比對，防止 AI 擅自改題名
                for ai_key, ai_val in answer_set.items():
                    clean_q = re.sub(r'[^\w\s]', '', q_title)
                    clean_ai = re.sub(r'[^\w\s]', '', ai_key)
                    if clean_q and clean_ai and (clean_q in clean_ai or clean_ai in clean_q):
                        payload[q['entry_id']] = ai_val
                        break
                        
        if payload:
            res = requests.post(post_url, data=payload)
            if res.status_code == 200:
                success_count += 1
        else:
            st.warning("攔截到一份空數據，未提交至表單。")
            
        time.sleep(0.5)
        
    return success_count

# ================= Web UI 設計 =================
st.set_page_config(page_title="自動問卷生成系統", page_icon="🤖")
st.title("🤖 Google Form 自動填寫系統")
st.markdown("輸入 Google 表單連結與目標人設，系統將自動生成並批量提交資料。")

with st.form("auto_form"):
    form_url = st.text_input(
        "Google 表單連結 (必須是 /viewform 結尾)", 
        placeholder="https://docs.google.com/forms/d/e/.../viewform"
    )
    
    persona = st.text_area(
        "填寫方向與偏好設定", 
        value="希望專業多元一點，年齡是大學生，然後對 rightpick JUPAS 選科輔助工具的評價很高，認為解決了升學痛點",
        height=100
    )
    
    target_count = st.number_input("需要生成的問卷數量", min_value=1, max_value=500, value=3)
    
    submitted = st.form_submit_button("開始生成並提交")

# ================= 執行邏輯 =================
if submitted:
    if not form_url:
        st.error("請輸入表單連結！")
    elif "/viewform" not in form_url:
        st.error("連結格式錯誤！請確保連結包含 /viewform")
    else:
        with st.status("任務執行中...", expanded=True) as status:
            try:
                st.write("正在解析表單結構並繞過防護機制...")
                questions = parse_google_form(form_url)
                st.write(f"✅ 成功解析出 {len(questions)} 道題目！")
                
                st.write(" 正在呼叫 AI 分批生成模擬數據...")
                answers = generate_answers(questions, persona, target_count)
                
                if len(answers) > 0:
                    st.write("正在併發提交至 Google 伺服器...")
                    success_count = submit_form(form_url, questions, answers)
                    
                    if success_count > 0:
                        status.update(label=f"任務完成！成功提交 {success_count}/{target_count} 份問卷。", state="complete", expanded=False)
                        st.balloons()
                    else:
                        status.update(label="提交失敗，請檢查資料格式是否被表單阻擋。", state="error")
                else:
                    status.update(label="未成功生成任何數據，請檢查 AI 回傳結果。", state="error")
                    
            except Exception as e:
                status.update(label="執行發生錯誤", state="error")
                st.error(f"錯誤詳情：{str(e)}")
