# ============================================================
# streamlit_app.py — PFM PORTAL (SECRETS MULTI-EVENT)
# ============================================================
import streamlit as st
from style import apply_style

st.set_page_config(page_title="PFM Portal", layout="wide", initial_sidebar_state="expanded")
apply_style()

is_admin = st.session_state.get("is_admin", False)

# ============================================================
# 1. DAFTAR PAGES
# ============================================================
info_page = st.Page("info_page.py", title="Pendaftaran Vendor", default=True)

# Halaman detail acara: disembunyikan dari sidebar.
# Streamlit terkini  -> guna visibility="hidden".
# Streamlit lama     -> daftar biasa, menu sidebar dibina sendiri (lihat bawah).
HIDDEN_PAGE_SUPPORTED = True
try:
    event_detail_page = st.Page(
        "event_detail.py",
        title="Maklumat Acara & Semak Status",
        visibility="hidden",
    )
except TypeError:
    HIDDEN_PAGE_SUPPORTED = False
    event_detail_page = st.Page("event_detail.py", title="Maklumat Acara & Semak Status")

# Admin Pages
admin_dash = st.Page("admin_dashboard.py", title="1 - Dashboard")
admin_slots = st.Page("admin_slots.py", title="2 - Slot")
admin_list = st.Page("admin_list.py", title="3 - Senarai Vendor")
admin_pages = [admin_dash, admin_slots, admin_list]

# ============================================================
# 2. NAVIGASI
# ============================================================
custom_menu = False

if HIDDEN_PAGE_SUPPORTED:
    pages = {"Menu Utama": [info_page, event_detail_page]}
    if is_admin:
        pages["Admin Panel"] = admin_pages
    pg = st.navigation(pages)
else:
    flat_pages = [info_page, event_detail_page] + (admin_pages if is_admin else [])
    try:
        # Sembunyikan menu automatik, menu dibina sendiri dalam sidebar
        pg = st.navigation(flat_pages, position="hidden")
        custom_menu = True
    except TypeError:
        # Streamlit terlalu lama: semua halaman akan kelihatan. Sila naik taraf Streamlit.
        pg = st.navigation(flat_pages)

# ============================================================
# 3. SIDEBAR (MENU, PILIHAN EVENT DARI SECRETS & ADMIN LOGIN)
# ============================================
with st.sidebar:
    
# ============================================================
# SIDEBAR — BRANDED HEADER + LOGIN
# ============================================================
def _image_base64(image_path):
    path = Path(image_path)
    if not path.exists():
        return None
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


with st.sidebar:

    # --- Brand header dengan icon PFM ---
    logo_b64 = _image_base64("assets/icon.jpg")

    if logo_b64:
        st.markdown(f"""
        <div style="
            text-align: center;
            padding: 1.25rem 0.5rem 1.25rem 0.5rem;
            border-bottom: 1px solid #e8dcc7;
            margin-bottom: 1.5rem;
        ">
            <img src="data:image/jpeg;base64,{logo_b64}" style="
                width: 90px;
                height: 90px;
                object-fit: contain;
                margin-bottom: 0.75rem;
                border-radius: 12px;
            ">
            <h3 style="
                color: #292524 !important;
                margin: 0;
                font-size: 1rem;
                font-weight: 700;
                letter-spacing: 1px;
            ">PFM CAR BOOT SALE</h3>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="
            text-align: center;
            padding: 1.25rem 0.5rem 1.25rem 0.5rem;
            border-bottom: 1px solid #e8dcc7;
            margin-bottom: 1.5rem;
        ">
            <div style="
                width: 56px;
                height: 56px;
                background-color: #f2ebe0;
                border-radius: 12px;
                margin: 0 auto 0.75rem auto;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 1.75rem;
            ">🎪</div>
            <h3 style="
                color: #292524 !important;
                margin: 0;
                font-size: 1rem;
                font-weight: 700;
                letter-spacing: 1px;
            ">PFM CAR BOOT SALE</h3>
        </div>
        """, unsafe_allow_html=True)
    
    if custom_menu:
        st.page_link(info_page, label="Pendaftaran Vendor")
        if is_admin:
            st.page_link(admin_dash, label="1 - Dashboard")
            st.page_link(admin_slots, label="2 - Slot")
            st.page_link(admin_list, label="3 - Senarai Vendor")
        st.markdown("---")

    if is_admin:
        st.markdown("### 🎯 Pilih Event Aktif")

        # Ambil senarai event daripada secrets.toml secara dinamik
        event_keys = sorted(k for k in st.secrets.keys() if k.startswith("event_"))

        if event_keys:
            event_options = {st.secrets[k]["name"]: k for k in event_keys}
            selected_event_name = st.selectbox(
                "Pilih event untuk diuruskan:",
                options=list(event_options.keys()),
                key="sidebar_event_select",
            )

            selected_key = event_options[selected_event_name]
            # Simpan dalam session state supaya page admin boleh baca
            st.session_state["active_event"] = dict(st.secrets[selected_key])
            st.session_state["active_event_name"] = selected_event_name
        else:
            st.warning("Tiada konfigurasi event dijumpai dalam secrets.toml")
            st.session_state["active_event"] = {}
            st.session_state["active_event_name"] = "Default Event"

        st.markdown("---")
    else:
        # Untuk pengguna biasa/public, tetapkan default ke event_1 secara automatik
        if "active_event" not in st.session_state:
            event_keys = [k for k in st.secrets.keys() if k.startswith("event_")]
            if event_keys:
                first_key = sorted(event_keys)[0]
                st.session_state["active_event"] = dict(st.secrets[first_key])
                st.session_state["active_event_name"] = st.secrets[first_key]["name"]
            else:
                st.session_state["active_event"] = {}
                st.session_state["active_event_name"] = "Default Event"

    st.markdown("### 🔐 Admin Access")

    if not is_admin:
        pwd = st.text_input("Kata Laluan", type="password", key="sidebar_pwd", placeholder="Masukkan kata laluan")
        if st.button("Log Masuk", type="primary", use_container_width=True):
            if pwd == st.secrets["admin"]["password"]:
                st.session_state.is_admin = True
                st.session_state.admin_name = "Admin"
                st.rerun()
            else:
                st.error("❌ Kata laluan salah")
    else:
        st.success(f"Admin: {st.session_state.get('admin_name', 'Admin')}")
        if st.button("Log Keluar", use_container_width=True):
            st.session_state.is_admin = False
            st.session_state.admin_name = "Admin"
            st.rerun()

        st.markdown("---")
        try:
            # Ambil link Google Sheet mengikut event yang sedang dipilih
            active_sheet_url = (
                st.session_state.get("active_event", {}).get("sheet_url")
                or st.secrets.get("connections", {}).get("gsheets", {}).get("spreadsheet", "")
            )
            if active_sheet_url:
                st.link_button("📊 Buka Google Sheet", active_sheet_url, use_container_width=True)
        except Exception:
            pass

# ============================================================
# 4. JALANKAN HALAMAN
# ============================================================
pg.run()
