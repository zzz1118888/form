import streamlit as st
import requests
import re
import json
import time
import random
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
        1. 保持人設一致：對於選擇題或判斷題，請根據你已經設定的背景資訊來推斷並填寫最合理的選項文字。
        2. 鍵值匹配：返回的 JSON 鍵值(Key)必須「完全等於」上述列表中的題目名稱，一字不差，絕對不要自己縮寫或加上題號。
        3. 選擇題極度嚴格：請務必猜測該題目的可能選項，並僅輸出一個選項文字。
        
        請以 JSON 陣列格式返回，每個元素代表一份問卷的答案。絕對不要輸出任何解釋文字，只需輸出標準的 JSON 陣列格式。
        """
        
        try:
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

# ================= 模組三：並發提交模組 (時間分散模擬版) =================
def submit_form(form_url, parsed_questions, answers, duration_hours):
    post_url = form_url.replace("/viewform", "/formResponse")
    success_count = 0
    
    total_seconds = duration_hours * 3600
    avg_wait = total_seconds / len(answers) if len(answers) > 0 else 0
    
    wait_status = st.empty()
    
    for idx, answer_set in enumerate(answers):
        payload = {}
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
                        
        if payload:
            res = requests.post(post_url, data=payload)
            if res.status_code == 200:
                success_count += 1
            else:
                st.error(f"第 {idx+1} 份問卷被 Google 拒絕！(狀態碼: {res.status_code})")
                st.json(answer_set)
        else:
            st.warning("攔截到一份空數據，未提交至表單。")
            
        # 如果不是最後一份，就執行隨機等待
        if idx < len(answers) - 1:
            if duration_hours > 0:
                # 隨機波動：平均時間的 0.5 倍 ~ 1.5 倍
                wait_time = random.uniform(avg_wait * 0.5, avg_wait * 1.5)
                wait_status.info(f"⏳ 模擬真實真人填寫中... 第 {idx+1} 份已提交，將隨機等待 {int(wait_time)} 秒後提交下一份。")
                time.sleep(wait_time)
            else:
                time.sleep(0.5)
                
    wait_status.empty()
    return success_count

# ================= Web UI 設計 =================
st.set_page_config(page_title="自動問卷生成系統", page_icon="🤖")
st.title("🤖 Google Form 自動填寫系統")
st.markdown("輸入 Google 表單連結與目標人設，系統將自動生成並批量提交資料。")

# 預設的 35 組 JUPAS 人設 Prompt
default_persona = """你現在是一個正在參加香港 JUPAS 升學聯招的高中畢業生，正在填寫未來的升學意向調查。你需要隨機扮演不同興趣的學生。

【核心綁定規定（極度重要）】：
關於「你想读的大学是？」、「你想报的专业名称是？」、「专业的js code是？」與隱藏的「學科偏向」，請你【必須且只能】從下方列表隨機挑選「完整的一組」來填寫。絕對不能拆開拼湊，也不能自己捏造代碼！

