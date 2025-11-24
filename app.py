import streamlit as st
import pandas as pd
import pyodbc
import plotly.express as px

# 1. PAGE CONFIGURATION
st.set_page_config(page_title="Lodge Booking Dashboard", layout="wide")

# 2. DATABASE CONNECTION & DATA FETCHING
# We use @st.cache_data so we don't hit the database on every interaction
@st.cache_data(ttl=600) # Cache clears every 10 mins
def load_data():
    # Fetch credentials from secrets.toml
    creds = st.secrets["db_credentials"]
    
    conn_str = (
        f"DRIVER={{{creds['DRIVER']}}};"
        f"SERVER={creds['SERVER']};"
        f"DATABASE={creds['DATABASE']};"
        f"UID={creds['UID']};"
        f"PWD={creds['PWD']};"
    )

    # THE SQL QUERY (Optimized for Dashboard - All Clients)
    query = """
    SELECT
        D.department_description AS [Lodge Name],
        D.department_code AS [Lodge Code],
        B.booking_reference AS [Booking Ref],
        B.booking_status AS [Status Code],
        
        CAST(DATEADD(minute, B.arrival_minute, '1897-01-01') AS DATE) AS [Arrival Date],
        CAST(DATEADD(minute, B.departure_minute, '1897-01-01') AS DATE) AS [Departure Date],
        CAST(DATEADD(minute, B.creation_minute, '1897-01-01') AS DATE) AS [Date Booked],

        (B.adult_category_1_quantity + B.adult_category_2_quantity) AS [Total Adults],
        (B.child_category_1_quantity + B.child_category_2_quantity) AS [Total Children],
        
        BUT.unit_type_description AS [Unit Type],
        BU.unit_name AS [Unit Number],
        C.client_nationality AS [Nationality]

    FROM [NWR_Training].[dbo].[bkmain] B
    INNER JOIN [NWR_Training].[dbo].[clmain] C ON B.guest_clmain = C.client_clmain
    LEFT JOIN [NWR_Training].[dbo].[bkunit] BU ON B.id_bkunit = BU.booking_unit_bkunit
    LEFT JOIN [NWR_Training].[dbo].[bkunittp] BUT ON BU.unit_type_bkunittp = BUT.id_bkunittp
    LEFT JOIN [NWR_Training].[dbo].[spdept] D ON BUT.location_department_bkunittp = D.department_spdept

    WHERE 
        -- Filter: Data from 2023 onwards for the dashboard
        CAST(DATEADD(minute, B.arrival_minute, '1897-01-01') AS DATE) >= '2023-01-01'
        AND C.record_marked_deleted = 0
        AND D.record_marked_deleted = 0
    """
    
    conn = pyodbc.connect(conn_str)
    df = pd.read_sql(query, conn)
    
    # Convert dates to datetime objects for Pandas
    df['Arrival Date'] = pd.to_datetime(df['Arrival Date'])
    df['Date Booked'] = pd.to_datetime(df['Date Booked'])
    
    # Create a Total Guests Column
    df['Total Guests'] = df['Total Adults'] + df['Total Children']
    
    return df

# Load the data
try:
    df = load_data()
except Exception as e:
    st.error(f"Error connecting to database: {e}")
    st.stop()

# 3. SIDEBAR FILTERS
st.sidebar.header("Filter Options")

# Date Filter
min_date = df['Arrival Date'].min()
max_date = df['Arrival Date'].max()
start_date, end_date = st.sidebar.date_input(
    "Select Arrival Date Range",
    [min_date, max_date]
)

# Lodge Filter
lodge_list = df['Lodge Name'].unique().tolist()
selected_lodges = st.sidebar.multiselect("Select Lodge", lodge_list, default=lodge_list)

# Status Filter
status_list = df['Status Code'].unique().tolist()
selected_status = st.sidebar.multiselect("Select Status Code", status_list, default=status_list)

# 4. FILTERING THE DATAFRAME
mask = (
    (df['Arrival Date'].dt.date >= start_date) &
    (df['Arrival Date'].dt.date <= end_date) &
    (df['Lodge Name'].isin(selected_lodges)) &
    (df['Status Code'].isin(selected_status))
)
filtered_df = df.loc[mask]

# 5. DASHBOARD LAYOUT

st.title("🏨 Hospitality & Booking Overview")
st.markdown("### Key Performance Indicators (KPIs)")

# KPI ROW
kpi1, kpi2, kpi3, kpi4 = st.columns(4)

total_bookings = filtered_df['Booking Ref'].nunique()
total_guests = filtered_df['Total Guests'].sum()
avg_stay = (filtered_df['Departure Date'] - filtered_df['Arrival Date']).dt.days.mean()
top_nat = filtered_df['Nationality'].mode()[0] if not filtered_df.empty else "N/A"

kpi1.metric("Total Bookings", f"{total_bookings:,}")
kpi2.metric("Total Guests (Pax)", f"{total_guests:,}")
kpi3.metric("Avg Length of Stay", f"{avg_stay:.1f} Days")
kpi4.metric("Top Nationality", top_nat)

st.markdown("---")

# CHARTS ROW 1
col1, col2 = st.columns(2)

with col1:
    st.subheader("Bookings by Lodge")
    lodge_counts = filtered_df['Lodge Name'].value_counts().reset_index()
    lodge_counts.columns = ['Lodge Name', 'Count']
    fig_lodge = px.bar(lodge_counts, x='Lodge Name', y='Count', color='Count', template="plotly_white")
    st.plotly_chart(fig_lodge, use_container_width=True)

with col2:
    st.subheader("Guest Nationality Distribution")
    nat_counts = filtered_df['Nationality'].value_counts().reset_index().head(10) # Top 10
    nat_counts.columns = ['Nationality', 'Guests']
    fig_nat = px.pie(nat_counts, values='Guests', names='Nationality', hole=0.4)
    st.plotly_chart(fig_nat, use_container_width=True)

# CHARTS ROW 2
st.subheader("Occupancy Trend (Arrivals per Month)")
# Group by Month
filtered_df['Month'] = filtered_df['Arrival Date'].dt.to_period('M').astype(str)
trend_data = filtered_df.groupby('Month')['Booking Ref'].count().reset_index()
fig_trend = px.line(trend_data, x='Month', y='Booking Ref', markers=True, template="plotly_white")
st.plotly_chart(fig_trend, use_container_width=True)

# RAW DATA EXPLORER
with st.expander("View Detailed Booking Data"):
    st.dataframe(filtered_df)
