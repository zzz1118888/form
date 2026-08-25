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
        為我生成 1 份問卷答案。
        
        問卷題目如下：
        {questions_str}
        
        【填寫邏輯規則】：
        1. 保持人設一致：請根據背景資訊推斷。
        2. 鍵值匹配：返回的 JSON 鍵值(Key)必須「完全等於」上述列表中的題目名稱。
        3. 請以 JSON 陣列格式返回。絕對不要輸出任何解釋文字。
        """
        
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                response = CLIENT.chat.completions.create(
                    model="glm-4-flash",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.8,
                    max_tokens=8192
                )
                
                result_text = response.choices[0].message.content
                result_text = result_text.replace("```json", "").replace("```", "").strip()
                batch_answers = json.loads(result_text)
                
                if isinstance(batch_answers, dict):
                    batch_answers = [batch_answers]
                    
                if isinstance(batch_answers, list):
                    all_answers.extend(batch_answers)
                    break 
                else:
                    raise ValueError("JSON 格式不是陣列或字典")
                    
            except Exception as e:
                error_msg = str(e)
                if attempt < max_retries - 1:
                    wait_time = 3 + attempt * 2 
                    st.warning(f"⚠️ 智譜伺服器暫時無回應，{wait_time} 秒後重試...")
                    time.sleep(wait_time)
                else:
                    st.error(f"❌ 第 {i+1} 份生成連續失敗，已略過。錯誤詳情：{error_msg}")
        
        current_progress = min(1.0, (i + current_count) / total_count)
        progress_bar.progress(current_progress)
        time.sleep(1) 
        
    status_text.text(f"✅ AI 數據生成完畢！共準備好 {len(all_answers)} 份資料。")
    return all_answers

# ================= 模組三：並發提交模組 (真人翻頁狀態機版) =================
def submit_form(form_url, parsed_questions, answers, duration_hours):
    post_url = form_url.replace("/viewform", "/formResponse")
    success_count = 0
    total_seconds = duration_hours * 3600
    avg_wait = total_seconds / len(answers) if len(answers) > 0 else 0
    wait_status = st.empty()
    
    for idx, answer_set in enumerate(answers):
        # 建立專屬會話，模擬真實瀏覽器
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8'
        })
        
        # 1. 第一步：先拿一把全新乾淨的鑰匙 (fbzx)
        init_res = session.get(form_url)
        fbzx_match = re.search(r'name="fbzx"\s+value="([^"]*)"', init_res.text)
        current_fbzx = fbzx_match.group(1) if fbzx_match else ""
        
        # 拍扁 JSON 並清洗不合法的陣列格式
        flat_answers = {}
        for key, value in answer_set.items():
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    flat_answers[f"{key} - {sub_key}"] = str(sub_value)
            elif isinstance(value, list):
                flat_answers[key] = ", ".join([str(v) for v in value])
            else:
                flat_answers[key] = str(value)
                
        # 準備萬能資料包 (準備好所有題目的答案，Google要哪頁我們就給哪頁)
        base_payload = {}
        for q in parsed_questions:
            q_title = q['title']
            answer_val = None
            if q_title in flat_answers:
                answer_val = flat_answers[q_title]
            else:
                for ai_key, ai_val in flat_answers.items():
                    clean_q = re.sub(r'[^\w\s]', '', q_title)
                    clean_ai = re.sub(r'[^\w\s]', '', ai_key)
                    if clean_q and clean_ai and (clean_q in clean_ai or clean_ai in clean_q):
                        answer_val = ai_val
                        break
            
            if answer_val is not None and str(answer_val).strip() != "":
                answer_str = str(answer_val)
                if answer_str.startswith("[") and answer_str.endswith("]"): answer_str = "NA"
                if re.search(r'\([WSCIRE]\)', q_title) and not answer_str.isdigit(): answer_str = str(random.randint(4, 8))
                if "入學年份" in q_title and answer_str not in ["2023", "2024", "2025", "2026", "其他:"]: answer_str = random.choice(["2023", "2024", "2025", "2026"])
                if "年級" in q_title and answer_str not in ["Year 1", "Year 2", "Year 3", "Year 4", "其他:"]: answer_str = random.choice(["Year 1", "Year 2", "Year 3", "Year 4"])
                base_payload[q['entry_id']] = answer_str
            else:
                # 無差別安全預設值填滿
                if "五大職業" in q_title: base_payload[q['entry_id']] = "NA"
                elif "(0" in q_title and "10" in q_title: base_payload[q['entry_id']] = str(random.randint(4, 8))
                elif "兄弟姊妹數目" in q_title: base_payload[q['entry_id']] = str(random.choice([0, 1, 2]))
                elif re.search(r'\([WSCIRE]\)', q_title): base_payload[q['entry_id']] = str(random.randint(4, 8))
                elif "月薪" in q_title or "收入" in q_title: base_payload[q['entry_id']] = "20000"
                elif "時間" in q_title or "經驗" in q_title or "就業率" in q_title: base_payload[q['entry_id']] = "90"
                elif "行業" in q_title or "職能" in q_title or "職位名稱" in q_title: base_payload[q['entry_id']] = "NA"
                elif "DSE成績" in q_title: base_payload[q['entry_id']] = str(random.randint(3, 5))
                else: base_payload[q['entry_id']] = "NA"

        # 🔥 狀態機啟動：自動按「下一頁」直到成功
        current_page_history = "0"
        current_draft_response = None
        is_success = False
        
        for step in range(15): # 最多支援跳 15 頁
            step_payload = base_payload.copy()
            step_payload['pageHistory'] = current_page_history
            step_payload['fvv'] = "1"
            if current_fbzx: step_payload['fbzx'] = current_fbzx
            if current_draft_response: step_payload['draftResponse'] = current_draft_response
            
            res = session.post(post_url, data=step_payload)
            
            # 如果成功提交，網頁會出現完成的畫面，且不會再有表單數據區塊
            if "FB_PUBLIC_LOAD_DATA_" not in res.text:
                is_success = True
                break
                
            # 解析下一頁的密碼與進度
            new_ph_match = re.search(r'name="pageHistory"\s+value="([^"]*)"', res.text)
            new_fbzx_match = re.search(r'name="fbzx"\s+value="([^"]*)"', res.text)
            new_draft_match = re.search(r'name="draftResponse"\s+value="([^"]*)"', res.text)
            
            new_ph = new_ph_match.group(1) if new_ph_match else current_page_history
            
            # 如果頁碼沒有前進，代表我們被擋在這一頁了
            if new_ph == current_page_history:
                error_msgs = re.findall(r'data-error-message="([^"]+)"', res.text)
                error_msgs = list(set([e for e in error_msgs if e.strip()]))
                st.error(f"第 {idx+1} 份問卷遭遇「假成功」！(卡在表單的第 {current_page_history} 頁)")
                
                if error_msgs:
                    st.warning(f"🚨 Google 終於說出原因了！錯誤提示：【 {', '.join(error_msgs)} 】")
                else:
                    st.warning("🚨 伺服器拒絕前進，但無具體錯誤訊息（可能選項格式還是不合）。")
                    
                with st.expander("點擊查看在該頁送出的資料詳情"):
                    st.json(step_payload)
                break
                
            # 成功換頁，更新進度
            current_page_history = new_ph
            if new_fbzx_match: current_fbzx = new_fbzx_match.group(1)
            if new_draft_match: current_draft_response = html.unescape(new_draft_match.group(1))

        if is_success:
            success_count += 1
            if idx < len(answers) - 1:
                if duration_hours > 0:
                    wait_time = random.uniform(avg_wait * 0.5, avg_wait * 1.5)
                    wait_status.info(f"⏳ 第 {idx+1} 份已提交，隨機等待 {int(wait_time)} 秒...")
                    time.sleep(wait_time)
                else:
                    time.sleep(0.5)
        else:
            if not is_success and step == 14:
                st.error("跳頁次數過多，判定為無窮迴圈失敗。")
                
    wait_status.empty()
    return success_count

# ================= Web UI 設計 =================
st.set_page_config(page_title="自動問卷生成系統", page_icon="🤖")
st.title("🤖 Google Form 自動填寫系統")
st.markdown("輸入 Google 表單連結與目標人設，系統將自動生成並批量提交資料。")

default_persona = """你現在是一位香港八大院校的受訪者，正在填寫一份關於升學與職涯意向的大型深度調查問卷。

