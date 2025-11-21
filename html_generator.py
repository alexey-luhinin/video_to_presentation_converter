"""
HTML slideshow generator from video frames for browser viewing.
"""

from PIL import Image
import io
import base64
from typing import List, Dict
from datetime import timedelta


class HTMLGenerator:
    """Generates HTML slideshow presentations from video frames."""
    
    def __init__(self):
        """Initialize HTML generator."""
        pass
    
    def format_timestamp(self, seconds: float) -> str:
        """Format timestamp in MM:SS format."""
        td = timedelta(seconds=int(seconds))
        total_seconds = int(td.total_seconds())
        mins = total_seconds // 60
        secs = total_seconds % 60
        return f"{mins}:{secs:02d}"
    
    def image_to_base64(self, image: Image.Image, max_size: tuple = (1920, 1080)) -> str:
        """
        Convert PIL Image to base64 encoded JPEG string.
        
        Args:
            image: PIL Image object
            max_size: Maximum dimensions (width, height) for resizing
            
        Returns:
            Base64 encoded JPEG string
        """
        # Ensure image is a PIL Image, not BytesIO or other type
        if not isinstance(image, Image.Image):
            # If it's a BytesIO or file-like object, load from bytes
            # Check for BytesIO specifically - BytesIO has getvalue() method
            is_bytesio = (isinstance(image, io.BytesIO) or 
                         (hasattr(image, 'getvalue') and hasattr(image, 'read') and 
                          not hasattr(image, 'name')))  # File handles have 'name' attribute
            
            if is_bytesio:
                # BytesIO or BytesIO-like object: read bytes and create image
                if hasattr(image, 'seek'):
                    image.seek(0)
                image_bytes = image.read()
                if not image_bytes:
                    raise ValueError("BytesIO object is empty")
                # Create fresh BytesIO from bytes to avoid any state issues
                fresh_bytesio = io.BytesIO(image_bytes)
                image = Image.open(fresh_bytesio)
            elif hasattr(image, 'read'):
                # It's a file-like object (file handle, etc.)
                if hasattr(image, 'seek'):
                    image.seek(0)
                # Read bytes from file-like object
                image_bytes = image.read()
                if not image_bytes:
                    raise ValueError("File-like object returned empty bytes")
                image = Image.open(io.BytesIO(image_bytes))
            elif isinstance(image, (str, bytes)):
                # Try to open as file path (string) or bytes
                try:
                    image = Image.open(image)
                except (TypeError, AttributeError, OSError) as e:
                    raise ValueError(f"Could not open image from {type(image)}: {e}")
            else:
                raise ValueError(f"Expected PIL Image, BytesIO, file path, or file-like object, got {type(image)}")
        
        # Resize if too large
        img_width, img_height = image.size
        if img_width > max_size[0] or img_height > max_size[1]:
            aspect_ratio = img_width / img_height
            if img_width > img_height:
                new_width = max_size[0]
                new_height = int(max_size[0] / aspect_ratio)
            else:
                new_height = max_size[1]
                new_width = int(max_size[1] * aspect_ratio)
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Convert to JPEG bytes
        img_bytes = io.BytesIO()
        # Convert RGBA to RGB if necessary
        if image.mode == 'RGBA':
            rgb_image = Image.new('RGB', image.size, (255, 255, 255))
            rgb_image.paste(image, mask=image.split()[3])
            image = rgb_image
        elif image.mode != 'RGB':
            image = image.convert('RGB')
        
        image.save(img_bytes, format='JPEG', quality=90)
        img_bytes.seek(0)
        
        # Encode to base64
        img_b64 = base64.b64encode(img_bytes.getvalue()).decode('utf-8')
        return f"data:image/jpeg;base64,{img_b64}"
    
    def create_slideshow(self, frames: List[Dict], title: str = "Video Presentation") -> str:
        """
        Create HTML slideshow from selected frames.
        
        Args:
            frames: List of frame dictionaries with 'image' PIL Image objects
            title: Title of the presentation
            
        Returns:
            HTML string for the slideshow
        """
        # Convert all images to base64
        slide_images = []
        for idx, frame_data in enumerate(frames):
            image = frame_data['image']
            # Ensure image is a PIL Image (make a copy to avoid modifying original)
            if isinstance(image, Image.Image):
                image = image.copy()
            img_b64 = self.image_to_base64(image)
            timestamp = self.format_timestamp(frame_data.get('timestamp', 0))
            frame_number = frame_data.get('frame_number', idx + 1)
            
            slide_images.append({
                'image': img_b64,
                'timestamp': timestamp,
                'frame_number': frame_number,
                'index': idx
            })
        
        # Generate HTML
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: #1a1a1a;
            color: #ffffff;
            overflow: hidden;
            height: 100vh;
        }}
        
        .slideshow-container {{
            position: relative;
            width: 100%;
            height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            background: #000;
        }}
        
        .slide {{
            display: none;
            width: 100%;
            height: 100%;
            position: absolute;
            top: 0;
            left: 0;
            animation: fadeIn 0.5s;
        }}
        
        .slide.active {{
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        
        @keyframes fadeIn {{
            from {{ opacity: 0; }}
            to {{ opacity: 1; }}
        }}
        
        .slide img {{
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
            user-select: none;
        }}
        
        .controls {{
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            display: flex;
            gap: 10px;
            align-items: center;
            background: rgba(0, 0, 0, 0.7);
            padding: 10px 20px;
            border-radius: 30px;
            backdrop-filter: blur(10px);
            z-index: 1000;
        }}
        
        .control-btn {{
            background: rgba(255, 255, 255, 0.2);
            border: none;
            color: white;
            width: 40px;
            height: 40px;
            border-radius: 50%;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 18px;
            transition: all 0.2s;
            user-select: none;
        }}
        
        .control-btn:hover {{
            background: rgba(255, 255, 255, 0.3);
            transform: scale(1.1);
        }}
        
        .control-btn:active {{
            transform: scale(0.95);
        }}
        
        .control-btn:disabled {{
            opacity: 0.3;
            cursor: not-allowed;
        }}
        
        .slide-info {{
            color: white;
            font-size: 14px;
            margin: 0 15px;
            min-width: 120px;
            text-align: center;
        }}
        
        .slide-counter {{
            color: rgba(255, 255, 255, 0.7);
            font-size: 12px;
        }}
        
        .header {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            background: rgba(0, 0, 0, 0.7);
            padding: 15px 20px;
            backdrop-filter: blur(10px);
            z-index: 1000;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .header h1 {{
            font-size: 18px;
            font-weight: 500;
        }}
        
        .header-actions {{
            display: flex;
            gap: 10px;
        }}
        
        .header-btn {{
            background: rgba(255, 255, 255, 0.2);
            border: none;
            color: white;
            padding: 8px 16px;
            border-radius: 20px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.2s;
        }}
        
        .header-btn:hover {{
            background: rgba(255, 255, 255, 0.3);
        }}
        
        .fullscreen-btn {{
            position: fixed;
            top: 70px;
            right: 20px;
            background: rgba(0, 0, 0, 0.7);
            border: none;
            color: white;
            width: 40px;
            height: 40px;
            border-radius: 50%;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 18px;
            z-index: 1000;
            transition: all 0.2s;
        }}
        
        .fullscreen-btn:hover {{
            background: rgba(0, 0, 0, 0.9);
        }}
        
        @media (max-width: 768px) {{
            .header h1 {{
                font-size: 14px;
            }}
            
            .slide-info {{
                font-size: 12px;
                margin: 0 10px;
                min-width: 100px;
            }}
            
            .control-btn {{
                width: 35px;
                height: 35px;
                font-size: 16px;
            }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{title}</h1>
        <div class="header-actions">
            <button class="header-btn" onclick="window.print()">Print</button>
            <button class="header-btn" onclick="window.close()">Close</button>
        </div>
    </div>
    
    <button class="fullscreen-btn" onclick="toggleFullscreen()" title="Toggle Fullscreen">
        <span id="fullscreen-icon">⛶</span>
    </button>
    
    <div class="slideshow-container">
"""
        
        # Add all slides
        for slide in slide_images:
            html += f"""        <div class="slide" id="slide-{slide['index']}">
            <img src="{slide['image']}" alt="Slide {slide['index'] + 1}">
        </div>
"""
        
        html += """    </div>
    
    <div class="controls">
        <button class="control-btn" id="prev-btn" onclick="previousSlide()" title="Previous (←)">
            ‹
        </button>
        <div class="slide-info">
            <div id="slide-counter" class="slide-counter">1 / """ + str(len(slide_images)) + """</div>
            <div id="slide-timestamp">00:00</div>
        </div>
        <button class="control-btn" id="next-btn" onclick="nextSlide()" title="Next (→)">
            ›
        </button>
    </div>
    
    <script>
        let currentSlide = 0;
        const totalSlides = """ + str(len(slide_images)) + """;
        const slideData = """ + str([{'timestamp': s['timestamp'], 'frame_number': s['frame_number']} for s in slide_images]) + """;
        
        function showSlide(n) {
            const slides = document.querySelectorAll('.slide');
            
            if (n >= totalSlides) {
                currentSlide = 0;
            } else if (n < 0) {
                currentSlide = totalSlides - 1;
            } else {
                currentSlide = n;
            }
            
            slides.forEach(slide => slide.classList.remove('active'));
            slides[currentSlide].classList.add('active');
            
            // Update counter and timestamp
            document.getElementById('slide-counter').textContent = `${currentSlide + 1} / ${totalSlides}`;
            document.getElementById('slide-timestamp').textContent = slideData[currentSlide].timestamp || '00:00';
            
            // Update button states
            document.getElementById('prev-btn').disabled = totalSlides <= 1;
            document.getElementById('next-btn').disabled = totalSlides <= 1;
        }
        
        function nextSlide() {
            showSlide(currentSlide + 1);
        }
        
        function previousSlide() {
            showSlide(currentSlide - 1);
        }
        
        function toggleFullscreen() {
            if (!document.fullscreenElement) {
                document.documentElement.requestFullscreen().catch(err => {
                    console.log('Error attempting to enable fullscreen:', err);
                });
            } else {
                document.exitFullscreen();
            }
        }
        
        // Keyboard navigation
        document.addEventListener('keydown', function(e) {
            if (e.key === 'ArrowRight' || e.key === 'ArrowDown' || e.key === ' ') {
                e.preventDefault();
                nextSlide();
            } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
                e.preventDefault();
                previousSlide();
            } else if (e.key === 'Home') {
                e.preventDefault();
                showSlide(0);
            } else if (e.key === 'End') {
                e.preventDefault();
                showSlide(totalSlides - 1);
            } else if (e.key === 'f' || e.key === 'F') {
                e.preventDefault();
                toggleFullscreen();
            } else if (e.key === 'Escape') {
                if (document.fullscreenElement) {
                    document.exitFullscreen();
                }
            }
        });
        
        // Touch/swipe support for mobile
        let touchStartX = 0;
        let touchEndX = 0;
        
        document.addEventListener('touchstart', function(e) {
            touchStartX = e.changedTouches[0].screenX;
        });
        
        document.addEventListener('touchend', function(e) {
            touchEndX = e.changedTouches[0].screenX;
            handleSwipe();
        });
        
        function handleSwipe() {
            const swipeThreshold = 50;
            const diff = touchStartX - touchEndX;
            
            if (Math.abs(diff) > swipeThreshold) {
                if (diff > 0) {
                    nextSlide();
                } else {
                    previousSlide();
                }
            }
        }
        
        // Initialize
        showSlide(0);
        
        // Update fullscreen icon on change
        document.addEventListener('fullscreenchange', function() {
            const icon = document.getElementById('fullscreen-icon');
            if (document.fullscreenElement) {
                icon.textContent = '⛶';
            } else {
                icon.textContent = '⛶';
            }
        });
    </script>
</body>
</html>"""
        
        return html

