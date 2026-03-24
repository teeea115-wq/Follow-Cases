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
st.set_page_config(page_title="SLA KPI Evaluation Center", page_icon="🎯", layout="wide", initial_sidebar_state="expanded")

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
    st.markdown("<br><br><h2 style='text-align: center; color: #1E293B;'>🔒 KPI Tracking Login</h2>", unsafe_allow_html=True)
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

# 💡 อัปเกรดลอจิกการนับจำนวนครั้งที่ตามงานใหม่ทั้งหมด!
def extract_tracking_info(row, col_msg_actual, col_time_actual):
    msg_str = str(row.get(col_msg_actual, ''))
    time_str = str(row.get(col_time_actual, ''))
    
    if msg_str in ('nan', '', 'None'): 
        return pd.Series({'Track_Status': 'ไม่ติดตาม', 'Track_Count': 0, 'First_Agent': 'ไม่มี', 'First_Track_Time': pd.NaT, 'Last_Track_Time': pd.NaT})
    
    # 🔍 สแกนหาคำว่าติดตาม "ทุกจุด" ในข้อความ (ไม่สนว่าจะเว้นบรรทัดแบบไหน)
    tracking_pattern = r"(?i)(เบื้องต้นทางเจ้าหน้าที่ทำการติดตาม|help\s*desk\s*[0-9]+.*ติดตาม)"
    track_matches = re.findall(tracking_pattern, msg_str)
    track_count = len(track_matches)
    
    first_agent = 'ไม่มี'
    agent_match = re.search(r"(?i)help\s*desk\s*([0-9]+)", msg_str)
    if agent_match:
        first_agent = f"Help Desk {agent_match.group(1)}"
        
    # ดึงเวลาออกมา (ถ้า format อ่านได้)
    track_times = []
    found_times = re.findall(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", time_str)
    if found_times:
        for t in found_times:
            try: track_times.append(pd.to_datetime(t))
            except: pass
            
    if not track_times:
        for t_val in re.split(r'[,|\n]', time_str):
            t_val = t_val.strip()
            try:
                t_obj = pd.to_datetime(t_val, errors='coerce') 
                if pd.notna(t_obj): track_times.append(t_obj)
            except: pass
            
    return pd.Series({
        'Track_Status': 'ติดตาม' if track_count > 0 else 'ไม่ติดตาม', 
        'Track_Count': track_count, 
        'First_Agent': first_agent, 
        'First_Track_Time': min(track_times) if track_times else pd.NaT, 
        'Last_Track_Time': max(track_times) if track_times else pd.NaT
    })

# ==========================================
# 5. โหลดข้อมูลจาก Google BigQuery
# ==========================================
@st.cache_data(ttl=600, show_spinner=False)
def load_and_prep_data_bq():
    key_dict = st.secrets["connections"]["bigquery"]
    credentials = service_account.Credentials.from_service_account_info(key_dict)
    client = bigquery.Client(credentials=credentials, project=credentials.project_id)

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
    with st.spinner("🚀 กำลังประมวลผลข้อมูล KPI..."):
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

    st.sidebar.markdown("<h2 style='margin-top: 15px;'>📅 รอบประเมิน KPI</h2>", unsafe_allow_html=True)
    st.sidebar.markdown("<p style='font-size: 12px; color: #64748B;'>เลือกวันที่ได้อิสระ ไม่บังคับรูปแบบ</p>", unsafe_allow_html=True)

    today_date = pd.Timestamp.now().date()
    first_day_of_month = today_date.replace(day=1)

    start_date_input = st.sidebar.date_input("เริ่มวันที่ (Start Date)", value=first_day_of_month)
    end_date_input = st.sidebar.date_input("ถึงวันที่ (End Date)", value=today_date)
    
    start_date = pd.to_datetime(start_date_input)
    end_date = pd.to_datetime(end_date_input).replace(hour=23, minute=59, second=59)

    open_mask = (df['Received_DT'] <= end_date) & (
        (~df['status'].isin(['ปิด Case', 'เสร็จสิ้น'])) | 
        (df['Closed_DT'] > end_date)
    )
    closed_mask = (df['status'].isin(['ปิด Case', 'เสร็จสิ้น'])) & (df['Closed_DT'] >= start_date) & (df['Closed_DT'] <= end_date)
    
    df_filtered = df[open_mask | closed_mask].copy()

    st.sidebar.markdown("<hr style='margin-top: 5px; margin-bottom: 20px;'>", unsafe_allow_html=True)
    all_depts = sorted([str(x) for x in df_filtered['department'].unique()])
    selected_depts = st.sidebar.multiselect("🏢 แผนก (Department):", all_depts)
    if selected_depts: df_filtered = df_filtered[df_filtered['department'].isin(selected_depts)]

    # ==========================================
    # 📊 แบ่งกลุ่มข้อมูล
    # ==========================================
    sla_debt_df = df_filtered[open_mask & (df_filtered['sla_status_label'].isin(['🔥 เกินกำหนด SLA (รีบปิดด่วน!)', '⚠️ ใกล้หลุด SLA (เร่งมือ)', '❌ เกิน SLA (ปิดแล้ว)']))]
    
    period_closed_df = df_filtered[closed_mask]
    tracked_closed_df = period_closed_df[period_closed_df['Track_Status'] == 'ติดตาม']

    tracked_over_sla_df = tracked_closed_df[tracked_closed_df['sla_status_label'].str.contains('เกิน SLA', na=False)]
    tracked_in_sla_df = tracked_closed_df[~tracked_closed_df['sla_status_label'].str.contains('เกิน SLA', na=False)]

    actual_breach_open_df = df_filtered[open_mask & (df_filtered['sla_status_label'].str.contains('เกิน', na=False))]
    all_closed_over_sla_df = period_closed_df[period_closed_df['sla_status_label'].str.contains('เกิน', na=False)]
    
    total_breached_cases = len(actual_breach_open_df) + len(all_closed_over_sla_df)
    rescued_cases = len(tracked_over_sla_df)
    rescue_rate = (rescued_cases / total_breached_cases * 100) if total_breached_cases > 0 else 0

    # ==========================================
    # 7. Dashboard Layout
    # ==========================================
    st.markdown("<h1>🎯 SLA KPI Evaluation Center</h1>", unsafe_allow_html=True)
    st.markdown(f"<p style='color: #64748B; margin-top: -15px; margin-bottom: 25px;'>ประเมินผลงานการติดตามและปิดเคสของรอบวันที่ <b>{start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')}</b></p>", unsafe_allow_html=True)

    st.markdown("#### 🚀 ประสิทธิภาพการตามบี้เคสที่เกิน SLA (SLA Rescue KPI)")
    k1, k2, k3, k4 = st.columns(4)
    with k1: create_kpi_card("เคสเกิน SLA ทั้งหมด", f"{total_breached_cases:,}", "#64748B", "เคสที่ทะลุ SLA ไปแล้ว (ทั้งค้างและปิด)")
    with k2: create_kpi_card("กู้ชีพสำเร็จ", f"{rescued_cases:,}", "#10B981", "จำนวนเคสเกิน SLA ที่ตามจนปิดได้")
    with k3: 
        color_rate = "#10B981" if rescue_rate >= 70 else "#EF4444"
        create_kpi_card("SLA Win Rate", f"{rescue_rate:.1f}%", color_rate, "อัตราการกู้ชีพสำเร็จ (เป้าหมาย 100%)")
    with k4: create_kpi_card("ปล่อยค้างไว้", f"{len(actual_breach_open_df):,}", "#EF4444", "เคสเกิน SLA ที่ยังปิดไม่ได้ (หนี้ค้าง)")

    st.markdown("<hr style='margin-top: 20px; margin-bottom: 20px;'>", unsafe_allow_html=True)

    # ==========================================
    # 🏆 เสาที่ 1: ผลงานกู้ชีพ (กว้างเต็มจอ)
    # ==========================================
    section_title("🚀 ผลงานกู้ชีพ (ปิดเคสที่เกิน SLA แล้ว)", "✅", "รวมผลงานเคสที่ทะลุ SLA ไปแล้ว แต่ Helpdesk ตามบี้จนแผนกยอมปิดเคสให้สำเร็จ")

    if not tracked_over_sla_df.empty:
        df_show1 = tracked_over_sla_df.copy()
        df_show1['SLA (ชม.)'] = (df_show1['sla_limit_minutes'] / 60).round(1)
        df_show1['ใช้เวลาจริง (ชม.)'] = (df_show1['actual_minutes_spent'] / 60).round(1)
        df_show1['วันที่เปิด'] = df_show1['Received_DT'].dt.strftime('%d/%m/%Y %H:%M').fillna('-')
        df_show1['วันที่ปิด'] = df_show1['Closed_DT'].dt.strftime('%d/%m/%Y %H:%M').fillna('-')
        df_show1 = df_show1.sort_values(by='Closed_DT', ascending=False)

        df_show1 = df_show1[['Case_Id', 'วันที่เปิด', 'วันที่ปิด', 'department', 'Category', 'Sub_Category', 'Track_Count', 'SLA (ชม.)', 'First_Agent_Name', 'ใช้เวลาจริง (ชม.)']]
        df_show1.columns = ['เลข Case', 'เวลาเปิดเคส', 'เวลาปิดสำเร็จ', 'แผนก', 'หมวดหมู่หลัก', 'หมวดหมู่ย่อย', 'ตามไป (ครั้ง)', 'SLA (ชม.)', 'ฮีโร่กู้ชีพ', 'ใช้เวลา (ชม.)']

        st.dataframe(df_show1, use_container_width=True, height=350, hide_index=True)
    else:
        st.info("ไม่มีผลงานกู้ชีพเคสเกิน SLA ในรอบนี้")

    # ==========================================
    # 🏆 เสาที่ 2: ผลงานตามปกติ (กว้างเต็มจอ)
    # ==========================================
    st.markdown("<br>", unsafe_allow_html=True)
    section_title("✅ ผลงานตามปกติ (ปิดเคสทันภายใน SLA)", "⏱️", "รวมเคสที่ Helpdesk ติดตามงานและสามารถปิดได้ทันเวลาตาม SLA ที่กำหนด")

    if not tracked_in_sla_df.empty:
        df_show2 = tracked_in_sla_df.copy()
        df_show2['SLA (ชม.)'] = (df_show2['sla_limit_minutes'] / 60).round(1)
        df_show2['ใช้เวลาจริง (ชม.)'] = (df_show2['actual_minutes_spent'] / 60).round(1)
        df_show2['วันที่เปิด'] = df_show2['Received_DT'].dt.strftime('%d/%m/%Y %H:%M').fillna('-')
        df_show2['วันที่ปิด'] = df_show2['Closed_DT'].dt.strftime('%d/%m/%Y %H:%M').fillna('-')
        df_show2 = df_show2.sort_values(by='Closed_DT', ascending=False)

        df_show2 = df_show2[['Case_Id', 'วันที่เปิด', 'วันที่ปิด', 'department', 'Category', 'Sub_Category', 'Track_Count', 'SLA (ชม.)', 'First_Agent_Name', 'ใช้เวลาจริง (ชม.)']]
        df_show2.columns = ['เลข Case', 'เวลาเปิดเคส', 'เวลาปิดสำเร็จ', 'แผนก', 'หมวดหมู่หลัก', 'หมวดหมู่ย่อย', 'ตามไป (ครั้ง)', 'SLA (ชม.)', 'คนตามงาน', 'ใช้เวลา (ชม.)']

        st.dataframe(df_show2, use_container_width=True, height=350, hide_index=True)
    else:
        st.info("ไม่มีผลงานติดตามเคสปกติในรอบนี้")

    # ==========================================
    # 👨‍💻 เสาที่ 3: ตะแกรงร่อนความขยัน
    # ==========================================
    st.markdown("<hr style='margin-top: 30px; margin-bottom: 10px;'>", unsafe_allow_html=True)
    section_title("🕵️‍♂️ ตะแกรงร่อนความขยัน: วัดผล KPI Helpdesk รายบุคคล", "📊", "ประเมินศักยภาพการตามงานในรอบเดือนนี้ ว่าใครมีผลงานประเภทไหนโดดเด่น")

    tracked_all_df = df_filtered[df_filtered['Track_Status'] == 'ติดตาม']
    if not tracked_all_df.empty:
        valid_agents_df = tracked_all_df[tracked_all_df['First_Agent_Name'] != 'ไม่มี'].copy()
        
        if not valid_agents_df.empty:
            agent_closed_period = valid_agents_df[valid_agents_df.index.isin(period_closed_df.index)]
            
            agent_stats = valid_agents_df.groupby('First_Agent_Name').agg(
                เคสที่ตามทั้งหมด=('Case_Id', 'count'),
                ตามแล้วยังค้างอยู่=('status', lambda x: (~x.isin(['ปิด Case', 'เสร็จสิ้น'])).sum())
            ).reset_index()

            closed_stats = agent_closed_period.groupby('First_Agent_Name').agg(
                ปิดเคสรวมในรอบ=('Case_Id', 'count')
            ).reset_index()

            over_sla_agent = agent_closed_period[agent_closed_period['sla_status_label'].str.contains('เกิน SLA', na=False)].groupby('First_Agent_Name').size().reset_index(name='ผลงานกู้ชีพ (เกิน SLA)')
            in_sla_agent = agent_closed_period[~agent_closed_period['sla_status_label'].str.contains('เกิน SLA', na=False)].groupby('First_Agent_Name').size().reset_index(name='ผลงานปิดปกติ (ใน SLA)')
            
            agent_stats = pd.merge(agent_stats, closed_stats, on='First_Agent_Name', how='left').fillna(0)
            agent_stats = pd.merge(agent_stats, over_sla_agent, on='First_Agent_Name', how='left').fillna(0)
            agent_stats = pd.merge(agent_stats, in_sla_agent, on='First_Agent_Name', how='left').fillna(0)
            
            agent_stats['% ปิดสำเร็จในรอบ'] = (agent_stats['ปิดเคสรวมในรอบ'] / agent_stats['เคสที่ตามทั้งหมด']) * 100
            agent_stats = agent_stats.sort_values(by=['ผลงานกู้ชีพ (เกิน SLA)', 'ปิดเคสรวมในรอบ'], ascending=[False, False])

            st.dataframe(
                agent_stats[['First_Agent_Name', 'เคสที่ตามทั้งหมด', 'ผลงานกู้ชีพ (เกิน SLA)', 'ผลงานปิดปกติ (ใน SLA)', 'ปิดเคสรวมในรอบ', 'ตามแล้วยังค้างอยู่', '% ปิดสำเร็จในรอบ']], 
                use_container_width=True, hide_index=True, 
                column_config={
                    "First_Agent_Name": st.column_config.TextColumn("รายชื่อเจ้าหน้าที่ Helpdesk"),
                    "เคสที่ตามทั้งหมด": st.column_config.NumberColumn("เข้าไปตามทั้งหมด (เคส)"),
                    "ผลงานกู้ชีพ (เกิน SLA)": st.column_config.NumberColumn("กู้ชีพเกิน SLA สำเร็จ 🚀"),
                    "ผลงานปิดปกติ (ใน SLA)": st.column_config.NumberColumn("ปิดทัน SLA ✅"),
                    "ปิดเคสรวมในรอบ": st.column_config.NumberColumn("รวมปิดได้ในรอบ KPI"),
                    "ตามแล้วยังค้างอยู่": st.column_config.NumberColumn("ตามแล้วแต่ยังค้าง"),
                    "% ปิดสำเร็จในรอบ": st.column_config.ProgressColumn("Win Rate (%)", format="%.1f%%", min_value=0, max_value=100)
                }
            )
        else:
            st.info("ยังไม่มีรายชื่อเจ้าหน้าที่เข้าทำการติดตามในระบบ")
    else:
        st.info("ไม่มีข้อมูลการติดตามงานในช่วงเวลานี้")

    # ==========================================
    # 🚨 เสาที่ 4: ศูนย์เตือนภัยวิกฤต SLA
    # ==========================================
    st.markdown("<hr style='margin-top: 30px; margin-bottom: 10px;'>", unsafe_allow_html=True)
    section_title("🚨 ศูนย์เตือนภัยวิกฤต: หนี้ SLA ที่ยังไม่ได้ตามงาน!", "⏰", "รายการเคสทะลุ SLA ที่ Helpdesk ปล่อยปละละเลย (ยังไม่มีประวัติติดตาม)")

    if not sla_debt_df.empty:
        untracked_sla_df = sla_debt_df[sla_debt_df['Track_Status'] == 'ไม่ติดตาม'].copy()
        
        if not untracked_sla_df.empty:
            untracked_sla_df['รอมาแล้ว (ชม.)'] = (untracked_sla_df['actual_minutes_spent'] / 60).round(1)
            untracked_sla_df['SLA (ชม.)'] = (untracked_sla_df['sla_limit_minutes'] / 60).round(1)
            untracked_sla_df = untracked_sla_df.sort_values(by=['sla_status_label', 'รอมาแล้ว (ชม.)'], ascending=[True, False])

            untracked_sla_df['วันที่เปิด'] = untracked_sla_df['Received_DT'].dt.strftime('%d/%m/%Y %H:%M').fillna('-')

            display_debt = untracked_sla_df[['Case_Id', 'วันที่เปิด', 'department', 'Category', 'Sub_Category', 'SLA (ชม.)', 'รอมาแล้ว (ชม.)', 'sla_status_label']]
            display_debt.columns = ['เลข Case', 'เวลาที่เปิดเคส', 'แผนก', 'หมวดหมู่หลัก', 'หมวดหมู่ย่อย', 'SLA (ชม.)', 'รอมาแล้ว (ชม.)', 'สถานะวิกฤต']

            st.dataframe(
                display_debt, use_container_width=True, height=350, hide_index=True,
                column_config={"สถานะวิกฤต": st.column_config.TextColumn("สถานะวิกฤต")}
            )
        else:
            st.success("🎉 เยี่ยมมาก! ไม่มีเคสที่ปล่อยหลุด SLA โดยไม่ตามงานเลย (จี้ครบทุกเคสแล้ว)")
    else:
        st.success("🎉 สุดยอดมาก! ตอนนี้ไม่มีเคสไหนที่ค้างเกิน SLA เลย")

    # ==========================================
    # 📋 เสาที่ 5: เคสที่ตามแล้วแต่ยังไม่ปิด
    # ==========================================
    st.markdown("<hr style='margin-top: 30px; margin-bottom: 10px;'>", unsafe_allow_html=True)
    section_title("🔄 รายการเคสที่ตามแล้วแต่ยังค้างอยู่ (Tracked but Pending)", "📞", "Helpdesk เข้าไปตามงานแล้ว แต่แผนกยังไม่ยอมปิดเคสให้ (ต้องไปจี้ซ้ำแบบรายคน!)")

    tracked_open_df = df_filtered[open_mask & (df_filtered['Track_Status'] == 'ติดตาม')].copy()

    if not tracked_open_df.empty:
        tracked_open_df['SLA (ชม.)'] = (tracked_open_df['sla_limit_minutes'] / 60).round(1)
        tracked_open_df['รอมาแล้ว (ชม.)'] = (tracked_open_df['actual_minutes_spent'] / 60).round(1)
        
        tracked_open_df['วันที่เปิด'] = tracked_open_df['Received_DT'].dt.strftime('%d/%m/%Y %H:%M').fillna('-')
        tracked_open_df['วันที่ตาม'] = tracked_open_df['First_Track_Time'].dt.strftime('%d/%m/%Y %H:%M').fillna('-')

        tracked_open_df = tracked_open_df.sort_values(by='รอมาแล้ว (ชม.)', ascending=False)

        display_tracked_open = tracked_open_df[['Case_Id', 'First_Agent_Name', 'วันที่เปิด', 'วันที่ตาม', 'department', 'Category', 'Sub_Category', 'Track_Count', 'SLA (ชม.)', 'รอมาแล้ว (ชม.)']]
        display_tracked_open.columns = ['เลข Case', 'ผู้ติดตาม', 'เปิดเคส', 'ตามล่าสุด', 'แผนก', 'หมวดหมู่หลัก', 'หมวดหมู่ย่อย', 'ตามไป (ครั้ง)', 'SLA (ชม.)', 'รอมาแล้ว (ชม.)']

        st.dataframe(
            display_tracked_open, use_container_width=True, height=400, hide_index=True,
            column_config={
                "เลข Case": st.column_config.TextColumn("เลข Case"),
                "ผู้ติดตาม": st.column_config.TextColumn("ผู้ติดตาม (ต้องไปจี้)"),
                "ตามไป (ครั้ง)": st.column_config.NumberColumn("ตามไป (ครั้ง)"),
            }
        )
    else:
        st.success("🎉 ไม่มีเคสที่ตามแล้วค้างอยู่ในระบบ! เคสที่ถูกตามปิดหมดแล้วเกลี้ยงตู้!")

except Exception as e:
    st.error(f"❌ เจอตัวการแล้ว! Error จากระบบคือ: {e}")
