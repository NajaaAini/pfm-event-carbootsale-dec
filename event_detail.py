import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

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
event_date_str = ev_data.get("event_date", "2026-12-11")
event_time_str = ev_data.get("event_time", "4:00 PM – 12:00 AM")
event_venue_str = ev_data.get("venue", "Perkarangan Penang Ferry Museum")
form_url = ev_data.get("google_form_responses_url", "https://forms.gle/7eoMCUDyQYRfLA7e8")
whatsapp_group = ev_data.get("whatsapp_group", "https://wa.me/601157727459")
whatsapp_admin = f"https://wa.me/601157727459?text=Hi%20Admin,%20saya%20nak%20tanya%20pasal%20{event_name.replace(' ', '%20')}"

TIMEZONE = ZoneInfo("Asia/Kuala_Lumpur")

COL_NAME = "Nama Perniagaan Syarikat"
COL_PHONE = "Nombor Telefon/Phone Number"
COL_TYPE = "Kategori Produk/Product Category"
COL_PLATE = "Plate Number"
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

def normalize_plate(series):
    return series.astype(str).str.upper().str.replace(" ", "")

@st.cache_data(ttl=60, show_spinner="Memuatkan data...")
def load_vendors():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try: return conn.read(worksheet="Vendors", ttl=60), None
    except Exception as e: return None, str(e)

@st.cache_data(ttl=30, show_spinner=False)
def check_payment_uploaded(plate):
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        payments_df = conn.read(worksheet="Payments", ttl=30)
        if payments_df is not None and not payments_df.empty:
            return normalize_plate(payments_df["Plate Number"]).str.contains(plate).any()
    except Exception: pass
    return False

def save_vendor_edit(conn, df, plate, new_phone, new_products):
    mask = normalize_plate(df[COL_PLATE]) == plate
    df.loc[mask, COL_PHONE] = new_phone
    p_col = find_products_column(df)
    if p_col: df.loc[mask, p_col] = new_products
    conn.update(worksheet="Vendors", data=df)
    st.cache_data.clear()

# ==========================================
# 3. DIALOG STATUS
# ==========================================
@st.dialog("Tiada Rekod Dijumpai", width="large")
def show_not_found_dialog(query):
    st.error(f"❌ Tiada permohonan dijumpai untuk No. Plate: `{query}`")
    st.info("Sila pastikan No. Plate anda betul, atau daftar sekarang jika belum mendaftar.")
    st.link_button("📝 Daftar Sekarang", form_url, type="primary", use_container_width=True)
    if st.button("Tutup", use_container_width=True): st.rerun()

@st.dialog("Status Permohonan", width="large")
def show_status_dialog(row, plate_norm, status, paid, products_text, lot_info):
    st.markdown(f"### 🚗 {row[COL_PLATE]} — {row[COL_NAME]}")
    st.caption(f"Kategori: {row[COL_TYPE]}")

    if status == "Pending":
        st.warning("⏳ Permohonan Sedang Disemak (2-3 hari bekerja). Belum perlu bayar.")
    elif status == "Rejected":
        st.error(f"❌ Permohonan Tidak Berjaya: {clean_text_field(row.get('Notes', ''))}")
    elif status == "Cancelled":
        st.error(f"🚫 Slot Dibatalkan: {clean_text_field(row.get('Notes', ''))}")
    elif status == "Approved":
        if paid:
            st.success("✅ Permohonan Disahkan & Bayaran Diterima.")
            
            # Papar Lot Pilihan jika ada
            if lot_info:
                st.info(f"📍 **Lot / Ruang Niaga Anda:** {lot_info}")

            if products_text:
                with st.container(border=True):
                    st.caption("🛍️ Senarai Produk Anda")
                    st.text(products_text)
            st.link_button("💬 Join WhatsApp Group Vendor", whatsapp_group, type="primary", use_container_width=True)
            st.balloons()
        else:
            if check_payment_uploaded(plate_norm):
                st.info("⏳ Bayaran Sedang Disemak (1-2 hari bekerja).")
                if lot_info:
                    st.info(f"📍 **Lot Pilihan:** {lot_info}")
            else:
                st.info("📤 Sila buat pembayaran & muat naik bukti bayaran.")
                
                # Kira anggaran harga berdasarkan kategori produk
                v_type = str(row[COL_TYPE]).lower()
                if "f&b" in v_type or "makanan" in v_type:
                    rent = float(ev_data.get("price_fb", 400))
                    dep = float(ev_data.get("deposit_fb", 100))
                elif "truck" in v_type:
                    rent = float(ev_data.get("price_ft", 400))
                    dep = float(ev_data.get("deposit_ft", 100))
                elif "art" in v_type or "craft" in v_type or "lain" in v_type:
                    rent = float(ev_data.get("price_others", 200))
                    dep = float(ev_data.get("deposit_others", 100))
                else:
                    rent = float(ev_data.get("price_car_boot", 160))
                    dep = float(ev_data.get("deposit_car_boot", 0))
                
                total_amt = rent + dep
                
                with st.container(border=True):
                    st.markdown(f"**💰 Ringkasan Bayaran Perlu Dibuat:**")
                    st.write(f"- Kadar Sewa Tapak: {format_rm(rent)}")
                    st.write(f"- Deposit Keselamatan: {format_rm(dep)}")
                    st.markdown(f"### **Jumlah Keseluruhan: {format_rm(total_amt)}**")

                if lot_info:
                    st.info(f"📍 **Lot Tapaga Anda:** {lot_info}")

                new_phone = st.text_input("No. Telefon", value=format_phone_display(str(row.get(COL_PHONE, ""))))
                new_products = st.text_area("Senarai Produk", value=products_text, height=68)
                cs1, cs2 = st.columns(2)
                with cs1:
                    if st.button("💾 Simpan", type="primary", use_container_width=True):
                        conn = st.connection("gsheets", type=GSheetsConnection)
                        df, _ = load_vendors()
                        if df is not None:
                            save_vendor_edit(conn, df, plate_norm, new_phone, new_products)
                            st.success("✅ Berjaya dikemaskini.")
                            time.sleep(1)
                            st.rerun()
                with cs2:
                    p_url = ev_data.get("payment_form_url", "")
                    if p_url: 
                        st.link_button("📤 Upload bukti pembayaran dan pemilihan slot", p_url, use_container_width=True)
    if st.button("Tutup", use_container_width=True): st.rerun()

