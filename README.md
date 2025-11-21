# Video to Presentation Converter

A web-based application that converts videos to presentations in multiple formats (PPTX, PDF, HTML) with automatic scene change detection using ML-based feature extraction. Perfect for processing large static videos like webinars.

## Features

- **ML-based scene detection**: Uses MobileNet (TensorFlow) for fast and accurate scene change detection with SSIM fallback
- **Multiple output formats**: Generate PPTX, PDF, or HTML slideshow presentations
- **Configurable detection**: Adjust sensitivity threshold and minimum frame interval
- **Web-based interface**: Easy video upload and frame selection
- **Frame preview**: Review and select frames before generating presentations
- **Real-time progress**: Detailed progress tracking with processing speed and time estimates
- **Browser viewing**: View HTML slideshows with keyboard navigation and fullscreen support
- **Fast processing**: Optimized in-memory processing for large files
- **Stop/cancel**: Cancel long-running processing operations

## Installation

1. Install Python 3.8 or higher
2. Install dependencies:
```bash
pip install -r requirements.txt
```

**Note**: TensorFlow is optional but recommended for faster ML-based scene detection. If you encounter DLL errors on Windows, the application will automatically fall back to SSIM-based detection. You can comment out the TensorFlow line in `requirements.txt` if needed.

## Usage

1. Start the server:
```bash
python app.py
```

2. Open your browser and navigate to `http://localhost:5000`

3. Upload a video file through the web interface

4. Configure detection settings (optional):
   - **Change Detection Sensitivity**: Lower values detect smaller changes (default: 0.3)
   - **Minimum Frame Interval**: Minimum frames between scene changes to prevent duplicates (default: 30)

5. Start processing and monitor real-time progress with detailed metrics

6. Review and select frames from automatically detected scene changes

7. Generate and download your presentation:
   - **PPTX**: Standard PowerPoint format (one frame per slide)
   - **PDF**: Portable document format (one frame per page)
   - **HTML**: Interactive browser slideshow with keyboard navigation

## Supported Video Formats

All formats supported by OpenCV (MP4, AVI, MOV, etc.)

## Output Formats

- **PPTX**: Standard PowerPoint presentation format compatible with Microsoft PowerPoint, Google Slides, and LibreOffice
- **PDF**: Multi-page PDF document suitable for sharing and printing
- **HTML**: Interactive browser slideshow with:
  - Keyboard navigation (arrow keys, space, Home, End, F for fullscreen)
  - Touch/swipe support for mobile devices
  - Fullscreen mode
  - Print functionality

## Technical Details

- **Backend**: Flask
- **Video Processing**: OpenCV
- **PPTX Generation**: python-pptx
- **PDF Generation**: reportlab
- **Scene Detection**: 
  - Primary: ML-based feature extraction using MobileNet (TensorFlow)
  - Fallback: SSIM (Structural Similarity Index) algorithm
- **Image Processing**: Pillow (PIL)
- **Dependencies**: Flask, opencv-python, python-pptx, reportlab, numpy, Pillow, Werkzeug, tensorflow (optional), scikit-image

## API Endpoints

- `POST /upload` - Upload video file and create processing session
- `POST /process` - Start video processing with optional parameters (threshold, min_interval, frame_skip)
- `POST /stop` - Stop current video processing
- `GET /progress` - Get current processing progress and metrics
- `GET /frames` - Get list of extracted frames with thumbnails
- `GET /frame_image/<session_id>/<frame_index>` - Get full-resolution frame image
- `POST /generate` - Generate presentations (PPTX, PDF, HTML) from selected frames
- `GET /download/<session_id>` - Download generated PPTX file
- `GET /download_pdf/<session_id>` - Download generated PDF file
- `GET /view/<session_id>` - View HTML slideshow in browser
- `POST /cleanup/<session_id>` - Clean up session data and files

## Troubleshooting

**TensorFlow DLL errors on Windows**: If you encounter DLL load errors when installing TensorFlow, it's optional. The application will automatically use SSIM-based detection instead. You can comment out or remove the TensorFlow line in `requirements.txt` if needed.

**Large video files**: The application supports files up to 500MB by default. For larger files, you can adjust `MAX_CONTENT_LENGTH` in `app.py`.

**Processing speed**: For faster processing of very long videos, you can adjust the frame skip parameter in the API (process every Nth frame instead of every frame).
