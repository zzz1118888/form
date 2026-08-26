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
                result_text = result_text.replace("```json", "").replace("```", "").strip()
                batch_answers = json.loads(result_text)
                
                if isinstance(batch_answers, dict):
                    batch_answers = [batch_answers]
                if isinstance(batch_answers, list):
                    all_answers.extend(batch_answers[:current_count])
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
    return all_answers[:total_count] 

# ================= 模組三：高落差亂數引擎與精準身分隔離 =================
def get_smart_score(q_title, major, options):
    score = random.choice([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    
    if "理學" in major or "工程" in major or "計算機" in major or "計算" in major or "數據" in major:
        if any(k in q_title for k in ["電腦", "邏輯", "科學", "力學", "電學", "工程", "數學"]): score = random.choice([8, 9, 10])
        elif any(k in q_title for k in ["文字", "藝術", "音樂", "繪畫"]): score = random.choice([0, 1, 2])
    elif "工商" in major or "管理" in major or "會計" in major or "金融" in major or "經濟" in major:
        if any(k in q_title for k in ["財經", "領袖", "商業", "高薪", "社交", "管理"]): score = random.choice([8, 9, 10])
        elif any(k in q_title for k in ["大自然", "物理"]): score = random.choice([0, 1, 2])
    elif "傳理" in major or "文" in major or "時裝" in major or "語文" in major or "翻譯" in major:
        if any(k in q_title for k in ["語言", "閱讀", "社交", "創作", "文字", "媒體", "繪畫"]): score = random.choice([8, 9, 10])
        elif any(k in q_title for k in ["數學", "程式", "工程", "力學"]): score = random.choice([0, 1, 2])
    elif "醫" in major or "護理" in major or "藥劑" in major or "牙醫" in major or "獸醫" in major:
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
        gen_year = ""
        
        for k, v in flat_answers.items():
            if "學科" in k or "學系" in k: gen_major = str(v)
            if "年級" in k: gen_grade = str(v)
            if "年份" in k: gen_year = str(v)
                
        is_graduate = "畢業" in gen_grade or "grad" in gen_grade.lower()
        
        # 強制接管邏輯：確保入學年份與年級 100% 精準對應
        if not is_graduate:
            if "2026" in gen_year: gen_grade = "Year 1"
            elif "2025" in gen_year: gen_grade = "Year 2"
            elif "2024" in gen_year: gen_grade = "Year 3"
            elif "2023" in gen_year: gen_grade = "Year 4"
            elif "Year 1" in gen_grade: gen_year = "2026"
            elif "Year 2" in gen_grade: gen_year = "2025"
            elif "Year 3" in gen_grade: gen_year = "2024"
            elif "Year 4" in gen_grade: gen_year = "2023"
            else:
                gen_year = random.choice(["2023", "2024", "2025", "2026"])
                year_map = {"2026": "Year 1", "2025": "Year 2", "2024": "Year 3", "2023": "Year 4"}
                gen_grade = year_map[gen_year]
                
            for k in flat_answers.keys():
                if "年級" in k: flat_answers[k] = gen_grade
                if "年份" in k: flat_answers[k] = gen_year
                
        my_dse_subjects = dse_core + random.sample(dse_electives_pool, 2)
        dse_cards = ["3", "4", "4", "5", "5*", "5**"] 
        random.shuffle(dse_cards) 
        my_dse_score_map = dict(zip(my_dse_subjects, dse_cards)) 
                
        base_payload = {}
        for q in parsed_questions:
            q_title = q['title']
            
            # 🔥 終極在校生黑名單：移除了容易誤殺的「請選擇」，保留絕對特徵詞
            if not is_graduate:
                grad_keywords = [
                    "[畢業生填寫]", "五大職業", "接駁廣泛", "薪酬掛", "輕鬆度過", 
                    "大過天", "大學品牌", "成為專業人士", "(W)", "(S)", "(C)", "(I)", "(R)", "(E)"
                ]
                if any(kw in q_title for kw in grad_keywords):
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
                    base_payload[q['entry_id']] = gen_year if gen_year in q['options'] else random.choice([o for o in q['options'] if "20" in o] or q['options'])
                elif "年級" in q_title:
                    base_payload[q['entry_id']] = gen_grade if gen_grade in q['options'] else random.choice([o for o in q['options'] if "Year" in o] or q['options'])
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
                    base_payload[q['entry_id']] = random.choice(["資訊科技", "金融", "教育", "工程", "市場策劃", "公營機構"])
                elif "姓名" in q_title or "全名" in q_title: base_payload[q['entry_id']] = "張大X"
                elif "編號" in q_title: base_payload[q['entry_id']] = "JS6963"
                elif "月薪" in q_title or "收入" in q_title: base_payload[q['entry_id']] = str(random.randint(18000, 28000))
                elif "時間" in q_title or "經驗" in q_title or "就業率" in q_title: base_payload[q['entry_id']] = "1"
                elif "行業" in q_title or "職能" in q_title or "職位名稱" in q_title: base_payload[q['entry_id']] = random.choice(["資訊科技", "工程", "市場營銷", "金融"])
                else: base_payload[q['entry_id']] = "NA"

        init_res = session.get(form_url)
        fbzx_match = re.search(r'name="fbzx"\s+value="([^"]*)"', init_res.text)
        current_fbzx = fbzx_match.group(1) if fbzx_match else ""
        
        step_payload = {"pageHistory": "0", "fvv": "1"}
        if current_fbzx: step_payload['fbzx'] = current_fbzx
        step_payload.update(base_payload)
        
        # 執行 POST
        res = session.post(post_url, data=step_payload)
        
        # 驗證成功關鍵字
        success_keywords = ['freebirdFormviewerViewResponseConfirmationMessage', '已記錄你的回覆', 'Your response has been recorded', '已經收到']
        is_success = any(kw in res.text for kw in success_keywords)

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
            st.error(f"❌ 第 {idx+1} 份問卷被 Google 拒絕！身分：{'畢業生' if is_graduate else '在校生'}")
            required_errors = re.findall(r'data-error-message="([^"]+)"', res.text)
            if required_errors:
                st.warning(f"Google 報錯訊息：{list(set(required_errors))}")
            else:
                st.warning("⚠️ Google 擋下表單，這代表你表單裡的「矩陣評分題」仍然設為「必填」。在校生跳過不填就會被阻擋，請務必去 Google 表單後台關閉該題的必填選項！")
                
    wait_status.empty()
    return success_count

# ================= Web UI 設計 =================
st.set_page_config(page_title="自動問卷生成系統", page_icon="🤖")
st.title("🤖 Google Form 自動填寫系統")
st.markdown("輸入 Google 表單連結與目標人設，系統將自動生成並批量提交資料。")

# 🔥 核心升級：將 408 組真實 JUPAS 數據寫入 AI 大腦，強制邏輯關聯
default_persona = """你現在是一位香港大專院校的受訪者，正在填寫一份關於升學與職涯意向的調查。
身分請隨機決定是「在校大學生」還是「已全職工作3個月以上的畢業生」。

【極度嚴格的欄位邏輯】：
1. 入學年份與年級必須嚴格對應：
   - 入學年份 2026 對應 年級「Year 1」
   - 入學年份 2025 對應 年級「Year 2」
   - 入學年份 2024 對應 年級「Year 3」
   - 入學年份 2023 對應 年級「Year 4」
   - 若為畢業生，入學年份請隨機填寫 2019~2022，年級填寫「畢業生」。

【核心身分與代碼綁定】（請務必從以下 408 個真實組合中「隨機」挑選一組）：
- 組合1：學科全名「建築學文學士」, JS code「JS6004」
- 組合2：學科全名「理學士(測量學)」, JS code「JS6016」
- 組合3：學科全名「園境學文學士」, JS code「JS6028」
- 組合4：學科全名「文學士(城市研究)」, JS code「JS6042」
- 組合5：學科全名「文學士」, JS code「JS6054」
- 組合6：學科全名「文學士及教育學士(語文教育)-英文教育」, JS code「JS6066」
- 組合7：學科全名「文學士及法學士」, JS code「JS6078」
- 組合8：學科全名「文學士及教育學士(語文教育)-中文教育」, JS code「JS6080」
- 組合9：學科全名「教育學士(幼兒教育及特殊教育)」, JS code「JS6092」
- 組合10：學科全名「牙醫學士」, JS code「JS6107」
- 組合11：學科全名「教育學士及理學士」, JS code「JS6119」
- 組合12：學科全名「理學士(言語及語言病理學)」, JS code「JS6157」
- 組合13：學科全名「計算與數據科學(港滬科技菁英)」, JS code「JS6200」
- 組合14：學科全名「文理學士(應用人工智能)」, JS code「JS6224」
- 組合15：學科全名「文理學士(設計+)」, JS code「JS6236」
- 組合16：學科全名「文理學士(金融科技)」, JS code「JS6248」
- 組合17：學科全名「文理學士(環球衛生及發展)」, JS code「JS6250」
- 組合18：學科全名「文學士(全球創意產業)」, JS code「JS6274」
- 組合19：學科全名「文學士(人文及數碼科技)」, JS code「JS6286」
- 組合20：學科全名「文學士及工學學士(人工智能及數據科學)」, JS code「JS6298」
- 組合21：學科全名「工學學士精英課程」, JS code「JS6303」
- 組合22：學科全名「工學學士(數據與系統工程)」, JS code「JS6315」
- 組合23：學科全名「工學學士(機械工程)」, JS code「JS6339」
- 組合24：學科全名「工學學士(土木工程)」, JS code「JS6353」
- 組合25：學科全名「工學學士與人工智能理學碩士聯合課程」, JS code「JS6377」
- 組合26：學科全名「法學士」, JS code「JS6406」
- 組合27：學科全名「護理學學士菁英領袖培育專修組別」, JS code「JS6418」
- 組合28：學科全名「內外全科醫學士」, JS code「JS6456」
- 組合29：學科全名「護理學學士」, JS code「JS6468」
- 組合30：學科全名「中醫全科學士」, JS code「JS6482」
- 組合31：學科全名「藥劑學學士」, JS code「JS6494」
- 組合32：學科全名「理學士(創新與科技)」, JS code「JS6602」
- 組合33：學科全名「內外全科醫學士 - 傑出醫科學人」, JS code「JS6626」
- 組合34：學科全名「科研專才啟導課程」, JS code「JS6688」
- 組合35：學科全名「心理學學士」, JS code「JS6705」
- 組合36：學科全名「社會科學學士」, JS code「JS6717」
- 組合37：學科全名「理學士(精算學)」, JS code「JS6729」
- 組合38：學科全名「社會工作學學士」, JS code「JS6731」
- 組合39：學科全名「工商管理學學士」, JS code「JS6755」
- 組合40：學科全名「經濟學學士 / 經濟金融學學士」, JS code「JS6767」
- 組合41：學科全名「統計決策科學」, JS code「JS6779」
- 組合42：學科全名「工商管理學學士(會計及財務) / 工商管理學學士(會計數據分析)」, JS code「JS6781」
- 組合43：學科全名「工商管理學學士(商業分析)」, JS code「JS6793」
- 組合44：學科全名「工商管理學學士(法學)及法學士」, JS code「JS6808」
- 組合45：學科全名「社會科學學士(政治學與法學)及法學士」, JS code「JS6810」
- 組合46：學科全名「新聞媒體及人工智能學士」, JS code「JS6822」
- 組合47：學科全名「理學士(營銷分析及科技)」, JS code「JS6846」
- 組合48：學科全名「理學士及法學士」, JS code「JS6858」
- 組合49：學科全名「金融學學士(資產管理及私人銀行)」, JS code「JS6860」
- 組合50：學科全名「理學士(計量金融)」, JS code「JS6884」
- 組合51：學科全名「工商管理學學士(國際商業及環球管理)」, JS code「JS6896」
- 組合52：學科全名「理學士」, JS code「JS6901」
- 組合53：學科全名「工學學士(生物醫學工程)」, JS code「JS6925」
- 組合54：學科全名「環球工程與商業課程」, JS code「JS6937」
- 組合55：學科全名「生物醫學學士」, JS code「JS6949」
- 組合56：學科全名「工學學士(計算機工程/電機工程/電子工程)」, JS code「JS6987」
- 組合57：學科全名「計算與數據科學」, JS code「JS6999」
- 組合58：學科全名「國際科研」, JS code「JS5101」
- 組合59：學科全名「理學A組」, JS code「JS5102」
- 組合60：學科全名「理學B組」, JS code「JS5103」
- 組合61：學科全名「理學士(生物醫學及健康科學)」, JS code「JS5118」
- 組合62：學科全名「理學A組-人工智能延伸主修」, JS code「JS5181」
- 組合63：學科全名「工學士(計算機工程學)」, JS code「JS5212」
- 組合64：學科全名「化學及生物工程學系」, JS code「JS5220」
- 組合65：學科全名「土木及環境工程學系」, JS code「JS5230」
- 組合66：學科全名「計算機科學及工程學系」, JS code「JS5240」
- 組合67：學科全名「電子及計算機工程學系」, JS code「JS5250」
- 組合68：學科全名「工業工程及決策分析學系」, JS code「JS5260」
- 組合69：學科全名「機械及航空航天工程學系」, JS code「JS5270」
- 組合70：學科全名「工程學-人工智能延伸主修」, JS code「JS5282」
- 組合71：學科全名「工商管理」, JS code「JS5300」
- 組合72：學科全名「工商管理學士(經濟學)」, JS code「JS5311」
- 組合73：學科全名「工商管理學士(金融學)」, JS code「JS5312」
- 組合74：學科全名「工商管理學士(環球商業管理)」, JS code「JS5313」
- 組合75：學科全名「工商管理學士(資訊系統學)」, JS code「JS5314」
- 組合76：學科全名「工商管理學士(管理學)」, JS code「JS5315」
- 組合77：學科全名「工商管理學士(市場學)」, JS code「JS5316」
- 組合78：學科全名「工商管理學士(營運管理學)」, JS code「JS5317」
- 組合79：學科全名「工商管理學士(專業會計學)」, JS code「JS5318」
- 組合80：學科全名「理學士(經濟及金融學)」, JS code「JS5331」
- 組合81：學科全名「理學士(量化金融學)」, JS code「JS5332」
- 組合82：學科全名「理學士(環球中國研究)」, JS code「JS5411」
- 組合83：學科全名「理學士(定量社會數據分析)」, JS code「JS5412」
- 組合84：學科全名「理學士(創新設計與科技)」, JS code「JS5711」
- 組合85：學科全名「理學士(生物科技及商學)」, JS code「JS5811」
- 組合86：學科全名「理學士(環境管理及科技)」, JS code「JS5812」
- 組合87：學科全名「理學士（數學與經濟學）」, JS code「JS5813」
- 組合88：學科全名「理學士（風險管理及商業智能學）」, JS code「JS5814」
- 組合89：學科全名「理學士（可持續發展及綠色金融）」, JS code「JS5822」
- 組合90：學科全名「科技及管理學雙學位課程」, JS code「JS5901」
- 組合91：學科全名「跨學科組合學士課程」, JS code「JS3000」
- 組合92：學科全名「工商管理組合學士課程」, JS code「JS3003」
- 組合93：學科全名「建設及環境組合學士課程」, JS code「JS3004」
- 組合94：學科全名「工程學科組合學士課程」, JS code「JS3005」
- 組合95：學科全名「計算機及數學科學組合學士課程」, JS code「JS3006」
- 組合96：學科全名「人文學科組合學士課程」, JS code「JS3007」
- 組合97：學科全名「理學組合學士課程」, JS code「JS3008」
- 組合98：學科全名「生物科技及化學科技(榮譽)理學士組合課程」, JS code「JS3011」
- 組合99：學科全名「物理學(榮譽)理學士副主修人工智能及數據分析/創新及創業」, JS code「JS3030」
- 組合100：學科全名「時裝(榮譽)文學士組合課程」, JS code「JS3050」
- 組合101：學科全名「會計及金融(榮譽)工商管理學士組合課程」, JS code「JS3060」
- 組合102：學科全名「環球商業及物流、航空、航運及供應鏈管理(榮譽)工商管理學士組合課程」, JS code「JS3070」
- 組合103：學科全名「管理及市場學(榮譽)工商管理學士組合課程」, JS code「JS3080」
- 組合104：學科全名「空間數據科學及智慧城市(榮譽)理學士組合課程」, JS code「JS3130」
- 組合105：學科全名「航空工程學(榮譽)工學士組合課程」, JS code「JS3140」
- 組合106：學科全名「生物醫學工程(榮譽)理學士」, JS code「JS3150」
- 組合107：學科全名「體育科技(榮譽)理學士」, JS code「JS3160」
- 組合108：學科全名「電機工程學(榮譽)工學士組合課程」, JS code「JS3170」
- 組合109：學科全名「資訊及人工智能工程學(榮譽)工學士/理學士組合課程」, JS code「JS3180」
- 組合110：學科全名「建築科學及工程學(榮譽)工學士」, JS code「JS3211」
- 組合111：學科全名「建築學(榮譽)理學士」, JS code「JS3214」
- 組合112：學科全名「應用數學及金融分析(榮譽)理學士組合課程」, JS code「JS3220」
- 組合113：學科全名「數據科學及人工智能(榮譽)理學士組合課程」, JS code「JS3223」
- 組合114：學科全名「產品創新及智能製造(榮譽)工學士組合課程」, JS code「JS3236」
- 組合115：學科全名「智能供應鏈及工程管理(榮譽)理學士組合課程」, JS code「JS3237」
- 組合116：學科全名「英文及應用語言學(榮譽)文學士」, JS code「JS3240」
- 組合117：學科全名「言語治療(榮譽)理學士」, JS code「JS3242」
- 組合118：學科全名「語言科學及技術(榮譽)理學士」, JS code「JS3243」
- 組合119：學科全名「應用社會科學(榮譽)文學士組合課程」, JS code「JS3250」
- 組合120：學科全名「食品科學及營養學(榮譽)理學士組合課程」, JS code「JS3255」
- 組合121：學科全名「眼科視光學(榮譽)理學士」, JS code「JS3290」
- 組合122：學科全名「酒店及旅遊管理(榮譽)理學士組合課程」, JS code「JS3310」
- 組合123：學科全名「中國歷史及文化(榮譽)文學士」, JS code「JS3320」
- 組合124：學科全名「精神健康護理學(榮譽)理學士」, JS code「JS3337」
- 組合125：學科全名「環境工程及可持續發展學(榮譽)工學士」, JS code「JS3375」
- 組合126：學科全名「醫療化驗科學(榮譽)理學士」, JS code「JS3478」
- 組合127：學科全名「設計學(榮譽)文學士組合課程」, JS code「JS3569」
- 組合128：學科全名「放射學(榮譽)理學士」, JS code「JS3612」
- 組合129：學科全名「創意藝術與數碼藝術榮譽文學士及音樂教育榮譽學士」, JS code「JS8001」
- 組合130：學科全名「創意藝術與數碼藝術榮譽文學士及視覺藝術教育榮譽學士」, JS code「JS8002」
- 組合131：學科全名「數碼中國文化與傳意榮譽文學士及中文教育榮譽學士」, JS code「JS8003」
- 組合132：學科全名「英語研究及數碼傳訊榮譽文學士及英文教育榮譽學士」, JS code「JS8004」
- 組合133：學科全名「文化傳承教育與藝術管理榮譽文學士及中國歷史教育榮譽學士」, JS code「JS8005」
- 組合134：學科全名「心理學榮譽社會科學學士及幼兒教育榮譽學士」, JS code「JS8006」
- 組合135：學科全名「個人理財榮譽文學士及企業、會計與財務概論教育榮譽學士」, JS code「JS8007」
- 組合136：學科全名「人工智能與教育科技榮譽理學士及資訊及通訊科技及小學科學教育榮譽學士」, JS code「JS8008」
- 組合137：學科全名「人工智能與教育科技榮譽理學士及小學數學教育榮譽學士」, JS code「JS8009」
- 組合138：學科全名「運動科學及教練榮譽理學士及體育教育榮譽學士」, JS code「JS8010」
- 組合139：學科全名「綜合環境管理榮譽理學士及科學教育榮譽學士」, JS code「JS8011」
- 組合140：學科全名「社會學與社區研究榮譽社會科學學士及地理教育榮譽學士」, JS code「JS8012」
- 組合141：學科全名「社會學與社區研究榮譽社會科學學士及小學人文科教育榮譽學士」, JS code「JS8013」
- 組合142：學科全名「幼兒教育高級文憑」, JS code「JS8507」
- 組合143：學科全名「心理學榮譽社會科學學士」, JS code「JS8651」
- 組合144：學科全名「特殊教育榮譽文學士」, JS code「JS8663」
- 組合145：學科全名「數碼中國文化與傳意榮譽文學士」, JS code「JS8674」
- 組合146：學科全名「英語研究及數碼傳訊榮譽文學士」, JS code「JS8675」
- 組合147：學科全名「創意藝術與數碼藝術榮譽文學士(音樂)」, JS code「JS8685」
- 組合148：學科全名「創意藝術與數碼藝術榮譽文學士(視覺藝術)」, JS code「JS8686」
- 組合149：學科全名「文化傳承教育與藝術管理榮譽文學士」, JS code「JS8687」
- 組合150：學科全名「個人理財榮譽文學士」, JS code「JS8688」
- 組合151：學科全名「綜合環境管理榮譽理學士」, JS code「JS8702」
- 組合152：學科全名「人工智能與教育科技榮譽理學士」, JS code「JS8714」
- 組合153：學科全名「運動科學及教練榮譽理學士」, JS code「JS8726」
- 組合154：學科全名「言語病理學及復康榮譽理學士」, JS code「JS8727」
- 組合155：學科全名「人類學」, JS code「JS4006」
- 組合156：學科全名「中國語言及文學」, JS code「JS4018」
- 組合157：學科全名「英文」, JS code「JS4032」
- 組合158：學科全名「藝術」, JS code「JS4044」
- 組合159：學科全名「歷史」, JS code「JS4056」
- 組合160：學科全名「日本研究」, JS code「JS4068」
- 組合161：學科全名「語言學」, JS code「JS4070」
- 組合162：學科全名「音樂」, JS code「JS4082」
- 組合163：學科全名「哲學」, JS code「JS4094」
- 組合164：學科全名「公共人文學」, JS code「JS4100」
- 組合165：學科全名「宗教研究」, JS code「JS4109」
- 組合166：學科全名「神學」, JS code「JS4111」
- 組合167：學科全名「翻譯」, JS code「JS4123」
- 組合168：學科全名「中國研究」, JS code「JS4136」
- 組合169：學科全名「工商管理學士綜合課程」, JS code「JS4202」
- 組合170：學科全名「環球商業學」, JS code「JS4214」
- 組合171：學科全名「酒店旅遊及房地產」, JS code「JS4226」
- 組合172：學科全名「保險、金融與精算學」, JS code「JS4238」
- 組合173：學科全名「專業會計學」, JS code「JS4240」
- 組合174：學科全名「計量金融學」, JS code「JS4252」
- 組合175：學科全名「環球經濟與金融跨學科主修課程」, JS code「JS4254」
- 組合176：學科全名「工商管理學士(工商管理學士綜合課程)及法律博士雙學位課程」, JS code「JS4264」
- 組合177：學科全名「計量金融學及風險管理科學」, JS code「JS4276」
- 組合178：學科全名「人體運動科學與健康研究」, JS code「JS4320」
- 組合179：學科全名「健康與體育運動科學」, JS code「JS4329」
- 組合180：學科全名「文學士(中國語文研究)及教育學士(中國語文教育)」, JS code「JS4331」
- 組合181：學科全名「文學士(英國語文研究)及教育學士(英國語文教育)」, JS code「JS4343」
- 組合182：學科全名「教育學士(數學及數學教育)」, JS code「JS4361」
- 組合183：學科全名「教育學士(幼兒教育)」, JS code「JS4372」
- 組合184：學科全名「理學士(學習設計與科技)」, JS code「JS4386」
- 組合185：學科全名「機械與自動化工程學」, JS code「JS4408」
- 組合186：學科全名「計算機科學與工程」, JS code「JS4412」
- 組合187：學科全名「計算數據科學」, JS code「JS4416」
- 組合188：學科全名「金融科技學」, JS code「JS4428」
- 組合189：學科全名「電子工程學」, JS code「JS4434」
- 組合190：學科全名「信息工程學」, JS code「JS4446」
- 組合191：學科全名「系統工程與工程管理」, JS code「JS4458」
- 組合192：學科全名「生物醫學工程學」, JS code「JS4460」
- 組合193：學科全名「能源與環境工程學」, JS code「JS4462」
- 組合194：學科全名「人工智能：系統與科技」, JS code「JS4468」
- 組合195：學科全名「材料科學與工程學」, JS code「JS4470」
- 組合196：學科全名「內外全科醫學士課程」, JS code「JS4501」
- 組合197：學科全名「內外全科醫學士課程環球醫學領袖培訓專修組別」, JS code「JS4502」
- 組合198：學科全名「護理學」, JS code「JS4513」
- 組合199：學科全名「藥劑學」, JS code「JS4525」
- 組合200：學科全名「公共衞生」, JS code「JS4537」
- 組合201：學科全名「中醫學」, JS code「JS4542」
- 組合202：學科全名「生物醫學」, JS code「JS4550」
- 組合203：學科全名「理學」, JS code「JS4601」
- 組合204：學科全名「地球與環境科學」, JS code「JS4648」
- 組合205：學科全名「數學精研」, JS code「JS4682」
- 組合206：學科全名「理論物理精研」, JS code「JS4690」
- 組合207：學科全名「風險管理科學」, JS code「JS4719」
- 組合208：學科全名「生物科技、創業與醫療管理」, JS code「JS4725」
- 組合209：學科全名「數學與信息工程學」, JS code「JS4733」
- 組合210：學科全名「航天科學與地球信息學及Ｘ雙主修課程」, JS code「JS4750」
- 組合211：學科全名「跨學科數據分析及Ｘ雙主修課程」, JS code「JS4760」
- 組合212：學科全名「社會科學」, JS code「JS4801」
- 組合213：學科全名「建築學」, JS code「JS4812」
- 組合214：學科全名「經濟學」, JS code「JS4824」
- 組合215：學科全名「地理與資源管理學」, JS code「JS4836」
- 組合216：學科全名「城市研究」, JS code「JS4838」
- 組合217：學科全名「政治與行政學」, JS code「JS4848」
- 組合218：學科全名「新聞與傳播學」, JS code「JS4850」
- 組合219：學科全名「全球傳播」, JS code「JS4858」
- 組合220：學科全名「心理學」, JS code「JS4862」
- 組合221：學科全名「中文(榮譽)文學士」, JS code「JS7101」
- 組合222：學科全名「環球可持續發展(榮譽)博雅學士」, JS code「JS7123」
- 組合223：學科全名「動畫及數碼藝術(榮譽)文學士」, JS code「JS7133」
- 組合224：學科全名「翻譯(榮譽)文學士」, JS code「JS7204」
- 組合225：學科全名「工商管理(榮譽)學士-會計與企業管治」, JS code「JS7211」
- 組合226：學科全名「工商管理(榮譽)學士-商業分析與創新」, JS code「JS7212」
- 組合227：學科全名「工商管理(榮譽)學士-金融」, JS code「JS7213」
- 組合228：學科全名「工商管理(榮譽)學士-管理與分析」, JS code「JS7214」
- 組合229：學科全名「工商管理(榮譽)學士-市場學及社交媒體」, JS code「JS7215」
- 組合230：學科全名「工商管理(榮譽)學士-風險及保險管理」, JS code「JS7216」
- 組合231：學科全名「數據科學(榮譽)理學士」, JS code「JS7225」
- 組合232：學科全名「社會科學(榮譽)學士-經濟學」, JS code「JS7301」
- 組合233：學科全名「社會科學(榮譽)學士-政府與國際事務學」, JS code「JS7302」
- 組合234：學科全名「社會科學(榮譽)學士-心理學」, JS code「JS7303」
- 組合235：學科全名「社會科學(榮譽)學士-社會學」, JS code「JS7304」
- 組合236：學科全名「社會科學(榮譽)學士-健康及社會服務管理」, JS code「JS7305」
- 組合237：學科全名「社會科學(榮譽)學士-社會與公共政策研究」, JS code「JS7306」
- 組合238：學科全名「社會科學(榮譽)學士-社會數據科學」, JS code「JS7307」
- 組合239：學科全名「英語語言文學課程(榮譽)文學士」, JS code「JS7503」
- 組合240：學科全名「文化研究(榮譽)文學士」, JS code「JS7606」
- 組合241：學科全名「歷史(榮譽)文學士」, JS code「JS7709」
- 組合242：學科全名「哲學(榮譽)文學士」, JS code「JS7802」
- 組合243：學科全名「電影與視覺藝術(榮譽)文學士」, JS code「JS7905」
- 組合244：學科全名「理學士(計算金融及金融科技)」, JS code「JS1000」
- 組合245：學科全名「工商管理學士(環球商業)」, JS code「JS1001」
- 組合246：學科全名「工商管理學士(會計)」, JS code「JS1002」
- 組合247：學科全名「工商管理學士(管理學)」, JS code「JS1005」
- 組合248：學科全名「工商管理學士(市場學)」, JS code「JS1007」
- 組合249：學科全名「經濟及金融」, JS code「JS1012」
- 組合250：學科全名「工商管理學士(商業經濟)」, JS code「JS1013」
- 組合251：學科全名「工商管理學士(金融)」, JS code「JS1014」
- 組合252：學科全名「智能資訊系統學」, JS code「JS1017」
- 組合253：學科全名「工商管理學士(環球商業系統管理)」, JS code「JS1018」
- 組合254：學科全名「工商管理學士(商業人工智能)」, JS code「JS1019」
- 組合255：學科全名「工商管理學士(商業決策分析)」, JS code「JS1026」
- 組合256：學科全名「工商管理學士(環球營運管理)」, JS code「JS1027」
- 組合257：學科全名「卓越創藝與科技課程」, JS code「JS1040」
- 組合258：學科全名「創意媒體」, JS code「JS1041」
- 組合259：學科全名「文學士(創意媒體)」, JS code「JS1042」
- 組合260：學科全名「理學士(創意媒體)」, JS code「JS1043」
- 組合261：學科全名「文理學士(新媒體)」, JS code「JS1044」
- 組合262：學科全名「環球可持續發展科創課程」, JS code「JS1050」
- 組合263：學科全名「能源及環境學」, JS code「JS1051」
- 組合264：學科全名「工學士(環境科學及工程學)與工商管理學士(金融)[雙學位]」, JS code「JS1052」
- 組合265：學科全名「理學士(環境及可持續發展商業)」, JS code「JS1053」
- 組合266：學科全名「法律學學士」, JS code「JS1061」
- 組合267：學科全名「法律學學士與工商管理學士(會計)(雙學位)」, JS code「JS1062」
- 組合268：學科全名「人工智能、計算・突破課程」, JS code「JS1070」
- 組合269：學科全名「數據科學」, JS code「JS1071」
- 組合270：學科全名「理學士(數據科學)」, JS code「JS1072」
- 組合271：學科全名「理學士(數據與系統工程)」, JS code「JS1074」
- 組合272：學科全名「社會科學學士(國際關係及全球事務)」, JS code「JS1102」
- 組合273：學科全名「文學士(中文及歷史)」, JS code「JS1103」
- 組合274：學科全名「文學士(英語語言)」, JS code「JS1104」
- 組合275：學科全名「媒體與傳播」, JS code「JS1106」
- 組合276：學科全名「社會科學學士(公共事務與管理)」, JS code「JS1108」
- 組合277：學科全名「文學士(語言學及語言應用)」, JS code「JS1109」
- 組合278：學科全名「社會科學學士 (犯罪科學)」, JS code「JS1111」
- 組合279：學科全名「社會科學學士(心理學)」, JS code「JS1112」
- 組合280：學科全名「社會科學學士(社會工作)」, JS code「JS1113」
- 組合281：學科全名「社會科學學士(犯罪科學)與法律學學士 (雙學位)」, JS code「JS1123」
- 組合282：學科全名「環球精研與科創課程」, JS code「JS1200」
- 組合283：學科全名「建築學及土木工程學」, JS code「JS1201」
- 組合284：學科全名「理學士(化學)」, JS code「JS1202」
- 組合285：學科全名「理學士(計算機科學)」, JS code「JS1204」
- 組合286：學科全名「電機工程學」, JS code「JS1205」
- 組合287：學科全名「理學士 (計算數學)」, JS code「JS1206」
- 組合288：學科全名「機械工程學」, JS code「JS1207」
- 組合289：學科全名「理學士 (物理學)」, JS code「JS1208」
- 組合290：學科全名「工學士(材料科學及工程)」, JS code「JS1210」
- 組合291：學科全名「工學士(生物醫學工程)」, JS code「JS1211」
- 組合292：學科全名「工學士(智能製造工程學)」, JS code「JS1216」
- 組合293：學科全名「研究、創新和環球工程課程」, JS code「JS1217」
- 組合294：學科全名「理學士 (網絡安全)」, JS code「JS1218」
- 組合295：學科全名「工學士(創新與企業工程)」, JS code「JS1219」
- 組合296：學科全名「理學士（計算機科學）與理學士（計算金融及金融科技）(雙學位)」, JS code「JS1221」
- 組合297：學科全名「綜合生物科學與生物工程課程」, JS code「JS1300」
- 組合298：學科全名「獸醫學學士」, JS code「JS1801」
- 組合299：學科全名「生物醫學」, JS code「JS1805」
- 組合300：學科全名「理學士(生物科學)」, JS code「JS1806」
- 組合301：學科全名「理學士(生物醫學)」, JS code「JS1807」
- 組合302：學科全名「文學士(榮譽)」, JS code「JS2020」
- 組合303：學科全名「宗教、哲學及倫理文學士(榮譽)」, JS code「JS2025」
- 組合304：學科全名「文學士(榮譽)/音樂學士(榮譽)(音樂/創意產業)」, JS code「JS2060」
- 組合305：學科全名「工商管理學士(榮譽)-會計學專修」, JS code「JS2110」
- 組合306：學科全名「工商管理學士(榮譽)」, JS code「JS2120」
- 組合307：學科全名「傳理學學士(榮譽)」, JS code「JS2310」
- 組合308：學科全名「電影電視文學士(榮譽)」, JS code「JS2330」
- 組合309：學科全名「環球螢幕演技藝術學士(榮譽)」, JS code「JS2340」
- 組合310：學科全名「傳理學學士(榮譽)-遊戲設計與動畫主修」, JS code「JS2370」
- 組合311：學科全名「中醫學學士及生物醫學理學士(榮譽)」, JS code「JS2410」
- 組合312：學科全名「中藥學學士(榮譽)」, JS code「JS2420」
- 組合313：學科全名「理學士(榮譽)」, JS code「JS2510」
- 組合314：學科全名「文學士(榮譽)/社會科學學士(榮譽)」, JS code「JS2610」
- 組合315：學科全名「體育及康樂管理文學士(榮譽)」, JS code「JS2620」
- 組合316：學科全名「社會工作學士(榮譽)」, JS code「JS2660」
- 組合317：學科全名「視覺藝術文學士(榮譽)」, JS code「JS2810」
- 組合318：學科全名「商業計算及數據分析理學士(榮譽)」, JS code「JS2910」
- 組合319：學科全名「藝術及科技文理學士(榮譽)」, JS code「JS2920」
- 組合320：學科全名「工商管理文學士(榮譽)(全球娛樂)」, JS code「JS2930」
- 組合321：學科全名「創新醫療及社會健康社會科學學士(榮譽)理學士(榮譽)」, JS code「JS2940」
- 組合322：學科全名「文理及科技學士(榮譽)自訂主修」, JS code「JS2950」
- 組合323：學科全名「數位未來與人文學科文理學士(榮譽)」, JS code「JS2960」
- 組合324：學科全名「由聖方濟各大學開辦：護理學（榮譽）學士」, JS code「JSSA01」
- 組合325：學科全名「由聖方濟各大學開辦：人工智能及數碼娛樂（榮譽）理學士」, JS code「JSSA02」
- 組合326：學科全名「由聖方濟各大學開辦：物理治療學（榮譽）理學士」, JS code「JSSA03」
- 組合327：學科全名「由聖方濟各大學開辦：人工智能（榮譽）理學士」, JS code「JSSA04」
- 組合328：學科全名「由聖方濟各大學開辦：翻譯科技（榮譽）文學士」, JS code「JSSA05」
- 組合329：學科全名「由聖方濟各大學開辦：工商管理（榮譽）酒店及旅遊管理應用學士」, JS code「JSSA06」
- 組合330：學科全名「由香港珠海學院開辦：建築學（榮譽）理學士」, JS code「JSSC02」
- 組合331：學科全名「由香港恒生大學開辦：供應鏈管理工商管理（榮譽）學士」, JS code「JSSH01」
- 組合332：學科全名「由香港恒生大學開辦：精算及保險 （榮譽）理學士」, JS code「JSSH02」
- 組合333：學科全名「由香港恒生大學開辦：計算機應用（榮譽）理學士」, JS code「JSSH03」
- 組合334：學科全名「由香港恒生大學開辦：數據科學及商業智能學（榮譽）理學士」, JS code「JSSH04」
- 組合335：學科全名「由香港恒生大學開辦：商業分析與資訊管理（榮譽）理學士」, JS code「JSSH05」
- 組合336：學科全名「由香港恒生大學開辦：藝術設計（榮譽）文學士」, JS code「JSSH06」
- 組合337：學科全名「由東華學院開辦：護理學（榮譽）健康科學學士」, JS code「JSST01」
- 組合338：學科全名「由東華學院開辦：醫療化驗科學（榮譽）理學士」, JS code「JSST02」
- 組合339：學科全名「由東華學院開辦：放射治療學（榮譽）理學士」, JS code「JSST03」
- 組合340：學科全名「由東華學院開辦：職業治療學（榮譽）理學士」, JS code「JSST04」
- 組合341：學科全名「由東華學院開辦：物理治療學（榮譽）理學士」, JS code「JSST05」
- 組合342：學科全名「由東華學院開辦：應用老年學（榮譽）理學士」, JS code「JSST06」
- 組合343：學科全名「由東華學院開辦：醫療資訊及服務管理（榮譽）學士」, JS code「JSST07」
- 組合344：學科全名「由東華學院開辦：醫療影像學（榮譽）理學士」, JS code「JSST08」
- 組合345：學科全名「由香港都會大學開辦：創意寫作與電影藝術榮譽文學士」, JS code「JSSU12」
- 組合346：學科全名「由香港都會大學開辦：動畫及視覺特效榮譽藝術學士」, JS code「JSSU14」
- 組合347：學科全名「由香港都會大學開辦：影像設計及數碼藝術榮譽藝術學士」, JS code「JSSU15」
- 組合348：學科全名「由香港都會大學開辦：新音樂及互動娛樂榮譽文學士」, JS code「JSSU18」
- 組合349：學科全名「由香港都會大學開辦：護理學榮譽學士（普通科）」, JS code「JSSU40」
- 組合350：學科全名「由香港都會大學開辦：護理學榮譽學士（精神科）」, JS code「JSSU50」
- 組合351：學科全名「由香港都會大學開辦：物理治療學榮譽理學士」, JS code「JSSU55」
- 組合352：學科全名「由香港都會大學開辦：綜合檢測和認證榮譽應用理學士」, JS code「JSSU61」
- 組合353：學科全名「由香港都會大學開辦：放射診斷學榮譽理學士」, JS code「JSSU66」
- 組合354：學科全名「由香港都會大學開辦：醫療化驗科學榮譽理學士」, JS code「JSSU67」
- 組合355：學科全名「由香港都會大學開辦：食品測試科學榮譽理學士」, JS code「JSSU69」
- 組合356：學科全名「由香港都會大學開辦：數據科學及人工智能榮譽理學士」, JS code「JSSU70」
- 組合357：學科全名「由香港都會大學開辦：電腦科學榮譽理學士」, JS code「JSSU72」
- 組合358：學科全名「由香港都會大學開辦：建築管理及工料測量學榮譽理學士」, JS code「JSSU77」
- 組合359：學科全名「由香港都會大學開辦：屋宇設備工程及可持續發展榮譽工學士」, JS code「JSSU78」
- 組合360：學科全名「由香港都會大學開辦：土木工程榮譽工學士」, JS code「JSSU79」
- 組合361：學科全名「由香港都會大學開辦：國際款待及景區管理榮譽工商管理學士」, JS code「JSSU90」
- 組合362：學科全名「由香港都會大學開辦：航空服務管理榮譽工商管理學士」, JS code「JSSU93」
- 組合363：學科全名「由香港都會大學開辦：運動及康樂管理榮譽工商管理學士」, JS code「JSSU95」
- 組合364：學科全名「由香港都會大學開辦：財務及金融科技榮譽工商管理學士」, JS code「JSSU96」
- 組合365：學科全名「由香港都會大學開辦：環球市場及供應鏈管理榮譽工商管理學士」, JS code「JSSU97」
- 組合366：學科全名「由高科院開辦：時裝設計（榮譽）文學士」, JS code「JSSV01」
- 組合367：學科全名「由高科院開辦：產品設計（榮譽）文學士」, JS code「JSSV02」
- 組合368：學科全名「由高科院開辦：園境建築（榮譽）文學士」, JS code「JSSV03」
- 組合369：學科全名「由高科院開辦：廚藝及管理（榮譽）文學士」, JS code「JSSV04」
- 組合370：學科全名「由高科院開辦：土木工程（榮譽）工學士」, JS code「JSSV05」
- 組合371：學科全名「由高科院開辦：園藝樹藝及園境管理（榮譽）理學士」, JS code「JSSV07」
- 組合372：學科全名「由高科院開辦：測量學（榮譽）理學士」, JS code「JSSV08」
- 組合373：學科全名「由高科院開辦：運動及康樂管理（榮譽）社會科學學士」, JS code「JSSV09」
- 組合374：學科全名「由高科院開辦：屋宇設備工程（榮譽）工學士」, JS code「JSSV10」
- 組合375：學科全名「由高科院開辦：運動教練(榮譽)社會科學學士」, JS code「JSSV13」
- 組合376：學科全名「由高科院開辦：運動治療(榮譽)社會科學學士」, JS code「JSSV14」
- 組合377：學科全名「由香港伍倫貢學院開辦：營運及管理（榮譽）航空學士」, JS code「JSSW01」
- 組合378：學科全名「由香港伍倫貢學院開辦：航運服務及營運管理學士（榮譽）」, JS code「JSSW02」
- 組合379：學科全名「由香港樹仁大學開辦： 金融科技（榮譽）商學士」, JS code「JSSY01」
- 組合380：學科全名「由香港樹仁大學開辦：應用數據科學（榮譽）理學士」, JS code「JSSY02」
- 組合381：學科全名「社會科學榮譽學士」, JS code「JS9009」
- 組合382：學科全名「心理學榮譽社會科學學士」, JS code「JS9010」
- 組合383：學科全名「中文榮譽文學士」, JS code「JS9011」
- 組合384：學科全名「語言研究與翻譯榮譽文學士」, JS code「JS9013」
- 組合385：學科全名「創意廣告及媒體設計榮譽文學士」, JS code「JS9016」
- 組合386：學科全名「英語及文化榮譽文學士」, JS code「JS9019」
- 組合387：學科全名「專業會計榮譽工商管理學士」, JS code「JS9220」
- 組合388：學科全名「商業管理學榮譽工商管理學士」, JS code「JS9230」
- 組合389：學科全名「環球商業榮譽工商管理學士」, JS code「JS9240」
- 組合390：學科全名「人力資源管理學榮譽工商管理學士」, JS code「JS9262」
- 組合391：學科全名「市場學榮譽工商管理學士」, JS code「JS9266」
- 組合392：學科全名「房地產及測量學榮譽工商管理學士」, JS code「JS9276」
- 組合393：學科全名「應用心理學榮譽學士，商業管理榮譽學士」, JS code「JS9280」
- 組合394：學科全名「持續旅遊及款待管理榮譽工商管理學士」, JS code「JS9291」
- 組合395：學科全名「運動及電競運動管理榮譽工商管理學士」, JS code「JS9294」
- 組合396：學科全名「教育榮譽學士（普通話及中文教育）及語言研究榮譽學士（漢語語言學研究）」, JS code「JS9520」
- 組合397：學科全名「英語教學榮譽教育學士及英語研究榮譽學士」, JS code「JS9530」
- 組合398：學科全名「英語研究榮譽學士」, JS code「JS9540」
- 組合399：學科全名「語言研究榮譽學士（應用中國語言）」, JS code「JS9550」
- 組合400：學科全名「教育榮譽學士（中國語文教學）及語言研究榮譽學士（應用中國語言）」, JS code「JS9560」
- 組合401：學科全名「教育榮譽學士(幼兒教育:領導及特殊教育需要)」, JS code「JS9580」
- 組合402：學科全名「網路及電腦安全榮譽理學士」, JS code「JS9719」
- 組合403：學科全名「電子及電腦工程學榮譽工學士」, JS code「JS9720」
- 組合404：學科全名「環境科學與綠色管理榮譽理學士」, JS code「JS9731」
- 組合405：學科全名「生物醫學與生物科技榮譽理學士」, JS code「JS9732」
- 組合406：學科全名「科學（ＳＴＥＡＭ）榮譽理學士」, JS code「JS9733」
- 組合407：學科全名「機器人和自動化工程榮譽應用理學士」, JS code「JS9775」
- 組合408：學科全名「建造工程與管理榮譽理學士」, JS code「JS9776」
"""

with st.form("auto_form"):
    form_url = st.text_input("Google 表單連結 (必須是 /viewform 結尾)")
    persona = st.text_area("填寫方向與偏好設定", value=default_persona, height=250)
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