# ==========================================
# 4. TOP NAVIGATION BAR (MENU PANTAS)
# ==========================================
if st.button("⬅️ Kembali ke Menu Utama"):
    st.switch_page("info_page.py")

nav_col1, nav_col2, nav_col3, nav_col4 = st.columns(4)
with nav_col1:
    if st.button("Pendaftaran Vendor", use_container_width=True):
        components.html("""
            <script>
                const el = window.parent.document.getElementById('daftar-vendor');
                if (el) { el.scrollIntoView({ behavior: 'smooth' }); }
            </script>
        """, height=0)
with nav_col2:
    if st.button("Semak Status", use_container_width=True):
        components.html("""
            <script>
                const el = window.parent.document.getElementById('semak-status');
                if (el) { el.scrollIntoView({ behavior: 'smooth' }); }
            </script>
        """, height=0)
with nav_col3:
    if st.button("Harga & Sewa", use_container_width=True):
        components.html("""
            <script>
                const el = window.parent.document.getElementById('harga-sewa');
                if (el) { el.scrollIntoView({ behavior: 'smooth' }); }
            </script>
        """, height=0)
with nav_col4:
    if st.button("Layout Tapak", use_container_width=True):
        components.html("""
            <script>
                const el = window.parent.document.getElementById('layout-tapak');
                if (el) { el.scrollIntoView({ behavior: 'smooth' }); }
            </script>
        """, height=0)

st.divider()

# ==========================================
# 5. PAPARAN UTAMA & HERO
# ==========================================
st.markdown(f"<h1 style='text-align: center; font-size: 2.8rem;'>{event_name}</h1>", unsafe_allow_html=True)
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
        st.markdown("<h4 style='font-size: 1.5rem; margin-bottom: 0px;'>📌 Maklumat Rasmi Acara</h4>", unsafe_allow_html=True)
        st.markdown("---")
        
        d_col1, d_col2 = st.columns([1, 2])
        with d_col1: st.markdown("<p style='font-size: 1.1rem; font-weight: bold;'>Tarikh Acara:</p>", unsafe_allow_html=True)
        with d_col2: st.markdown(f"<p style='font-size: 1.1rem;'>{event_date_str}</p>", unsafe_allow_html=True)
            
        d_col3, d_col4 = st.columns([1, 2])
        with d_col3: st.markdown("<p style='font-size: 1.1rem; font-weight: bold;'>Masa Operasi:</p>", unsafe_allow_html=True)
        with d_col4: st.markdown(f"<p style='font-size: 1.1rem;'>{event_time_str}</p>", unsafe_allow_html=True)
            
        d_col5, d_col6 = st.columns([1, 2])
        with d_col5: st.markdown("<p style='font-size: 1.1rem; font-weight: bold;'>Lokasi Tapak:</p>", unsafe_allow_html=True)
        with d_col6: st.markdown(f"<p style='font-size: 1.1rem;'>{event_venue_str}</p>", unsafe_allow_html=True)

    sub_col1, sub_col2 = st.columns(2)
    with sub_col1:
        with st.container(border=True):
            try:
                target = datetime(2026, 12, 11, 0, 0, tzinfo=TIMEZONE)
                rem = int((target - datetime.now(TIMEZONE)).total_seconds())
                if rem > 0:
                    d, h = rem // 86400, (rem % 86400) // 3600
                    m, s = (rem % 3600) // 60, rem % 60
                    st.metric("⏳ Countdown Menuju Hari Acara", f"{d} Hari {h} Jam {m} Minit {s} Saat")
                else:
                    st.info("🎉 Acara sedang berlangsung / telah bermula!")
            except Exception:
                st.caption("Tarikh acara tidak sah.")

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

    # BORANG PENDAFTARAN VENDOR
    st.divider()
    st.markdown('<div id="daftar-vendor"></div>', unsafe_allow_html=True)
    st.markdown("<h3 style='font-size: 1.5rem; margin-top: 5px;'>📝 Pendaftaran Vendor</h3>", unsafe_allow_html=True)
    st.caption("Sila klik butang di bawah untuk mendaftar slot perniagaan anda melalui Google Form.")
    st.link_button("Buka Borang Pendaftaran Vendor", form_url, type="primary", use_container_width=True)

