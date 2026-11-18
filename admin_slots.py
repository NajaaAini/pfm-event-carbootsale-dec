# ============================================================
# admin_slots.py — MULTI-EVENT VERSION
# ============================================================
import re

import pandas as pd
import streamlit as st
from streamlit_gsheets import GSheetsConnection

from style import apply_style
from components import page_header, load_sheet_safe, get_active_event

st.set_page_config(page_title="Admin - Slot & Mapping", layout="wide")
apply_style()

if not st.session_state.get("is_admin", False):
    st.error("Sila log masuk di sidebar kiri.")
    st.stop()

page_header()

# ============================================================
# AMBIL EVENT DARI SESSION STATE (MULTI-EVENT)
# ============================================================
if "active_event" in st.session_state:
    active_event = st.session_state["active_event"]
    event_name = st.session_state.get("active_event_name", "Event 1")
else:
    active_event, event_name = get_active_event()
    st.session_state["active_event"] = active_event
    st.session_state["active_event_name"] = event_name

COL_NAME = "Nama Perniagaan Syarikat"
COL_TYPE = "Kategori Produk/Product Category"
COL_CAT = "F&B CATEGORY"
COL_PLATE = "Plate Number"
COL_PRODUCTS = "Senarai Produk yang Dijual"

FB_CATEGORIES = [
    "Local Food", "Dessert", "Coffee/Air", "Grill and BBQ",
    "Deep-Fry", "Italian/Western Food", "Japanese Food", "Chinese Food",
]

conn = st.connection("gsheets", type=GSheetsConnection)
df = load_sheet_safe(conn, "Vendors", ttl=0)
payments_df = load_sheet_safe(conn, "Payments", ttl=0)

if df is None:
    st.stop()

# Kesan lajur produk walaupun tajuknya ada teks tambahan (cth: "... / Product List")
COL_PRODUCTS = next(
    (c for c in df.columns if "senarai produk yang dijual" in str(c).lower()),
    COL_PRODUCTS,
)

# --- PERISAI KESELAMATAN ---
if "Status" not in df.columns:
    df["Status"] = "Pending"
else:
    df["Status"] = df["Status"].fillna("Pending").astype(str).str.strip().str.title()

if COL_NAME not in df.columns: df[COL_NAME] = ""
if COL_TYPE not in df.columns: df[COL_TYPE] = ""
if COL_CAT not in df.columns: df[COL_CAT] = ""
if COL_PLATE not in df.columns: df[COL_PLATE] = ""
if COL_PRODUCTS not in df.columns: df[COL_PRODUCTS] = ""
df[COL_TYPE] = df[COL_TYPE].astype(str).str.strip()  # buang ruang kosong tersembunyi
# ---------------------------

tab1, tab2, tab3 = st.tabs(["📊 Slot Available", "🗺️ Mapping Lot", "🍔 Menu F&B"])

# ============================================================
# TAB 1: SLOT AVAILABLE (APPROVED SAHAJA)
# ============================================================
with tab1:
    st.subheader(f"Baki Slot Semasa ({event_name})")

    CAR_BOOT_LIMIT = active_event["total_car_boot"]
    FB_OVERALL_LIMIT = active_event["total_fb"]
    OTHERS_LIMIT = active_event["total_others"]
    FB_CAT_LIMIT = active_event["fb_per_category"]

    cb_used = df[(df[COL_TYPE] == "Car Boot Sales") & (df["Status"] == "Approved")].shape[0]
    fb_used = df[(df[COL_TYPE] == "F&B") & (df["Status"] == "Approved")].shape[0]
    ot_used = df[(~df[COL_TYPE].isin(["Car Boot Sales", "F&B", "Food Truck"])) & (df["Status"] == "Approved")].shape[0]

    c1, c2, c3 = st.columns(3)
    c1.metric("Car Boot", f"{cb_used} / {CAR_BOOT_LIMIT}", f"{max(0, CAR_BOOT_LIMIT-cb_used)} baki")
    c2.metric("F&B", f"{fb_used} / {FB_OVERALL_LIMIT}", f"{max(0, FB_OVERALL_LIMIT-fb_used)} baki")
    c3.metric("Others", f"{ot_used} / {OTHERS_LIMIT}", f"{max(0, OTHERS_LIMIT-ot_used)} baki")

    st.markdown("**Pecahan Sub-Kategori F&B**")
    fb_rows = []
    for cat in FB_CATEGORIES:
        c_used = df[(df[COL_TYPE] == "F&B") & (df[COL_CAT] == cat) & (df["Status"] == "Approved")].shape[0]
        fb_rows.append({
            "Sub-Kategori": cat,
            "Diambil": c_used,
            "Had": FB_CAT_LIMIT,
            "Baki": max(0, FB_CAT_LIMIT - c_used),
        })
    st.dataframe(pd.DataFrame(fb_rows), hide_index=True, use_container_width=True)

