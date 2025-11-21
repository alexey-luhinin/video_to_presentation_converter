# Multi Screenshot Queue Desktop App

A Python desktop application that captures screenshots using a customizable hotkey and stores them in a queue (FIFO) buffer in memory. Users can view, manage, and export screenshots through a GUI.

## Features

- **Queue-based storage**: Screenshots stored in FIFO (First In, First Out) order
- **Customizable hotkey**: Change the capture hotkey in settings (default: Ctrl+Shift+S)
- **Capture modes**:
  - Full screen capture
  - Region selection (interactive rectangle selection)
- **In-memory storage**: All screenshots kept in memory as PIL Image objects
- **Unlimited capacity**: No limit on number of screenshots
- **HUD display**: Shows current screenshot count in buffer
- **Screenshot management**:
  - View full-size screenshot
  - Delete individual screenshots
  - Export screenshot to file
  - Clear all screenshots

## Requirements

- Python 3.7 or higher
- Windows, macOS, or Linux

## Installation

1. Clone or download this repository

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Building an Executable

To create a standalone executable that can be run without Python installed:

### Windows

1. Install build dependencies:
```bash
pip install -r build-requirements.txt
```

2. Run the build script:
```bash
build.bat
```

Or manually:
```bash
pyinstaller app.spec --clean
```

The executable will be created in the `dist` folder as `MultiScreenshotQueue.exe`.

### Linux/macOS

1. Install build dependencies:
```bash
pip install -r build-requirements.txt
```

2. Run the build script:
```bash
chmod +x build.sh
./build.sh
```

Or manually:
```bash
pyinstaller app.spec --clean
```

The executable will be created in the `dist` folder.

**Note:** The executable will be quite large (typically 50-100MB) as it includes Python and all dependencies. You can distribute just the `.exe` file - no additional installation is needed.

## Usage

1. Run the application:
```bash
python app.py
```

2. **Capture Screenshots**:
   - Use the default hotkey `Ctrl+Shift+S` (or your custom hotkey)
   - Or click the "Capture Screenshot" button
   - Select capture mode: "Full Screen" or "Region"

3. **Region Selection**:
   - When in "Region" mode, a transparent overlay will appear
   - Click and drag to select the area you want to capture
   - Release to capture the selected region
   - Press `Escape` to cancel

4. **Manage Screenshots**:
   - View: Click "View" to see full-size screenshot
   - Export: Click "Export" to save screenshot to file
   - Delete: Click "Delete" to remove screenshot from queue
   - Clear All: Remove all screenshots from the queue

5. **Settings**:
   - Click "Settings" to change the capture hotkey
   - Enter key combination separated by commas (e.g., `ctrl,shift,s`)
   - Available modifiers: `ctrl`, `alt`, `shift`, `win`
   - Regular keys: any letter or number

## Configuration

The application saves configuration in `config.json`:
- `hotkey`: List of keys for screenshot capture
- `capture_mode`: Default capture mode ("full" or "region")

## Project Structure

```
multiprintscreen/
├── app.py                 # Main application window
├── screenshot.py          # Screenshot capture functions
├── region_selector.py     # Region selection UI
├── hotkey_manager.py      # Hotkey registration and management
├── config.json           # User configuration
├── requirements.txt       # Python dependencies
├── build-requirements.txt # Build dependencies (PyInstaller)
├── app.spec              # PyInstaller configuration
├── build.bat             # Windows build script
├── build.sh              # Linux/macOS build script
└── README.md             # This file
```

## Notes

- Screenshots are stored in memory only - they are not automatically saved to disk
- Use "Export" to save individual screenshots
- The queue follows FIFO order (oldest screenshots appear first)
- The HUD shows the current number of screenshots in the buffer

## License

This project is provided as-is for personal use.

