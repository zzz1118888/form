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

# ================= 模組二：智譜 API (多樣化生成版) =================
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
        
        【極度嚴格限制】：
        1. 請從 5 個科系組合中「隨機」挑選，確保每次生成的科系盡量不同。
        2. 姓名請隨機生成不同的姓氏。
        3. 你 **只能** 輸出以下 5 個 Key：
        - "姓名（不用填寫姓名最後一個字，如陳大X）"
        - "大學學科全名"
        - "大學學系編號"
        - "入學年份"
        - "年級" (如果是學生請填寫 Year 1 到 Year 4，如果是已畢業工作的人，請直接填寫「畢業生」)
        
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

# ================= 模組三：高落差亂數引擎與精準身分隔離 =================
def get_smart_score(q_title, major, options):
    # 打破平庸，0到10分全頻譜大亂跳
    score = random.choice([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    
    # 科系極端偏好 (創造真實的波峰波谷)
    if "理學" in major or "工程" in major:
        if any(k in q_title for k in ["電腦", "邏輯", "科學", "力學", "電學", "工程", "數學"]): score = random.choice([8, 9, 10])
        elif any(k in q_title for k in ["文字", "藝術", "音樂", "繪畫"]): score = random.choice([0, 1, 2])
    elif "工商" in major or "管理" in major:
        if any(k in q_title for k in ["財經", "領袖", "商業", "高薪", "社交", "管理"]): score = random.choice([8, 9, 10])
        elif any(k in q_title for k in ["大自然", "物理"]): score = random.choice([0, 1, 2])
    elif "傳理" in major or "文" in major:
        if any(k in q_title for k in ["語言", "閱讀", "社交", "創作", "文字", "媒體"]): score = random.choice([8, 9, 10])
        elif any(k in q_title for k in ["數學", "程式", "工程", "力學"]): score = random.choice([0, 1, 2])
    elif "醫" in major:
        if any(k in q_title for k in ["科學", "病人", "醫藥", "生物", "價值"]): score = random.choice([8, 9, 10])
        elif any(k in q_title for k in ["物理", "程式"]): score = random.choice([2, 3, 4])
        
    if any(k in q_title for k in ["壓力低", "工作與生活平衡", "準時下班", "自由", "快樂"]):
        score = random.choice([8, 9, 10])
        
    score_str = str(score)
    if options:
        if score_str in options: return score_str
        return random.choice(options)
    return score_str


def submit_form(form_url, parsed_questions, answers, duration_hours):
    post_url = form_url.replace("/viewform", "/formResponse")
    success_count = 0
    total_seconds = duration_hours * 3600
    avg_wait = total_seconds / len(answers) if len(answers) > 0 else 0
    wait_status = st.empty()
    
    dse_core = ["中國語文", "英國語文", "數學", "通識教育"]
    dse_electives_pool = ["經濟", "物理", "化學", "生物", "地理", "歷史", "資訊及通訊科技", "企業、會計與財務概論"]
    
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
            
        gen_major = ""
        gen_grade = ""
        for k, v in flat_answers.items():
            if "學科" in k or "學系" in k:
                gen_major = str(v)
            if "年級" in k:
                gen_grade = str(v)
                
        # 判斷是否為畢業生
        is_graduate = "畢業" in gen_grade or "grad" in gen_grade.lower()
                
        # DSE 絕對發牌系統
        my_dse_subjects = dse_core + random.sample(dse_electives_pool, 2)
        dse_cards = ["3", "4", "4", "5", "5*", "5**"] 
        random.shuffle(dse_cards) 
        my_dse_score_map = dict(zip(my_dse_subjects, dse_cards)) 
                
        base_payload = {}
        for q in parsed_questions:
            q_title = q['title']
            
            # 🔥 身分閘門：如果是在校學生，直接跳過所有帶有 [畢業生填寫] 的題目！
            if not is_graduate and "[畢業生填寫]" in q_title:
                continue
            
            ai_val = None
            for ai_key, ai_val_iter in flat_answers.items():
                if re.sub(r'[^\w\s]', '', q_title) in re.sub(r'[^\w\s]', '', ai_key) or re.sub(r'[^\w\s]', '', ai_key) in re.sub(r'[^\w\s]', '', q_title):
                    ai_val = str(ai_val_iter).strip()
                    break
            
            if q['options']:
                if ai_val and any(ai_val in opt for opt in q['options']):
                    base_payload[q['entry_id']] = ai_val
                elif "入學年份" in q_title:
                    base_payload[q['entry_id']] = random.choice([o for o in q['options'] if "20" in o] or q['options'])
                elif "年級" in q_title:
                    base_payload[q['entry_id']] = random.choice([o for o in q['options'] if "Year" in o] or q['options'])
                elif "DSE成績" in q_title:
                    matched_subj = next((s for s in my_dse_subjects if s in q_title), None)
                    if matched_subj:
                        grade = my_dse_score_map[matched_subj]
                        if grade in q['options']:
                            base_payload[q['entry_id']] = grade
                        else:
                            safe_dse = [o for o in q['options'] if o in ["3", "4", "5", "5*", "5**"]]
                            base_payload[q['entry_id']] = random.choice(safe_dse if safe_dse else q['options'])
                else:
                    if any(x in q['options'] for x in ["0", "1", "2", "3", "7", "8", "9", "10"]):
                        base_payload[q['entry_id']] = get_smart_score(q_title, gen_major, q['options'])
                    else:
                        base_payload[q['entry_id']] = random.choice(q['options'])
            else:
                if ai_val:
                    base_payload[q['entry_id']] = ai_val
                elif "五大職業" in q_title: 
                    # 五大職業對所有人都必填，在校生填 NA，畢業生填隨機職業
                    base_payload[q['entry_id']] = "NA" if not is_graduate else random.choice(["資訊科技", "金融", "教育", "工程"])
                elif "姓名" in q_title or "全名" in q_title: base_payload[q['entry_id']] = "張大X"
                elif "編號" in q_title: base_payload[q['entry_id']] = "JS6963"
                elif "月薪" in q_title or "收入" in q_title: base_payload[q['entry_id']] = str(random.randint(18000, 28000))
                elif "時間" in q_title or "經驗" in q_title or "就業率" in q_title: base_payload[q['entry_id']] = "1"
                elif "行業" in q_title or "職能" in q_title or "職位名稱" in q_title: base_payload[q['entry_id']] = random.choice(["資訊科技", "工程", "市場營銷", "金融"])
                else: base_payload[q['entry_id']] = "NA"

        # 提交程序
        init_res = session.get(form_url)
        fbzx_match = re.search(r'name="fbzx"\s+value="([^"]*)"', init_res.text)
        current_fbzx = fbzx_match.group(1) if fbzx_match else ""
        
        step_payload = {"pageHistory": "0", "fvv": "1"}
        if current_fbzx: step_payload['fbzx'] = current_fbzx
        step_payload.update(base_payload)
        
        res = session.post(post_url, data=step_payload)
        
        error_msgs = re.findall(r'data-error-message="([^"]+)"', res.text)
        error_msgs = list(set([e for e in error_msgs if e.strip()]))
        
        is_success = False
        if not error_msgs and ("formResponse" in res.url or 'class="vHW8K"' in res.text or 'freebirdFormviewerViewResponseConfirmationMessage' in res.text):
            is_success = True
        elif not error_msgs:
            is_success = True

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
            st.error(f"第 {idx+1} 份問卷提交異常！")
            if error_msgs:
                st.warning(f"🚨 Google 拒絕原因：【 {', '.join(error_msgs)} 】")
                
    wait_status.empty()
    return success_count

# ================= Web UI 設計 =================
st.set_page_config(page_title="自動問卷生成系統", page_icon="🤖")
st.title("🤖 Google Form 自動填寫系統")
st.markdown("輸入 Google 表單連結與目標人設，系統將自動生成並批量提交資料。")

default_persona = """你現在是一位香港八大院校的受訪者，正在填寫一份關於升學與職涯意向的調查。
身分請隨機決定是「在校大學生」還是「已全職工作3個月以上的畢業生」。

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
                    st.write("🚀 正在啟動「精準身分隔離版」提交程序...")
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
