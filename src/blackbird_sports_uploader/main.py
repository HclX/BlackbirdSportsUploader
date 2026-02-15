import typer
import time
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Set, Tuple, Optional

from .auth import get_session, save_session, authenticate, get_user_info
from .fit_processor import FitProcessor
from .uploader import compress_xml, upload_record
from .config import settings
from .logger import setup_logging
from . import bb16

# Setup logger for main module
logger = setup_logging("main")

app = typer.Typer()


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
            json.dump(list(history), f)
    except IOError as e:
        logger.error(f"Failed to save history: {e}")


@app.command()
def login(
    user_id: str = typer.Option(..., prompt=True),
    password: str = typer.Option(..., prompt=True, hide_input=True),
    ton: Optional[str] = typer.Option(None, help="Session Token (ton). If not provided, it will be retrieved automatically.")
) -> None:
    """
    Login and cache session token.
    If 'ton' is not provided, it will be automatically retrieved via bk_setClient.
    """
    logger.info("Attempting login...")
    try:
        cookies, account_id, used_ton = authenticate(ton, user_id, password)
        save_session(used_ton, user_id, account_id, cookies)
        msg = f"Login successful! Session cached. Account ID: {account_id}"
        logger.info(msg)
        typer.echo(msg)
    except Exception as e:
        logger.error(f"Login failed: {e}")
        typer.echo(f"Login failed: {e}")
        raise typer.Exit(code=1)


@app.command()
def info() -> None:
    """
    Get user info using cached session.
    """
    session = get_session()
    if not session:
        msg = "No session found. Please login first."
        logger.warning(msg)
        typer.echo(msg)
        return

    try:
        # Use accountId for friendId
        info_data = get_user_info(session.ton, session.accountId, session.cookies)
        logger.info("User Info retrieved successfully")
        typer.echo(f"User Info: {info_data}")
    except Exception as e:
        logger.error(f"Failed to get info: {e}")
        typer.echo(f"Failed to get info: {e}")


@app.command()
def convert(fit_file: Path) -> None:
    """
    Convert a .fit file to the XML format and print it.
    """
    if not fit_file.exists():
        msg = f"File not found: {fit_file}"
        logger.error(msg)
        typer.echo(msg)
        return

    # Use dummy account ID for pure conversion test
    try:
        processor = FitProcessor(str(fit_file), 123456)
        processor.parse()
        xml_output = processor.generate_xml()
        print(xml_output)
    except Exception as e:
        logger.error(f"Conversion failed: {e}")
        typer.echo(f"Conversion failed: {e}")


@app.command()
def upload(
    fit_file: Path,
    device_type: str = typer.Option(settings.DEVICE_TYPE, help="Device type (e.g. android, ios)"),
    sn: str = typer.Option(settings.DEVICE_SN, help="Device Serial Number"),
) -> None:
    """
    Convert and upload a .fit file to the server.
    """
    session = get_session()
    if not session:
        msg = "No session found. Please login first."
        logger.warning(msg)
        typer.echo(msg)
        return

    if not fit_file.exists():
        msg = f"File not found: {fit_file}"
        logger.error(msg)
        typer.echo(msg)
        return

    try:
        logger.info(f"Starting upload process for {fit_file}")
        typer.echo("Parsing FIT file...")

        # Use cached accountId
        try:
            account_id = int(session.accountId)
        except ValueError:
            account_id = 0
            logger.warning("accountId is not an integer. Using 0 for fingerprint.")

        processor = FitProcessor(str(fit_file), account_id)
        processor.parse()
        xml_content = processor.generate_xml()

        # XML filename uses recordId.
        timestamp_ms = int(processor.start_time * 1000)  # Ensure ms
        # Wait, start_time in processor is seconds (float) or ms?
        # In processor refactor: self.start_time = val.timestamp() * 1000 # ms
        # Wait, check fit_processor again.
        # In original: self.start_time = frame.get_value('start_time').timestamp() * 1000 # ms
        # In refactor: self.start_time = val.timestamp() * 1000 # ms
        # So it is ms.
        timestamp_ms = int(processor.start_time)

        record_id, fittime = generate_params(timestamp_ms)

        typer.echo(f"Compressing with Record ID: {record_id}...")
        zip_data = compress_xml(xml_content, record_id)

        typer.echo(f"Uploading... (fittime={fittime})")

        result = upload_record(
            zip_data, session.ton, record_id, fittime, device_type, sn
        )
        msg = f"Upload successful: {result}"
        logger.info(msg)
        typer.echo(msg)

    except Exception as e:
        msg = f"Error during upload: {e}"
        logger.error(msg)
        typer.echo(msg)


@app.command()
def sync(
    device_type: str = typer.Option(settings.DEVICE_TYPE, help="Device type (e.g. android, ios)"),
    sn: str = typer.Option(settings.DEVICE_SN, help="Device Serial Number"),
    once: bool = typer.Option(False, help="Run once and exit (disable continuous loop)."),
) -> None:
    """
    Automated sync: Scan, Download, and Upload new records.
    Default behavior is to run in a continuous loop. Use --once to run a single iteration.
    """
    if not settings.DATA_DIR.exists():
        settings.DATA_DIR.mkdir(parents=True)

    while True:
        if not bb16.download():
            continue

        history = load_history()
        new_files = [f for f in settings.DATA_DIR.glob("*.fit") if f.name not in history]
        logger.info(f"Found {len(new_files)} new records.")

        session = get_session()
        if not session:
            # Try auto-login if credentials are provided
            if settings.BB_USERNAME and settings.BB_PASSWORD:
                logger.info("No active session found. Attempting auto-login...")
                # authenticate returns a tuple: (cookies, account_id, ton)
                cookies, account_id, ton = authenticate(None, settings.BB_USERNAME, settings.BB_PASSWORD)
                save_session(ton, settings.BB_USERNAME, account_id, cookies)
                # Reload session to get the SessionData object
                session = get_session()
                logger.info("Auto-login successful.")
            else:
                msg = "No session found. Please login first."
                logger.warning(msg)
                return
                
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
            if not upload_record(session, zip_data, record_id, fittime):
                logger.error(f"Failed to upload {f.name}")
                continue

            logger.info(f"Upload successful: {f.name}")
            history.add(f.name)
            save_history(history)

        logger.info("All records already uploaded.")
        if once:
            logger.info("Sync completed.")
            typer.echo("Sync completed.")
            break

        logger.info(f"Sync cycle completed successfully. Sleeping for {settings.SYNC_INTERVAL} seconds...")
        time.sleep(settings.SYNC_INTERVAL)

if __name__ == "__main__":
    app()
