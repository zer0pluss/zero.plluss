import io
import json
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

SCOPES = ["https://www.googleapis.com/auth/drive"]
ROOT_NAME = "ZERO Advertising"


def _credentials():
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON غير موجود.")
    try:
        info = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON غير صالح.") from exc
    return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)


def service():
    return build("drive", "v3", credentials=_credentials(), cache_discovery=False)


def _find_or_create(svc, name, parent_id=None):
    q = "name = %s and mimeType = 'application/vnd.google-apps.folder' and trashed = false" % repr(name)
    # Use query parameters safely instead of interpolation.
    q = "name = '%s' and mimeType = 'application/vnd.google-apps.folder' and trashed = false" % name.replace("'", "\\'")
    if parent_id:
        q += " and '%s' in parents" % parent_id
    found = svc.files().list(q=q, spaces="drive", fields="files(id,name)", pageSize=10).execute().get("files", [])
    if found:
        return found[0]["id"]
    body = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        body["parents"] = [parent_id]
    return svc.files().create(body=body, fields="id").execute()["id"]


def folder_tree():
    svc = service()
    root = _find_or_create(svc, ROOT_NAME)
    daily_orders = _find_or_create(svc, "Daily Orders", root)
    daily_data = _find_or_create(svc, "Daily Data", root)
    backups = _find_or_create(svc, "Backups", root)
    return svc, root, daily_orders, daily_data, backups


def month_folder(parent, year: int, month: int):
    svc = parent[0]
    year_id = _find_or_create(svc, str(year), parent[1])
    month_id = _find_or_create(svc, f"{month:02d}", year_id)
    return month_id


def upload_or_update(data: bytes, filename: str, mime_type: str, parent_id: str):
    svc = service()
    q = "name = '%s' and '%s' in parents and trashed = false" % (filename.replace("'", "\\'"), parent_id)
    files = svc.files().list(q=q, spaces="drive", fields="files(id,name)", pageSize=10).execute().get("files", [])
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime_type, resumable=False)
    if files:
        file_id = files[0]["id"]
        svc.files().update(fileId=file_id, media_body=media).execute()
        return file_id
    meta = {"name": filename, "parents": [parent_id]}
    return svc.files().create(body=meta, media_body=media, fields="id").execute()["id"]


def upload_daily(pdf_bytes: bytes, json_bytes: bytes, year: int, month: int, pdf_name: str, json_name: str):
    svc, root, daily_orders, daily_data, backups = folder_tree()
    orders_month = month_folder((svc, daily_orders), year, month)
    data_month = month_folder((svc, daily_data), year, month)
    p1 = upload_or_update(pdf_bytes, pdf_name, "application/pdf", orders_month)
    p2 = upload_or_update(json_bytes, json_name, "application/json", data_month)
    return p1, p2


def upload_db_snapshot(data: bytes, filename: str):
    svc, root, daily_orders, daily_data, backups = folder_tree()
    return upload_or_update(data, filename, "application/octet-stream", backups)


def status():
    try:
        folder_tree()
        return True, "Google Drive متصل"
    except Exception as exc:
        return False, str(exc)
