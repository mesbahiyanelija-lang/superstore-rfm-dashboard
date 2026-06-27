import sqlite3
import pandas as pd
import plotly.express as px
import streamlit as st
import sys
sys.stdout.reconfigure(encoding='utf_8')

pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)
pd.set_option('display.unicode.east_asian_width', True)

# ۱. خواندن فایل و تمیزکاری اولیه (مثل مراحل قبل)
try:
    df = pd.read_csv("superstore_final_dataset (1).csv", encoding='utf-8-sig')
except:
    df = pd.read_csv("superstore_final_dataset (1).csv", encoding='latin1')

df.columns = df.columns.str.replace('_', '', regex=False)
df['OrderDate'] = pd.to_datetime(
    df['OrderDate'], format='mixed', errors='coerce')
df['OrderDate'] = df['OrderDate'].dt.strftime('%Y-%m-%d')

# ۲. اتصال به دیتابیس و محاسبه متغیرهای اصلی
conn = sqlite3.connect('superstore.db')
df.to_sql('sales_data', conn, if_exists='replace', index=False)

rfm_query = """
SELECT 
    CustomerID,
    CustomerName,
    Segment AS CustomerSegment, -- تغییر نام برای قاطی نشدن با بخش‌بندی RFM
    ROUND(JULIANDAY((SELECT MAX(OrderDate) FROM sales_data)) - JULIANDAY(OrderDate)) AS Recency,
    COUNT(DISTINCT OrderID) AS Frequency,
    SUM(Sales) AS Monetary
FROM sales_data
GROUP BY CustomerID;
"""
rfm_df = pd.read_sql_query(rfm_query, conn)
conn.close()
# ----------------------------------------------------
# 🔥 مرحله جدید: محاسبه امتیازهای ۱ تا ۵ (RFM Scoring)
# ----------------------------------------------------

# امتیاز Recency: هرچه روزها کمتر، امتیاز بالاتر (5 تا 1)
rfm_df['R_Score'] = pd.qcut(rfm_df['Recency'], q=5, labels=[5, 4, 3, 2, 1])

# امتیاز Frequency و Monetary: هرچه مقدار بیشتر، امتیاز بالاتر (1 تا 5)
# (نکته: از rank برای جلوگیری از خطای مقادیر تکراری در دیتای واقعی استفاده کردیم)
rfm_df['F_Score'] = pd.qcut(rfm_df['Frequency'].rank(
    method='first'), q=5, labels=[1, 2, 3, 4, 5])
rfm_df['M_Score'] = pd.qcut(rfm_df['Monetary'], q=5, labels=[1, 2, 3, 4, 5])

# چسباندن امتیازها به هم برای ایجاد یک کد ۳ رقمی (مثلاً ۵۵۵ یا ۱۴۲)
rfm_df['RFM_Cell'] = rfm_df['R_Score'].astype(
    str) + rfm_df['F_Score'].astype(str) + rfm_df['M_Score'].astype(str)

# ----------------------------------------------------
# 🎯 مرحله نهایی: دسته‌بندی هوشمند مشتریان (Segmentation)
# ----------------------------------------------------


def segment_customer(row):
    r = int(row['R_Score'])
    f = int(row['F_Score'])

    if r >= 4 and f >= 4:
        return 'Champions (قهرمانان)'
    elif r >= 3 and f >= 3:
        return 'Loyal Customers (مشتریان وفادار)'
    elif r >= 4 and f <= 2:
        return 'New Customers (مشتریان جدید)'
    elif r <= 2 and f >= 4:
        return 'Cant Lose Them (نباید از دست بروند!)'
    elif r <= 2 and f <= 2:
        return 'Lost (از دست رفته)'
    else:
        return 'About to Sleep (در آستانه خواب)'


# اعمال دسته‌بندی روی کل دیتاست
rfm_df['RFM_Segment'] = rfm_df.apply(segment_customer, axis=1)

st.set_page_config(page_title="دشبورد سوپراستور", layout="wide")

# تزریق کدهای CSS برای راست‌چین سازی (RTL) و فونت فارسی وزیر
# ====================================================================
st.markdown(
    """
    <style>
    /* ۱. دانلود و بارگذاری فونت زیبای وزیر */
    @import url('https://v1.fontapi.ir/css/Vazir');
    
    /* ۲. راست‌چین کردن بدنه اصلی دشبورد */
    .main .block-container {
        direction: rtl;
        text-align: right;
    }
    
    /* ۳. راست‌چین کردن منوی کناری (Sidebar) */
    [data-testid="stSidebar"] {
        direction: rtl;
        text-align: right;
    }
    
    /* ۴. اعمال فونت روی تمام نوشته‌ها، تیترها و دکمه‌ها */
    html, body, [class*="css"], p, h1, h2, h3, h4, h5, h6, span, label, button {
        font-family: 'Vazir', sans-serif !important;
    }
    </style>`
    """,
    unsafe_allow_html=True  # این گزینه اجازه می‌دهد کدهای HTML و CSS اجرا شوند
)

