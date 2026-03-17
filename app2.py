import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re
import numpy as np

# ==========================================
# ⚙️ 1. ตั้งค่าชื่อคอลัมน์
# ==========================================
COL_MSG = 'response_message'  
COL_TIME = 'response_time_v'  

# ==========================================
# 2. ตั้งค่าหน้าเว็บและ CSS
# ==========================================
st.set_page_config(page_title="Helpdesk Executive Analytics", page_icon="📈", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Prompt:wght@300;400;500;600;700&display=swap');
    html, body, [class*="css"], .stApp { font-family: 'Prompt', sans-serif !important; background-color: #F8FAFC !important; color: #0F172A !important; }
    p, label, h1, h2, h3, h4, h5, h6 { color: #0F172A !important; font-weight: 600 !important; }
    div.stPlotlyChart, div[data-testid="stDataFrame"] {
        background-color: #ffffff !important; border-radius: 12px; padding: 24px 10px;
        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.05); border: 1px solid #E2E8F0 !important; margin-bottom: 24px; 
    }
    [data-testid="stSidebar"], [data-testid="stSidebar"] > div:first-child { background-color: #FFFFFF !important; border-right: 1px solid #E2E8F0 !important; }
    div[data-testid="stDateInput"] div, div[data-testid="stTextInput"] div, div[data-baseweb="select"] > div, input { 
        background-color: #F8FAFC !important; color: #0F172A !important; border-color: #CBD5E1 !important; border-radius: 6px !important; 
    }
    [data-testid="stSidebar"] [data-testid="stButton"] button, div[data-testid="stButton"] button {
        background-color: #FFFFFF !important; color: #0F172A !important; border: 1px solid #CBD5E1 !important; 
        font-weight: 700 !important; border-radius: 8px !important; transition: all 0.3s !important;
    }
    [data-testid="stSidebar"] [data-testid="stButton"] button:hover { border-color: #EF4444 !important; color: #EF4444 !important; background-color: #FEF2F2 !important; }
    
    /* แต่งกล่อง Metric ให้ตัวใหญ่เตะตา */
    div[data-testid="stMetricValue"] { font-size: 36px !important; font-weight: 800 !important;}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3. 🔒 ระบบ Login
# ==========================================
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.markdown("<br><br><h2 style='text-align: center; color: #1E293B;'>🔒 Helpdesk Analytics Login</h2>", unsafe_allow_html=True)
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
    <div style="background-color: #ffffff; padding: 20px; border-radius: 12px; 
                border: 1px solid #E2E8F0; border-top: 5px solid {accent_color}; 
                box-shadow: 0 4px 6px rgba(0,0,0,0.02); height: 100%;">
        <p style="color: #475569; font-size: 14px; font-weight: 700; margin: 0 0 8px 0;">{title}</p>
        <h1 style="color: #0F172A; font-size: 32px; font-weight: 800; margin: 0; line-height: 1.1;">{value}</h1>
        {sub_html}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

def section_title(text, icon="", desc=""):
    st.markdown(f"<h3 style='color: #0F172A; font-weight: 700; margin-top: 35px; margin-bottom: 5px; border-bottom: 2px solid #E2E8F0; padding-bottom: 8px;'>{icon} {text}</h3>", unsafe_allow_html=True)
    if desc:
        st.markdown(f"<p style='color: #64748B; font-size: 15px; margin-bottom: 20px; line-height: 1.5;'><i>{desc}</i></p>", unsafe_allow_html=True)

def parse_sla_to_mins(sla_text):
    if pd.isna(sla_text): return 0
    text = str(sla_text)
    days = sum(map(int, re.findall(r'(\d+)\s*วัน', text)))
    hours = sum(map(int, re.findall(r'(\d+)\s*ชั่วโมง', text)))
    mins = sum(map(int, re.findall(r'(\d+)\s*นาที', text)))
    return (days * 1440) + (hours * 60) + mins

def calculate_actual_mins(row, now):
    if row.get('status') in ['ปิด Case', 'เสร็จสิ้น']:
        if pd.notna(row.get('Received_DT')) and pd.notna(row.get('Closed_DT')): 
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
    if is_closed: return '✅ ภายใน SLA' if actual <= limit else '❌ เกิน SLA (ปิดแล้ว)'
    else:
        if actual > limit: return '🔥 เกินกำหนด (รีบปิดด่วน!)'
        elif limit > 0 and (actual / limit) >= 0.8: return '⚠️ ใกล้หลุด SLA (เร่งมือ)'
        else: return '🟢 ปกติ'

def extract_tracking_info(row, col_msg_actual, col_time_actual):
    msg_str = str(row.get(col_msg_actual, ''))
    time_str = str(row.get(col_time_actual, ''))

    if msg_str == 'nan' or msg_str == '':
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
                t_obj = pd.to_datetime(t_val, format='%d/%m/%Y %H:%M', errors='coerce')
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
# 5. โหลดข้อมูล
# ==========================================
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSRVUhShKYRay7zI0R4LcD9YBoe9VaZHIYvSRMWNXBAMDFws78ImtPqVPAfqKSvD_4lua8dgJm1OTaG/pub?output=csv"

@st.cache_data(ttl=300)
def load_and_prep_data(url):
    df = pd.read_csv(url)
    df.columns = df.columns.str.strip() 

    # 🔥 ระบบป้องกัน Error: สร้างคอลัมน์รอไว้ล่วงหน้าเสมอ จะได้ไม่เกิด KeyError 'Received_DT'
    df['Received_DT'] = pd.NaT
    df['Received_Date'] = pd.NaT
    df['Closed_DT'] = pd.NaT

   # ค้นหาชื่อคอลัมน์แบบไม่สนใจตัวพิมพ์เล็ก/ใหญ่
    recv_col = next((c for c in df.columns if str(c).lower() == 'datetime_received'), None)
    if recv_col:
        # 💥 พระเอกคือ dayfirst=True บังคับให้ระบบรู้ว่าตัวเลขชุดแรกคือ "วัน" ไม่ใช่ "เดือน"
        df['Received_DT'] = pd.to_datetime(df[recv_col], dayfirst=True, errors='coerce')
        df['Received_Date'] = df['Received_DT'].dt.date
        
    closed_col = next((c for c in df.columns if str(c).lower() == 'datetime_closed'), None)
    if closed_col:
        df['Closed_DT'] = pd.to_datetime(df[closed_col], dayfirst=True, errors='coerce')

    df['department'] = df.get('department', pd.Series(['ไม่ระบุ']*len(df))).fillna('ไม่ระบุ')
    df['status'] = df.get('status', pd.Series(['ไม่ระบุ']*len(df))).fillna('ไม่ระบุ')
    df['Category'] = df.get('Category', pd.Series(['ไม่ระบุ']*len(df))).fillna('ไม่ระบุ')
    df['Sub_Category'] = df.get('Sub_Category', pd.Series(['ไม่ระบุ']*len(df))).fillna('ไม่ระบุ')

    now = pd.Timestamp.now()
    if 'SLA' in df.columns:
        df['sla_limit_minutes'] = df['SLA'].apply(parse_sla_to_mins)
        df['actual_minutes_spent'] = df.apply(lambda row: calculate_actual_mins(row, now), axis=1)
        df['sla_status_label'] = df.apply(get_sla_status_label, axis=1)
    else: df['sla_status_label'] = 'ไม่พบข้อมูล SLA'

    actual_msg_col = next((col for col in df.columns if COL_MSG in col), None)
    actual_time_col = next((col for col in df.columns if COL_TIME in col), None)

    if actual_msg_col and actual_time_col:
        tracking_df = df.apply(lambda row: extract_tracking_info(row, actual_msg_col, actual_time_col), axis=1)
        df = pd.concat([df, tracking_df], axis=1)
    else:
        df['Track_Status'] = 'ไม่ติดตาม'
        df['Track_Count'] = 0
        df['First_Agent'] = 'ไม่มี'
        df['Last_Track_Time'] = pd.NaT

    agent_mapping = {
        'Help Desk 2': 'Help Desk 2 (เจนจิรา)',
        'Help Desk 3': 'Help Desk 3 (มนัส)',
        'Help Desk 4': 'Help Desk 4 (ฉัตรลดา)',
        'Help Desk 5': 'Help Desk 5 (จิรวัฒน์)',
        'Help Desk 6': 'Help Desk 6 (กิติลักษณ์)'
    }
    df['First_Agent_Name'] = df.get('First_Agent', pd.Series(['ไม่มี']*len(df))).map(agent_mapping).fillna(df.get('First_Agent', 'ไม่มี'))

    return df, actual_msg_col, actual_time_col

try:
    df, found_msg, found_time = load_and_prep_data(SHEET_URL)

    if not found_msg or not found_time:
        st.warning(f"⚠️ **ระบบหาคอลัมน์ไม่เจอ!** กรุณาเช็คในไฟล์ Sheets ว่ามีคอลัมน์ชื่อ `{COL_MSG}` และ `{COL_TIME}` เป๊ะๆ หรือไม่")

    # ==========================================
    # 6. Sidebar Filter
    # ==========================================
    if st.sidebar.button("🚪 ล็อกเอาท์ (Logout)", use_container_width=True):
        st.session_state["authenticated"] = False
        st.rerun()

    st.sidebar.markdown("<h2 style='margin-top: 15px;'>🎯 ตัวกรองข้อมูล</h2>", unsafe_allow_html=True)
    st.sidebar.markdown("<hr style='margin-top: 5px; margin-bottom: 20px;'>", unsafe_allow_html=True)

    if df['Received_Date'].dropna().empty: min_date = max_date = pd.Timestamp.now().date()
    else: min_date, max_date = df['Received_Date'].min(), df['Received_Date'].max()

    date_range = st.sidebar.date_input("📅 ช่วงเวลา", value=(min_date, max_date), min_value=min_date, max_value=max_date)
    start_date = date_range[0] if len(date_range) > 0 else min_date
    end_date = date_range[1] if len(date_range) > 1 else start_date
    df_filtered = df[(df['Received_Date'] >= start_date) & (df['Received_Date'] <= end_date)]

    all_depts = sorted([str(x) for x in df_filtered['department'].unique()])
    all_status = sorted([str(x) for x in df_filtered['status'].unique()])
    all_sla = sorted([str(x) for x in df_filtered['sla_status_label'].unique()]) 

    selected_depts = st.sidebar.multiselect("🏢 แผนก (Department):", all_depts)
    selected_status = st.sidebar.multiselect("📌 สถานะ (Status):", all_status)
    selected_sla = st.sidebar.multiselect("⏱️ เกณฑ์ SLA:", all_sla) 

    if selected_depts: df_filtered = df_filtered[df_filtered['department'].isin(selected_depts)]
    if selected_status: df_filtered = df_filtered[df_filtered['status'].isin(selected_status)]
    if selected_sla: df_filtered = df_filtered[df_filtered['sla_status_label'].isin(selected_sla)] 

    df_interactive = df_filtered.copy() 

    # สไตล์กราฟพื้นฐาน (บังคับฟอนต์และสีให้ดูเป็นมืออาชีพ)
    pro_layout = dict(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
