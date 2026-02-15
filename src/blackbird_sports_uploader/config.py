from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Data directories
    DATA_DIR: Path = Path("data")
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Filenames (relative to DATA_DIR)
    SESSION_FILENAME: str = ".session.json"
    UPLOAD_HISTORY_FILENAME: str = "uploaded_records.json"

    @property
    def SESSION_FILE(self) -> Path:
        """Return the full path to the session file."""
        return self.DATA_DIR / self.SESSION_FILENAME

    @property
    def UPLOAD_HISTORY_FILE(self) -> Path:
        """Return the full path to the upload history file."""
        return self.DATA_DIR / self.UPLOAD_HISTORY_FILENAME

    # Device
    BLE_ADDRESS: Optional[str] = None  # MAC address of the device

    # Auto-login credentials (optional)
    BB_USERNAME: Optional[str] = None
    BB_PASSWORD: Optional[str] = None
    
    # Sync Configuration
    SYNC_INTERVAL: int = 300  # Seconds to wait between syncs in loop mode (default 5 mins)

    # API Configuration
    BASE_URL: str = "https://client.blackbirdsport.com"

    # Request Parameters
    APP_VERSION: str = "1.0.13"
    CLIENT_TYPE: str = "android"
    CLIENT_DETAIL: str = "Android 7.1.2; SM-G965N Build/N2G48H"
    IMEI: str = "123456789012345"
    CHANNEL_ID: str = "111"
    USER_AGENT: str = "Dalvik/2.1.0 (Linux; U; Android 7.1.2; SM-G965N Build/N2G48H)"
    DEVICE_SN: str = "BB16_2_00000000"
    DEVICE_TYPE: str = "BB16"

    # Logging
    LOG_FILE_NAME: str = "app.log"
    LOG_LEVEL_CONSOLE: str = "INFO"
    LOG_LEVEL_FILE: str = "DEBUG"

    @property
    def log_file_path(self) -> Path:
        return self.DATA_DIR / self.LOG_FILE_NAME

    def model_post_init(self, __context: object) -> None:
        """Ensure directories exist."""
        # Create directories if they don't exist
        if not self.DATA_DIR.exists():
            self.DATA_DIR.mkdir(parents=True, exist_ok=True)




# Global settings instance
settings = Settings()
# Initialize directories immediately
settings.model_post_init(None)
