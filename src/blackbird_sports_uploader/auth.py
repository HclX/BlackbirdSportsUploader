import time
import requests
from typing import Optional, Dict, Tuple, Any
from pydantic import BaseModel
from .config import settings
from .logger import setup_logging

logger = setup_logging(__name__)


class SessionData(BaseModel):
    ton: str
    userId: str
    cookies: Dict[str, str] = {}
    accountId: str = ""


def save_session(
    ton: str, user_id: str, account_id: str, cookies: Dict[str, str]
) -> None:
    """Save session data to a local file for persistence."""
    session = SessionData(
        ton=ton, userId=user_id, accountId=account_id, cookies=cookies
    )
    try:
        with open(settings.SESSION_FILE, "w") as f:
            f.write(session.model_dump_json())
        logger.info(f"Session saved to {settings.SESSION_FILE}")
    except IOError as e:
        logger.error(f"Failed to save session: {e}")
        raise


def get_session() -> Optional[SessionData]:
    """Load session data from the local file."""
    if settings.SESSION_FILE.exists():
        try:
            with open(settings.SESSION_FILE, "r") as f:
                return SessionData.model_validate_json(f.read())
        except Exception as e:
            logger.warning(f"Failed to load session, file may be corrupted: {e}")
            return None
    return None

def set_client() -> str:
    """
    Register client and retrieve session token (ton).
    
    Returns:
        The session token 'ton'.
        
    Raises:
        Exception: If request fails.
    """
    url = f"{settings.BASE_URL}/bk_setClient"
    params = {
        "version": settings.APP_VERSION,
        "type": settings.CLIENT_TYPE,
        "detail": settings.CLIENT_DETAIL,
        "code": "",
        "imei": settings.IMEI,
        "timeStamp": str(int(time.time() * 1000)),
        "channelId": settings.CHANNEL_ID
    }
    headers = {
        "User-Agent": settings.USER_AGENT
    }
    
    logger.debug("Setting client to retrieve ton...")
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        if data.get("status") != "ok":
            error_msg = data.get('msg', 'Unknown error')
            logger.error(f"setClient failed: {error_msg}")
            raise Exception(f"setClient failed: {error_msg}")
            
        ton = data.get("token", {}).get("token")
        if not ton:
            raise Exception("No token found in setClient response")
            
        logger.info("Successfully retrieved automatic ton.")
        return ton

    except requests.RequestException as e:
        logger.error(f"Network error during setClient: {e}")
        raise

def authenticate(ton: Optional[str], user_id: str, password: str) -> Tuple[Dict[str, str], str, str]:
    """
    Authenticate with the Blackbird Sport server.
    
    Args:
        ton: The session token. If None, it will be retrieved automatically.
        user_id: The user email/ID.
        password: The user password.
        
    Returns:
        Tuple containing cookies dictionary, accountId string, and the ton used.
        
    Raises:
        Exception: If login fails or API returns error status.
    """
    if not ton:
        ton = set_client()
        
    url = f"{settings.BASE_URL}/bk_login"
    params = {
        "ton": ton,
        "userId": user_id,
        "password": password,
        "timeStamp": str(int(time.time() * 1000))
    }
    headers = {
        "User-Agent": settings.USER_AGENT
    }

    logger.debug(f"Authenticating user: {user_id}")
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()

        data = response.json()
        if data.get("status") != "ok":
            error_msg = data.get("msg", "Unknown error")
            logger.error(f"Login failed: {error_msg}")
            raise Exception(f"Login failed: {error_msg}")

        account_id = str(data.get("user", {}).get("accountId", ""))
        logger.info(f"Authentication successful for accountId: {account_id}")
        return response.cookies.get_dict(), account_id, ton

    except requests.RequestException as e:
        logger.error(f"Network error during authentication: {e}")
        raise


def get_user_info(ton: str, friend_id: str, cookies: Dict[str, str]) -> Dict[str, Any]:
    """
    Retrieve user information.

    Args:
        ton: Session token.
        friend_id: User/Friend ID.
        cookies: Session cookies.

    Returns:
        Dictionary containing user info.
    """
    url = f"{settings.BASE_URL}/bk_getUserInfo"
    params = {"ton": ton, "friendId": friend_id}
    headers = {
        "User-Agent": settings.USER_AGENT
    }

    logger.debug(f"Getting info for friendId: {friend_id}")
    try:
        response = requests.get(
            url, params=params, headers=headers, cookies=cookies, timeout=10
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Failed to get user info: {e}")
        raise
