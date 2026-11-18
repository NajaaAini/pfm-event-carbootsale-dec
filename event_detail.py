import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import re

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from streamlit_gsheets import GSheetsConnection

from style import apply_style
from components import page_header

st.set_page_config(page_title="PFM | Maklumat Acara & Semak Status", layout="wide")
apply_style()
page_header()

# ==========================================
# 1. DATA EVENT & CONFIG
# ==========================================
event_key = st.query_params.get("event", "event_1")
if event_key not in st.secrets:
    event_key = "event_1"

ev_data = st.secrets.get(event_key, {})

if not ev_data.get("active", event_key == "event_1"):
    st.info("Maklumat acara ini akan diumumkan tidak lama lagi.")
    if st.button("⬅️ Kembali ke Menu Utama"):
        st.switch_page("info_page.py")
    st.stop()

event_name = ev_data.get("name", "Event PFM")
event_date_str = ev_data.get("event_date", "11 - 12 December 2026")
event_time_str = ev_data.get("event_time", "4:00 PM – 12:00 AM")
event_venue_str = ev_data.get("venue", "Perkarangan Penang Ferry Museum")
form_url = ev_data.get("google_form_responses_url", "https://forms.gle/7eoMCUDyQYRfLA7e8")
whatsapp_group = ev_data.get("whatsapp_group", "https://wa.me/601157727459")
whatsapp_admin = f"https://wa.me/601157727459?text=Hi%20Admin,%20saya%20nak%20tanya%20pasal%20{event_name.replace(' ', '%20')}"

TIMEZONE = ZoneInfo("Asia/Kuala_Lumpur")

COL_NAME = "Nama Perniagaan Syarikat"
COL_PHONE = "Nombor Telefon/Phone Number"
COL_TYPE = "Kategori Produk/Product Category"
COL_CAT = "F&B CATEGORY"
COL_PLATE = "Plate Number"
COL_ADDON = "ADD ON"
COL_REMARK = "Remark"
PROOF_COL = "Upload Bukti Bayaran dan Pemilihan Lot"

VALID_STATUSES = ["Pending", "Approved", "Rejected", "Cancelled"]

# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================
def normalize_status(raw):
    if raw is None or pd.isna(raw) or str(raw).strip() == "":
        return "Pending"
    s = str(raw).strip().title()
    aliases = {
        "Menunggu": "Pending", "Waiting": "Pending", "New": "Pending",
        "Approve": "Approved", "Reject": "Rejected", "Cancel": "Cancelled", "Canceled": "Cancelled",
    }
    return aliases.get(s, s) if aliases.get(s, s) in VALID_STATUSES else "Pending"

def format_phone_display(raw):
    if raw is None or pd.isna(raw):
        return "-"
    s = str(raw).strip()
    if s.endswith(".0"): s = s[:-2]
    s = s.replace("-", "").replace(" ", "")
    if not s.startswith("0"): s = "0" + s
    if len(s) == 11: return f"{s[:3]}-{s[3:7]} {s[7:]}"
    elif len(s) == 10: return f"{s[:2]}-{s[2:5]} {s[5:]}"
    return s

def format_rm(amount):
    try: return f"RM {float(amount):,.2f}"
    except Exception: return "RM 0.00"

def clean_text_field(raw):
    if raw is None or pd.isna(raw) or str(raw).strip().lower() in ("", "nan", "none", "nat", "null"):
        return ""
    return str(raw).strip()

def find_products_column(df_):
    for c in df_.columns:
        if "Senarai Produk yang Dijual" in str(c): return c
    return None

def find_lot_column(df_):
    for c in df_.columns:
        if any(k in str(c).lower() for k in ["lot", "no. lot", "space", "tapak"]):
            return c
    return None

def _clean_plate_str(p):
    """Bersihkan satu string plate — buang semua simbol, uppercase."""
    if p is None or pd.isna(p):
        return ""
    return "".join(e for e in str(p) if e.isalnum()).upper()

def normalize_plate(series):
    return series.astype(str).apply(lambda p: _clean_plate_str(p))

def get_category_price(vendor_type):
    try:
        if vendor_type == "Car Boot Sales":
            return float(ev_data.get("price_car_boot", 160))
        elif vendor_type == "F&B":
            return float(ev_data.get("price_fb", 400))
        elif vendor_type == "Food Truck":
            return float(ev_data.get("price_ft", 400))
        else:
            return float(ev_data.get("price_others", 200))
    except Exception:
        return 0.0

