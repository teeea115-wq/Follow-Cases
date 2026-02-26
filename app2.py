import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re
import numpy as np

# ==========================================
# ⚙️ 1. ตั้งค่าชื่อคอลัมน์
# ==========================================
COL_MSG = 'ข้อความตอบกลับ'  
COL_TIME = 'เวลาข้อความตอบกลับ'  

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
    if row['สถานะ'] in ['ปิด Case', 'เสร็จสิ้น']:
        if pd.notna(row['Received_DT']) and pd.notna(row['Closed_DT']): return (row['Closed_DT'] - row['Received_DT']).total_seconds() / 60
        return 0
    else:
        if pd.notna(row['Received_DT']): return (now - row['Received_DT']).total_seconds() / 60
        return 0

def get_sla_status_label(row):
    limit = row['sla_limit_minutes']
    actual = row['actual_minutes_spent']
    is_closed = row['สถานะ'] in ['ปิด Case', 'เสร็จสิ้น']
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
    
    if 'วัน / เวลา (รับเรื่องร้องขอ)' in df.columns:
        df['Received_DT'] = pd.to_datetime(df['วัน / เวลา (รับเรื่องร้องขอ)'], format='%d/%m/%y %H:%M:%S', errors='coerce')
        df['Received_Date'] = df['Received_DT'].dt.date
    if 'วัน / เวลา (ปิดเคส)' in df.columns:
        df['Closed_DT'] = pd.to_datetime(df['วัน / เวลา (ปิดเคส)'], format='%d/%m/%y %H:%M:%S', errors='coerce')

    df['แผนก'] = df.get('แผนก', pd.Series(['ไม่ระบุ']*len(df))).fillna('ไม่ระบุ')
    df['สถานะ'] = df.get('สถานะ', pd.Series(['ไม่ระบุ']*len(df))).fillna('ไม่ระบุ')
    df['Category'] = df.get('Category', pd.Series(['ไม่ระบุ']*len(df))).fillna('ไม่ระบุ')
    df['Sub Category'] = df.get('Sub Category', pd.Series(['ไม่ระบุ']*len(df))).fillna('ไม่ระบุ')

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

    all_depts = sorted([str(x) for x in df_filtered['แผนก'].unique()])
    all_status = sorted([str(x) for x in df_filtered['สถานะ'].unique()])
    all_sla = sorted([str(x) for x in df_filtered['sla_status_label'].unique()]) 

    selected_depts = st.sidebar.multiselect("🏢 แผนก (Department):", all_depts)
    selected_status = st.sidebar.multiselect("📌 สถานะ (Status):", all_status)
    selected_sla = st.sidebar.multiselect("⏱️ เกณฑ์ SLA:", all_sla) 

    if selected_depts: df_filtered = df_filtered[df_filtered['แผนก'].isin(selected_depts)]
    if selected_status: df_filtered = df_filtered[df_filtered['สถานะ'].isin(selected_status)]
    if selected_sla: df_filtered = df_filtered[df_filtered['sla_status_label'].isin(selected_sla)] 

    df_interactive = df_filtered.copy() 

    # สไตล์กราฟพื้นฐาน (บังคับฟอนต์และสีให้ดูเป็นมืออาชีพ)
    pro_layout = dict(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", 
        font=dict(family="Prompt", color="#0F172A", size=14)
    )
    axis_style = dict(
        tickfont=dict(size=13, weight='bold', color='#1E293B'), 
        title_font=dict(size=14, weight='bold', color='#0F172A'), 
        showgrid=True, gridcolor="#E2E8F0", automargin=True
    )
    axis_style_no_grid = dict(axis_style, showgrid=False)

    # ==========================================
    # 7. Dashboard Layout 
    # ==========================================
    st.markdown("<h1>📊 Helpdesk Executive Analytics</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color: #64748B; margin-top: -15px; margin-bottom: 25px;'>ระบบวิเคราะห์ข้อมูลและติดตามผลการดำเนินงานแบบเรียลไทม์</p>", unsafe_allow_html=True)

    total = len(df_interactive)
    closed = len(df_interactive[df_interactive['สถานะ'].isin(['ปิด Case', 'เสร็จสิ้น'])])
    open_cases = total - closed
    tracked_df = df_interactive[df_interactive['Track_Status'] == 'ติดตาม']
    total_tracked = len(tracked_df)
    track_percent = (total_tracked / total * 100) if total > 0 else 0
    top_tracked_dept = tracked_df['แผนก'].mode()[0] if not tracked_df.empty else "-"

    # ----------------------------------
    # 1. SCORECARDS
    # ----------------------------------
    st.markdown("#### 📈 ภาพรวมเคสทั้งหมด (Overall Cases)")
    c1, c2, c3, c4 = st.columns(4)
    with c1: create_kpi_card("Total Cases", f"{total:,}", "#3B82F6", "เคสที่รับเข้ามาทั้งหมด")
    with c2: create_kpi_card("Completed", f"{closed:,}", "#10B981", "เคสที่ดำเนินการเสร็จสิ้น")
    with c3: create_kpi_card("In Progress", f"{open_cases:,}", "#F59E0B", "เคสที่ยังค้างอยู่ในระบบ")
    with c4: create_kpi_card("SLA Breached", f"{len(df_interactive[df_interactive['sla_status_label'].isin(['❌ เกิน SLA (ปิดแล้ว)', '🔥 เกินกำหนด (รีบปิดด่วน!)'])]):,}", "#EF4444", "เคสที่ใช้เวลาเกินเกณฑ์ SLA")

    st.markdown("#### 🎯 ภาพรวมการติดตามงาน (Follow-up Tracking)")
    t1, t2, t3, t4 = st.columns(4)
    with t1: create_kpi_card("รวมเคสที่มีการติดตาม", f"{total_tracked:,}", "#8B5CF6", "เคสทั้งหมดที่ถูกติดตาม")
    with t2: create_kpi_card("% การติดตามงาน", f"{track_percent:.1f}%", "#6366F1", "สัดส่วนเคสที่ถูกติดตาม")
    with t3: create_kpi_card("แผนกที่โดนตามบ่อยสุด", f"{top_tracked_dept}", "#EC4899", "แผนกที่ต้องไปสะกิดบ่อยที่สุด")
    with t4: create_kpi_card("ค้างชำระ (ตามแล้วไม่เสร็จ)", f"{len(tracked_df[~tracked_df['สถานะ'].isin(['ปิด Case', 'เสร็จสิ้น'])]):,}", "#F43F5E", "ตามแล้วแต่ยังค้างอยู่")

    st.markdown("<br>", unsafe_allow_html=True)

    # ----------------------------------
    # 2. กราฟปริมาณเคสรายวัน
    # ----------------------------------
    section_title("ปริมาณเคสรายวัน (Daily Volume Trend)", "📈", "แสดงแนวโน้มปริมาณเคสที่รับเข้ามาในแต่ละวัน เพื่อประเมินภาระงานของทีม")
    trend_df = df_interactive.groupby('Received_Date').size().reset_index(name='Cases')
    if not trend_df.empty:
        fig_trend = go.Figure()
        fig_trend.add_trace(go.Scatter(
            x=trend_df['Received_Date'], y=trend_df['Cases'], mode='lines+markers+text',
            text=trend_df['Cases'], textposition='top center', textfont=dict(color='#0F172A', size=14, weight="bold"),
            line=dict(color='#2563EB', width=3, shape='spline'), marker=dict(size=8, color='#FFFFFF', line=dict(width=2, color='#2563EB')),
            fill='tozeroy', fillcolor='rgba(59, 130, 246, 0.1)'
        ))
        fig_trend.update_traces(cliponaxis=False) 
        fig_trend.update_layout(**pro_layout, height=400, xaxis=axis_style_no_grid, yaxis=axis_style, margin=dict(t=30, b=30, l=30, r=30))
        fig_trend.update_yaxes(range=[0, trend_df['Cases'].max() * 1.25]) 
        st.plotly_chart(fig_trend, use_container_width=True)

    # ----------------------------------
    # 3. พลังของการติดตามงาน (กู้ชีพเคสติดขัด)
    # ----------------------------------
    section_title("⚡ พลังของการติดตามงาน (Intervention Impact)", "🔥", "วิเคราะห์ประสิทธิภาพของ Helpdesk ในการผลักดันเคสที่ติดขัดให้สำเร็จ และความรวดเร็วที่แผนกยอมปิดเคสหลังจากโดนจี้งาน")
    
    tracked_all = df_interactive[df_interactive['Track_Status'] == 'ติดตาม'].copy()
    tracked_closed = tracked_all[tracked_all['สถานะ'].isin(['ปิด Case', 'เสร็จสิ้น'])].copy()
    
    if not tracked_closed.empty and not tracked_all.empty:
        tracked_closed['Hours_After_Track'] = (tracked_closed['Closed_DT'] - tracked_closed['First_Track_Time']).dt.total_seconds() / 3600
        tracked_closed = tracked_closed[tracked_closed['Hours_After_Track'] >= 0]
        
        avg_hours_after = tracked_closed['Hours_After_Track'].mean() if not tracked_closed.empty else 0
        success_rate = (len(tracked_closed) / len(tracked_all)) * 100
        
        col_eff1, col_eff2 = st.columns([1, 2])
        with col_eff1:
            st.markdown(f"""
            <div style='background-color: #ECFDF5; border-left: 5px solid #10B981; padding: 15px; border-radius: 8px; margin-bottom: 15px;'>
                <h4 style='color: #065F46; margin: 0;'>🎯 อัตรากู้ชีพสำเร็จ</h4>
                <p style='color: #047857; font-size: 13px; margin: 5px 0 0 0;'>ผลักดันเคสที่ติดขัดจนปิดสำเร็จ</p>
                <h2 style='color: #10B981; margin: 5px 0 0 0;'>{success_rate:.1f} %</h2>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown(f"""
            <div style='background-color: #EFF6FF; border-left: 5px solid #3B82F6; padding: 15px; border-radius: 8px;'>
                <h4 style='color: #1E3A8A; margin: 0;'>⏱️ ความเร็วหลังโดนจี้</h4>
                <p style='color: #1D4ED8; font-size: 13px; margin: 5px 0 0 0;'>เวลาเฉลี่ยที่ปิดเคส (นับจากตอนทวงถาม)</p>
                <h2 style='color: #3B82F6; margin: 5px 0 0 0;'>{avg_hours_after:.1f} ชม.</h2>
            </div>
            """, unsafe_allow_html=True)
            
        with col_eff2:
            dept_response = tracked_closed.groupby('แผนก')['Hours_After_Track'].mean().reset_index()
            # จัดเรียงให้ค่าน้อยอยู่บน (ตอบสนองไวสุด)
            dept_response = dept_response.sort_values('Hours_After_Track', ascending=False) 
            
            # 💥 แก้ไข: กำหนดความสูงกราฟแบบไดนามิก และตั้งค่า tickmode='linear' ห้ามซ่อนชื่อแผนก
            dynamic_resp_h = max(300, len(dept_response) * 40)
            
            fig_resp = px.bar(
                dept_response, x='Hours_After_Track', y='แผนก', orientation='h', 
                text='Hours_After_Track', color_discrete_sequence=['#8B5CF6'],
                title="ความตื่นตัว: แผนกไหนตอบสนองไวที่สุดหลังโดนจี้งาน? (ชั่วโมง)"
            )
            fig_resp.update_traces(
                texttemplate='<b>%{x:.1f} ชม.</b>', textposition='outside', 
                textfont=dict(size=14, color='#0F172A', weight='bold'), cliponaxis=False
            )
            # 💥 แก้ไข: บังคับโชว์ทุกชื่อแผนก ไม่ให้เหลื่อมกัน
            fig_resp.update_layout(
                **pro_layout, height=dynamic_resp_h, 
                xaxis=dict(axis_style_no_grid, title="", range=[0, dept_response['Hours_After_Track'].max() * 1.3]), 
                yaxis=dict(axis_style_no_grid, title="", tickmode='linear', dtick=1), # tickmode คือพระเอกแก้บัค
                margin=dict(t=40, b=20, l=180, r=40)
            )
            st.plotly_chart(fig_resp, use_container_width=True)
    else:
        st.info("ยังไม่มีข้อมูลเคสที่ปิดแล้วเพื่อนำมาคำนวณเปรียบเทียบในหมวดนี้")

    # ----------------------------------
    # 4. กราฟแท่งแผนก (💥 จับแยกกางเต็มจอ และบังคับโชว์ทุกชื่อแผนก)
    # ----------------------------------
    st.markdown("<hr style='margin-top: 30px; margin-bottom: 10px;'>", unsafe_allow_html=True)
    
    section_title("ปริมาณงานทั้งหมด แยกตามแผนก (Total Cases)", "🏢", "แสดงปริมาณเคสที่แต่ละแผนกได้รับมอบหมาย เพื่อดูการกระจายตัวของงาน")
    dept_df = df_filtered['แผนก'].value_counts().reset_index()
    dept_df.columns = ['Department', 'Count']
    # 💥 แก้ไข: เพิ่มพื้นที่ความสูงให้พอดีกับจำนวนแผนก (แท่งละ 40px)
    dynamic_h = max(400, len(dept_df) * 40) 
    
    fig_dept = px.bar(dept_df, x='Count', y='Department', orientation='h', text='Count')
    fig_dept.update_traces(marker_color='#3B82F6', textposition='outside', textfont=dict(size=14, color='#0F172A', weight='bold'), cliponaxis=False)
    # 💥 แก้ไข: ใส่ tickmode='linear' เพื่อบังคับให้แสดงชื่อแผนกครบทุกอัน ห้ามข้าม
    fig_dept.update_layout(**pro_layout, height=dynamic_h, xaxis=dict(axis_style_no_grid, range=[0, dept_df['Count'].max() * 1.15], title="จำนวนเคส"), yaxis=dict(axis_style_no_grid, categoryorder='total ascending', title="", tickmode='linear', dtick=1), margin=dict(t=20, b=30, l=180, r=30))
    st.plotly_chart(fig_dept, use_container_width=True)

    section_title("ปริมาณเคสที่มีการติดตาม แยกตามแผนก (Tracked Cases)", "🎯", "แสดงเฉพาะเคสที่เกิดความล่าช้าจนต้องถูกติดตามงาน เพื่อหาจุดที่เป็นคอขวด")
    tracked_dept_df = tracked_df['แผนก'].value_counts().reset_index()
    tracked_dept_df.columns = ['Department', 'Count']
    if not tracked_dept_df.empty:
        dynamic_h2 = max(400, len(tracked_dept_df) * 40)
        fig_track_dept = px.bar(tracked_dept_df, x='Count', y='Department', orientation='h', text='Count')
        fig_track_dept.update_traces(marker_color='#F43F5E', textposition='outside', textfont=dict(size=14, color='#0F172A', weight='bold'), cliponaxis=False) 
        # 💥 แก้ไข: ใส่ tickmode='linear'
        fig_track_dept.update_layout(**pro_layout, height=dynamic_h2, xaxis=dict(axis_style_no_grid, range=[0, tracked_dept_df['Count'].max() * 1.15], title="จำนวนครั้งที่ถูกติดตาม"), yaxis=dict(axis_style_no_grid, categoryorder='total ascending', title="", tickmode='linear', dtick=1), margin=dict(t=20, b=30, l=180, r=30))
        st.plotly_chart(fig_track_dept, use_container_width=True)
    else:
        st.info("ยังไม่มีข้อมูลการติดตามงานในแผนกใดๆ")

    # ----------------------------------
    # 5. กราฟวงกลม (💥 แก้ไข: ถ่างขอบมหาศาลให้เส้นชี้และตัวหนังสือโชว์ครบ 100%)
    # ----------------------------------
    st.markdown("<hr style='margin-top: 30px; margin-bottom: 10px;'>", unsafe_allow_html=True)
    col_pie1, col_pie2 = st.columns(2)

    with col_pie1:
        section_title("สัดส่วนสถานะงาน (Status)", "📌", "สัดส่วนของสถานะงานทั้งหมดในระบบ")
        status_df = df_interactive['สถานะ'].value_counts().reset_index()
        status_df.columns = ['Status', 'Count']
        status_color_map = {'ปิด Case': '#10B981', 'เสร็จสิ้น': '#10B981', 'รับเรื่องร้องขอ': '#F59E0B', 'กำลังดำเนินการ': '#3B82F6', 'ไม่ระบุ': '#94A3B8'}
        
        fig_status = px.pie(status_df, names='Status', values='Count', hole=0.55, color='Status', color_discrete_map=status_color_map, title=None)
        fig_status.update_traces(
            textposition='outside', textinfo='percent+label', 
            textfont=dict(size=14, color='#0F172A', weight='bold'), 
            marker=dict(line=dict(color='#FFFFFF', width=2))
        )
        # 💥 แก้ไข: ให้ Margin ซ้าย-ขวา กว้างมากๆ (140px) และปิดโดนัทให้มีช่องว่าง
        fig_status.update_layout(**pro_layout, height=450, showlegend=False, margin=dict(t=50, b=50, l=140, r=140))
        st.plotly_chart(fig_status, use_container_width=True)

    with col_pie2:
        section_title("สัดส่วนสถานะ SLA", "⏱️", "สัดส่วนความสามารถในการปิดเคสตามกรอบเวลาที่กำหนด")
        sla_df = df_interactive['sla_status_label'].value_counts().reset_index()
        sla_df.columns = ['SLA_Status', 'Count']
        color_map = {'✅ ภายใน SLA': '#10B981', '🟢 ปกติ': '#34D399', '⚠️ ใกล้หลุด SLA (เร่งมือ)': '#F59E0B', '🔥 เกินกำหนด (รีบปิดด่วน!)': '#EF4444', '❌ เกิน SLA (ปิดแล้ว)': '#B91C1C'}
        
        fig_sla = px.pie(sla_df, names='SLA_Status', values='Count', hole=0.55, color='SLA_Status', color_discrete_map=color_map, title=None)
        fig_sla.update_traces(
            textposition='outside', textinfo='percent+label', 
            textfont=dict(size=14, color='#0F172A', weight='bold'), 
            marker=dict(line=dict(color='#FFFFFF', width=2))
        )
        # 💥 แก้ไข: ถ่าง Margin ซ้าย-ขวา ให้กว้างสุดๆ ป้องกันตัวหนังสือตกขอบ
        fig_sla.update_layout(**pro_layout, height=450, showlegend=False, margin=dict(t=50, b=50, l=140, r=140))
        st.plotly_chart(fig_sla, use_container_width=True)

    # ----------------------------------
    # 6. ตารางผลงานรายบุคคล 
    # ----------------------------------
    section_title("ตารางวัดผลการติดตามงานรายบุคคล (Agent Performance)", "👩‍💻", "ดูความขยันและปริมาณเคสที่เจ้าหน้าที่แต่ละท่านทำการติดตาม")
    if not tracked_df.empty:
        valid_agents_df = tracked_df[tracked_df['First_Agent_Name'] != 'ไม่มี']
        agent_stats = valid_agents_df.groupby('First_Agent_Name').agg(
            เคสที่ติดตาม=('หมายเลข Case', 'count'),
            ปิดเคส=('สถานะ', lambda x: x.isin(['ปิด Case', 'เสร็จสิ้น']).sum()),
            ยังไม่ปิด=('สถานะ', lambda x: (~x.isin(['ปิด Case', 'เสร็จสิ้น'])).sum())
        ).reset_index()
        
        agent_stats['% ติดตามรวม'] = (agent_stats['เคสที่ติดตาม'] / total_tracked) * 100
        agent_stats['% เคสที่ยังไม่ปิด'] = (agent_stats['ยังไม่ปิด'] / agent_stats['เคสที่ติดตาม']) * 100
        agent_stats = agent_stats.sort_values(by='เคสที่ติดตาม', ascending=False)
        
        st.dataframe(
            agent_stats[['First_Agent_Name', 'เคสที่ติดตาม', '% ติดตามรวม', 'ปิดเคส', 'ยังไม่ปิด', '% เคสที่ยังไม่ปิด']],
            use_container_width=True, hide_index=True,
            column_config={
                "First_Agent_Name": st.column_config.TextColumn("รายชื่อเจ้าหน้าที่"),
                "เคสที่ติดตาม": st.column_config.NumberColumn("จำนวนเคสที่ติดตาม (ครั้ง)"),
                "% ติดตามรวม": st.column_config.ProgressColumn("% เทียบกับทุกคน", format="%.2f%%", min_value=0, max_value=100),
                "ปิดเคส": st.column_config.NumberColumn("ปิดเคสสำเร็จ"),
                "ยังไม่ปิด": st.column_config.NumberColumn("ยังไม่ปิด (ค้าง)"),
                "% เคสที่ยังไม่ปิด": st.column_config.NumberColumn("% เคสที่ยังไม่ปิด", format="%.2f%%")
            }
        )

    # ----------------------------------
    # 7. หมวดหมู่ที่โดนตาม 
    # ----------------------------------
    section_title("🔥 หมวดหมู่ปัญหาที่ถูกติดตามงานมากที่สุด (Top Tracked Categories)", "📑", "จัดอันดับหมวดหมู่ปัญหาที่เกิดความล่าช้าจนผู้ใช้งานต้องทวงถามบ่อยที่สุด")
    if not tracked_df.empty:
        cat_sub_df = tracked_df.groupby(['Category', 'Sub Category']).size().reset_index(name='จำนวนเคสที่ตาม')
        cat_sub_df = cat_sub_df.sort_values('จำนวนเคสที่ตาม', ascending=False)
        max_val = int(cat_sub_df['จำนวนเคสที่ตาม'].max()) if not cat_sub_df.empty else 100
        
        st.dataframe(
            cat_sub_df, 
            use_container_width=True, height=350, hide_index=True,
            column_config={
                "จำนวนเคสที่ตาม": st.column_config.ProgressColumn("จำนวนเคสที่ถูกติดตาม (ครั้ง)", format="%d", min_value=0, max_value=max_val)
            }
        )
    else:
        st.info("ไม่มีข้อมูลการติดตามงานสำหรับหมวดหมู่นี้")

    # ----------------------------------
    # 8. ตารางเคสรอติดตาม 
    # ----------------------------------
    section_title("🚨 เคสค้างที่รอการติดตามซ้ำ (Pending Follow-up)", "📞", "รายการเคสที่ถูกติดตามไปแล้วแต่ปัจจุบันยังไม่ปิด (จัดเรียงจากเคสที่โดนทิ้งช่วงมานานที่สุด)")
    active_tracked_cases = tracked_df[~tracked_df['สถานะ'].isin(['ปิด Case', 'เสร็จสิ้น'])].copy()

    if not active_tracked_cases.empty:
        now_ts = pd.Timestamp.now()
        active_tracked_cases['ชั่วโมงที่เงียบหาย'] = (now_ts - active_tracked_cases['Last_Track_Time']).dt.total_seconds() / 3600
        active_tracked_cases['ชั่วโมงที่เงียบหาย'] = active_tracked_cases['ชั่วโมงที่เงียบหาย'].round(1)
        active_tracked_cases = active_tracked_cases.sort_values(by='ชั่วโมงที่เงียบหาย', ascending=False)
        
        display_followup = active_tracked_cases[['หมายเลข Case', 'First_Agent_Name', 'แผนก', 'สถานะ', 'Track_Count', 'Last_Track_Time', 'ชั่วโมงที่เงียบหาย']]
        display_followup.columns = ['หมายเลข Case', 'คนตามเคสคนแรก', 'แผนก', 'สถานะปัจจุบัน', 'ติดตามมาแล้ว (ครั้ง)', 'อัปเดตล่าสุด', 'เงียบหายไป (ชั่วโมง)']
        
        st.dataframe(
            display_followup, use_container_width=True, height=350, hide_index=True,
            column_config={
                "เงียบหายไป (ชั่วโมง)": st.column_config.ProgressColumn("เงียบหายไป (ชั่วโมง)", format="%.1f ชม.", min_value=0, max_value=72),
                "อัปเดตล่าสุด": st.column_config.DatetimeColumn("อัปเดตล่าสุด", format="DD/MM/YYYY HH:mm")
            }
        )
    else:
        st.info("🎉 ไม่มีเคสค้างที่รอการติดตามซ้ำในขณะนี้")

except Exception as e:
    st.error(f"เกิดข้อผิดพลาดในการรันระบบ: {e}") 
