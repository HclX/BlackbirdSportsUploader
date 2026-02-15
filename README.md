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

### pip/uv

```bash
uv pip install .
# or
pip install .
```

## Usage

After installation, the `blackbird-sync` command is available:

```bash
# Start continuous sync loop
blackbird-sync sync

# Run a single sync iteration
blackbird-sync sync --once

# Show help
blackbird-sync --help
```

### Docker

```bash
docker-compose up -d
```

## Project Structure

-   `src/blackbird_sports_uploader/`: Source code package.
    -   `main.py`: Entry point.
    -   `device.py`: BLE communication.
    -   `fit_processor.py`: FIT file parsing.
    -   `uploader.py`: API interaction.
-   `tests/`: Unit tests.

## Development

### Running Tests

To run the test suite, you need to install development dependencies:

```bash
uv sync --extra dev
```

Then run `pytest`:

```bash
uv run pytest
```


