# Video to PowerPoint Converter

A web-based application that converts videos to PowerPoint presentations with automatic scene change detection. Perfect for processing large static videos like webinars.

## Features

- Automatic scene change detection using histogram comparison
- Web-based interface for easy video upload
- Frame preview and selection before generating PPTX
- Fast in-memory processing optimized for large files
- One frame per slide in standard PPTX format

## Installation

1. Install Python 3.8 or higher
2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

1. Start the server:
```bash
python app.py
```

2. Open your browser and navigate to `http://localhost:5000`

3. Upload a video file through the web interface

4. Review and select frames from the automatically detected scene changes

5. Generate and download your PowerPoint presentation

## Supported Video Formats

All formats supported by OpenCV (MP4, AVI, MOV, etc.)

## Technical Details

- Backend: Flask
- Video Processing: OpenCV
- PPTX Generation: python-pptx
- Scene Detection: Histogram comparison algorithm
