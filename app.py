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

# ================= 模組一：自動解析表單結構與官方選項 =================
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
    page_index = 0
    
    try:
        questions_data = data[1][1]
        for q in questions_data:
            try:
                item_type = q[3]
                if item_type == 8:  # 分頁符號
                    page_index += 1
                    continue
                    
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
                        
                        # 精準抽取官方選項，並過濾掉容易報錯的「其他」選項
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
                            "options": options,
                            "page": page_index
                        })
            except (IndexError, TypeError):
                continue
    except (IndexError, TypeError) as e:
        raise ValueError(f"解析題目結構失敗：{e}")
        
    return parsed_questions

# ================= 模組二：智譜 API (穩定版) =================
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
        為我生成 1 份 JSON 格式的基本資料。
        
        你 **只能** 輸出以下 5 個 Key，絕對禁止增加其他欄位：
        - "姓名（不用填寫姓名最後一個字，如陳大X）"
        - "大學學科全名"
        - "大學學系編號"
        - "入學年份"
        - "年級"
        
        請只輸出這 5 個欄位的 JSON 陣列，例如 [{{"姓名...": "王小X", ...}}]。
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
                if attempt < max_retries - 1:
                    time.sleep(3 + attempt * 2)
                else:
                    st.error(f"❌ 第 {i+1} 份生成連續失敗。")
        
        current_progress = min(1.0, (i + current_count) / total_count)
        progress_bar.progress(current_progress)
        time.sleep(1) 
        
    status_text.text(f"✅ AI 數據生成完畢！共準備好 {len(all_answers)} 份資料。")
    return all_answers