【重要身分設定】：
身分請隨機決定是「在校大學生」還是「已全職工作3個月以上的畢業生」。

【核心身分與代碼綁定】：
- 組合1：學科全名填寫「理學」, JS code填寫「JS6901」
- 組合2：學科全名填寫「內外全科醫學」, JS code填寫「JS6456」
- 組合3：學科全名填寫「工程學」, JS code填寫「JS6963」
- 組合4：學科全名填寫「工商管理學」, JS code填寫「JS6755」
- 組合5：學科全名填寫「傳理學」, JS code填寫「JS2310」

【各類題型極度嚴格填寫規則】：
1. 「姓名」：最後一個字強制為大寫字母「X」（如「張小X」）。
2. 【入學年份】只能選擇輸出：2023、2024、2025 或 2026。
3. 【年級】只能選擇輸出：Year 1、Year 2、Year 3 或 Year 4。
4. ⚠️「畢業生五大職業(不清楚請填NA)」：請直接填寫字串 "NA"，絕對不可以輸出陣列或括號。
5. DSE成績評分矩陣：為所有科目隨機填寫「3」到「5**」。
"""

with st.form("auto_form"):
    form_url = st.text_input("Google 表單連結 (必須是 /viewform 結尾)")
    persona = st.text_area("填寫方向與偏好設定", value=default_persona, height=300)
    col1, col2 = st.columns(2)
    with col1:
        target_count = st.number_input("需要生成的問卷數量", min_value=1, max_value=500, value=3)
    with col2:
        duration_hours = st.number_input("設定要在幾小時內陸續填寫", min_value=0.0, max_value=72.0, value=0.0, step=0.5)
    submitted = st.form_submit_button("開始生成並提交")

if submitted:
    if not form_url or "/viewform" not in form_url:
        st.error("連結錯誤！請確保包含 /viewform")
    else:
        with st.status("任務執行中...", expanded=True) as status:
            try:
                st.write("🔍 正在解析表單結構...")
                questions = parse_google_form(form_url)
                st.write(f"✅ 成功解析出 {len(questions)} 道題目！")
                
                st.write("🧠 正在呼叫 AI 生成模擬數據...")
                answers = generate_answers(questions, persona, target_count)
                
                if len(answers) > 0:
                    st.write("🚀 正在啟動「真人翻頁模擬器」提交程序...")
                    success_count = submit_form(form_url, questions, answers, duration_hours)
                    if success_count > 0:
                        status.update(label=f"任務完成！成功提交 {success_count}/{target_count} 份。", state="complete", expanded=False)
                        st.balloons()
                    else:
                        status.update(label="提交失敗，資料被表單阻擋。", state="error")
                else:
                    status.update(label="未成功生成任何數據。", state="error")
            except Exception as e:
                status.update(label="執行發生錯誤", state="error")
                st.error(f"錯誤詳情：{str(e)}")