st.divider()

# ==========================================
# 6. SEMAK STATUS KELAYAKAN
# ==========================================
st.markdown('<div id="semak-status"></div>', unsafe_allow_html=True)
st.markdown("<h3 style='font-size: 1.8rem;'>🔍 Semak Status Kelayakan</h3>", unsafe_allow_html=True)
st.caption("Masukkan No. Plate kenderaan anda untuk menyemak status permohonan.")

with st.container(border=True):
    with st.form("search_form_detail"):
        query = st.text_input("No. Plate Kenderaan", placeholder="Contoh: NNA1806").strip().upper()
        submitted = st.form_submit_button("Semak Status Kelayakan", type="primary", use_container_width=True)

        st.markdown(f"""
        <div style='text-align: center; font-size: 0.9rem; margin-top: 0.5rem;'>
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

        result = df[normalize_plate(df[COL_PLATE]) == query.replace(" ", "")]
        if result.empty:
            show_not_found_dialog(query)
        else:
            row = result.iloc[0]
            p_col = find_products_column(df)
            l_col = find_lot_column(df)
            
            p_text = clean_text_field(row.get(p_col, "")) if p_col else ""
            l_text = clean_text_field(row.get(l_col, "")) if l_col else ""
            
            show_status_dialog(
                row, 
                query.replace(" ", ""), 
                str(row["Status"]).strip(), 
                bool(row.get("Paid", False)), 
                p_text, 
                l_text
            )

st.divider()

# ==========================================
# 7. HARGA SEWA TAPAK & DEPOSIT
# ==========================================
st.markdown('<div id="harga-sewa"></div>', unsafe_allow_html=True)
st.markdown("<h3 style='font-size: 1.8rem;'>💰 Harga Sewa Tapak & Deposit</h3>", unsafe_allow_html=True)
st.caption("Nota: Deposit dipulangkan selepas acara tamat tertakluk kepada peraturan tapak.")

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
st.markdown("<h3 style='font-size: 1.8rem;'>🗺️ Layout & Zon Tapak Niaga</h3>", unsafe_allow_html=True)
st.caption("Pelan susun atur ruang niaga dan tapak rasmi di perkarangan Penang Ferry Museum.")

with st.container(border=True):
    layout_path = Path("assets/layout.png")
    if layout_path.exists():
        st.image("assets/layout.png", caption="Pelan Susun Atur Tapak PFM Car Boot Sale", use_container_width=True)
    else:
        st.warning("⚠️ Fail gambar `layout.png` tidak dijumpai di dalam folder `assets/`.")

    st.markdown("""
    <div style="background-color: #FFFCF7; padding: 1rem; border-radius: 8px; border: 1px dashed #D97706; margin-top: 10px;">
        <h4 style="color: #78350F; margin-top: 0;">📍 Panduan Zon Tapak PFM</h4>
        <p style="color: #57534e; font-size: 14px;">
            Zon tapak dibahagikan mengikut kategori kenderaan dan perniagaan bagi memastikan aliran trafik pengunjung lancar serta selesa:
        </p>
        <ul style="color: #57534e; font-size: 14px; line-height: 1.6;">
            <li><b>Zon A (Car Boot Sales):</b> Bahagian utama berhampiran pintu masuk muzium (Khas untuk berniaga terus dari bonet kereta).</li>
            <li><b>Zon B (F&B / Makanan & Minuman):</b> Ruang khusus yang mempunyai laluan pengudaraan luas dan kemudahan tapak memasak yang selamat.</li>
            <li><b>Zon C (Food Truck):</b> Lot parkir berturap rata khas untuk trak makanan (*food truck*).</li>
            <li><b>Zon D (Arts, Crafts & Retail):</b> Tapak khemah pameran produk kraftangan, pakaian, dan aksesori.</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)

st.divider()

# ==========================================
# 9. HUBUNGI ADMIN
# ==========================================
st.link_button("📲 Ada Pertanyaan? Hubungi Admin di WhatsApp", whatsapp_admin, use_container_width=True)
