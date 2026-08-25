import streamlit as st
import requests
import re
import json
import time
import random
from zhipuai import ZhipuAI

# ================= 配置區 =================
ZHIPU_API_KEY = "2040bad6a4de457db8783082ea9120bc.FDSw7nPPtfv8KCaD"
CLIENT = ZhipuAI(api_key=ZHIPU_API_KEY)

# ================= 模組一：自動解析表單 (終極網格題深度解析版) =================
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
        raise ValueError(f"找不到表單資料，可能被防爬蟲機制擋下。")

    data = json.loads(match.group(1))
    parsed_questions = []
    
    try:
        questions_data = data[1][1]
        for q in questions_data:
            try:
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

                        if sub_title and sub_title != main_title:
                             final_title = f"{main_title} - {sub_title}"
                        else:
                             final_title = main_title
                             
                        parsed_questions.append({"title": final_title, "entry_id": entry_id})
                        
            except (IndexError, TypeError):
                continue
    except (IndexError, TypeError) as e:
        raise ValueError(f"解析題目結構失敗：{e}")
        
    return parsed_questions

# ================= 模組二：智譜 API 策略引擎 =================
def generate_answers(questions, persona, total_count):
    all_answers = []
    batch_size = 1 
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i in range(0, total_count, batch_size):
        current_count = min(batch_size, total_count - i)
        status_text.text(f"⏳ 正在與 AI 溝通生成數據... (目前進度: {i+1}/{total_count})")
        
        questions_str = "\n".join([f"- {q['title']}" for q in questions])
        prompt = f"""
        你現在是一個自動化數據生成引擎。我需要填寫一份問卷，請根據以下設定的方向/人設：【{persona}】
        為我生成 {current_count} 份問卷答案。
        
        問卷題目如下：
        {questions_str}
        
        【填寫邏輯規則】：
        1. 保持人設一致：請根據背景資訊推斷並填寫最合理的文字。
        2. 鍵值匹配：返回的 JSON 鍵值(Key)必須「完全等於」上述列表中的題目名稱（包含破折號與空格），一字不差。
        3. 請以 JSON 陣列格式返回。絕對不要輸出任何解釋文字，只需輸出標準的 JSON 陣列。
        """
        
        try:
            response = CLIENT.chat.completions.create(
                model="glm-4-flash",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.8,
                max_tokens=8192  # 🚨 關鍵防斷設定：放大輸出的字數上限，防止被切斷
            )
            
            result_text = response.choices[0].message.content
            result_text = result_text.replace("```json", "").replace("```", "").strip()
            batch_answers = json.loads(result_text)
            
            if isinstance(batch_answers, dict):
                batch_answers = [batch_answers]
                
            if isinstance(batch_answers, list):
                all_answers.extend(batch_answers)
            else:
                st.warning(f"第 {i+1} 份資料格式有誤，已略過。")
        except Exception as e:
            st.warning(f"第 {i+1} 份生成發生錯誤，略過... ({str(e)})")
            
        current_progress = min(1.0, (i + current_count) / total_count)
        progress_bar.progress(current_progress)
        time.sleep(1) 
        
    status_text.text(f"✅ AI 數據生成完畢！共準備好 {len(all_answers)} 份資料。")
    return all_answers

# ================= 模組三：並發提交模組 =================
def submit_form(form_url, parsed_questions, answers, duration_hours):
    post_url = form_url.replace("/viewform", "/formResponse")
    success_count = 0
    total_seconds = duration_hours * 3600
    avg_wait = total_seconds / len(answers) if len(answers) > 0 else 0
    wait_status = st.empty()
    
    for idx, answer_set in enumerate(answers):
        payload = {}
        payload['pageHistory'] = "0,1,2,3,4,5,6" 
        
        for q in parsed_questions:
            q_title = q['title']
            if q_title in answer_set:
                payload[q['entry_id']] = answer_set[q_title]
            else:
                for ai_key, ai_val in answer_set.items():
                    clean_q = re.sub(r'[^\w\s]', '', q_title)
                    clean_ai = re.sub(r'[^\w\s]', '', ai_key)
                    if clean_q and clean_ai and (clean_q in clean_ai or clean_ai in clean_q):
                        payload[q['entry_id']] = ai_val
                        break
                        
        if len(payload) > 1:
            res = requests.post(post_url, data=payload)
            
            if res.status_code == 200 and "FB_PUBLIC_LOAD_DATA_" not in res.text:
                success_count += 1
            else:
                st.error(f"第 {idx+1} 份問卷遭遇「假成功」！(資料被 Google 退件，可能是必填未填)")
                st.warning("請檢查下方資料，比對表單必填項：")
                st.json(payload) 
        else:
            st.warning("攔截到一份空數據，未提交至表單。")
            
        if idx < len(answers) - 1:
            if duration_hours > 0:
                wait_time = random.uniform(avg_wait * 0.5, avg_wait * 1.5)
                wait_status.info(f"⏳ 第 {idx+1} 份已提交，隨機等待 {int(wait_time)} 秒...")
                time.sleep(wait_time)
            else:
                time.sleep(0.5)
                
    wait_status.empty()
    return success_count

# ================= Web UI 設計 =================
st.set_page_config(page_title="自動問卷生成系統", page_icon="🤖")
st.title("🤖 Google Form 自動填寫系統")
st.markdown("輸入 Google 表單連結與目標人設，系統將自動生成並批量提交資料。")