# ============================================================
# TAB 2: MAPPING LOT (AUTO-JANA & SEMAK DARI SHEET)
# ============================================================
with tab2:
    st.subheader("Senarai Lot Diambil (Paid)")
    st.caption("Status 'Available' akan bertukar kepada No. Plate jika lot tersebut telah ditempah oleh vendor Approved.")

    # 1. Senarai lot penuh (Food Truck guna padding 0: K01-K05)
    all_lots = {
        "Car Boot": [f"A{i}" for i in range(1, 13)] + [f"B{i}" for i in range(1, 11)] +
                    [f"C{i}" for i in range(1, 11)] + [f"D{i}" for i in range(1, 5)] +
                    [f"E{i}" for i in range(1, 11)] + [f"F{i}" for i in range(1, 6)],
        "F&B": [f"H{i}" for i in range(1, 22)] + [f"I{i}" for i in range(1, 18)],
        "Arts & Crafts / Others": [f"J{i}" for i in range(1, 52)],
        "Food Truck": [f"K{i:02d}" for i in range(1, 6)],
    }
    valid_lots = {lot for lots in all_lots.values() for lot in lots}
    # Kunci tanpa padding -> nama lot sebenar (K1 / K01 -> K01, A01 -> A1)
    lot_lookup = {f"{lot[0]}{int(lot[1:])}": lot for lot in valid_lots}

    def norm_plate(value):
        """Buang semua ruang kosong dan jadikan huruf besar (NNA 1806 == nna1806)."""
        return re.sub(r"\s+", "", str(value)).upper()

    def parse_lots(value):
        """Ambil kod lot daripada teks. Contoh: 'A01', 'Lot A1', 'A1, A2' -> A1, A2."""
        if value is None or pd.isna(value):
            return []
        found = []
        for letter, number in re.findall(r"\b([A-K])\s*0*(\d{1,2})\b", str(value).upper()):
            lot = lot_lookup.get(f"{letter}{int(number)}")
            if lot and lot not in found:
                found.append(lot)
        return found

    # 2. Cari lot yang sudah ditempah dari sheet Payments
    booked_lots = {}
    problems = []
    lot_columns = []
    plate_col = None

    if payments_df is None or payments_df.empty:
        problems.append({"Plate": "-", "Masalah": "Sheet Payments kosong atau tidak dapat dimuatkan"})
    else:
        plate_col = next((c for c in payments_df.columns if "plate" in str(c).lower()), None)
        # Lajur lot dikesan daripada tajuk (tidak sensitif huruf besar/kecil)
        lot_columns = [
            c for c in payments_df.columns
            if "lot" in str(c).lower() and "pilih" in str(c).lower()
        ]

        if plate_col is None:
            problems.append({"Plate": "-", "Masalah": "Tiada lajur 'Plate Number' dalam sheet Payments"})
        elif not lot_columns:
            problems.append({"Plate": "-", "Masalah": "Tiada lajur 'Pilih ... Lot' dalam sheet Payments"})
        else:
            pay = payments_df.copy()
            pay["_plate"] = pay[plate_col].map(norm_plate)

            for _, row in df.iterrows():
                plate = norm_plate(row[COL_PLATE])
                if not plate:
                    continue

                matched = pay[pay["_plate"] == plate]

                if row["Status"] != "Approved":
                    if not matched.empty:
                        problems.append({
                            "Plate": plate,
                            "Masalah": f"Ada rekod bayaran tetapi status vendor '{row['Status']}', bukan Approved",
                        })
                    continue

                if matched.empty:
                    problems.append({"Plate": plate, "Masalah": "Approved tetapi tiada rekod dalam sheet Payments"})
                    continue

                latest = matched.iloc[-1]
                raw_values = []
                lots_found = []
                for col in lot_columns:
                    raw = latest.get(col, "")
                    if raw is not None and not pd.isna(raw) and str(raw).strip():
                        raw_values.append(f"{col}: {raw}")
                    lots_found.extend(parse_lots(raw))

                if not lots_found:
                    problems.append({
                        "Plate": plate,
                        "Masalah": "Rekod bayaran ada tetapi lot tidak dikenali/kosong. Nilai: "
                                   + (" | ".join(raw_values) if raw_values else "(kosong)"),
                    })
                    continue

                for lot in lots_found:
                    if lot in booked_lots and booked_lots[lot] != plate:
                        problems.append({
                            "Plate": plate,
                            "Masalah": f"Lot {lot} bertindih dengan {booked_lots[lot]}",
                        })
                    booked_lots[lot] = plate

    # 3. Bina dataframe untuk setiap kategori dengan styling
    def build_styled_lot_df(lot_list, booked_dict):
        data = []
        for lot in lot_list:
            if lot in booked_dict:
                data.append({"Lot": lot, "Status": booked_dict[lot], "Booked": True})
            else:
                data.append({"Lot": lot, "Status": "Available", "Booked": False})

        df_temp = pd.DataFrame(data)

        def highlight_status(row):
            if not row["Booked"]:
                return ["background-color: #f0fdf4; color: #16a34a; font-weight: bold;" if col == "Status" else "" for col in row.index]
            return ["background-color: #fef2f2; color: #991b1b; font-weight: 900;" if col == "Status" else "" for col in row.index]

        styled_df = df_temp.style.apply(highlight_status, axis=1)
        return styled_df.hide(axis="columns", subset=["Booked"])

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.markdown("**Car Boot Lot**")
        st.dataframe(build_styled_lot_df(all_lots["Car Boot"], booked_lots), hide_index=True, use_container_width=True, height=700)

    with c2:
        st.markdown("**F&B Lot**")
        st.dataframe(build_styled_lot_df(all_lots["F&B"], booked_lots), hide_index=True, use_container_width=True, height=700)

    with c3:
        st.markdown("**Arts & Crafts / Others**")
        st.dataframe(build_styled_lot_df(all_lots["Arts & Crafts / Others"], booked_lots), hide_index=True, use_container_width=True, height=700)

    with c4:
        st.markdown("**Food Truck**")
        st.dataframe(build_styled_lot_df(all_lots["Food Truck"], booked_lots), hide_index=True, use_container_width=True, height=700)
