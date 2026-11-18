# ============================================================
# admin_slots.py — MULTI EVENT VERSION
# NATIVE STREAMLIT VERSION
# NO HTML DIV / NO CUSTOM CSS
# ============================================================

import re
import pandas as pd
import streamlit as st
from streamlit_gsheets import GSheetsConnection

from style import apply_style
from components import page_header, load_sheet_safe, get_active_event


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Admin - Slot & Mapping",
    layout="wide"
)

apply_style()

if not st.session_state.get("is_admin", False):
    st.error("Sila log masuk di sidebar kiri.")
    st.stop()

page_header()


# ============================================================
# ACTIVE EVENT
# ============================================================

if "active_event" in st.session_state:
    active_event = st.session_state["active_event"]
    event_name = st.session_state.get("active_event_name", "Event 1")
else:
    active_event, event_name = get_active_event()
    st.session_state["active_event"] = active_event
    st.session_state["active_event_name"] = event_name


# ============================================================
# COLUMN SETTINGS
# ============================================================

COL_NAME = "Nama Perniagaan Syarikat"
COL_TYPE = "Kategori Produk/Product Category"
COL_CAT = "F&B CATEGORY"
COL_PLATE = "Plate Number"
COL_PRODUCTS = "Senarai Produk yang Dijual"


# ============================================================
# OFFICIAL F&B CATEGORIES (STANDARDISED & SHORT)
# ============================================================

FB_CATEGORIES = [
    "Local Food",
    "Dessert",
    "Coffee/Air",
    "Grill and BBQ",
    "Deep-Fry",
    "Western Food",
    "Japanese Food",
    "Chinese Food",
]


# ============================================================
# CATEGORY NORMALIZATION
# ============================================================

def normalize_fb_category(value):

    if pd.isna(value):
        return ""

    value = str(value).strip()

    # Buang penerangan dalam kurungan
    value = re.sub(r"\s*\([^)]*\)", "", value)

    # Buang ruang berlebihan
    value = re.sub(r"\s+", " ", value)

    return value.strip().casefold()


# ============================================================
# CONNECT GOOGLE SHEETS
# ============================================================

conn = st.connection(
    "gsheets",
    type=GSheetsConnection
)

df = load_sheet_safe(conn, "Vendors", ttl=0)
payments_df = load_sheet_safe(conn, "Payments", ttl=0)

if df is None:
    st.stop()


# ============================================================
# DETECT PRODUCT COLUMN
# ============================================================

COL_PRODUCTS = next(
    (
        c for c in df.columns
        if "senarai produk yang dijual" in str(c).lower()
    ),
    COL_PRODUCTS
)


# ============================================================
# DATA PROTECTION
# ============================================================

if "Status" not in df.columns:
    df["Status"] = "Pending"
else:
    df["Status"] = (
        df["Status"]
        .fillna("Pending")
        .astype(str)
        .str.strip()
        .str.title()
    )

for col in [
    COL_NAME,
    COL_TYPE,
    COL_CAT,
    COL_PLATE,
    COL_PRODUCTS
]:
    if col not in df.columns:
        df[col] = ""

df[COL_TYPE] = (
    df[COL_TYPE]
    .fillna("")
    .astype(str)
    .str.strip()
)

# Normalized F&B Category
df["_FB_CAT_NORMALIZED"] = (
    df[COL_CAT].apply(normalize_fb_category)
)


# ============================================================
# TABS
# ============================================================

tab1, tab2, tab3 = st.tabs([
    "📊 Slot Available",
    "🗺️ Mapping Lot",
    "🍔 Menu F&B"
])


# ============================================================
# TAB 1: SLOT AVAILABLE
# ============================================================

