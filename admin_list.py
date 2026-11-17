import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from style import apply_style
from components import page_header, load_sheet_safe

st.set_page_config(page_title="Admin - Senarai Vendor", layout="wide")
apply_style()
page_header()

if not st.session_state.get("is_admin", False):
    st.error("Sila log masuk di sidebar kiri."); st.stop()

COL_NAME = "Nama Perniagaan Syarikat"
COL_PHONE = "Nombor Telefon/Phone Number"
COL_TYPE = "Kategori Produk/Product Category"
COL_CAT = "F&B CATEGORY"
COL_PLATE = "Plate Number"

conn = st.connection("gsheets", type=GSheetsConnection)
df = load_sheet_safe(conn, "Vendors", ttl=0)
if df is None: st.stop()

# --- PERISAI KESELAMATAN ---
if "Status" not in df.columns:
    df["Status"] = "Pending"
else:
    df["Status"] = df["Status"].fillna("Pending").astype(str).str.title()

if "Paid" not in df.columns:
    df["Paid"] = False
else:
    df["Paid"] = df["Paid"].fillna(False).astype(bool)
# ---------------------------

st.title("📋 Senarai Penuh Vendor")
st.caption("Cari, tapis, dan muat turun senarai vendor.")

# Filter
f1, f2, f3 = st.columns([1, 1, 2])
with f1:
    status_filter = st.multiselect("Status", options=["Pending", "Approved", "Rejected", "Cancelled"], default=["Pending", "Approved"])
with f2:
    type_filter = st.selectbox("Kategori", options=["Semua", "Car Boot Sales", "F&B", "Food Truck", "Arts/Crafts & Others"])
with f3:
    search = st.text_input("🔍 Cari (Nama / Plate)").strip().lower()

filtered_df = df[df["Status"].isin(status_filter)]
if type_filter != "Semua":
    filtered_df = filtered_df[filtered_df[COL_TYPE] == type_filter]
if search:
    filtered_df = filtered_df[
        filtered_df[COL_NAME].astype(str).str.lower().str.contains(search, na=False) |
        filtered_df[COL_PLATE].astype(str).str.lower().str.contains(search, na=False)
    ]

# Paparan
display_df = filtered_df[[COL_PLATE, COL_NAME, COL_PHONE, COL_TYPE, COL_CAT, "Status", "Paid"]].copy()
display_df["Paid"] = display_df["Paid"].map({True: "✅ Yes", False: "❌ No"})
display_df.columns = ["Plate", "Nama", "Telefon", "Kategori", "Sub-Kat", "Status", "Paid"]

st.dataframe(display_df, hide_index=True, use_container_width=True)

# Download
import io
buffer = io.BytesIO()
with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
    display_df.to_excel(writer, index=False, sheet_name="Vendors")
    
st.download_button(
    label="📥 Muat Turun Excel",
    data=buffer.getvalue(),
    file_name="senarai_vendor.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)