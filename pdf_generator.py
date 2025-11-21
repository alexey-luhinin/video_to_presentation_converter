"""
PDF presentation generator from video frames.
"""

from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from PIL import Image
import io
from typing import List, Dict


class PDFGenerator:
    """Generates PDF presentations from video frames."""
    
    def __init__(self, page_width: float = 10.0, page_height: float = 7.5):
        """
        Initialize PDF generator.
        
        Args:
            page_width: Page width in inches (default 10.0 for 16:9 aspect ratio)
            page_height: Page height in inches (default 7.5 for 16:9 aspect ratio)
        """
        self.page_width = page_width
        self.page_height = page_height
        self.max_image_width = (page_width - 0.5) * inch  # Leave margins
        self.max_image_height = (page_height - 0.5) * inch
    
    def create_presentation(self, frames: List[Dict], output_path: str = None) -> bytes:
        """
        Create PDF presentation from selected frames.
        
        Args:
            frames: List of frame dictionaries with 'image' PIL Image objects
            output_path: Optional path to save file. If None, returns bytes.
            
        Returns:
            Bytes of PDF file if output_path is None, otherwise None
        """
        # Create PDF in memory
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=(self.page_width * inch, self.page_height * inch))
        
        print(f"Creating PDF with {len(frames)} pages...")
        
        for idx, frame_data in enumerate(frames):
            # Get image and ensure it's a PIL Image
            image = frame_data['image']
            
            # Validate and convert to PIL Image if needed
            if not isinstance(image, Image.Image):
                if hasattr(image, 'read'):
                    # It's a file-like object (BytesIO, file handle, etc.)
                    if hasattr(image, 'seek'):
                        image.seek(0)
                    image_bytes = image.read()
                    if not image_bytes:
                        raise ValueError(f"Frame {idx} has empty image data")
                    image = Image.open(io.BytesIO(image_bytes))
                else:
                    raise ValueError(f"Frame {idx} has invalid image type: {type(image)}")
            
            # Calculate dimensions maintaining aspect ratio
            img_width, img_height = image.size
            aspect_ratio = img_width / img_height
            
            # Fit image within page bounds while maintaining aspect ratio
            if aspect_ratio > (self.max_image_width / self.max_image_height):
                # Image is wider - fit to width
                width = self.max_image_width
                height = width / aspect_ratio
            else:
                # Image is taller - fit to height
                height = self.max_image_height
                width = height * aspect_ratio
            
            # Resize image if it's too large (optimize for PDF)
            if img_width > 1920 or img_height > 1080:
                # Resize to max 1920x1080 while maintaining aspect ratio
                max_dimension = 1920
                if img_width > img_height:
                    new_width = max_dimension
                    new_height = int(img_height * (max_dimension / img_width))
                else:
                    new_height = max_dimension
                    new_width = int(img_width * (max_dimension / img_height))
                image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Center image on page
            # Note: reportlab uses bottom-left origin, so we calculate from bottom
            left = (self.page_width * inch - width) / 2
            bottom = (self.page_height * inch - height) / 2
            
            # Convert PIL Image to bytes for reportlab
            # Use ImageReader which properly handles PIL Images and BytesIO
            img_bytes = io.BytesIO()
            image.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            
            # Use ImageReader to wrap the BytesIO or PIL Image
            # ImageReader can handle both PIL Images and BytesIO objects
            try:
                # Try using ImageReader with BytesIO
                img_reader = ImageReader(img_bytes)
                c.drawImage(img_reader, left, bottom, width=width, height=height, preserveAspectRatio=True)
            except Exception as e:
                # If BytesIO doesn't work with ImageReader, try PIL Image directly
                try:
                    img_reader = ImageReader(image)
                    c.drawImage(img_reader, left, bottom, width=width, height=height, preserveAspectRatio=True)
                except Exception as e2:
                    # Last resort: save to BytesIO and use ImageReader again with fresh BytesIO
                    img_bytes_fresh = io.BytesIO()
                    image.save(img_bytes_fresh, format='PNG')
                    img_bytes_fresh.seek(0)
                    img_reader = ImageReader(img_bytes_fresh)
                    c.drawImage(img_reader, left, bottom, width=width, height=height, preserveAspectRatio=True)
            
            # Create new page for next frame
            if idx < len(frames) - 1:
                c.showPage()
            
            if (idx + 1) % 10 == 0:
                print(f"Added {idx + 1}/{len(frames)} pages...")
        
        # Save PDF
        c.save()
        buffer.seek(0)
        
        print(f"PDF created successfully with {len(frames)} pages")
        
        # Return bytes or save to file
        if output_path:
            with open(output_path, 'wb') as f:
                f.write(buffer.getvalue())
            return None
        else:
            return buffer.getvalue()
    
    def create_from_selected_indices(self, all_frames: List[Dict], 
                                     selected_indices: List[int],
                                     output_path: str = None) -> bytes:
        """
        Create PDF from selected frame indices.
        
        Args:
            all_frames: All available frames
            selected_indices: List of frame indices to include
            output_path: Optional path to save file
            
        Returns:
            Bytes of PDF file if output_path is None, otherwise None
        """
        selected_frames = [all_frames[i] for i in selected_indices if 0 <= i < len(all_frames)]
        return self.create_presentation(selected_frames, output_path)

