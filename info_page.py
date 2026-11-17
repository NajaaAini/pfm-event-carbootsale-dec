from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st
import streamlit.components.v1 as components

from style import apply_style
from components import page_header

# ==========================================
# 1. PAGE CONFIG
# ==========================================

st.set_page_config(
    page_title="PFM | Pendaftaran & Maklumat Acara",
    page_icon="🛍️",
    layout="wide",
)

apply_style()
page_header()

# ==========================================
# 2. CONFIGURATION & HELPERS
# ==========================================

MAP_URL = "https://www.google.com/maps/search/?api=1&query=Penang+Ferry+Museum"
MAP_EMBED_URL = "https://www.google.com/maps?q=Penang+Ferry+Museum&output=embed"
WHATSAPP_URL = (
    "https://wa.me/601157727459?"
    "text=Hi%20Admin,%20saya%20nak%20tanya%20pasal%20PFM%20Car%20Boot%20Sale"
)

TIMEZONE = ZoneInfo("Asia/Kuala_Lumpur")
TODAY = datetime.now(TIMEZONE).date()

MONTHS_MS = [
    "Januari", "Februari", "Mac", "April", "Mei", "Jun",
    "Julai", "Ogos", "September", "Oktober", "November", "Disember",
]

# Tarikh pendaftaran dibuka jika `reg_open_date` tiada dalam secrets.toml.
# Index 0 = event pertama (sentiasa dibuka).
FALLBACK_OPEN_DATES = {1: "2026-11-23", 2: "2026-11-26"}

STATUS_BADGES = {
    "open": ("🟢 Pendaftaran dibuka", "green"),
    "soon": ("🟡 Akan datang", "orange"),
    "closed": ("⚪ Acara selesai", "gray"),
}


def parse_date(value):
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def format_date(d, raw="TBA"):
    return f"{d.day} {MONTHS_MS[d.month - 1]} {d.year}" if d else str(raw)


def build_events():
    keys = sorted(k for k in st.secrets.keys() if k.startswith("event_"))
    events = []
    for idx, key in enumerate(keys):
        data = st.secrets[key]
        event_date = parse_date(data.get("event_date"))
        open_date = parse_date(data.get("reg_open_date", FALLBACK_OPEN_DATES.get(idx)))

        if event_date and TODAY > event_date:
            status, note = "closed", "Pendaftaran telah ditutup"
        elif open_date and TODAY < open_date:
            # Buang paparan tarikh buka untuk event selain event pertama (cth: Christmas & New Year)
            if idx == 0:
                status, note = "soon", f"Pendaftaran dibuka: {format_date(open_date)}"
            else:
                status, note = "soon", "Pendaftaran akan dibuka tidak lama lagi"
        else:
            status, note = "open", "Pendaftaran kini dibuka"

        # Hanya event_1 (School Holiday) aktif buat masa ini.
        # Untuk aktifkan event lain, letak `active = true` dalam secrets.toml.
        active = bool(data.get("active", key == "event_1"))
        if not active and status == "open":
            status, note = "soon", "Maklumat akan diumumkan"

        events.append({
            "key": key,
            "active": active,
            "name": data.get("name", "Event PFM"),
            "date_obj": event_date,
            "date_text": format_date(event_date, data.get("event_date", "TBA")),
            "status": status,
            "note": note,
        })
    return events


events_list = build_events()


# ==========================================
# 3. ADVANCED STYLING (TERMASUK BACKGROUND CBSSH.PNG)
# ==========================================