with tab1:

    st.subheader(
        f"Baki Slot Semasa ({event_name})"
    )

    CAR_BOOT_LIMIT = active_event["total_car_boot"]
    FB_OVERALL_LIMIT = active_event["total_fb"]
    OTHERS_LIMIT = active_event["total_others"]
    FB_CAT_LIMIT = active_event["fb_per_category"]

    # --------------------------------------------------------
    # TOTAL APPROVED
    # --------------------------------------------------------

    cb_used = df[
        (df[COL_TYPE] == "Car Boot Sales") &
        (df["Status"] == "Approved")
    ].shape[0]

    fb_used = df[
        (df[COL_TYPE] == "F&B") &
        (df["Status"] == "Approved")
    ].shape[0]

    ot_used = df[
        (~df[COL_TYPE].isin([
            "Car Boot Sales",
            "F&B",
            "Food Truck"
        ])) &
        (df["Status"] == "Approved")
    ].shape[0]

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "Car Boot",
        f"{cb_used} / {CAR_BOOT_LIMIT}",
        f"{max(0, CAR_BOOT_LIMIT - cb_used)} baki"
    )

    c2.metric(
        "F&B",
        f"{fb_used} / {FB_OVERALL_LIMIT}",
        f"{max(0, FB_OVERALL_LIMIT - fb_used)} baki"
    )

    c3.metric(
        "Others",
        f"{ot_used} / {OTHERS_LIMIT}",
        f"{max(0, OTHERS_LIMIT - ot_used)} baki"
    )

    # --------------------------------------------------------
    # F&B CATEGORY BREAKDOWN
    # --------------------------------------------------------

    st.markdown("### Pecahan Sub-Kategori F&B")

    fb_rows = []

    for cat in FB_CATEGORIES:

        normalized_cat = normalize_fb_category(cat)

        c_used = df[
            (df[COL_TYPE] == "F&B") &
            (df["_FB_CAT_NORMALIZED"] == normalized_cat) &
            (df["Status"] == "Approved")
        ].shape[0]

        fb_rows.append({
            "Sub-Kategori": cat,
            "Diambil": c_used,
            "Had": FB_CAT_LIMIT,
            "Baki": max(0, FB_CAT_LIMIT - c_used)
        })

    st.dataframe(
        pd.DataFrame(fb_rows),
        hide_index=True,
        use_container_width=True
    )


# ============================================================
# TAB 2: MAPPING LOT
# ============================================================

