import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Set, Tuple, Optional

from .auth import get_session, save_session, authenticate, get_user_info, SessionData
from .fit_processor import FitProcessor
from .uploader import compress_xml, upload_record
from .config import settings
from .logger import setup_logging
from . import bb16

# Setup logger for main module
logger = setup_logging("main")

def get_beijing_time(timestamp_ms: int) -> datetime:
    """Convert UTC timestamp (ms) to Beijing Time (UTC+8)."""
    utc_dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    beijing_tz = timezone(timedelta(hours=8))
    return utc_dt.astimezone(beijing_tz)


def generate_params(timestamp_ms: int) -> Tuple[str, str]:
    """
    Generate localRecordId and fittime based on DeviceThreeUtil logic.
    Formula: ((j + 28800000) - 631065600000L) / 1000
    j is the UTC timestamp of the record time (derived from parsing logic).
    """
    # 1. localRecordId is the string representation in Beijing Time (likely)
    beijing_dt = get_beijing_time(timestamp_ms)
    local_record_id = beijing_dt.strftime("%Y%m%d%H%M%S")

    # 2. fittime calculation
    # DeviceThreeUtil adds 28800000 (8h) to the input timestamp, then subtracts epoch.
    # This implies the input 'j' is UTC, and we want seconds since 1989 in Beijing Time.
    fittime = int((timestamp_ms + 28800000 - 631065600000) / 1000)

    return local_record_id, str(fittime)


def load_history() -> Set[str]:
    """Load upload history from file."""
    if settings.UPLOAD_HISTORY_FILE.exists():
        try:
            with open(settings.UPLOAD_HISTORY_FILE, "r") as f:
                return set(json.load(f))
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load history: {e}")
            return set()
    return set()


def save_history(history: Set[str]) -> None:
    """Save upload history to file."""
    try:
        with open(settings.UPLOAD_HISTORY_FILE, "w") as f:
            json.dump(sorted(history), f, indent=4)
    except IOError as e:
        logger.error(f"Failed to save history: {e}")

def verify_session() -> Optional[SessionData]:
    token = None
    session = get_session()

    if session:
        token = session.token

        # Try to verify session by getting user info
        try:
            info_data = get_user_info(token, session.accountId, session.cookies)
            logger.info(f"User Info retrieved successfully: {info_data}")
        except Exception:
            logger.error("Failed to get info, will re-authenticate")
            session = None

    if not session:
        # Try auto-login if credentials are provided
        if None in (settings.BB_USERNAME, settings.BB_PASSWORD):
            logger.error("No active session found. Please login first.")
            return None

        logger.info("No active session found. Attempting auto-login...")
        # authenticate returns a tuple: (cookies, account_id, ton)
        cookies, account_id, token = authenticate(settings.BB_USERNAME, settings.BB_PASSWORD, token)
        save_session(token, settings.BB_USERNAME, account_id, cookies)
        # Reload session to get the SessionData object
        session = get_session()
        logger.info("Auto-login successful.")

    return session

async def do_sync(session: SessionData) -> bool:
    """
    Synchronizing data from device to server
    return True if sync is successful, False otherwise
    """
    if not await bb16.download():
        return False

    history = load_history()
    new_files = [f for f in settings.DATA_DIR.glob("*.fit") if f.name not in history]
    logger.info(f"Found {len(new_files)} new records.")

    account_id = int(session.accountId)
    for f in new_files:
        logger.info(f"Processing {f.name}...")
        try:
            processor = FitProcessor(str(f), account_id)
            processor.parse()
            xml_content = processor.generate_xml()
            timestamp_ms = int(processor.start_time)
                        
            record_id, fittime = generate_params(timestamp_ms)
            zip_data = compress_xml(xml_content, record_id)
        except Exception as e:
            logger.error(f'Error processing {f.name}: {e}')
            continue

        logger.info(f"Uploading {f.name} (ID: {record_id})...")
        # upload_record is synchronous (requests). That's fine for now, 
        # or we could make it async later.
        if not upload_record(session.token, zip_data, record_id, fittime):
            logger.error(f"Failed to upload {f.name}")
            continue

        logger.info(f"Upload successful: {f.name}")
        history.add(f.name)
        save_history(history)

    logger.info("All records processed.")
    return True

async def main():
    logger.info("Starting Blackbird Sports Uploader...")
    session = verify_session()
    if not session:
        logger.error("Failed to verify session. Exiting...")
        return

    while True:
        result = await do_sync(session)
        if result:
            logger.info(f"Sync cycle completed successfully. Sleeping for {settings.SYNC_INTERVAL} seconds...")
            await asyncio.sleep(settings.SYNC_INTERVAL)
        else:
            await asyncio.sleep(5)

def run():
    asyncio.run(main())

if __name__ == "__main__":
    run()