def get_deposit(vendor_type):
    try:
        if vendor_type == "F&B":
            return float(ev_data.get("deposit_fb", 100))
        elif vendor_type == "Food Truck":
            return float(ev_data.get("deposit_ft", 100))
        elif vendor_type == "Arts/Crafts & Others":
            return float(ev_data.get("deposit_others", 100))
        return 0.0
    except Exception:
        return 0.0

def get_addon_price(addon_str):
    if addon_str is None or pd.isna(addon_str):
        return 0.0
    try:
        matches = re.findall(r"RM\s*([0-9]+(?:\.[0-9]+)?)", str(addon_str))
        return sum(float(m) for m in matches)
    except Exception:
        return 0.0

@st.cache_data(ttl=60, show_spinner="Memuatkan data...")
def load_vendors():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try: return conn.read(worksheet="Vendors", ttl=60), None
    except Exception as e: return None, str(e)

@st.cache_data(ttl=5, show_spinner=False)
def load_payments():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try: return conn.read(worksheet="Payments", ttl=5), None
    except Exception as e: return None, str(e)

def get_vendor_payment_info(payments_df, plate_norm):
    """Versi tahan lasak — auto-detect column bukti, normalize plate sepenuhnya."""
    if payments_df is None or payments_df.empty:
        return {}
    if "Plate Number" not in payments_df.columns:
        return {}

    payments_df = payments_df.copy()
    payments_df["_plate_norm"] = payments_df["Plate Number"].apply(_clean_plate_str)

    matched = payments_df[payments_df["_plate_norm"] == _clean_plate_str(plate_norm)]
    if matched.empty:
        return {}

    try:
        matched = matched.sort_values("Timestamp", ascending=False)
    except Exception:
        pass

    latest = matched.iloc[0]

    def _clean(v):
        if v is None or pd.isna(v):
            return ""
        s = str(v).strip()
        if s.lower() in ("nan", "none", "nat", "null"):
            return ""
        return s

    proof_col_actual = None
    for c in payments_df.columns:
        cname = str(c).strip().lower()
        if "bukti" in cname or "proof" in cname:
            proof_col_actual = c
            break

    if proof_col_actual is None:
        proof_col_actual = PROOF_COL

    proof_raw = _clean(latest.get(proof_col_actual, ""))

    proof_url = proof_raw
    if proof_raw and "drive.google.com" in proof_raw:
        file_id = None
        if "id=" in proof_raw:
            file_id = proof_raw.split("id=")[1].split("&")[0]
        elif "/file/d/" in proof_raw:
            file_id = proof_raw.split("/file/d/")[1].split("/")[0]
        elif "/d/" in proof_raw:
            file_id = proof_raw.split("/d/")[1].split("/")[0]
        if file_id:
            proof_url = f"https://drive.google.com/file/d/{file_id}/preview"

    return {
        "proof_url": proof_url,
        "timestamp": _clean(latest.get("Timestamp", "")),
        "parking_lot": _clean(latest.get("Pilih parking lot", "")),
        "fnb_lot": _clean(latest.get("Pilih F&B Lot", "")),
        "ft_lot": _clean(latest.get("Pilih Food Truck Lot", "") or latest.get("Pilih F&B Lot", "")),
        "arts_lot": _clean(latest.get("Pilih Arts/Crafts & Others Lot", "") or latest.get("Pilih Arts & Crafts / Toys Lot", "")),
    }

def render_products_box(products_text):
    st.markdown(
        "<div style='background:#faf5ec; border-left:4px solid #78350f; "
        "border-radius:8px; padding:0.6rem 0.9rem; margin:0.4rem 0;'>"
        "<div style='font-size:0.7rem; color:#78350f; letter-spacing:0.04em; "
        "font-weight:700; text-transform:uppercase; margin-bottom:0.25rem;'>"
        "🛍️ Senarai Produk Anda</div>"
        f"<div style='font-size:0.82rem; color:#44403c; white-space:pre-wrap; "
        f"line-height:1.4;'>{products_text}</div>"
        "</div>",
        unsafe_allow_html=True,
    )