with tab2:

    st.subheader(
        "Senarai Lot Diambil (Approved Sahaja)"
    )

    st.caption(
        "Status Available akan bertukar kepada No. Plate "
        "jika lot telah ditempah oleh vendor Approved."
    )

    # --------------------------------------------------------
    # LOT LIST
    # --------------------------------------------------------

    all_lots = {

        "Car Boot": (
            [f"A{i}" for i in range(1, 13)] +
            [f"B{i}" for i in range(1, 11)] +
            [f"C{i}" for i in range(1, 11)] +
            [f"D{i}" for i in range(1, 5)] +
            [f"E{i}" for i in range(1, 11)] +
            [f"F{i}" for i in range(1, 12)]
        ),

        "F&B": (
            [f"H{i}" for i in range(1, 22)] +
            [f"I{i}" for i in range(1, 18)]
        ),

        "Arts & Crafts / Others": [
            f"J{i}" for i in range(1, 52)
        ],

        "Food Truck": [
            f"K{i:02d}" for i in range(1, 6)
        ]
    }

    valid_lots = {
        lot
        for lots in all_lots.values()
        for lot in lots
    }

    lot_lookup = {
        f"{lot[0]}{int(lot[1:])}": lot
        for lot in valid_lots
    }

    # --------------------------------------------------------
    # HELPER FUNCTIONS
    # --------------------------------------------------------

    def norm_plate(value):

        if value is None or pd.isna(value):
            return ""

        return re.sub(
            r"\s+",
            "",
            str(value)
        ).upper()


    def parse_lots(value):

        if value is None or pd.isna(value):
            return []

        found = []

        for letter, number in re.findall(
            r"\b([A-K])\s*0*(\d{1,2})\b",
            str(value).upper()
        ):

            lot = lot_lookup.get(
                f"{letter}{int(number)}"
            )

            if lot and lot not in found:
                found.append(lot)

        return found


    # --------------------------------------------------------
    # FIND BOOKED LOTS FROM PAYMENTS
    # --------------------------------------------------------

    booked_lots = {}
    problems = []
    lot_columns = []
    plate_col = None

    if payments_df is None or payments_df.empty:

        problems.append({
            "Plate": "-",
            "Masalah": "Sheet Payments kosong atau tidak dapat dimuatkan"
        })

    else:

        plate_col = next(
            (
                c for c in payments_df.columns
                if "plate" in str(c).lower()
            ),
            None
        )

        lot_columns = [
            c for c in payments_df.columns
            if (
                "lot" in str(c).lower()
                and "pilih" in str(c).lower()
            )
        ]

        if plate_col is None:

            problems.append({
                "Plate": "-",
                "Masalah": "Tiada lajur Plate Number dalam Payments"
            })

        elif not lot_columns:

            problems.append({
                "Plate": "-",
                "Masalah": "Tiada lajur Pilih Lot dalam Payments"
            })

        else:

            pay = payments_df.copy()

            pay["_plate"] = pay[plate_col].map(norm_plate)

            for _, row in df.iterrows():

                plate = norm_plate(row[COL_PLATE])

                if not plate:
                    continue

                matched = pay[
                    pay["_plate"] == plate
                ]

                if row["Status"] != "Approved":

                    if not matched.empty:

                        problems.append({
                            "Plate": plate,
                            "Masalah": (
                                f"Ada rekod bayaran tetapi status "
                                f"vendor '{row['Status']}', bukan Approved"
                            )
                        })

                    continue

                if matched.empty:

                    problems.append({
                        "Plate": plate,
                        "Masalah": "Approved tetapi tiada rekod dalam Payments"
                    })

                    continue

                latest = matched.iloc[-1]

                raw_values = []
                lots_found = []

                for col in lot_columns:

                    raw = latest.get(col, "")

                    if (
                        raw is not None
                        and not pd.isna(raw)
                        and str(raw).strip()
                    ):

                        raw_values.append(
                            f"{col}: {raw}"
                        )

                    lots_found.extend(
                        parse_lots(raw)
                    )

                if not lots_found:

                    problems.append({
                        "Plate": plate,
                        "Masalah": (
                            "Rekod bayaran ada tetapi lot tidak dikenali/kosong. "
                            + (
                                " | ".join(raw_values)
                                if raw_values
                                else "(kosong)"
                            )
                        )
                    })

                    continue

                for lot in lots_found:

                    if (
                        lot in booked_lots
                        and booked_lots[lot] != plate
                    ):

                        problems.append({
                            "Plate": plate,
                            "Masalah": (
                                f"Lot {lot} bertindih dengan "
                                f"{booked_lots[lot]}"
                            )
                        })

                    booked_lots[lot] = plate


    # --------------------------------------------------------
    # BUILD LOT DATAFRAME
    # --------------------------------------------------------

    def build_styled_lot_df(lot_list, booked_dict):

        data = []

        for lot in lot_list:

            if lot in booked_dict:

                data.append({
                    "Lot": lot,
                    "Status": booked_dict[lot],
                    "Booked": True
                })

            else:

                data.append({
                    "Lot": lot,
                    "Status": "Available",
                    "Booked": False
                })

        df_temp = pd.DataFrame(data)

        def highlight_status(row):

            if not row["Booked"]:

                return [
                    (
                        "background-color: #f0fdf4; "
                        "color: #16a34a; font-weight: bold;"
                        if col == "Status"
                        else ""
                    )
                    for col in row.index
                ]

            return [
                (
                    "background-color: #fef2f2; "
                    "color: #991b1b; font-weight: 900;"
                    if col == "Status"
                    else ""
                )
                for col in row.index
            ]

        styled_df = df_temp.style.apply(
            highlight_status,
            axis=1
        )

        return styled_df.hide(
            axis="columns",
            subset=["Booked"]
        )


    # --------------------------------------------------------
    # DISPLAY LOTS
    # --------------------------------------------------------

    c1, c2, c3, c4 = st.columns(4)

    with c1:

        st.markdown("**Car Boot Lot**")

        st.dataframe(
            build_styled_lot_df(
                all_lots["Car Boot"],
                booked_lots
            ),
            hide_index=True,
            use_container_width=True,
            height=700
        )

    with c2:

        st.markdown("**F&B Lot**")

        st.dataframe(
            build_styled_lot_df(
                all_lots["F&B"],
                booked_lots
            ),
            hide_index=True,
            use_container_width=True,
            height=700
        )

    with c3:

        st.markdown("**Arts & Crafts / Others**")

        st.dataframe(
            build_styled_lot_df(
                all_lots["Arts & Crafts / Others"],
                booked_lots
            ),
            hide_index=True,
            use_container_width=True,
            height=700
        )

    with c4:

        st.markdown("**Food Truck**")

        st.dataframe(
            build_styled_lot_df(
                all_lots["Food Truck"],
                booked_lots
            ),
            hide_index=True,
            use_container_width=True,
            height=700
        )


