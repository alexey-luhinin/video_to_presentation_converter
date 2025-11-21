"""Region selector UI for selecting screen area to capture."""
import tkinter as tk
from typing import Optional, Tuple


class RegionSelector:
    """Interactive region selector overlay."""
    
    def __init__(self, callback, cancel_callback=None):
        """
        Initialize the region selector.
        
        Args:
            callback: Function to call with (x1, y1, x2, y2) when selection is complete
            cancel_callback: Optional function to call when selection is cancelled
        """
        self.callback = callback
        self.cancel_callback = cancel_callback
        self.start_x = None
        self.start_y = None
        self.current_x = None
        self.current_y = None
        self.window = None
        self.canvas = None
        self.selection_rect = None
        
    def start_selection(self):
        """Start the region selection process."""
        # Create fullscreen transparent window
        self.window = tk.Toplevel()
        self.window.attributes('-fullscreen', True)
        self.window.attributes('-alpha', 0.3)
        self.window.attributes('-topmost', True)
        self.window.overrideredirect(True)
        self.window.configure(bg='black')
        
        # Position window at (0, 0) to ensure accurate coordinates
        self.window.geometry(f"{self.window.winfo_screenwidth()}x{self.window.winfo_screenheight()}+0+0")
        
        # Create canvas for drawing selection rectangle
        self.canvas = tk.Canvas(
            self.window,
            highlightthickness=0,
            bg='black',
            cursor='crosshair'
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Force update to ensure window is positioned correctly
        self.window.update_idletasks()
        self.window.update()
        
        # Bind mouse events
        self.canvas.bind('<Button-1>', self.on_button_press)
        self.canvas.bind('<B1-Motion>', self.on_mouse_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_button_release)
        
        # Bind Escape key to window
        self.window.bind('<Escape>', self.on_cancel)
        self.canvas.bind('<Escape>', self.on_cancel)
        
        # Make window focusable to receive Escape key
        self.window.focus_set()
        
        # Get screen dimensions
        self.screen_width = self.window.winfo_screenwidth()
        self.screen_height = self.window.winfo_screenheight()
        
    def on_button_press(self, event):
        """Handle mouse button press - start selection."""
        # Use event root coordinates which are absolute screen coordinates
        self.start_x = event.x_root
        self.start_y = event.y_root
        self.current_x = self.start_x
        self.current_y = self.start_y
        
    def on_mouse_drag(self, event):
        """Handle mouse drag - update selection rectangle."""
        # Use event root coordinates which are absolute screen coordinates
        self.current_x = event.x_root
        self.current_y = event.y_root
        self._draw_selection()
        
    def on_button_release(self, event):
        """Handle mouse button release - complete selection."""
        # Use event root coordinates which are absolute screen coordinates
        self.current_x = event.x_root
        self.current_y = event.y_root
        
        # Calculate selection coordinates
        x1 = min(self.start_x, self.current_x)
        y1 = min(self.start_y, self.current_y)
        x2 = max(self.start_x, self.current_x)
        y2 = max(self.start_y, self.current_y)
        
        # Only proceed if selection has meaningful size
        if abs(x2 - x1) > 5 and abs(y2 - y1) > 5:
            # Store window reference, root window, and callback before closing
            window_ref = self.window
            callback_func = self.callback
            coords = (x1, y1, x2, y2)
            
            # Get root window before closing (Toplevel.master is the root)
            root = window_ref.master if window_ref else None
            
            # Close window first to prevent it from being captured
            self.close()
            
            # Use root window to schedule callback after window is fully removed
            # The delay ensures the window is completely destroyed before capture
            if root:
                root.after(100, lambda: callback_func(*coords))
            else:
                # Fallback: call directly if root not available
                callback_func(*coords)
        else:
            # Selection too small, treat as cancel
            if self.cancel_callback:
                self.cancel_callback()
            self.close()
        
    def on_cancel(self, event):
        """Handle Escape key - cancel selection."""
        if self.cancel_callback:
            self.cancel_callback()
        self.close()
        
    def _draw_selection(self):
        """Draw the selection rectangle on canvas."""
        if self.start_x is None or self.current_x is None:
            return
            
        # Delete previous rectangle
        if self.selection_rect:
            self.canvas.delete(self.selection_rect)
        
        # Convert screen coordinates back to canvas coordinates for drawing
        canvas_x = self.canvas.winfo_rootx()
        canvas_y = self.canvas.winfo_rooty()
        canvas_x1 = self.start_x - canvas_x
        canvas_y1 = self.start_y - canvas_y
        canvas_x2 = self.current_x - canvas_x
        canvas_y2 = self.current_y - canvas_y
        
        # Draw new rectangle
        x1 = min(canvas_x1, canvas_x2)
        y1 = min(canvas_y1, canvas_y2)
        x2 = max(canvas_x1, canvas_x2)
        y2 = max(canvas_y1, canvas_y2)
        
        # Draw border
        self.selection_rect = self.canvas.create_rectangle(
            x1, y1, x2, y2,
            outline='white',
            width=2,
            fill='',
            stipple='gray50'
        )
        
    def close(self):
        """Close the region selector window."""
        if self.window:
            self.window.destroy()
            self.window = None