# ==========================================
# 3. POPUPS (DIALOGS) — SEMUA STATUS
# ==========================================
@st.dialog("⏳ Permohonan Sedang Disemak", width="large")
def show_pending_dialog(row, plate, products_text=""):
    st.markdown(
        "<div style='text-align:center; padding:0.2rem 0 0.5rem 0;'>"
        "<div style='font-size:2.2rem; line-height:1;'>⏳</div>"
        "<div style='font-size:1.15rem; font-weight:700; color:#92400e; margin-top:0.3rem;'>Permohonan Sedang Disemak</div>"
        "<div style='font-size:0.85rem; color:#a16207; margin-top:0.2rem;'>Anggaran 2-3 hari bekerja</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    cat_str = f" · {row[COL_CAT]}" if pd.notna(row.get(COL_CAT)) and str(row.get(COL_CAT)).strip() else ""
    st.markdown(
        f"<div style='background:#fffbeb; border:1px solid #fde68a; border-radius:8px; padding:0.6rem 0.8rem; margin:0.3rem 0;'>"
        f"<div style='font-size:0.95rem; font-weight:700; color:#92400e;'>🚗 {plate} — {row[COL_NAME]}</div>"
        f"<div style='font-size:0.8rem; color:#a16207;'>{row[COL_TYPE]}{cat_str}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    admin_note = str(row.get("Notes", "")).strip() if pd.notna(row.get("Notes")) else ""
    if admin_note and admin_note.lower() not in ("nan", "none", "null"):
        st.info(f"📝 **Nota Admin:** {admin_note}")
    vendor_remark = str(row.get(COL_REMARK, "")).strip() if pd.notna(row.get(COL_REMARK)) else ""
    if vendor_remark and vendor_remark.lower() not in ("nan", "none", "null"):
        st.caption(f"📋 **Remark anda:** {vendor_remark}")
    if products_text:
        render_products_box(products_text)
    st.info("📌 Sila tunggu pengesahan admin. Anda akan dapat notifikasi selepas disemak.")
    if st.button("Tutup", width="stretch"): st.rerun()

@st.dialog("🎉 Tahniah!", width="large")
def show_success_dialog(row, plate, status, paid, slot_items, products_text=""):
    st.markdown(
        "<div style='text-align:center; padding:0.2rem 0 0.5rem 0;'>"
        "<div style='font-size:2.2rem; line-height:1;'>🎉</div>"
        "<div style='font-size:1.2rem; font-weight:700; color:#14532d; margin-top:0.3rem;'>Pendaftaran Berjaya Disahkan!</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    cat_str = f" · {row[COL_CAT]}" if pd.notna(row.get(COL_CAT)) and str(row.get(COL_CAT)).strip() else ""
    st.markdown(
        f"<div style='background:#f0fdf4; border:1px solid #bbf7d0; border-radius:8px; padding:0.6rem 0.8rem; margin:0.3rem 0;'>"
        f"<div style='font-size:0.95rem; font-weight:700; color:#14532d;'>🚗 {plate} — {row[COL_NAME]}</div>"
        f"<div style='font-size:0.8rem; color:#166534;'>{row[COL_TYPE]}{cat_str}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    if slot_items:
        cols = st.columns(2)
        for i, (label, val) in enumerate(slot_items):
            with cols[i % 2]:
                st.markdown(
                    f"<div style='background:#f7f3ee; border-radius:6px; padding:0.4rem 0.6rem; margin-bottom:0.3rem; font-size:0.82rem;'><b>{label}:</b> {val}</div>",
                    unsafe_allow_html=True,
                )
    admin_note = str(row.get("Notes", "")).strip() if pd.notna(row.get("Notes")) else ""
    if admin_note and admin_note.lower() not in ("nan", "none", "null"):
        st.info(f"📝 **Nota Admin:** {admin_note}")
    vendor_remark = str(row.get(COL_REMARK, "")).strip() if pd.notna(row.get(COL_REMARK)) else ""
    if vendor_remark and vendor_remark.lower() not in ("nan", "none", "null"):
        st.caption(f"📋 **Remark anda:** {vendor_remark}")
    if products_text:
        render_products_box(products_text)
    st.info("📌 **Jangan lupa join WhatsApp Group Vendor** untuk info terkini.")
    st.link_button("💬 Join WhatsApp Group Vendor", whatsapp_group, width="stretch", type="primary")
    if st.button("Tutup", width="stretch"): st.rerun()

@st.dialog("📤 Bukti Bayaran Dihantar", width="large")
def show_proof_uploaded_dialog(row, plate, proof_upload_time, products_text=""):
    st.markdown(
        "<div style='text-align:center; padding:0.2rem 0 0.5rem 0;'>"
        "<div style='font-size:2.2rem; line-height:1;'>📤</div>"
        "<div style='font-size:1.15rem; font-weight:700; color:#1e40af; margin-top:0.3rem;'>Bukti Bayaran Telah Dihantar</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    cat_str = f" · {row[COL_CAT]}" if pd.notna(row.get(COL_CAT)) and str(row.get(COL_CAT)).strip() else ""
    st.markdown(
        f"<div style='background:#eff6ff; border:1px solid #bfdbfe; border-radius:8px; padding:0.6rem 0.8rem; margin:0.3rem 0;'>"
        f"<div style='font-size:0.95rem; font-weight:700; color:#1e40af;'>🚗 {plate} — {row[COL_NAME]}</div>"
        f"<div style='font-size:0.8rem; color:#1d4ed8;'>{row[COL_TYPE]}{cat_str}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    if proof_upload_time:
        st.markdown(
            f"<div style='background:#f8fafc; border-radius:6px; padding:0.5rem 0.8rem; font-size:0.82rem; color:#475569;'>"
            f"🕐 <b>Diterima:</b> {proof_upload_time}</div>",
            unsafe_allow_html=True,
        )
    admin_note = str(row.get("Notes", "")).strip() if pd.notna(row.get("Notes")) else ""
    if admin_note and admin_note.lower() not in ("nan", "none", "null"):
        st.info(f"📝 **Nota Admin:** {admin_note}")
    vendor_remark = str(row.get(COL_REMARK, "")).strip() if pd.notna(row.get(COL_REMARK)) else ""
    if vendor_remark and vendor_remark.lower() not in ("nan", "none", "null"):
        st.caption(f"📋 **Remark anda:** {vendor_remark}")
    if products_text:
        render_products_box(products_text)
    st.info("📌 Admin sedang menyemak bukti bayaran anda. Sila tunggu pengesahan.")
    if st.button("Tutup", width="stretch"): st.rerun()

@st.dialog("💳 Maklumat Pembayaran", width="large")
def show_payment_dialog(row, plate, vendor_type, cat_price, deposit_amount, addon_price, total_price, admin_note="", products_text=""):
    st.markdown(
        f"<div style='text-align:center; padding:0.2rem 0 0.4rem 0;'>"
        f"<div style='font-size:0.7rem; color:#9a3412; font-weight:700; text-transform:uppercase;'>💰 Jumlah Perlu Dibayar</div>"
        f"<div style='font-size:1.8rem; font-weight:800; color:#7c2d12; line-height:1.1;'>{format_rm(total_price)}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    
    st.markdown(
        f"<div style='background:#fafaf9; border-radius:6px; padding:0.5rem 0.8rem; margin:0.3rem 0; font-size:0.82rem; color:#57534e; text-align:center;'>"
        f"📦 {vendor_type}: <b>{format_rm(cat_price)}</b> "
        f"{f'| 🔒 Deposit: <b>{format_rm(deposit_amount)}</b>' if deposit_amount > 0 else ''} "
        f"{f'| ➕ Add On: <b>{format_rm(addon_price)}</b>' if addon_price > 0 else ''}"
        f"</div>",
        unsafe_allow_html=True,
    )

    if admin_note:
        st.markdown(f"<div style='background:#eff6ff; border-left:3px solid #2563eb; border-radius:6px; padding:0.5rem 0.8rem; font-size:0.82rem; color:#44403c; margin:0.3rem 0;'><b>Nota Admin:</b> {admin_note}</div>", unsafe_allow_html=True)

    if products_text:
        render_products_box(products_text)

    st.markdown("<div style='font-size:0.7rem; color:#78716c; font-weight:700; text-transform:uppercase; margin-top:0.4rem;'>🏦 Maklumat Bank</div>", unsafe_allow_html=True)
    bc1, bc2 = st.columns(2)
    with bc1:
        st.markdown("<div style='font-size:0.8rem; background:#eff6ff; border-radius:6px; padding:0.5rem;'><b>MAYBANK</b><br>PRINTHERO MERCHANDISE</div>", unsafe_allow_html=True)
    with bc2:
        st.markdown("<div style='font-size:0.8rem; background:#eff6ff; border-radius:6px; padding:0.5rem;'>Akaun: <b>557054621057</b><br>Remark: <b>PFMCBS + 4 digit tel</b></div>", unsafe_allow_html=True)

    st.link_button("📤 Upload bukti pembayaran dan pemilihan slot", ev_data.get("payment_form_url", form_url), width="stretch", type="primary")
    if st.button("Tutup", width="stretch"): st.rerun()

@st.dialog("✕ Permohonan Tidak Berjaya", width="large")
def show_reject_dialog(row, plate, reject_reason, products_text=""):
    st.markdown(
        "<div style='text-align:center; padding:0.2rem 0 0.5rem 0;'>"
        "<div style='font-size:2.2rem; line-height:1;'>✕</div>"
        "<div style='font-size:1.15rem; font-weight:700; color:#991b1b; margin-top:0.3rem;'>Permohonan Tidak Berjaya</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    cat_str = f" · {row[COL_CAT]}" if pd.notna(row.get(COL_CAT)) and str(row.get(COL_CAT)).strip() else ""
    st.markdown(
        f"<div style='background:#fef2f2; border:1px solid #fecaca; border-radius:8px; padding:0.6rem 0.8rem; margin:0.3rem 0;'>"
        f"<div style='font-size:0.95rem; font-weight:700; color:#991b1b;'>🚗 {plate} — {row[COL_NAME]}</div>"
        f"<div style='font-size:0.8rem; color:#b91c1c;'>{row[COL_TYPE]}{cat_str}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    if reject_reason:
        st.markdown(f"<div style='background:#fff7ed; border-left:3px solid #dc2626; border-radius:6px; padding:0.5rem; font-size:0.82rem;'><b>Mesej Admin:</b> {reject_reason}</div>", unsafe_allow_html=True)
    if products_text:
        render_products_box(products_text)
    st.info("📌 Sila hubungi admin jika anda ingin bertanya lanjut.")
    st.link_button("📲 Hubungi Admin", whatsapp_admin, width="stretch", type="primary")
    if st.button("Tutup", width="stretch"): st.rerun()

@st.dialog("🚫 Slot Dibatalkan", width="large")
def show_cancel_dialog(row, plate, cancel_reason, products_text=""):
    st.markdown(
        "<div style='text-align:center; padding:0.2rem 0 0.5rem 0;'>"
        "<div style='font-size:2.2rem; line-height:1;'>🚫</div>"
        "<div style='font-size:1.15rem; font-weight:700; color:#991b1b; margin-top:0.3rem;'>Slot Dibatalkan</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    cat_str = f" · {row[COL_CAT]}" if pd.notna(row.get(COL_CAT)) and str(row.get(COL_CAT)).strip() else ""
    st.markdown(
        f"<div style='background:#fef2f2; border:1px solid #fecaca; border-radius:8px; padding:0.6rem 0.8rem; margin:0.3rem 0;'>"
        f"<div style='font-size:0.95rem; font-weight:700; color:#991b1b;'>🚗 {plate} — {row[COL_NAME]}</div>"
        f"<div style='font-size:0.8rem; color:#b91c1c;'>{row[COL_TYPE]}{cat_str}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    if cancel_reason:
        st.markdown(f"<div style='background:#fef2f2; border-left:3px solid #dc2626; border-radius:6px; padding:0.5rem; font-size:0.82rem;'><b>Mesej Admin:</b> {cancel_reason}</div>", unsafe_allow_html=True)
    if products_text:
        render_products_box(products_text)
    st.info("📌 Sila hubungi admin jika anda ingin bertanya lanjut.")
    st.link_button("📲 Hubungi Admin", whatsapp_admin, width="stretch", type="primary")
    if st.button("Tutup", width="stretch"): st.rerun()

@st.dialog("❌ Tiada Permohonan Dijumpai", width="large")
def show_not_found_dialog(query):
    st.markdown(
        "<div style='text-align:center; padding:0.2rem 0 0.5rem 0;'>"
        "<div style='font-size:2.2rem; line-height:1;'>❌</div>"
        "<div style='font-size:1.15rem; font-weight:700; color:#991b1b; margin-top:0.3rem;'>Tiada Permohonan Dijumpai</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div style='background:#fef2f2; border:1px solid #fecaca; border-radius:8px; padding:0.6rem 0.8rem; margin:0.3rem 0; text-align:center;'>"
        f"<div style='font-size:0.85rem; color:#991b1b;'>No. Plate: <b>{query}</b></div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.info("Sila pastikan No. Plate anda betul, atau daftar sekarang jika belum mendaftar.")
    st.link_button("📝 Daftar Sekarang", form_url, type="primary", width="stretch")
    if st.button("Tutup", width="stretch"): st.rerun()

# ==========================================
# 4. TOP NAVIGATION BAR (MENU PANTAS)
# ==========================================
if st.button("⬅️ Kembali ke Menu Utama"):
    st.switch_page("info_page.py")


nav_col1, nav_col2, nav_col3, nav_col4 = st.columns(4)
with nav_col1:
    if st.button("Pendaftaran Vendor", use_container_width=True):
        components.html("""<script>const el = window.parent.document.getElementById('daftar-vendor'); if (el) { el.scrollIntoView({ behavior: 'smooth' }); }</script>""", height=0)
with nav_col2:
    if st.button("Semak Status", use_container_width=True):
        components.html("""<script>const el = window.parent.document.getElementById('semak-status'); if (el) { el.scrollIntoView({ behavior: 'smooth' }); }</script>""", height=0)
with nav_col3:
    if st.button("Harga Tapak", use_container_width=True):
        components.html("""<script>const el = window.parent.document.getElementById('harga-sewa'); if (el) { el.scrollIntoView({ behavior: 'smooth' }); }</script>""", height=0)
with nav_col4:
    if st.button("Layout Tapak", use_container_width=True):
        components.html("""<script>const el = window.parent.document.getElementById('layout-tapak'); if (el) { el.scrollIntoView({ behavior: 'smooth' }); }</script>""", height=0)

st.divider()

# ==========================================
# 5. PAPARAN UTAMA & HERO
# ==========================================
st.markdown(f"<h1 style='text-align: center; font-size: 2.5rem;'>{event_name}</h1>", unsafe_allow_html=True)
st.write("") 

col_left, col_right = st.columns([1, 2])
banner_file = ev_data.get("banner", "assets/cbssh.png" if event_key == "event_1" else "")

with col_left:
    if banner_file and Path(banner_file).exists():
        st.image(banner_file, use_container_width=True)
    else:
        st.info("Tiada banner.")

with col_right:
    with st.container(border=True):
        st.markdown("<h4 style='font-size: 1.3rem; margin-bottom: 0px;'>📌 Maklumat Rasmi Acara</h4>", unsafe_allow_html=True)
        st.markdown("---")
        
        d_col1, d_col2 = st.columns([1, 2])
        with d_col1: st.markdown("<p style='font-size: 1rem; font-weight: bold;'>Tarikh Acara:</p>", unsafe_allow_html=True)
        with d_col2: st.markdown(f"<p style='font-size: 1rem;'>{event_date_str}</p>", unsafe_allow_html=True)
            
        d_col3, d_col4 = st.columns([1, 2])
        with d_col3: st.markdown("<p style='font-size: 1rem; font-weight: bold;'>Masa Operasi:</p>", unsafe_allow_html=True)
        with d_col4: st.markdown(f"<p style='font-size: 1rem;'>{event_time_str}</p>", unsafe_allow_html=True)
            
        d_col5, d_col6 = st.columns([1, 2])
        with d_col5: st.markdown("<p style='font-size: 1rem; font-weight: bold;'>Lokasi Tapak:</p>", unsafe_allow_html=True)
        with d_col6: st.markdown(f"<p style='font-size: 1rem;'>{event_venue_str}</p>", unsafe_allow_html=True)

    sub_col1, sub_col2 = st.columns(2)
    with sub_col1:
        with st.container(border=True):
            try:
                target = datetime(2026, 12, 11, 0, 0, tzinfo=TIMEZONE)
                rem = int((target - datetime.now(TIMEZONE)).total_seconds())
                if rem > 0:
                    d, h = rem // 86400, (rem % 86400) // 3600
                    m, s = (rem % 3600) // 60, rem % 60
                    st.metric("⏳ Countdown Acara", f"{d} Hari {h} Jam {m} Minit")
                else:
                    st.info("🎉 Acara sedang berlangsung!")
            except Exception:
                pass

    total_vendor = "Tidak Diketahui"
    try:
        vend_df, _ = load_vendors()
        if vend_df is not None: total_vendor = len(vend_df)
    except Exception: pass

    with sub_col2:
        with st.container(border=True):
            max_s = ev_data.get("max_slots")
            val_text = f"{total_vendor} / {max_s} Slot" if max_s else str(total_vendor)
            st.metric("Vendor Berdaftar", val_text)

    st.divider()
    st.markdown('<div id="daftar-vendor"></div>', unsafe_allow_html=True)
    st.markdown("<h3 style='font-size: 1.3rem; margin-top: 0px;'>📝 Pendaftaran Vendor</h3>", unsafe_allow_html=True)
    st.link_button("Borang Pendaftaran Vendor", form_url, type="primary", use_container_width=True)

st.divider()

# ==========================================
# 6. SEMAK STATUS KELAYAKAN
# ==========================================
st.markdown('<div id="semak-status"></div>', unsafe_allow_html=True)
st.markdown("<h3 style='font-size: 1.6rem;'>🔍 Semak Status Kelayakan</h3>", unsafe_allow_html=True)
st.caption("Masukkan No. Plate kenderaan anda untuk menyemak status permohonan.")

with st.container(border=True):
    with st.form("search_form_detail"):
        query = st.text_input("No. Plate Kenderaan", placeholder="Contoh: NNA1806").strip().upper()
        submitted = st.form_submit_button("Semak Status Kelayakan", type="primary", use_container_width=True)

        st.markdown(f"""
        <div style='text-align: center; font-size: 0.85rem; margin-top: 0.3rem;'>
            Belum mendaftar? <a href='{form_url}' target='_blank' style='color: #78350f; font-weight: 600; text-decoration: underline;'>Daftar Sekarang</a>
        </div>
        """, unsafe_allow_html=True)

if submitted and query:
    df, err = load_vendors()
    if df is None:
        st.error(f"Gagal memuatkan data: {err}")
    else:
        if "Status" not in df.columns: df["Status"] = "Pending"
        else: df["Status"] = df["Status"].apply(normalize_status)

        result = df[normalize_plate(df[COL_PLATE]) == _clean_plate_str(query)]
        if result.empty:
            show_not_found_dialog(query)
        else:
            row = result.iloc[0]
            status = str(row["Status"]).strip()
            paid = bool(row["Paid"]) if "Paid" in row and pd.notna(row["Paid"]) else False
            plate_norm = _clean_plate_str(row[COL_PLATE])

            payments_df, _ = load_payments()
            payment_info = get_vendor_payment_info(payments_df if payments_df is not None else pd.DataFrame(), plate_norm)
            has_uploaded_proof = bool(payment_info.get("proof_url"))
            proof_upload_time = payment_info.get("timestamp", "")
            
            parking_lot = payment_info.get("parking_lot", "")
            fnb_lot = payment_info.get("fnb_lot", "")
            ft_lot = payment_info.get("ft_lot", "")
            arts_lot = payment_info.get("arts_lot", "")

            products_col_name = find_products_column(df)
            products_text = clean_text_field(row.get(products_col_name, "")) if products_col_name else ""

            # ===== SEMUA STATUS JADI POPUP =====
            if status == "Pending":
                show_pending_dialog(row, plate_norm, products_text)

            elif status == "Rejected":
                reject_reason = str(row.get("Notes", "") or "").strip()
                show_reject_dialog(row, plate_norm, reject_reason, products_text)

            elif status == "Cancelled":
                cancel_reason = str(row.get("Notes", "") or "").strip()
                show_cancel_dialog(row, plate_norm, cancel_reason, products_text)

            elif status == "Approved":
                if not paid and has_uploaded_proof:
                    show_proof_uploaded_dialog(row, plate_norm, proof_upload_time, products_text)

                elif not paid and not has_uploaded_proof:
                    vendor_type = str(row.get(COL_TYPE, "")).strip()
                    cat_price = get_category_price(vendor_type)
                    deposit_amount = get_deposit(vendor_type)
                    addon_str_raw = str(row.get(COL_ADDON, "") or "")
                    addon_price = get_addon_price(addon_str_raw)
                    total_price = cat_price + deposit_amount + addon_price

                    admin_note_for_popup = str(row.get("Notes", "")).strip() if pd.notna(row.get("Notes")) else ""

                    if total_price > 0:
                        show_payment_dialog(
                            row, plate_norm, vendor_type,
                            cat_price, deposit_amount, addon_price, total_price,
                            admin_note=admin_note_for_popup,
                            products_text=products_text,
                        )
                    else:
                        show_pending_dialog(row, plate_norm, products_text)

                else:
                    slot_items = []
                    if parking_lot: slot_items.append(("🅿️ Parking Lot", parking_lot))
                    if fnb_lot: slot_items.append(("🍴 F&B Lot", fnb_lot))
                    if ft_lot and ft_lot != fnb_lot: slot_items.append(("🚚 Food Truck Lot", ft_lot))
                    if arts_lot: slot_items.append(("🎨 Arts/Crafts Lot", arts_lot))

                    if not slot_items:
                        l_col = find_lot_column(df)
                        if l_col and clean_text_field(row.get(l_col, "")):
                            slot_items.append(("📍 Lot / Ruang Niaga", clean_text_field(row.get(l_col, ""))))

                    show_success_dialog(row, plate_norm, status, paid, slot_items, products_text)

st.divider()

# ==========================================
# 7. HARGA SEWA TAPAK & DEPOSIT
# ==========================================
st.markdown('<div id="harga-sewa"></div>', unsafe_allow_html=True)
st.markdown("<h3 style='font-size: 1.6rem;'>💰 Harga Sewa Tapak & Deposit</h3>", unsafe_allow_html=True)
st.caption("Nota: Deposit dipulangkan selepas acara tamat tertakluk kepada peraturan tapak. Kadar sewa tidak termasuk deposit.")

pricing_rows = [
    {"Kategori Tapak": "Car Boot Sales", "Kadar Sewa": format_rm(ev_data.get("price_car_boot", 160)), "Deposit": format_rm(0)},
    {"Kategori Tapak": "F&B", "Kadar Sewa": format_rm(ev_data.get("price_fb", 400)), "Deposit": format_rm(ev_data.get("deposit_fb", 100))},
    {"Kategori Tapak": "Food Truck", "Kadar Sewa": format_rm(ev_data.get("price_ft", 400)), "Deposit": format_rm(ev_data.get("deposit_ft", 100))},
    {"Kategori Tapak": "Arts / Crafts & Lain-lain", "Kadar Sewa": format_rm(ev_data.get("price_others", 200)), "Deposit": format_rm(ev_data.get("deposit_others", 100))},
]
st.dataframe(pd.DataFrame(pricing_rows), hide_index=True, use_container_width=True)

st.divider()

# ==========================================
# 8. LAYOUT TAPAK CAR BOOT SALE (DENGAN LAYOUT.PNG)
# ==========================================
st.markdown('<div id="layout-tapak"></div>', unsafe_allow_html=True)
st.markdown("<h3 style='font-size: 1.6rem;'>🗺️ Layout & Zon Tapak Niaga</h3>", unsafe_allow_html=True)
st.caption("Pelan susun atur ruang niaga dan tapak rasmi di perkarangan Penang Ferry Museum.")

with st.container(border=True):
    layout_path = Path("assets/layout.png")
    if layout_path.exists():
        st.image("assets/layout.png", caption="Pelan Susun Atur Tapak PFM Car Boot Sale", use_container_width=True)
    else:
        st.warning("⚠️ Fail gambar `layout.png` tidak dijumpai di dalam folder `assets/`.")

    st.markdown("""
    <div style="background-color: #FFFCF7; padding: 0.8rem; border-radius: 8px; border: 1px dashed #D97706; margin-top: 10px;">
        <h4 style="color: #78350F; margin-top: 0; font-size: 1rem;">📍 Panduan Zon Tapak PFM</h4>
        <ul style="color: #57534e; font-size: 0.85rem; line-height: 1.5; margin-bottom: 0;">
            <li><b>Zon A - F (Car Boot Sales):</b> Khas untuk kenderaan peserta berniaga terus dari bonet.</li>
            <li><b>Zon H - I (F&B):</b> Ruang untuk vendor f&b.</li>
            <li><b>Zon K (Food Truck):</b> Lot parkir khas untuk trak makanan.</li>
            <li><b>Zon J (Arts, Crafts & Retail):</b> Tapak khemah produk kraftangan & pakaian.</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)

st.divider()

# ==========================================
# 9. HUBUNGI ADMIN
# ==========================================
st.link_button("📲 Ada Pertanyaan? Hubungi Admin di WhatsApp", whatsapp_admin, use_container_width=True)