# ============================================================
# TAB 3: MENU F&B
# ============================================================

with tab3:

    st.subheader(
        "🍔 Dashboard Menu F&B (Approved Sahaja)"
    )

    # --------------------------------------------------------
    # APPROVED F&B ONLY
    # --------------------------------------------------------

    fb_df = df[
        (df[COL_TYPE] == "F&B") &
        (df["Status"] == "Approved")
    ].copy()

    if fb_df.empty:

        st.info(
            "Tiada vendor F&B yang berstatus Approved buat masa ini."
        )

    else:

        # ----------------------------------------------------
        # CATEGORY BREAKDOWN
        # ----------------------------------------------------

        st.markdown(
            "### Kategori F&B"
        )

        rows_kategori = []

        for cat in FB_CATEGORIES:

            normalized_cat = normalize_fb_category(cat)

            c_used = len(
                fb_df[
                    fb_df["_FB_CAT_NORMALIZED"] ==
                    normalized_cat
                ]
            )

            rows_kategori.append({

                "Sub-Kategori": cat,

                "Diambil": c_used,

                "Had": FB_CAT_LIMIT,

                "Baki": max(
                    0,
                    FB_CAT_LIMIT - c_used
                )
            })

        # ----------------------------------------------------
        # COMPACT CARDS (WITHOUT 'BAKI', CLEAN & NO SCROLL)
        # ----------------------------------------------------

        cols = st.columns(8, gap="small")

        for i, row in enumerate(rows_kategori):

            with cols[i]:

                with st.container(height=90, border=True):

                    st.markdown(
                        f"<span style='font-size: 13px; line-height: 1.0;'>**{row['Sub-Kategori']}**</span>",
                        unsafe_allow_html=True
                    )

                    st.markdown(
                        f"<span style='font-size: 16px; font-weight: bold; line-height: 1.0;'>{row['Diambil']} / {row['Had']}</span>",
                        unsafe_allow_html=True
                    )

        st.divider()

        # ----------------------------------------------------
        # MENU / PRODUCT TABLE
        # ----------------------------------------------------

        st.markdown(
            "### Senarai Menu / Produk F&B"
        )

        menu_data = []

        for _, row in fb_df.iterrows():

            menu = str(
                row.get(COL_PRODUCTS, "")
            )

            if menu.lower() in ("", "nan", "none"):
                continue

            menu_data.append({

                "Nama Vendor": row[COL_NAME],

                "Sub-Kategori": row.get(
                    COL_CAT,
                    "-"
                ),

                "Menu / Produk": menu

            })

        if menu_data:

            st.dataframe(

                pd.DataFrame(menu_data),

                hide_index=True,

                use_container_width=True,

                column_config={

                    "Nama Vendor":
                        st.column_config.TextColumn(
                            "Nama Vendor",
                            width="medium"
                        ),

                    "Sub-Kategori":
                        st.column_config.TextColumn(
                            "Sub-Kategori",
                            width="small"
                        ),

                    "Menu / Produk":
                        st.column_config.TextColumn(
                            "Menu/Produk",
                            width="large"
                        )

                }
            )

        else:

            st.info(
                "Tiada maklumat menu F&B diisi oleh vendor yang diluluskan."
            )

            st.caption(
                f"Lajur menu yang dikesan: {COL_PRODUCTS}"
            )


# ============================================================
# END OF FILE
# ============================================================
