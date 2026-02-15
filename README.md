# BB16 Script

A Python-based tool for synchronizing, processing, and uploading workout data from **BB16** bike computers (and potentially other generic BLE cycling computers) to the Blackbird Sport server.

## Features

- **BLE Synchronization**: Connects to the device via Bluetooth Low Energy (BLE) to download `.fit` workout files.
- **Data Processing**: Parses `.fit` files and converts them into the proprietary XML format required by the Blackbird API.
- **Authentication**: Handles user login and session management for the Blackbird platform.
- **Upload**: Uploads processed workout records to your Blackbird account.
- **Local History**: Tracks uploaded files to prevent duplicates.

## Prerequisites

- **Python 3.11** or higher.
- A computer with **Bluetooth** support (for device synchronization).
- A valid **Blackbird Sport** account.

## Installation

This project uses `pyproject.toml` for dependency management. You can install the dependencies using `pip` or `uv`.

### Using pip

```bash
pip install .
```

### Using uv (Recommended)

If you have `uv` installed:

```bash
uv sync
```

## Configuration

1.  **Create the Environment File**:
    Copy the example environment file to `.env`:

    ```bash
    cp .env.example .env
    ```

    *(On Windows PowerShell: `Copy-Item .env.example .env`)*

2.  **Edit `.env`**:
    Open `.env` in a text editor and configure the following:

    -   `BLE_ADDRESS`: **Required** for the `sync` command. The MAC address of your BB16 device (e.g., `C3:26:30:11:22:33`).
    -   Other optional fields (`DEVICE_SN`, etc.) can usually be left as default unless you need to spoof a specific device identity.

## Usage

The script provides a Command Line Interface (CLI) via `main.py`.

### 1. Login

First, log in to your Blackbird account. This will cache your session token locally.

```bash
python main.py login
```
*You will be prompted for your User ID (phone/email) and Password.*

### 2. Device Sync (Automated)

To automatically scan for your device (configured in `.env`), download new `.fit` files, and upload them:

```bash
python main.py sync
```

You can control whether to wait for the device to appear (default is False):

```bash
# Wait for the device to appear
python main.py sync --wait
```

### 3. Manual Upload

If you already have a `.fit` file locally and want to upload it:

```bash
python main.py upload <path_to_fit_file>
```

### 4. Other Commands

-   **Check User Info**:
    View your current account details and verify your session.
    ```bash
    python main.py info
    ```

-   **Convert File**:
    Convert a `.fit` file to the XML format for debugging purposes (prints to stdout).
    ```bash
    python main.py convert <path_to_fit_file>
    ```

## Project Structure

-   `main.py`: Entry point for the CLI.
-   `device_sync.py`: Handles BLE communication and file downloading.
-   `fit_processor.py`: Parses `.fit` files using `fitdecode` and generates XML.
-   `uploader.py`: Handles file compression and HTTP requests to the server.
-   `auth.py`: Manages authentication and session storage.
-   `config.py`: Configuration management using `pydantic-settings`.
