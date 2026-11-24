import streamlit as st
import base64
import io
import re
import pandas as pd
from pathlib import Path
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# ==========================================
# FUNGSI BAHARU: MULTI-EVENT DROPDOWN
# ==========================================
def get_active_event():
    """
    Fungsi untuk papar dropdown event di sidebar dan pulangkan 
    konfigurasi event yang sedang aktif.
    """
    # Senarai event (untuk dropdown). 
    # Pastikan 'event_1' sepadan dengan blok dalam secrets.toml
    EVENTS = {
        "Event 1: School Holiday (Dis 2026)": "event_1",
        # Buka comment di bawah bila Event 2 & 3 dah siap
        # "Event 2: Xmas (Dis 2026)": "event_2",
        # "Event 3: New Year (Jan 2027)": "event_3",
    }
    
    # Papar dropdown di sidebar
    selected_event_name = st.sidebar.selectbox(
        "🎯 Pilih Event Aktif:", 
        list(EVENTS.keys()),
        key="event_selector"
    )
    
    event_key = EVENTS[selected_event_name]
    
    # Simpan dalam session_state supaya page lain boleh baca
    st.session_state['active_event_key'] = event_key
    
    # Semak kewujudan event dalam secrets untuk elak KeyError
    if event_key not in st.secrets:
        st.error(f"❌ Konfigurasi `[{event_key}]` tiada dalam `secrets.toml`. Sila tambah konfigurasi.")
        st.stop()
        
    active_event = dict(st.secrets[event_key])
    
    # Masukkan default values untuk field optional supaya tak crash
    defaults = {
        "deposit_others": 100,
        "payment_proof_folder_id": "",
        "google_form_responses_url": "",
        "sheet_url": "",
        "whatsapp_group": "",
        "previous_sheet_url": "",
    }
    for k, v in defaults.items():
        active_event.setdefault(k, v)

    return active_event, selected_event_name


# ==========================================
# FUNGSI ASAL (TIDAK DIUBAH)
# ==========================================
def _image_base64(image_path):
    path = Path(image_path)
    if not path.exists():
        return None
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

def page_header(title="", subtitle="", image_path="assets/headerpfm.jpeg"):
    img_b64 = _image_base64(image_path)
    if img_b64:
        st.markdown(f"""
        <div style="
            overflow: hidden; margin-bottom: 2rem; height: 320px;
            background-image: url('data:image/jpeg;base64,{img_b64}');
            background-size: cover; background-position: center;
            margin-left: -1rem; margin-right: -1rem; margin-top: -1rem;
        "></div>
        """, unsafe_allow_html=True)

def load_sheet_safe(conn, worksheet_name, ttl=60, spreadsheet_url=None):
    try:
        if spreadsheet_url:
            return conn.read(worksheet=worksheet_name, ttl=ttl, spreadsheet=spreadsheet_url)
        return conn.read(worksheet=worksheet_name, ttl=ttl)
    except Exception as e:
        st.error(f"Gagal memuatkan data dari {worksheet_name}: {e}")
        return None

def log_action(conn, admin_name, action, plate, details=""):
    try:
        logs = conn.read(worksheet="Log", ttl=0)
        if logs is None or logs.empty:
            logs = pd.DataFrame(columns=["Timestamp", "Admin", "Action", "Plate", "Details"])
    except Exception:
        logs = pd.DataFrame(columns=["Timestamp", "Admin", "Action", "Plate", "Details"])

    new_log = pd.DataFrame([{
        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Admin": admin_name, "Action": action, "Plate": plate, "Details": details,
    }])
    updated = pd.concat([logs, new_log], ignore_index=True)
    try:
        conn.update(worksheet="Log", data=updated)
    except Exception:
        pass

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
FOLDER_MIME = "application/vnd.google-apps.folder"

def _get_drive_service():
    info = dict(st.secrets["connections"]["gsheets"])
    creds_dict = info.get("credentials") or info
    creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=DRIVE_SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)

def _sanitize(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]', "-", str(name)).strip()
    return name or "UNKNOWN"

def _get_or_create_folder(service, parent_id: str, folder_name: str) -> str:
    folder_name = _sanitize(folder_name)
    query = f"'{parent_id}' in parents and name = '{folder_name}' and mimeType = '{FOLDER_MIME}' and trashed = false"
    res = service.files().list(q=query, fields="files(id)").execute()
    files = res.get("files", [])
    if files:
        return files[0]["id"]
    meta = {"name": folder_name, "mimeType": FOLDER_MIME, "parents": [parent_id]}
    return service.files().create(body=meta, fields="id").execute()["id"]

def upload_payment_proof(file_bytes, plate, vendor_type, fb_category="", parent_folder_id="", mime_type="image/jpeg"):
    try:
        service = _get_drive_service()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        ext = "jpg"
        if mime_type:
            ext = mime_type.split("/")[-1].lower()
            if ext in ("jpeg", "jpg"): ext = "jpg"

        safe_plate = _sanitize(plate).upper().replace(" ", "")
        filename = f"{safe_plate}_{timestamp}.{ext}"

        if vendor_type == "F&B":
            fb_root = _get_or_create_folder(service, parent_folder_id, "F&B")
            target_folder = _get_or_create_folder(service, fb_root, fb_category or "Uncategorized")
        elif vendor_type == "Car Boot Sales":
            target_folder = _get_or_create_folder(service, parent_folder_id, "Car Boot Sales")
        else:
            target_folder = _get_or_create_folder(service, parent_folder_id, "Others")

        file_metadata = {"name": filename, "parents": [target_folder]}
        media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type, resumable=False)
        file = service.files().create(body=file_metadata, media_body=media, fields="id, webViewLink").execute()

        try:
            service.permissions().create(fileId=file["id"], body={"role": "reader", "type": "anyone"}).execute()
        except Exception:
            pass

        folder_url = f"https://drive.google.com/drive/folders/{target_folder}"
        return file["id"], file["webViewLink"], folder_url
    except Exception as e:
        st.error(f"Gagal upload ke Google Drive: {e}")
        return None, None, None
    
def load_previous_sheet(worksheet="Vendors", ttl=0):
    """Fungsi khas untuk baca Google Sheet event LEPAS"""
    try:
        import gspread
        from gspread_dataframe import get_as_dataframe
        
        # ✅ DIBETULKAN: Ambil dari active_event_key (Multi-Event)
        event_key = st.session_state.get('active_event_key', 'event_1')
        
        if event_key not in st.secrets:
            return None, f"Konfigurasi [{event_key}] tiada dalam secrets.toml"

        prev_url = st.secrets[event_key].get("previous_sheet_url", "")
        
        if not prev_url:
            return None, "Link 'previous_sheet_url' tiada dalam secrets.toml"

        # Guna kredential dari secrets yang sama
        info = dict(st.secrets["connections"]["gsheets"])
        creds_dict = info.get("credentials") or info
        
        SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        
        # Sambung ke Google Sheet lama
        client = gspread.authorize(creds)
        sheet = client.open_by_url(prev_url)
        worksheet_data = sheet.worksheet(worksheet)
        
        df = get_as_dataframe(worksheet_data, evaluate_formulas=True)
        df = df.dropna(how="all") # Buang baris kosong
        return df, None
        
    except Exception as e:
        return None, str(e)