st.title("دشبورد تحلیل و بخش بندی مشتریان (RFM)")
st.subheader("تحلیل رفتار خرید مشتریان فروشگاه بزرگ سوپراستور")
st.markdown("---")
# ۱. ساخت منوی فیلتر در سایدبار (منوی کناری)
# ====================================================================
st.sidebar.header("🎯 فیلترهای دشبورد")

# گرفتن لیست سگمنت‌های منحصربه‌فرد و اضافه کردن گزینه "همه بخش‌ها" به اول آن
available_segments = ["همه بخش‌ها"] + list(rfm_df['RFM_Segment'].unique())

# ساخت جعبه انتخاب در سایدبار
selected_segment = st.sidebar.selectbox(
    "یک بخش (Segment) را انتخاب کنید:",
    options=available_segments
)

# ====================================================================
# ۲. فیلتر کردن هوشمند دیتابیس بر اساس انتخاب کاربر
# ====================================================================
if selected_segment != "همه بخش‌ها":
    # اگر کاربر گروه خاصی را انتخاب کرد، دیتا را محدود کن
    filtered_df = rfm_df[rfm_df['RFM_Segment'] == selected_segment]
else:
    # اگر روی "همه بخش‌ها" بود، کل دیتا را استفاده کن
    filtered_df = rfm_df

# --- ۱. محاسبات شاخص‌ها از روی دیتابیس RFM شما ---
total_customers = filtered_df['CustomerID'].nunique()  # تعداد کل مشتریان یکتا
total_revenue = filtered_df['Monetary'].sum()          # مجموع کل درآمد فروشگاه
# میانگین روزهای دوری مشتریان
avg_recency = filtered_df['Recency'].mean()

# --- ۲. ستون‌بندی صفحه برای قرارگیری کارت‌ها کنار هم ---
# صفحه را به ۳ ستون مساوی تقسیم می‌کنیم
col1, col2, col3 = st.columns(3)
# --- ۳. ساخت و نمایش کارت‌ها در ستون‌های مربوطه ---
with col1:
    st.metric(
        label="👥 تعداد کل مشتریان",
        value=f"{total_customers:,}"
    )

with col2:
    st.metric(
        label="💰 مجموع درآمد کل (Monetary)",
        value=f"${total_revenue:,.0f}"
    )

with col3:
    st.metric(
        label="⏱️ میانگین تازگی خرید (Recency)",
        value=f"{avg_recency:.1f} روز"
    )

# یک خط فاصله تا نمودار بعدی زیباتر شود
st.markdown("---")


# نمایش نتیجه نهایی
print("🎉 دیتای شما با موفقیت بخش‌بندی شد:")
columns_to_show = ['CustomerID', 'CustomerName', 'Recency',
                   'Frequency', 'Monetary', 'RFM_Cell', 'RFM_Segment']
print(rfm_df[columns_to_show].head(10))

segment_counts = rfm_df['RFM_Segment'].value_counts().reset_index()
segment_counts.columns = ['RFM_Segment', 'Customer_Count']

fig = px.bar(
    segment_counts,
    x='Customer_Count',
    y='RFM_Segment',
    orientation='h',
    color='RFM_Segment',
    text='Customer_Count',
    title=f'توزیع و فراوانی مشتریان - وضعیت: {selected_segment}',
    labels={'Customer_Count': 'تعداد مشتریان', 'RFM_Segment': 'بخش مشتریان'},
    template='plotly_dark'
)

fig.update_layout(
    title_font_size=22,
    xaxis_title="تعداد مشتریان در هر بخش",
    yaxis_title="گروه های مشتریان",
    showlegend=False,
    yaxis={'categoryorder': 'total ascending'}
)

st.plotly_chart(fig, use_container_width=True)
# ۵. نمایش جدول مشخصات مشتریان فیلتر شده
# ====================================================================
st.markdown("---")  # یک خط جداکننده برای زیبایی بیشتر
st.subheader("📋 لیست و جزئیات مشتریان این بخش")

# ۱. انتخاب ستون‌هایی که برای مدیر جذاب و کاربردی هستند
columns_to_display = ['CustomerID', 'CustomerName',
                      'Recency', 'Frequency', 'Monetary']

# ۲. نمایش هوشمند و تعاملی جدول با استریم‌لیت
st.dataframe(
    filtered_df[columns_to_display],
    use_container_width=True,  # پر کردن کامل عرض صفحه
    hide_index=True  # مخفی کردن شماره ردیف‌های پیش‌فرض پانداز برای تمیزی کار
)