[真實 JUPAS 組合菜單]
- 組合1：大學「香港大學」, 專業「理學」, JS code「JS6901」, 學科偏向「理科」
- 組合2：大學「香港大學」, 專業「內外全科醫學」, JS code「JS6456」, 學科偏向「理科」
- 組合3：大學「香港大學」, 專業「工程學」, JS code「JS6963」, 學科偏向「工科」
- 組合4：大學「香港大學」, 專業「文學」, JS code「JS6054」, 學科偏向「文科」
- 組合5：大學「香港大學」, 專業「工商管理學」, JS code「JS6755」, 學科偏向「商科」
- 組合6：大學「香港大學」, 專業「社會科學」, JS code「JS6810」, 學科偏向「文科」
- 組合7：大學「香港中文大學」, 專業「綜合工商管理」, JS code「JS4202」, 學科偏向「商科」
- 組合8：大學「香港中文大學」, 專業「工程學」, JS code「JS4401」, 學科偏向「工科」
- 組合9：大學「香港中文大學」, 專業「理學」, JS code「JS4601」, 學科偏向「理科」
- 組合10：大學「香港中文大學」, 專業「文學」, JS code「JS4006」, 學科偏向「文科」
- 組合11：大學「香港中文大學」, 專業「社會科學」, JS code「JS4801」, 學科偏向「文科」
- 組合12：大學「香港中文大學」, 專業「護理學」, JS code「JS4331」, 學科偏向「理科」
- 組合13：大學「香港科技大學」, 專業「工商管理」, JS code「JS5300」, 學科偏向「商科」
- 組合14：大學「香港科技大學」, 專業「工程學」, JS code「JS5200」, 學科偏向「工科」
- 組合15：大學「香港科技大學」, 專業「理學」, JS code「JS5100」, 學科偏向「理科」
- 組合16：大學「香港科技大學」, 專業「計算機科學」, JS code「JS5211」, 學科偏向「工科」
- 組合17：大學「香港理工大學」, 專業「物理治療學」, JS code「JS3636」, 學科偏向「理科」
- 組合18：大學「香港理工大學」, 專業「電子計算」, JS code「JS3180」, 學科偏向「工科」
- 組合19：大學「香港理工大學」, 專業「設計學」, JS code「JS3866」, 學科偏向「文科」
- 組合20：大學「香港理工大學」, 專業「護理學」, JS code「JS3390」, 學科偏向「理科」
- 組合21：大學「香港理工大學」, 專業「航空及供應鏈管理」, JS code「JS3140」, 學科偏向「商科」
- 組合22：大學「香港城市大學」, 專業「計算機科學」, JS code「JS1204」, 學科偏向「工科」
- 組合23：大學「香港城市大學」, 專業「工商管理」, JS code「JS1001」, 學科偏向「商科」
- 組合24：大學「香港城市大學」, 專業「媒體與傳播」, JS code「JS1106」, 學科偏向「文科」
- 組合25：大學「香港城市大學」, 專業「會計學」, JS code「JS1041」, 學科偏向「商科」
- 組合26：大學「香港浸會大學」, 專業「傳理學」, JS code「JS2310」, 學科偏向「文科」
- 組合27：大學「香港浸會大學」, 專業「工商管理」, JS code「JS2120」, 學科偏向「商科」
- 組合28：大學「香港浸會大學」, 專業「理學」, JS code「JS2910」, 學科偏向「理科」
- 組合29：大學「香港浸會大學」, 專業「文學」, JS code「JS2510」, 學科偏向「文科」
- 組合30：大學「嶺南大學」, 專業「工商管理」, JS code「JS7200」, 學科偏向「商科」
- 組合31：大學「嶺南大學」, 專業「文學」, JS code「JS7101」, 學科偏向「文科」
- 組合32：大學「嶺南大學」, 專業「社會科學」, JS code「JS7300」, 學科偏向「文科」
- 組合33：大學「香港教育大學」, 專業「幼兒教育」, JS code「JS8404」, 學科偏向「文科」
- 組合34：大學「香港教育大學」, 專業「小學教育」, JS code「JS8105」, 學科偏向「文科」
- 組合35：大學「香港教育大學」, 專業「心理學」, JS code「JS8663」, 學科偏向「理科」

【其他欄位生成規定】：
1. 你的名字是？：請隨機生成真實、常見的中文姓名（2-3個字）。
2. 你的年龄是？：請在 17 到 19 之間隨機選擇一個數字。
3. 你对rightpick有什么看法？：請隨機用 1-2 句話表達高度評價。內容需提及 rightpick 幫助你解決了升學規劃的痛點、減少了對未來的迷惘等。

【選擇題嚴格規定（必須一字不差）】：
- 「你偏向于什么学科？」：請根據你上面抽到的組合填寫（必須完全等於「文科」、「理科」、「商科」或「工科」）。
- 「你在大学期待小组合作还是个人合作？」：只能回答「小组合作」或「个人合作」。
- 「在大学你期待认识更多朋友还是专注学业？」：只能回答「认识更多朋友」或「专注学业」。
- 「你期待选择自己感兴趣的专业还是高人工的专业？」：只能回答「感兴趣的专业」或「高人工的专业」。
- 「你是愿意毕业就就业还是继续深造学历（读master、phd）」：只能回答「毕业就就业」或「继续深造学历」。"""

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
        duration_hours = st.number_input("設定要在幾小時內陸續填寫", min_value=0.0, max_value=72.0, value=0.0, step=0.5, help="輸入0代表全速提交。輸入例如1代表在1小時內隨機分散提交完畢。")
    
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
                
                st.write("🧠 正在呼叫 AI 分批生成模擬數據...")
                answers = generate_answers(questions, persona, target_count)
                
                if len(answers) > 0:
                    st.write("🚀 正在啟動擬真時間分散提交程序...")
                    success_count = submit_form(form_url, questions, answers, duration_hours)
                    
                    if success_count > 0:
                        status.update(label=f"任務完成！成功提交 {success_count}/{target_count} 份問卷。", state="complete", expanded=False)
                        st.balloons()
                    else:
                        status.update(label="提交失敗，請檢查下方紅框中的資料格式錯誤。", state="error")
                else:
                    status.update(label="未成功生成任何數據，請檢查 AI 回傳結果。", state="error")
                    
            except Exception as e:
                status.update(label="執行發生錯誤", state="error")
                st.error(f"錯誤詳情：{str(e)}")
