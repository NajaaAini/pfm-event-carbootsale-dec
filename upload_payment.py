import streamlit as st
import pandas as pd
import re
from datetime import datetime
from streamlit_gsheets import GSheetsConnection
from style import apply_style
from components import page_header, load_sheet_safe, upload_payment_proof

st.set_page_config(page_title="Upload Bukti Bayaran", layout="wide")
apply_style()
page_header()

st.title("📤 Upload Bukti Bayaran")
st.caption("Bukti bayaran akan disimpan automatik ke Google Drive.")

COL_NAME = "Nama/Name"
COL_PHONE = "Nombor Telefon/Phone Number"
COL_TYPE = "Kategori Produk/Product Category"
COL_CAT = "F&B CATEGORY"
COL_PLATE = "Plate Number"
COL_ADDON = "ADD ON"
PROOF_COL = "Upload Bukti Bayaran"

def get_category_price(vendor_type):
    try:
        if vendor_type == "Car Boot Sales": return float(st.secrets["event"]["price_car_boot"])
        elif vendor_type == "F&B": return float(st.secrets["event"]["price_fb"])
        elif vendor_type == "Food Truck": return float(st.secrets["event"]["price_ft"])
        else: return float(st.secrets["event"]["price_others"])
    except: return 0.0

def get_deposit(vendor_type):
    try:
        if vendor_type == "F&B": return float(st.secrets["event"]["deposit_fb"])
        elif vendor_type == "Food Truck": return float(st.secrets["event"]["deposit_ft"])
        elif vendor_type == "Arts/Crafts & Others": return float(st.secrets["event"].get("deposit_others", 100))
        return 0.0
    except: return 0.0

def get_addon_price(addon_str):
    if addon_str is None or pd.isna(addon_str): return 0.0
    try:
        matches = re.findall(r"RM\s*([0-9]+(?:\.[0-9]+)?)", str(addon_str))
        return sum(float(m) for m in matches)
    except: return 0.0

def format_rm(amount):
    try: return f"RM {float(amount):,.2f}"
    except: return "RM 0.00"

conn = st.connection("gsheets", type=GSheetsConnection)
df = load_sheet_safe(conn, "Vendors", ttl=0)
if df is None: st.stop()

if "Paid" not in df.columns: df["Paid"] = False
df["Paid"] = df["Paid"].fillna(False).astype(bool)

with st.form("payment_upload", clear_on_submit=False):
    plate_input = st.text_input("No. Pendaftaran Kenderaan / Plate Number", placeholder="Contoh: NNA1806").strip().upper()
    
    uploaded = st.file_uploader("📸 Pilih gambar/fail bukti bayaran", type=["jpg", "jpeg", "png", "pdf"], help="Format: JPG, PNG, PDF. Maks 10MB.")
    st.markdown("---")
    submitted = st.form_submit_button("Hantar Bukti Bayaran", type="primary", use_container_width=True)

if submitted:
    if not plate_input: st.error("Sila masukkan No. Plate."); st.stop()
    if not uploaded: st.error("Sila pilih fail bukti bayaran."); st.stop()
    
    MAX_SIZE_MB = 10
    if (uploaded.size / (1024 * 1024)) > MAX_SIZE_MB:
        st.error(f"Saiz fail terlalu besar. Maksimum {MAX_SIZE_MB} MB."); st.stop()

    normalized_input = plate_input.replace(" ", "").upper()
    matched = df[df[COL_PLATE].astype(str).str.upper().str.replace(" ", "") == normalized_input]

    if matched.empty:
        st.error(f"❌ No. Plate **{plate_input}** tidak dijumpai dalam sistem.")
        st.stop()

    vendor = matched.iloc[0]
    vendor_name = str(vendor.get(COL_NAME, ""))
    status = str(vendor.get("Status", "")).strip().title()
    vendor_type = str(vendor.get(COL_TYPE, "Car Boot Sales")).strip()
    fb_category = str(vendor.get(COL_CAT, "") or "").strip()

    if status == "Cancelled":
        st.warning("⚠️ Rekod anda telah dibatalkan. Sila buat pendaftaran baru melalui butang di bawah.")
        st.link_button("📝 Daftar Sekarang", "https://forms.gle/7eoMCUDyQYRfLA7e8", type="primary", use_container_width=True)
        st.stop()

    if status == "Pending":
        st.warning("⏳ Permohonan masih menunggu semakan. Sila tunggu sehingga diluluskan.")
        st.stop()

    if status == "Rejected":
        st.error("❌ Permohonan tidak berjaya. Sila hubungi admin.")
        st.stop()

    if status != "Approved":
        st.error(f"⚠️ Status tidak dikenali: **{status}**.")
        st.stop()

    st.success(f"✅ Vendor dijumpai: **{vendor_name}**")

    cat_price = get_category_price(vendor_type)
    deposit_amount = get_deposit(vendor_type)
    addon_price = get_addon_price(str(vendor.get(COL_ADDON, "") or ""))
    total_price = cat_price + deposit_amount + addon_price

    if total_price > 0:
        st.markdown(f"""
        <div style='background:#fef9ec; border:2px solid #f0e6d6; border-radius:12px; padding:1.5rem 1.75rem; margin:1rem 0 0.75rem 0;'>
            <div style='font-size:0.8rem; color:#78716c; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:0.5rem;'>💰 Jumlah Perlu Dibayar</div>
            <div style='font-size:2.25rem; font-weight:700; color:#78350f; margin-bottom:0.75rem; line-height:1;'>{format_rm(total_price)}</div>
        </div>
        """, unsafe_allow_html=True)

    existing_payments = load_sheet_safe(conn, "Payments", ttl=0)
    if existing_payments is None or existing_payments.empty:
        existing_payments = pd.DataFrame(columns=["Timestamp", "Plate Number", PROOF_COL, "FolderUrl"])

    # AUTO-REPLACE
    if not existing_payments.empty:
        existing_payments = existing_payments[
            existing_payments["Plate Number"].astype(str).str.upper().str.replace(" ", "") != normalized_input
        ]

    with st.spinner("Menghantar ke Google Drive..."):
        try: parent_folder_id = st.secrets["event"]["payment_proof_folder_id"]
        except: st.error("Konfigurasi folder Drive tidak dijumpai."); st.stop()

        file_id, view_url, folder_url = upload_payment_proof(
            file_bytes=uploaded.getvalue(),
            plate=plate_input,
            vendor_type=vendor_type,
            fb_category=fb_category,
            parent_folder_id=parent_folder_id,
            mime_type=uploaded.type or "image/jpeg",
        )

    if not view_url:
        st.error("Gagal upload ke Google Drive.")
        st.stop()

    new_row = pd.DataFrame([{
        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Plate Number": plate_input,
        PROOF_COL: view_url,
        "FolderUrl": folder_url,
    }])
    
    updated_payments = pd.concat([existing_payments, new_row], ignore_index=True)

    try:
        conn.update(worksheet="Payments", data=updated_payments)
        st.success("💾 Rekod pembayaran berjaya disimpan. Rekod lama (jika ada) telah diganti.")
    except Exception as e:
        st.warning(f"Fail berjaya diupload, tetapi rekod gagal disimpan. (Error: {e})")

    st.markdown("---")
    st.markdown("### ✅ Bukti Bayaran Berjaya Dihantar")
    st.markdown(f"**Vendor:** {vendor_name}  \n**No. Plate:** `{plate_input}`  \n**Fail:** [Lihat Bukti]({view_url})")
    st.info("Admin akan semak bukti bayaran anda. Sila sertai WhatsApp Group untuk update terkini.")
    st.balloons()