st.markdown("""
<style>
.stApp { background-color: #FFF8ED; }
.block-container { max-width: 900px; padding-top: 0.8rem; padding-bottom: 2rem; }
h1 { font-size: 26px !important; color: #292524 !important; font-weight: 750 !important; }
h2 { font-size: 21px !important; color: #78350F !important; font-weight: 700 !important; }
h3 { font-size: 16px !important; color: #78350F !important; font-weight: 700 !important; }
p { font-size: 13px; color: #57534e; }
div[data-testid="stVerticalBlock"] { gap: 0.55rem; }
div[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 12px; border-color: #E8DCC7; background-color: #FFFCF7; }

.custom-event-card {
    background-color: #FFFCF7;
    border: 1.5px solid #E8DCC7;
    border-radius: 14px;
    padding: 1.5rem;
    margin-bottom: 0.5rem;
    transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
    box-shadow: 0 4px 6px -1px rgba(120, 53, 15, 0.05);
}

/* Latar belakang imej cbssh.png khusus untuk kad pertama (School Holiday) */
.card-school-holiday {
    background-image: linear-gradient(rgba(255, 252, 247, 0.92), rgba(255, 252, 247, 0.92)), url('app/static/cbssh.png');
    background-size: cover;
    background-position: center;
    border: 1.5px solid #D97706;
}

.custom-event-card:hover {
    transform: translateY(-4px);
    border-color: #D97706;
    box-shadow: 0 10px 18px -3px rgba(120, 53, 15, 0.12);
}
@media (max-width: 768px) { .block-container { padding-left: 0.8rem; padding-right: 0.8rem; } }
</style>
""", unsafe_allow_html=True)


# ==========================================
# 4. HERO
# ==========================================

with st.container(border=True):
    st.header("🛍️ Pendaftaran Vendor PFM", anchor=False)
    st.write("Jom berniaga bersama PFM. Daftar sebagai vendor dan pilih ruang niaga anda.")
    st.write("**Slot adalah terhad.**")
    st.success("🎉 Pendaftaran PFM Mega Car Boot Sale X School Holiday kini dibuka !")

# ==========================================
# 5. COUNTDOWN ACARA SETERUSNYA
# ==========================================

st.divider()
st.subheader("⏳ Acara Seterusnya", anchor=False)

upcoming = sorted(
    (e for e in events_list if e["date_obj"] and e["date_obj"] >= TODAY),
    key=lambda e: e["date_obj"],
)

if upcoming:
    nxt = upcoming[0]
    days_left = (nxt["date_obj"] - TODAY).days
    if days_left == 0:
        st.success(f"🎊 {nxt['name']} berlangsung hari ini.")
    else:
        st.metric(nxt["name"], f"{days_left} hari lagi")
        st.caption(f"📅 Tarikh acara: {nxt['date_text']}")
elif events_list:
    st.info("Semua acara telah selesai. Nantikan acara PFM yang seterusnya.")
else:
    st.info("Tiada acara dijumpai. Sila semak konfigurasi secrets.toml.")

# ==========================================
# 6. TERMA & SYARAT
# ==========================================

st.divider()
st.subheader("📌 Terma & Syarat", anchor=False)
st.caption("Sila baca peraturan dan syarat kami sebelum membuat pendaftaran.")

with st.container(border=True):
    st.markdown("**Peraturan & Syarat Vendor PFM**")
    st.caption("Muat turun dokumen syarat vendor untuk rujukan anda sebelum mendaftar.")
    pdf_path = Path("assets/rules.pdf")
    if pdf_path.exists():
        st.download_button(
            label="📥 Muat turun terma & syarat",
            data=pdf_path.read_bytes(),
            file_name="PFM_Terma_dan_Syarat_Vendor.pdf",
            mime="application/pdf",
            type="primary",
            use_container_width=True,
        )
    else:
        st.warning("⚠️ Fail rules.pdf tidak dijumpai dalam folder assets.")

# ==========================================
# 7. SENARAI ACARA (DISUSUN KE BAWAH DENGAN BACKGROUND IMAGE)
# ==========================================

import base64

def get_base64_image(image_path):
    try:
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    except Exception:
        return ""

bg_image_base64 = ""
img_path = Path("assets/cbssh.png")
if img_path.exists():
    bg_image_base64 = get_base64_image(img_path)

st.divider()
st.subheader("🗓️ Senarai Acara", anchor=False)
st.caption("Pilih acara untuk melihat maklumat lanjut, countdown dan semak status pendaftaran.")