## ============================================================
# TAB 3: MENU F&B (APPROVED SAHAJA)
# ============================================================
with tab3:
    st.subheader("🍔 Dashboard Menu F&B (Paid)")
    
    # 1. Tapis vendor F&B yang Approved sahaja
    fb_df = df[(df[COL_TYPE] == "F&B") & (df["Status"] == "Approved")].copy()

    if fb_df.empty:
        st.info("Tiada vendor F&B yang berstatus Approved buat masa ini.")
    else:
        # 2. Bahagian Dashboard Kategori (Macam dalam gambar)
        st.markdown("**Sub-Kategori F&B**")
        
        # Kira jumlah diambil (Approved) bagi setiap sub-kategori
        rows_kategori = []
        for cat in FB_CATEGORIES:
            c_used = len(fb_df[fb_df[COL_CAT] == cat])
            rows_kategori.append({
                "Sub-Kategori": cat,
                "Diambil": c_used,
                "Had": FB_CAT_LIMIT,
                "Baki": max(0, FB_CAT_LIMIT - c_used),
            })
            
        df_kategori = pd.DataFrame(rows_kategori)

        # Paparkan sebagai Metric Cards menggunakan st.columns supaya nampak macam dashboard
        cols = st.columns(4)
        for i, row in enumerate(rows_kategori):
            with cols[i % 4]:
                st.metric(
                    label=row["Sub-Kategori"],
                    value=f"{row['Diambil']} / {row['Had']}",
                    delta=f"{row['Baki']} baki slot",
                    delta_color="off" if row["Diambil"] < row["Had"] else "inverse"
                )
                
        st.divider()

        # 3. Senarai Menu F&B (Jadual)
        st.markdown("**Senarai Menu / Produk F&B**")
        
        menu_data = []
        for _, row in fb_df.iterrows():
            menu = str(row.get(COL_PRODUCTS, ""))
            if menu.lower() in ("", "nan", "none"):
                continue

            menu_data.append({
                "Nama Vendor": row[COL_NAME],
                "Sub-Kategori": row.get(COL_CAT, "-"),
                "Menu / Produk": menu,
            })

        if menu_data:
            st.dataframe(
                pd.DataFrame(menu_data),
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Nama Vendor": st.column_config.TextColumn("Nama Vendor", width="medium"),
                    "Sub-Kategori": st.column_config.TextColumn("Sub-Kategori", width="small"),
                    "Menu / Produk": st.column_config.TextColumn("Menu / Produk", width="large"),
                },
            )
        else:
            st.info("Tiada maklumat menu F&B diisi oleh vendor yang diluluskan.")
            st.caption(f"Lajur menu yang dikesan: {COL_PRODUCTS}")
