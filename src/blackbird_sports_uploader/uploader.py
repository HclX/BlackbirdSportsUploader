import zipfile
import requests
import io
from .config import settings
from .logger import setup_logging

logger = setup_logging(__name__)


def compress_xml(xml_content: str, record_id: str) -> bytes:
    """
    Compresses the XML content into a ZIP file.

    Args:
        xml_content: The XML string to compress.
        record_id: The record ID used for the filename.

    Returns:
        Bytes of the ZIP file.
    """
    logger.debug(f"Compressing XML for record {record_id}")
    filename = f"sportRecord_{record_id}.xml"

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr(filename, xml_content)

    return zip_buffer.getvalue()


def upload_record(
    token: str,
    zip_data: bytes,
    record_id: str,
    fittime: str,
) -> bool:
    """
    Upload the compressed record to the server.

    Args:
        token: Session token.
        zip_data: Compressed XML record.
        record_id: Local record ID (timestamp string).
        fittime: FIT timestamp string (ms).

    Returns:
        True if upload successful, False otherwise.
    """
    url = f"{settings.BASE_URL}/bk_uploadRecord"

    logger.info(f"Uploading record {record_id} (fittime={fittime})")

    files = {
        "RecordFile": (f"sportRecord_{record_id}.zip", zip_data, "application/zip")
    }

    params = {
        "ton": token,
        "deviceType": settings.DEVICE_TYPE,
        "sn": settings.DEVICE_SN,
        "fittime": fittime,
        "localRecordId": record_id,
    }

    headers = {
        "User-Agent": settings.USER_AGENT
    }

    try:
        response = requests.post(
            url, files=files, params=params, headers=headers, timeout=30
        )
        result = response.json()
        if result.get("status") != "ok":
            error_msg = result.get("msg", "Unknown error")
            logger.error(f"Upload failed: {error_msg}. Response: {result}")
            return False
        logger.info(f"Upload successful for record {record_id}")
        return True
    except requests.RequestException as e:
        logger.error(f"Network error during upload: {e}")
        return False