if events_list:
    for idx, ev in enumerate(events_list):
        
        card_style = "padding: 1.5rem; border-radius: 12px; border: 1.5px solid #E8DCC7; margin-bottom: 0.5rem;"
        if idx == 0 and bg_image_base64:
            card_style = f"""
                padding: 1.5rem; 
                border-radius: 12px; 
                border: 1.5px solid #D97706; 
                margin-bottom: 0.5rem;
                background-image: linear-gradient(rgba(255, 252, 247, 0.88), rgba(255, 252, 247, 0.88)), url('data:image/png;base64,{bg_image_base64}');
                background-size: cover;
                background-position: center 2%;
            """
        else:
            card_style += " background-color: #FFFCF7;"

        with st.container(border=True):
            st.markdown(f"""
            <div style="{card_style}">
                <div style="font-size: 11px; font-weight: 700; margin-bottom: 8px;">
                    { '🟢 Pendaftaran dibuka' if ev['status'] == 'open' else ('🟡 Akan datang' if ev['status'] == 'soon' else '⚪ Acara selesai') }
                </div>
                <div style="font-size: 18px; font-weight: 700; color: #292524; margin-bottom: 8px;">{ev['name']}</div>
                <div style="font-size: 14px; color: #78716c; margin-bottom: 2px;">📅 Tarikh acara</div>
                <div style="font-size: 14px; font-weight: 700; color: #292524; margin-bottom: 8px;">{ev['date_text']}</div>
                <div style="font-size: 14px; color: #b45309; font-weight: 600; margin-bottom: 10px;">{ev['note']}</div>
                <div style="font-size: 12px; color: #57534e; margin-bottom: 5px;">
                    { 'Klik butang untuk pendaftaran dan semak kelayakan.' if ev['active'] else 'Maklumat pendaftaran akan diumumkan.' }
                </div>
            </div>
            """, unsafe_allow_html=True)

            if st.button(
                "Daftar dan Semak Status" if ev["active"] else "🔒 Akan datang",
                key=f"btn_info_{ev['key']}",
                disabled=not ev["active"],
                use_container_width=True,
                type="primary" if ev["active"] else "secondary",
            ):
                st.query_params.clear()
                st.query_params["event"] = ev["key"]
                st.switch_page("event_detail.py")
        
        st.write("")

# ==========================================
# 8. LOKASI
# ==========================================

st.divider()
st.subheader("📍 Lokasi Acara", anchor=False)

with st.container(border=True):
    st.markdown("**🏛️ Penang Ferry Museum**")
    st.caption("Perkarangan Penang Ferry Museum")
    components.iframe(MAP_EMBED_URL, height=300, scrolling=False)
    st.link_button("🗺️ Buka lokasi di Google Maps", MAP_URL, use_container_width=True)

# ==========================================
# 9. CARA PENDAFTARAN
# ==========================================

st.divider()
st.subheader("📝 Cara Pendaftaran", anchor=False)
st.caption("Ikuti langkah berikut untuk menjadi vendor PFM.")

steps = [
    ("Baca terma & syarat", "Fahami semua peraturan dan syarat yang ditetapkan oleh pihak PFM."),
    ("Klik maklumat lanjut", "Pilih acara di atas untuk melihat butiran lengkap dan menyemak status."),
    ("Lengkapkan borang pendaftaran", "Isi semua maklumat dengan tepat di Google Form."),
    ("Tunggu kelulusan admin", "Semak status permohonan anda di halaman khusus acara tersebut."),
    ("Buat pembayaran", "Selepas diluluskan, teruskan pembayaran dan pilih lot pilihan anda."),
    ("Pengesahan pembayaran", "Pihak admin akan menyemak dan mengesahkan pembayaran anda."),
    ("Sertai group WhatsApp", "Sertai kumpulan WhatsApp rasmi untuk pengumuman terkini."),
]

with st.container(border=True):
    for number, (title, description) in enumerate(steps, start=1):
        st.markdown(f"**{number}. {title}**")
        st.caption(description)

# ==========================================
# 10. HUBUNGI ADMIN
# ==========================================

st.divider()
st.subheader("💬 Perlukan Bantuan?", anchor=False)

with st.container(border=True):
    st.markdown("**Hubungi admin PFM**")
    st.link_button("📲 WhatsApp admin", WHATSAPP_URL, type="primary", use_container_width=True)