# ================= 模組三：並發提交模組 (全覆蓋無敵裝甲版) =================
def submit_form(form_url, parsed_questions, answers, duration_hours):
    post_url = form_url.replace("/viewform", "/formResponse")
    success_count = 0
    total_seconds = duration_hours * 3600
    avg_wait = total_seconds / len(answers) if len(answers) > 0 else 0
    wait_status = st.empty()
    
    for idx, answer_set in enumerate(answers):
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8'
        })
        
        flat_answers = {}
        for key, value in answer_set.items():
            if isinstance(value, dict):
                for sub_key, sub_value in value.items(): flat_answers[f"{key} - {sub_key}"] = str(sub_value)
            elif isinstance(value, list): flat_answers[key] = ", ".join([str(v) for v in value])
            else: flat_answers[key] = str(value)
                
        # 🔥 全面接管：保證表單上的每一個洞都被填滿！
        base_payload = {}
        for q in parsed_questions:
            q_title = q['title']
            
            # 優先比對 AI 生成的核心 5 題
            ai_val = None
            for ai_key, ai_val_iter in flat_answers.items():
                if re.sub(r'[^\w\s]', '', q_title) in re.sub(r'[^\w\s]', '', ai_key) or re.sub(r'[^\w\s]', '', ai_key) in re.sub(r'[^\w\s]', '', q_title):
                    ai_val = str(ai_val_iter).strip()
                    break
            
            # 1. 該題「有選項」 (例如 DSE、年級、0-10評分矩陣)
            if q['options']:
                if ai_val and any(ai_val in opt for opt in q['options']):
                    base_payload[q['entry_id']] = ai_val
                elif "入學年份" in q_title:
                    base_payload[q['entry_id']] = random.choice([o for o in q['options'] if "20" in o] or q['options'])
                elif "年級" in q_title:
                    base_payload[q['entry_id']] = random.choice([o for o in q['options'] if "Year" in o] or q['options'])
                elif "DSE成績" in q_title:
                    # 破解矩陣必填地雷：不管有沒有考，42 科全部隨機給 3~5 分！
                    safe_dse = [o for o in q['options'] if o in ["3", "4", "5", "5*", "5**"]]
                    base_payload[q['entry_id']] = random.choice(safe_dse if safe_dse else q['options'])
                else:
                    # 其他所有矩陣與選擇題，無差別填滿
                    base_payload[q['entry_id']] = random.choice(q['options'])
            
            # 2. 該題「無選項」 (文字輸入框)
            else:
                if ai_val:
                    base_payload[q['entry_id']] = ai_val
                elif "姓名" in q_title or "全名" in q_title: base_payload[q['entry_id']] = "張大X"
                elif "編號" in q_title: base_payload[q['entry_id']] = "JS6963"
                elif "月薪" in q_title or "收入" in q_title: base_payload[q['entry_id']] = "20000"
                elif "時間" in q_title or "經驗" in q_title or "就業率" in q_title: base_payload[q['entry_id']] = "1"
                elif "行業" in q_title or "職能" in q_title or "職位名稱" in q_title: base_payload[q['entry_id']] = "資訊科技"
                else: base_payload[q['entry_id']] = "NA"

        # 啟動自動翻頁狀態機
        init_res = session.get(form_url)
        current_html = init_res.text
        is_success = False
        current_page_history = "0"
        
        for step in range(15):
            fbzx_match = re.search(r'name="fbzx"\s+value="([^"]*)"', current_html)
            current_fbzx = fbzx_match.group(1) if fbzx_match else ""
            
            draft_match = re.search(r'name="draftResponse"\s+value="([^"]*)"', current_html)
            current_draft_response = html.unescape(draft_match.group(1)) if draft_match else ""
            
            current_page_index = int(current_page_history.split(',')[-1])
            
            step_payload = {
                "pageHistory": current_page_history,
                "fvv": "1"
            }
            if current_fbzx: step_payload['fbzx'] = current_fbzx
            if current_draft_response: step_payload['draftResponse'] = current_draft_response
            
            # 將這頁的題目全部塞入
            for q in parsed_questions:
                if q['page'] == current_page_index and q['entry_id'] in base_payload:
                    step_payload[q['entry_id']] = base_payload[q['entry_id']]
            
            res = session.post(post_url, data=step_payload)
            
            if "FB_PUBLIC_LOAD_DATA_" not in res.text:
                is_success = True
                break
                
            new_ph_match = re.search(r'name="pageHistory"\s+value="([^"]*)"', res.text)
            new_ph = new_ph_match.group(1) if new_ph_match else current_page_history
            
            if new_ph == current_page_history:
                error_msgs = re.findall(r'data-error-message="([^"]+)"', res.text)
                error_msgs = list(set([e for e in error_msgs if e.strip()]))
                st.error(f"第 {idx+1} 份問卷遭遇「假成功」！")
                if error_msgs:
                    st.warning(f"🚨 Google 拒絕原因：【 {', '.join(error_msgs)} 】")
                else:
                    st.warning("🚨 伺服器拒絕前進。所有欄位均已強制填滿安全預設值。")
                with st.expander("點擊查看這頁送出的無敵裝甲版資料"):
                    st.json(step_payload)
                break
                
            current_page_history = new_ph
            current_html = res.text

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

default_persona = """你現在是一位香港八大院校的受訪者，正在填寫一份關於升學與職涯意向的調查。

【核心身分與代碼綁定】：
- 組合1：學科全名填寫「理學」, JS code填寫「JS6901」
- 組合2：學科全名填寫「內外全科醫學」, JS code填寫「JS6456」
- 組合3：學科全名填寫「工程學」, JS code填寫「JS6963」
- 組合4：學科全名填寫「工商管理學」, JS code填寫「JS6755」
- 組合5：學科全名填寫「傳理學」, JS code填寫「JS2310」
"""

with st.form("auto_form"):
    form_url = st.text_input("Google 表單連結 (必須是 /viewform 結尾)")
    persona = st.text_area("填寫方向與偏好設定", value=default_persona, height=150)
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
                
                st.write("🧠 正在呼叫 AI 生成核心數據...")
                answers = generate_answers(questions, persona, target_count)
                
                if len(answers) > 0:
                    st.write("🚀 正在啟動「全覆蓋無敵裝甲版」提交程序...")
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