# 🚨 已優化的 Prompt，教導 AI 直接「省略 Key」來大幅縮減字數
default_persona = """你現在是一位香港八大院校的受訪者，正在填寫一份關於升學與職涯意向的大型深度調查問卷。

【重要身分設定】：
請你每次生成數據時，先隨機決定自己的身分是「在校大學生」還是「已全職工作3個月以上的畢業生」（兩者比例大約各半）。

【核心身分與代碼綁定】：
關於「大學學科全名」、「大學學系編號」與隱藏的「學科偏向」，請【必須且只能】從下方列表隨機挑選「完整的一組」。
[真實 JUPAS 組合菜單]
- 組合1：專業「理學」, JS code「JS6901」, 學科偏向「理科」
- 組合2：專業「內外全科醫學」, JS code「JS6456」, 學科偏向「理科」
- 組合3：專業「工程學」, JS code「JS6963」, 學科偏向「工科」
- 組合4：專業「文學」, JS code「JS6054」, 學科偏向「文科」
- 組合5：專業「工商管理學」, JS code「JS6755」, 學科偏向「商科」
- 組合6：專業「社會科學」, JS code「JS6810」, 學科偏向「文科」
- 組合7：專業「綜合工商管理」, JS code「JS4202」, 學科偏向「商科」
- 組合8：專業「工程學」, JS code「JS4401」, 學科偏向「工科」
- 組合9：專業「理學」, JS code「JS4601」, 學科偏向「理科」
- 組合10：專業「護理學」, JS code「JS4331」, 學科偏向「理科」
- 組合11：專業「工商管理」, JS code「JS5300」, 學科偏向「商科」
- 組合12：專業「計算機科學」, JS code「JS5211」, 學科偏向「工科」
- 組合13：專業「物理治療學」, JS code「JS3636」, 學科偏向「理科」
- 組合14：專業「設計學」, JS code「JS3866」, 學科偏向「文科」
- 組合15：專業「傳理學」, JS code「JS2310」, 學科偏向「文科」

【各類題型極度嚴格填寫規則】：

1. 基礎文字題：
- 「姓名」：隨機生成姓氏與名字，最後一個字強制為大寫字母「X」（如「李小X」、「張X」）。
- 「入學年份」及「年級」：如果是大學生，請在「2023~2026」及「Year 1~4」中合理選擇；如果是畢業生，這兩題請一律填寫「其他:」。
- 「畢業生五大職業(不清楚請填NA)」：大約一半機率填「NA」，一半機率根據專業列出 3-5 個具體職業。

2. [畢業生填寫] 專屬題邏輯（極度重要）：
- 若身分是「在校大學生」：所有標題包含「[畢業生填寫]」的欄位，【請直接省略該 Key，不要出現在 JSON 中】，絕對不要填空字串。
- 若身分是「畢業生」：請根據你抽到的專業，合理填寫行業、職位、月薪（純數字）、經驗等。

3. 海量的「0-10分」評分題（極度重要）：
- 只要題目後方有「(0:完全不同意; 10:完全同意)」，請【必須輸出純數字字串 "0" 到 "10"】。
- 請注意，網格題已被合併為「主題目 - 子題目」的形式（例如：「我感興趣的領域 (0完全不同意; 10完全同意) - 電腦科技」）。請根據你抽到的專業給分。
- 「物理科主題 (只限物理科學生)」開頭的題目：若抽到的不是理科/工程，【請直接省略該 Key，不要出現在 JSON 中】。

4. DSE成績評分矩陣：
- 題目形式為「DSE成績（請漏空沒修讀科目） - 中國語文」。
- 請為 4 科核心及隨機 2 科選修填寫「1」、「2」、「3」、「4」、「5」、「5*」或「5**」。
- 其餘沒修讀科目【請直接省略該 Key，不要出現在 JSON 中】。

5. 其他單選題：
- 「我的兄弟姊妹數目」：從 "0", "1", "2", "3" 中選一個。
- 單選題請確保選項文字一字不差。
"""

with st.form("auto_form"):
    form_url = st.text_input(
        "Google 表單連結 (必須是 /viewform 結尾)", 
        placeholder="https://docs.google.com/forms/d/e/.../viewform"
    )
    
    persona = st.text_area("填寫方向與偏好設定", value=default_persona, height=300)
    
    col1, col2 = st.columns(2)
    with col1:
        target_count = st.number_input("需要生成的問卷數量", min_value=1, max_value=500, value=3)
    with col2:
        duration_hours = st.number_input("設定要在幾小時內陸續填寫", min_value=0.0, max_value=72.0, value=0.0, step=0.5, help="輸入0代表全速提交。")
    
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
                st.write("🔍 正在解析表單結構並繞過防護機制...")
                questions = parse_google_form(form_url)
                st.write(f"✅ 成功解析出 {len(questions)} 道題目！")
                
                st.write("🧠 正在呼叫 AI 生成模擬數據...")
                answers = generate_answers(questions, persona, target_count)
                
                if len(answers) > 0:
                    st.write("🚀 正在啟動提交程序...")
                    success_count = submit_form(form_url, questions, answers, duration_hours)
                    
                    if success_count > 0:
                        status.update(label=f"任務完成！成功提交 {success_count}/{target_count} 份問卷。", state="complete", expanded=False)
                        st.balloons()
                    else:
                        status.update(label="提交失敗，請檢查下方紅框中的資料格式錯誤。", state="error")
                else:
                    status.update(label="未成功生成任何數據。", state="error")
                    
            except Exception as e:
                status.update(label="執行發生錯誤", state="error")
                st.error(f"錯誤詳情：{str(e)}")
