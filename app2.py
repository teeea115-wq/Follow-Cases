import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re
from google.oauth2 import service_account
from google.cloud import bigquery

# ==========================================
# ⚙️ 1. ตั้งค่าชื่อคอลัมน์จาก BigQuery
# ==========================================
COL_MSG = 'response_message'  
COL_TIME = 'response_time_v'  

# ==========================================
# 2. ตั้งค่าหน้าเว็บและ CSS
# ==========================================
st.set_page_config(page_title="Zero SLA Breach Command Center", page_icon="🎯", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Prompt:wght@300;400;500;600;700&display=swap');
    html, body, [class*="css"], .stApp { font-family: 'Prompt', sans-serif !important; background-color: #F8FAFC !important; color: #0F172A !important; }
    p, label, h1, h2, h3, h4, h5, h6 { color: #0F172A !important; font-weight: 600 !important; }
    div.stPlotlyChart, div[data-testid="stDataFrame"] { background-color: #ffffff !important; border-radius: 12px; padding: 24px 10px; box-shadow: 0 4px 10px rgba(0, 0, 0, 0.05); border: 1px solid #E2E8F0 !important; margin-bottom: 24px; }
    [data-testid="stSidebar"], [data-testid="stSidebar"] > div:first-child { background-color: #FFFFFF !important; border-right: 1px solid #E2E8F0 !important; }
    div[data-testid="stDateInput"] div, div[data-testid="stTextInput"] div, div[data-baseweb="select"] > div, input { background-color: #F8FAFC !important; color: #0F172A !important; border-color: #CBD5E1 !important; border-radius: 6px !important; }
    [data-testid="stSidebar"] [data-testid="stButton"] button, div[data-testid="stButton"] button { background-color: #FFFFFF !important; color: #0F172A !important; border: 1px solid #CBD5E1 !important; font-weight: 700 !important; border-radius: 8px !important; transition: all 0.3s !important; }
    div[data-testid="stMetricValue"] { font-size: 36px !important; font-weight: 800 !important;}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3. 🔒 ระบบ Login
# ==========================================
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.markdown("<br><br><h2 style='text-align: center; color: #1E293B;'>🔒 SLA Tracking Login</h2>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        password = st.text_input("🔑 รหัสผ่าน (Password):", type="password")
        if st.button("เข้าสู่ระบบ (Login)", use_container_width=True):
            if password == "123456":  
                st.session_state["authenticated"] = True
                st.rerun() 
            else:
                st.error("❌ รหัสผ่านไม่ถูกต้อง กรุณาลองใหม่!")
    st.stop() 

# ==========================================
# 4. ฟังก์ชันคำนวณและประมวลผล
# ==========================================
def create_kpi_card(title, value, accent_color, subtitle=""):
    sub_html = f"<p style='color: #64748B; font-size: 13px; margin: 5px 0 0 0; font-weight: 500;'>{subtitle}</p>" if subtitle else ""
    html = f"""
    <div style="background-color: #ffffff; padding: 20px; border-radius: 12px; border: 1px solid #E2E8F0; border-top: 5px solid {accent_color}; box-shadow: 0 4px 6px rgba(0,0,0,0.02); height: 100%;">
        <p style="color: #475569; font-size: 14px; font-weight: 700; margin: 0 0 8px 0;">{title}</p>
        <h1 style="color: #0F172A; font-size: 32px; font-weight: 800; margin: 0; line-height: 1.1;">{value}</h1>
        {sub_html}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

def section_title(text, icon="", desc=""):
    st.markdown(f"<h3 style='color: #0F172A; font-weight: 700; margin-top: 35px; margin-bottom: 5px; border-bottom: 2px solid #E2E8F0; padding-bottom: 8px;'>{icon} {text}</h3>", unsafe_allow_html=True)
    if desc: st.markdown(f"<p style='color: #64748B; font-size: 15px; margin-bottom: 20px; line-height: 1.5;'><i>{desc}</i></p>", unsafe_allow_html=True)

def calculate_actual_mins(row, now):
    if row.get('status') in ['ปิด Case', 'เสร็จสิ้น']:
        if pd.notna(row.get('duration_total_mins')):
            return row['duration_total_mins']
        elif pd.notna(row.get('Received_DT')) and pd.notna(row.get('Closed_DT')): 
            return (row['Closed_DT'] - row['Received_DT']).total_seconds() / 60
        return 0
    else:
        if pd.notna(row.get('Received_DT')): 
            return (now - row['Received_DT']).total_seconds() / 60
        return 0

def get_sla_status_label(row):
    limit = row['sla_limit_minutes']
    actual = row['actual_minutes_spent']
    is_closed = row.get('status') in ['ปิด Case', 'เสร็จสิ้น']
    if is_closed: 
        return '✅ ภายใน SLA' if actual <= limit else '❌ เกิน SLA (ปิดแล้ว)'
    else:
        if limit == 0: return '🟢 ปกติ (ไม่มี SLA)'
        if actual > limit: return '🔥 เกินกำหนด SLA (รีบปิดด่วน!)'
        elif (actual / limit) >= 0.8: return '⚠️ ใกล้หลุด SLA (เร่งมือ)'
        else: return '🟢 ปกติ'

def extract_tracking_info(row, col_msg_actual, col_time_actual):
    msg_str = str(row.get(col_msg_actual, ''))
    time_str = str(row.get(col_time_actual, ''))
    if msg_str == 'nan' or msg_str == '' or msg_str == 'None': 
        return pd.Series({'Track_Status': 'ไม่ติดตาม', 'Track_Count': 0, 'First_Agent': 'ไม่มี', 'First_Track_Time': pd.NaT, 'Last_Track_Time': pd.NaT})
    
    msgs = msg_str.split(',')
    times = time_str.split(',')
    track_times = []
    first_agent = 'ไม่มี'
    
    for i in range(min(len(msgs), len(times))):
        msg = msgs[i].strip()
        t_val = times[i].strip()
        if "เบื้องต้นทางเจ้าหน้าที่ทำการติดตาม" in msg or re.search(r"(?i)help\s*desk\s*[0-9]+.*ติดตาม", msg):
            agent_match = re.search(r"(?i)help\s*desk\s*([0-9]+)", msg)
            if agent_match:
                agent_name = f"Help Desk {agent_match.group(1)}"
                if first_agent == 'ไม่มี': first_agent = agent_name
            try:
                t_obj = pd.to_datetime(t_val, format='%Y-%m-%d %H:%M:%S', errors='coerce') 
                if pd.notna(t_obj): track_times.append(t_obj)
            except: pass
            
    return pd.Series({
        'Track_Status': 'ติดตาม' if track_times else 'ไม่ติดตาม', 
        'Track_Count': len(track_times), 
        'First_Agent': first_agent, 
        'First_Track_Time': min(track_times) if track_times else pd.NaT, 
        'Last_Track_Time': max(track_times) if track_times else pd.NaT
    })

# ==========================================
# 5. โหลดข้อมูลจาก Google BigQuery (ดูดจาก "ถังเล็ก" เท่านั้น)
# ==========================================
@st.cache_data(ttl=600, show_spinner=False)
def load_and_prep_data_bq():
    key_dict = st.secrets["connections"]["bigquery"]
    credentials = service_account.Credentials.from_service_account_info(key_dict)
    client = bigquery.Client(credentials=credentials, project=credentials.project_id)

    # 💡 SQL ชี้ไปที่ ถังเล็ก (tracked_cases_summary) โหลดลื่นไหล ไม่กิน RAM
    master_sql = r"""
        SELECT * FROM `helpdeskdb-486609.helpdesk_system.tracked_cases_summary`
    """

    df = client.query(master_sql).to_dataframe()
    
    if df.empty:
        return df, COL_MSG, COL_TIME

    df['Received_DT'] = pd.to_datetime(df['datetime_received'], errors='coerce')
    df['Closed_DT'] = pd.to_datetime(df['datetime_closed'], errors='coerce')

    now = pd.Timestamp.now()
    df['actual_minutes_spent'] = df.apply(lambda row: calculate_actual_mins(row, now), axis=1)

    if 'sla_limit_minutes' in df.columns:
        df['sla_status_label'] = df.apply(get_sla_status_label, axis=1)
    else: 
        df['sla_status_label'] = 'ไม่พบข้อมูล SLA'

    if COL_MSG in df.columns and COL_TIME in df.columns:
        tracking_df = df.apply(lambda row: extract_tracking_info(row, COL_MSG, COL_TIME), axis=1)
        df = pd.concat([df, tracking_df], axis=1)
    else:
        df['Track_Status'] = 'ไม่ติดตาม'
        df['Track_Count'] = 0
        df['First_Agent'] = 'ไม่มี'
        df['Last_Track_Time'] = pd.NaT

    agent_mapping = {'Help Desk 2': 'Help Desk 2 (เจนจิรา)', 'Help Desk 3': 'Help Desk 3 (มนัส)', 'Help Desk 4': 'Help Desk 4 (ฉัตรลดา)', 'Help Desk 5': 'Help Desk 5 (จิรวัฒน์)', 'Help Desk 6': 'Help Desk 6 (กิติลักษณ์)'}
    df['First_Agent_Name'] = df.get('First_Agent', pd.Series(['ไม่มี']*len(df))).map(agent_mapping).fillna(df.get('First_Agent', 'ไม่มี'))

    return df, COL_MSG, COL_TIME

# ==========================================
# 🚀 เริ่มการทำงานของ Dashboard
# ==========================================
try:
    with st.spinner("🚀 กำลังคำนวณหนี้ SLA สะสม..."):
        df, found_msg, found_time = load_and_prep_data_bq()

    if df.empty:
        st.warning("⚠️ ไม่พบข้อมูลเคสในระบบ")
        st.stop()

    # ==========================================
    # 6. Sidebar Filter
    # ==========================================
    if st.sidebar.button("🚪 ล็อกเอาท์ (Logout)", use_container_width=True):
        st.session_state["authenticated"] = False
        st.rerun()

    st.sidebar.markdown("<h2 style='margin-top: 15px;'>🎯 ช่วงเวลาอ้างอิง</h2>", unsafe_allow_html=True)
    st.sidebar.markdown("<p style='font-size: 12px; color: #64748B;'>* เคสที่ปิดแล้ว: นับผลงานตามเดือนที่เลือก<br>* หนี้ SLA: ดึงหนี้สะสมมาทั้งหมด</p>", unsafe_allow_html=True)

    valid_dates = df['Received_DT'].dropna()
    min_date = valid_dates.min().date() if not valid_dates.empty else pd.Timestamp.now().date()
    max_date = pd.Timestamp.now().date()

    date_range = st.sidebar.date_input("📅 เลือกช่วงเวลา", value=(min_date, max_date), min_value=min_date, max_value=max_date)
    start_date = pd.to_datetime(date_range[0]) if len(date_range) > 0 else pd.to_datetime(min_date)
    end_date = pd.to_datetime(date_range[1]) if len(date_range) > 1 else start_date
    end_date = end_date.replace(hour=23, minute=59, second=59)

    # 💡 LOGIC การกรองใหม่ตามที่คุณขอ!
    # 1. เคสที่ยังไม่ปิด (ดึงทั้งหมด ที่เกิดก่อนหรือเท่ากับ end_date)
    open_mask = (~df['status'].isin(['ปิด Case', 'เสร็จสิ้น'])) & (df['Received_DT'] <= end_date)
    # 2. เคสที่ปิดแล้ว (ดึงเฉพาะที่ปิดในช่วงเวลาที่เลือก)
    closed_mask = (df['status'].isin(['ปิด Case', 'เสร็จสิ้น'])) & (df['Closed_DT'] >= start_date) & (df['Closed_DT'] <= end_date)
    
    df_filtered = df[open_mask | closed_mask].copy()

    # ตัวกรองเพิ่มเติม
    st.sidebar.markdown("<hr style='margin-top: 5px; margin-bottom: 20px;'>", unsafe_allow_html=True)
    all_depts = sorted([str(x) for x in df_filtered['department'].unique()])
    selected_depts = st.sidebar.multiselect("🏢 แผนก (Department):", all_depts)
    if selected_depts: df_filtered = df_filtered[df_filtered['department'].isin(selected_depts)]

    # แบ่งกลุ่มข้อมูลตามแกน "SLA & การติดตาม"
    # กลุ่มที่ 1: หนี้ SLA (ยังไม่ปิด และเกิน/ใกล้เกิน SLA)
    sla_debt_df = df_filtered[(~df_filtered['status'].isin(['ปิด Case', 'เสร็จสิ้น'])) & (df_filtered['sla_status_label'].isin(['🔥 เกินกำหนด SLA (รีบปิดด่วน!)', '⚠️ ใกล้หลุด SLA (เร่งมือ)']))]
    
    # กลุ่มที่ 2: ผลงานเคลียร์หนี้ SLA ในเดือนนี้ (ปิดแล้ว และเคยเกิน SLA และถูกติดตาม)
    sla_cleared_df = df_filtered[(df_filtered['status'].isin(['ปิด Case', 'เสร็จสิ้น'])) & (df_filtered['sla_status_label'] == '❌ เกิน SLA (ปิดแล้ว)') & (df_filtered['Track_Status'] == 'ติดตาม')]

    # กลุ่มที่ 3: ผลงานติดตามเคสรวมในเดือนนี้
    tracked_closed_df = df_filtered[(df_filtered['status'].isin(['ปิด Case', 'เสร็จสิ้น'])) & (df_filtered['Track_Status'] == 'ติดตาม')]

    # ==========================================
    # 7. Dashboard Layout
    # ==========================================
    st.markdown("<h1>🎯 Zero SLA Breach Command Center</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color: #64748B; margin-top: -15px; margin-bottom: 25px;'>เป้าหมาย: หนี้ SLA สะสมต้องเป็น 0 และแสดงหลักฐานการติดตามงานทุกเคส</p>", unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    with c1: create_kpi_card("SLA Debt (เคสค้าง)", f"{len(sla_debt_df):,}", "#EF4444", "เคสที่ทะลุ SLA หรือกำลังจะทะลุ (ยังไม่ปิด)")
    with c2: create_kpi_card("SLA Cleared", f"{len(sla_cleared_df):,}", "#10B981", "เคสหลุด SLA ที่ตามบี้จนปิดสำเร็จในรอบนี้")
    with c3: create_kpi_card("Total Tracked & Closed", f"{len(tracked_closed_df):,}", "#3B82F6", "จำนวนเคสทั้งหมดที่ตามจนปิดสำเร็จ")
    with c4: 
        untracked_debt = len(sla_debt_df[sla_debt_df['Track_Status'] == 'ไม่ติดตาม'])
        create_kpi_card("Critical Untracked", f"{untracked_debt:,}", "#F59E0B", "เคสทะลุ SLA ที่ Helpdesk ยังไม่เคยตามเลย!")

    # ==========================================
    # 🚨 เสาที่ 1: หนี้ SLA ที่ต้องตามล้าง (เป้าหมายต้องเป็น 0)
    # ==========================================
    st.markdown("<hr style='margin-top: 30px; margin-bottom: 10px;'>", unsafe_allow_html=True)
    section_title("🚨 หนี้ SLA สะสมที่ต้องตามล้างด่วน (Pending SLA Breaches)", "🔥", "รายการเคสที่ทะลุ SLA หรือใกล้ทะลุ แต่ยังไม่มีการ 'ปิดเคส' (พร้อมหลักฐานการติดตามงานล่าสุด)")

    if not sla_debt_df.empty:
        sla_debt_df['รอมาแล้ว (ชม.)'] = (sla_debt_df['actual_minutes_spent'] / 60).round(1)
        sla_debt_df['SLA (ชม.)'] = (sla_debt_df['sla_limit_minutes'] / 60).round(1)
        sla_debt_df = sla_debt_df.sort_values(by=['sla_status_label', 'รอมาแล้ว (ชม.)'], ascending=[True, False])

        # จัดฟอร์แมตวันที่ให้โชว์สวยๆ (หลักฐาน)
        sla_debt_df['วันที่เปิด'] = sla_debt_df['Received_DT'].dt.strftime('%d/%m/%Y %H:%M').fillna('-')
        sla_debt_df['เวลาติดตามล่าสุด'] = sla_debt_df['Last_Track_Time'].dt.strftime('%d/%m/%Y %H:%M').fillna('❌ ยังไม่มีคนตาม!')

        display_debt = sla_debt_df[['Case_Id', 'วันที่เปิด', 'department', 'SLA (ชม.)', 'รอมาแล้ว (ชม.)', 'เวลาติดตามล่าสุด', 'First_Agent_Name', 'sla_status_label']]
        display_debt.columns = ['หมายเลข Case', 'เวลาที่เปิดเคส', 'แผนก', 'SLA (ชม.)', 'รอมาแล้ว (ชม.)', 'เวลาที่ติดตามล่าสุด', 'ผู้ติดตามคนแรก', 'สถานะวิกฤต']

        st.dataframe(
            display_debt, use_container_width=True, height=350, hide_index=True,
            column_config={
                "สถานะวิกฤต": st.column_config.TextColumn("สถานะวิกฤต"),
                "เวลาที่ติดตามล่าสุด": st.column_config.TextColumn("เวลาที่ติดตามล่าสุด"),
            }
        )
    else:
        st.success("🎉 สุดยอดมาก! ตอนนี้ไม่มีเคสไหนที่ค้างเกิน SLA เลย (หนี้ SLA เป็น 0)")

    # ==========================================
    # 🏆 เสาที่ 2: ผลงานเคลียร์หนี้ในเดือนนี้
    # ==========================================
    st.markdown("<hr style='margin-top: 30px; margin-bottom: 10px;'>", unsafe_allow_html=True)
    section_title("🏆 ผลงานกู้ชีพเคสเกิน SLA สำเร็จ (SLA Breaches Cleared)", "✅", "เคสที่เคยเกิน SLA แต่ Helpdesk ตามบี้จนแผนกยอม 'ปิดเคส' ได้สำเร็จในกรอบเวลาที่เลือก (พร้อมหลักฐาน)")

    if not sla_cleared_df.empty:
        sla_cleared_df['ใช้เวลาจริง (ชม.)'] = (sla_cleared_df['actual_minutes_spent'] / 60).round(1)
        sla_cleared_df['SLA (ชม.)'] = (sla_cleared_df['sla_limit_minutes'] / 60).round(1)
        sla_cleared_df = sla_cleared_df.sort_values(by='Closed_DT', ascending=False)

        # หลักฐาน 3 เวลา
        sla_cleared_df['วันที่เปิด'] = sla_cleared_df['Received_DT'].dt.strftime('%d/%m/%Y %H:%M').fillna('-')
        sla_cleared_df['วันที่เริ่มตาม'] = sla_cleared_df['First_Track_Time'].dt.strftime('%d/%m/%Y %H:%M').fillna('-')
        sla_cleared_df['วันที่ปิด'] = sla_cleared_df['Closed_DT'].dt.strftime('%d/%m/%Y %H:%M').fillna('-')

        display_cleared = sla_cleared_df[['Case_Id', 'วันที่เปิด', 'วันที่เริ่มตาม', 'วันที่ปิด', 'department', 'SLA (ชม.)', 'ใช้เวลาจริง (ชม.)', 'First_Agent_Name']]
        display_cleared.columns = ['หมายเลข Case', 'เวลาเปิดเคส', 'เวลาที่เริ่มติดตาม', 'เวลาที่ปิดเคส', 'แผนก', 'SLA (ชม.)', 'ใช้เวลาจนจบ (ชม.)', 'ฮีโร่ที่ตามงาน']

        st.dataframe(display_cleared, use_container_width=True, height=300, hide_index=True)
    else:
        st.info("ยังไม่มีผลงานการปิดเคสที่หลุด SLA ในช่วงเวลานี้")

    # ==========================================
    # 👨‍💻 เสาที่ 3: ตะแกรงร่อนความขยัน (Agent Performance)
    # ==========================================
    st.markdown("<hr style='margin-top: 30px; margin-bottom: 10px;'>", unsafe_allow_html=True)
    section_title("🕵️‍♂️ ตะแกรงร่อนความขยัน: สรุปผลงาน Helpdesk รายบุคคล", "📊", "ประเมินศักยภาพการตามงาน ว่าใครรับผิดชอบตามบี้จนสำเร็จ และใครปล่อยเคสที่ตามไว้ให้ค้างเติ่ง")

    tracked_all_df = df_filtered[df_filtered['Track_Status'] == 'ติดตาม']
    if not tracked_all_df.empty:
        valid_agents_df = tracked_all_df[tracked_all_df['First_Agent_Name'] != 'ไม่มี']
        
        agent_stats = valid_agents_df.groupby('First_Agent_Name').agg(
            เคสที่ตามทั้งหมด=('Case_Id', 'count'),
            กู้ชีพเกินSLAสำเร็จ=('Case_Id', lambda x: valid_agents_df.loc[x.index, 'sla_status_label'].isin(['❌ เกิน SLA (ปิดแล้ว)']).sum() if 'sla_status_label' in valid_agents_df.columns else 0),
            ปิดเคสรวมสำเร็จ=('status', lambda x: x.isin(['ปิด Case', 'เสร็จสิ้น']).sum()), 
            ตามแล้วยังค้างอยู่=('status', lambda x: (~x.isin(['ปิด Case', 'เสร็จสิ้น'])).sum())
        ).reset_index()

        agent_stats['% ปิดสำเร็จ'] = (agent_stats['ปิดเคสรวมสำเร็จ'] / agent_stats['เคสที่ตามทั้งหมด']) * 100
        agent_stats = agent_stats.sort_values(by=['ปิดเคสรวมสำเร็จ', 'เคสที่ตามทั้งหมด'], ascending=[False, False])

        st.dataframe(
            agent_stats[['First_Agent_Name', 'เคสที่ตามทั้งหมด', 'ปิดเคสรวมสำเร็จ', 'กู้ชีพเกินSLAสำเร็จ', 'ตามแล้วยังค้างอยู่', '% ปิดสำเร็จ']], 
            use_container_width=True, hide_index=True, 
            column_config={
                "First_Agent_Name": st.column_config.TextColumn("รายชื่อเจ้าหน้าที่ Helpdesk"),
                "เคสที่ตามทั้งหมด": st.column_config.NumberColumn("เข้าไปตามทั้งหมด (เคส)"),
                "กู้ชีพเกินSLAสำเร็จ": st.column_config.NumberColumn("กู้ชีพเคสเกิน SLA สำเร็จ 🏆"),
                "ปิดเคสรวมสำเร็จ": st.column_config.NumberColumn("บี้จนปิดสำเร็จรวม (เคส)"),
                "ตามแล้วยังค้างอยู่": st.column_config.NumberColumn("ตามแล้วแต่ยังค้าง (เคส)"),
                "% ปิดสำเร็จ": st.column_config.ProgressColumn("อัตราการบี้งานสำเร็จ (%)", format="%.1f%%", min_value=0, max_value=100)
            }
        )
    else:
        st.info("ไม่มีข้อมูลการติดตามงานรายบุคคลในช่วงเวลานี้")

except Exception as e:
    st.error(f"❌ เจอตัวการแล้ว! Error จากระบบคือ: {e}")
