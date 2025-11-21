"""Screenshot capture module for full screen and region selection."""
from PIL import ImageGrab
import sys
import tkinter as tk


def capture_full_screen():
    """
    Capture the entire screen.
    
    Returns:
        PIL.Image: Screenshot of the full screen
    """
    return ImageGrab.grab()


def capture_region(x1, y1, x2, y2):
    """
    Capture a specific region of the screen.
    
    Args:
        x1 (int): Left coordinate
        y1 (int): Top coordinate
        x2 (int): Right coordinate
        y2 (int): Bottom coordinate
    
    Returns:
        PIL.Image: Screenshot of the selected region
    """
    # Ensure coordinates are in correct order
    left = min(x1, x2)
    top = min(y1, y2)
    right = max(x1, x2)
    bottom = max(y1, y2)
    
    # Always capture full screen first, then crop
    # This ensures we work with the actual image dimensions
    # which may differ from reported screen size due to DPI scaling
    full_screen = ImageGrab.grab()
    
    # Get actual screen dimensions from the captured image
    actual_width, actual_height = full_screen.size
    
    # Get reported screen dimensions from tkinter
    # Try to get from default root first, otherwise create temporary
    reported_width = actual_width
    reported_height = actual_height
    try:
        # Try to access the default root window
        if hasattr(tk, '_default_root') and tk._default_root:
            root = tk._default_root
            reported_width = root.winfo_screenwidth()
            reported_height = root.winfo_screenheight()
        else:
            # Create temporary invisible root to get screen dimensions
            temp_root = tk.Tk()
            temp_root.withdraw()  # Hide the window
            reported_width = temp_root.winfo_screenwidth()
            reported_height = temp_root.winfo_screenheight()
            temp_root.destroy()
    except Exception:
        # If all else fails, assume no scaling
        reported_width = actual_width
        reported_height = actual_height
    
    # Calculate scaling factor if there's a mismatch
    # This handles DPI scaling on Windows
    scale_x = actual_width / reported_width if reported_width > 0 else 1.0
    scale_y = actual_height / reported_height if reported_height > 0 else 1.0
    
    # Scale coordinates to match actual image dimensions
    scaled_left = int(left * scale_x)
    scaled_top = int(top * scale_y)
    scaled_right = int(right * scale_x)
    scaled_bottom = int(bottom * scale_y)
    
    # Ensure coordinates are within image bounds
    scaled_left = max(0, min(scaled_left, actual_width))
    scaled_top = max(0, min(scaled_top, actual_height))
    scaled_right = max(0, min(scaled_right, actual_width))
    scaled_bottom = max(0, min(scaled_bottom, actual_height))
    
    # Crop to the selected region
    region = full_screen.crop((scaled_left, scaled_top, scaled_right, scaled_bottom))
    
    return region

