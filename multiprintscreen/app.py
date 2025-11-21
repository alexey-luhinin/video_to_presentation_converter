"""Main application for multi-screenshot queue desktop app."""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageDraw
import json
import os
import sys
from typing import List, Optional
import threading
import zipfile
import io
from datetime import datetime

from screenshot import capture_full_screen, capture_region
from region_selector import RegionSelector
from hotkey_manager import HotkeyManager

try:
    import pystray
    from pystray import MenuItem as item
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False
    print("Warning: pystray not available. System tray functionality disabled.")


class ScreenshotApp:
    """Main application window for screenshot queue management."""
    
    def __init__(self, root):
        """
        Initialize the application.
        
        Args:
            root: Tkinter root window
        """
        self.root = root
        self.root.title("Multi Screenshot Queue")
        # Set initial and minimum window size to ensure all UI buttons are visible (including minimize button)
        self.root.geometry("1000x600")
        self.root.minsize(1000, 400)
        
        # Queue to store screenshots (FIFO - list with append/pop(0))
        self.screenshot_queue: List[Image.Image] = []
        
        # Current capture mode
        self.capture_mode = self._load_capture_mode()
        
        # Minimize mode state
        self.minimize_mode = False
        
        # System tray
        self.tray_icon = None
        self.tray_thread = None
        self._setup_tray()
        
        # Initialize hotkey manager
        self.hotkey_manager = HotkeyManager()
        try:
            self.hotkey_manager.start(self.on_hotkey_pressed)
            # Show status in console for debugging
            hotkey_str = "+".join(self.hotkey_manager.get_hotkey()).upper()
            print(f"Hotkey registered: {hotkey_str}")
            # Update status indicator after UI is created
            self.root.after(100, self._update_hotkey_status)
        except Exception as e:
            error_msg = f"Failed to register hotkey: {str(e)}\n\n" \
                       f"Possible causes:\n" \
                       f"- Another application is using the keyboard hook\n" \
                       f"- Administrator privileges may be required\n" \
                       f"- The hotkey combination may be in use\n\n" \
                       f"Try changing the hotkey in Settings."
            messagebox.showerror("Hotkey Registration Failed", error_msg)
            print(f"ERROR: {error_msg}")
            # Update status indicator
            self.root.after(100, self._update_hotkey_status)
        
        # Region selector
        self.region_selector: Optional[RegionSelector] = None
        
        # Create UI
        self._create_ui()
        
        # Update HUD
        self._update_hud()
        
        # Handle window close - minimize to tray instead
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Store state for tray restore
        self.was_minimized_before_tray = False
    
    def _create_tray_icon(self):
        """Create system tray icon image."""
        # Create a simple icon (camera/screenshot icon)
        width = height = 64
        image = Image.new('RGB', (width, height), color='white')
        draw = ImageDraw.Draw(image)
        
        # Draw a simple camera icon
        # Camera body
        draw.rectangle([10, 20, 54, 50], fill='black', outline='gray', width=2)
        # Lens
        draw.ellipse([22, 28, 42, 48], fill='lightblue', outline='darkblue', width=2)
        # Flash
        draw.rectangle([45, 15, 50, 20], fill='yellow')
        
        return image
    
    def _setup_tray(self):
        """Setup system tray icon."""
        if not TRAY_AVAILABLE:
            return
        
        try:
            # Create tray icon image
            icon_image = self._create_tray_icon()
            
            # Create menu
            menu = pystray.Menu(
                item('Show (Minimized)', self.restore_from_tray),
                item('Exit', self.quit_app)
            )
            
            # Create tray icon
            self.tray_icon = pystray.Icon(
                "Screenshot Queue",
                icon_image,
                "Multi Screenshot Queue",
                menu
            )
            
            # Set default action (double-click) to restore window
            self.tray_icon.default_action = self.restore_from_tray
            
            # Start tray icon in a separate thread
            def run_tray():
                self.tray_icon.run()
            
            self.tray_thread = threading.Thread(target=run_tray, daemon=True)
            self.tray_thread.start()
        except Exception as e:
            print(f"Failed to setup system tray: {e}")
            self.tray_icon = None
    
    def restore_from_tray(self, icon=None, item=None):
        """Restore window from tray in minimize mode."""
        # Schedule on main thread (tray callbacks run in different thread)
        self.root.after(0, self._do_restore_from_tray)
    
    def _do_restore_from_tray(self):
        """Actually restore window from tray in minimize mode (runs on main thread)."""
        # Store that we want minimize mode
        self.was_minimized_before_tray = True
        
        # Force minimize mode state
        self.minimize_mode = True
        
        # Show window first
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.root.update_idletasks()
        
        # Set geometry to minimized size immediately
        self.root.minsize(200, 35)
        self.root.geometry("200x35")
        self.root.resizable(False, False)
        self.root.update_idletasks()
        
        # Now apply minimize UI
        self._force_minimize_ui()
        
        # Force update to ensure everything is visible
        self.root.update_idletasks()
        self.root.update()
    
    def quit_app(self, icon=None, item=None):
        """Quit application completely."""
        # Schedule on main thread
        self.root.after(0, self._do_quit_app)
    
    def _do_quit_app(self):
        """Actually quit application (runs on main thread)."""
        if self.tray_icon:
            self.tray_icon.stop()
        self.hotkey_manager.stop()
        self.root.quit()
        self.root.destroy()
    
    def _load_capture_mode(self) -> str:
        """Load capture mode from config."""
        if os.path.exists('config.json'):
            try:
                with open('config.json', 'r') as f:
                    config = json.load(f)
                    return config.get('capture_mode', 'full')
            except (json.JSONDecodeError, IOError):
                pass
        return 'full'
    
    def _save_capture_mode(self):
        """Save capture mode to config."""
        if os.path.exists('config.json'):
            try:
                with open('config.json', 'r') as f:
                    config = json.load(f)
            except (json.JSONDecodeError, IOError):
                config = {}
        else:
            config = {}
        
        config['capture_mode'] = self.capture_mode
        
        try:
            with open('config.json', 'w') as f:
                json.dump(config, f, indent=2)
        except IOError:
            pass
    
    def _create_ui(self):
        """Create the user interface."""
        # Top frame with HUD and controls
        self.top_frame = ttk.Frame(self.root, padding="5")
        self.top_frame.pack(fill=tk.X)
        
        # HUD - Screenshot count (smaller font to save space)
        self.hud_label = ttk.Label(
            self.top_frame,
            text="Screenshots: 0",
            font=("Arial", 9)
        )
        self.hud_label.pack(side=tk.LEFT, padx=5)
        
        # Capture mode selection
        self.mode_frame = ttk.Frame(self.top_frame)
        self.mode_frame.pack(side=tk.LEFT, padx=10)
        
        ttk.Label(self.mode_frame, text="Mode:").pack(side=tk.LEFT, padx=2)
        self.mode_var = tk.StringVar(value=self.capture_mode)
        self.mode_full = ttk.Radiobutton(
            self.mode_frame,
            text="Full Screen",
            variable=self.mode_var,
            value="full",
            command=self.on_mode_changed
        )
        self.mode_full.pack(side=tk.LEFT, padx=2)
        
        self.mode_region = ttk.Radiobutton(
            self.mode_frame,
            text="Region",
            variable=self.mode_var,
            value="region",
            command=self.on_mode_changed
        )
        self.mode_region.pack(side=tk.LEFT, padx=2)
        
        # Capture button
        self.capture_btn = ttk.Button(
            self.top_frame,
            text="Capture Screenshot",
            command=self.capture_screenshot
        )
        self.capture_btn.pack(side=tk.LEFT, padx=5)
        
        # Settings button
        self.settings_btn = ttk.Button(
            self.top_frame,
            text="Settings",
            command=self.open_settings
        )
        self.settings_btn.pack(side=tk.LEFT, padx=5)
        
        # Hotkey status indicator
        self.hotkey_status_label = ttk.Label(
            self.top_frame,
            text="",
            font=("Arial", 9),
            foreground="green"
        )
        self.hotkey_status_label.pack(side=tk.LEFT, padx=5)
        self._update_hotkey_status()
        
        # Export all button
        self.export_all_btn = ttk.Button(
            self.top_frame,
            text="Export All",
            command=self.export_all
        )
        self.export_all_btn.pack(side=tk.LEFT, padx=5)
        
        # Clear all button
        self.clear_btn = ttk.Button(
            self.top_frame,
            text="Clear All",
            command=self.clear_all
        )
        self.clear_btn.pack(side=tk.LEFT, padx=5)
        
        # Minimize/Maximize toggle button
        self.minimize_btn = ttk.Button(
            self.top_frame,
            text="Minimize",
            command=self.toggle_minimize_mode
        )
        self.minimize_btn.pack(side=tk.RIGHT, padx=5)
        
        # Separator
        self.separator = ttk.Separator(self.root, orient=tk.HORIZONTAL)
        self.separator.pack(fill=tk.X, pady=5)
        
        # Scrollable frame for screenshots
        self.canvas_frame = ttk.Frame(self.root)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Canvas with scrollbar
        self.canvas = tk.Canvas(self.canvas_frame, bg="white")
        self.scrollbar = ttk.Scrollbar(self.canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bind mousewheel to canvas
        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self.canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        # Store references for minimize mode
        self.full_ui_elements = [
            self.mode_frame, self.capture_btn, self.settings_btn,
            self.hotkey_status_label, self.export_all_btn, self.clear_btn,
            self.separator, self.canvas_frame
        ]
        
    def on_mode_changed(self):
        """Handle capture mode change."""
        self.capture_mode = self.mode_var.get()
        self._save_capture_mode()
    
    def _update_hud(self):
        """Update the HUD with current screenshot count."""
        count = len(self.screenshot_queue)
        if self.minimize_mode:
            # In minimize mode, show more detailed buffer info
            # Calculate approximate size in bytes (width * height * bytes_per_pixel)
            total_bytes = 0
            for img in self.screenshot_queue:
                # Get bytes per pixel based on mode
                if img.mode in ('1', 'L', 'P'):
                    bytes_per_pixel = 1
                elif img.mode in ('RGB', 'YCbCr', 'LAB'):
                    bytes_per_pixel = 3
                elif img.mode in ('RGBA', 'CMYK', 'I', 'F'):
                    bytes_per_pixel = 4
                else:
                    bytes_per_pixel = 3  # Default estimate
                total_bytes += img.width * img.height * bytes_per_pixel
            
            size_mb = total_bytes / (1024 * 1024)  # Convert to MB
            if count > 0:
                self.hud_label.config(text=f"Buffer: {count} | {size_mb:.2f} MB", font=("Arial", 8))
            else:
                self.hud_label.config(text=f"Buffer: {count} | 0.00 MB", font=("Arial", 8))
        else:
            self.hud_label.config(text=f"Screenshots: {count}", font=("Arial", 9))
    
    def toggle_minimize_mode(self):
        """Toggle between minimize and normal mode."""
        self.minimize_mode = not self.minimize_mode
        
        if self.minimize_mode:
            # Ensure top_frame is visible first
            self.top_frame.pack(fill=tk.X)
            # Reduce padding for compact mode
            self.top_frame.configure(padding="2")
            
            # Hide full UI elements
            for element in self.full_ui_elements:
                try:
                    element.pack_forget()
                except:
                    pass
            
            # Unpack and repack HUD to ensure it's visible
            try:
                self.hud_label.pack_forget()
            except:
                pass
            self.hud_label.pack(side=tk.LEFT, padx=2)
            
            # Small capture button for minimize mode (icon)
            if not hasattr(self, 'minimize_capture_btn'):
                self.minimize_capture_btn = ttk.Button(
                    self.top_frame,
                    text="⚡",
                    width=3,
                    command=self.capture_screenshot
                )
            try:
                self.minimize_capture_btn.pack_forget()
            except:
                pass
            self.minimize_capture_btn.pack(side=tk.LEFT, padx=2)
            
            # Update minimize button (icon)
            try:
                self.minimize_btn.pack_forget()
            except:
                pass
            self.minimize_btn.config(text="⛶", width=3)
            self.minimize_btn.pack(side=tk.RIGHT, padx=2)
            
            # Resize window to minimal size
            self.root.minsize(200, 35)
            self.root.geometry("200x35")
            self.root.resizable(False, False)
            
            # Update HUD with buffer info
            self._update_hud()
            
            # Force update to ensure everything is visible
            self.root.update_idletasks()
            self.root.update()
        else:
            # Hide minimize mode capture button if it exists
            if hasattr(self, 'minimize_capture_btn'):
                try:
                    self.minimize_capture_btn.pack_forget()
                except:
                    pass
            
            # Ensure top_frame is visible
            self.top_frame.pack(fill=tk.X)
            # Restore normal padding
            self.top_frame.configure(padding="5")
            
            # Repack HUD
            try:
                self.hud_label.pack_forget()
            except:
                pass
            self.hud_label.pack(side=tk.LEFT, padx=5)
            
            # Show all UI elements
            self.mode_frame.pack(side=tk.LEFT, padx=10)
            self.capture_btn.pack(side=tk.LEFT, padx=5)
            self.settings_btn.pack(side=tk.LEFT, padx=5)
            self.hotkey_status_label.pack(side=tk.LEFT, padx=5)
            self.export_all_btn.pack(side=tk.LEFT, padx=5)
            self.clear_btn.pack(side=tk.LEFT, padx=5)
            self.separator.pack(fill=tk.X, pady=5)
            self.canvas_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            # Update minimize button
            try:
                self.minimize_btn.pack_forget()
            except:
                pass
            self.minimize_btn.config(text="Minimize", width=0)  # Reset width to default (0 = auto-size)
            self.minimize_btn.pack(side=tk.RIGHT, padx=5)
            
            # Restore window size
            self.root.minsize(1000, 400)
            self.root.geometry("1000x600")
            self.root.resizable(True, True)
            
            # Update HUD
            self._update_hud()
            
            # Force update
            self.root.update_idletasks()
            self.root.update()
    
    def _update_hotkey_status(self):
        """Update the hotkey status indicator."""
        if hasattr(self, 'hotkey_manager') and self.hotkey_manager._running:
            hotkey_str = "+".join(self.hotkey_manager.get_hotkey()).upper()
            self.hotkey_status_label.config(
                text=f"Hotkey: {hotkey_str} ✓",
                foreground="green"
            )
        else:
            self.hotkey_status_label.config(
                text="Hotkey: Not active ✗",
                foreground="red"
            )
    
    def on_hotkey_pressed(self):
        """Handle hotkey press - capture screenshot."""
        print("Hotkey pressed - capturing screenshot...")  # Debug output
        # Use after() to ensure thread-safe GUI update
        self.root.after(0, self.capture_screenshot)
    
    def capture_screenshot(self):
        """Capture a screenshot based on current mode."""
        if self.capture_mode == 'full':
            self._capture_full_screen()
        else:
            self._capture_region()
    
    def _restore_window(self):
        """Restore window while preserving minimize mode state."""
        # Store minimize mode state before deiconify
        was_minimized = self.minimize_mode
        
        self.root.deiconify()
        self.root.update_idletasks()
        
        # If we were in minimize mode, restore that state
        if was_minimized:
            # Force geometry first
            self.root.minsize(200, 35)
            self.root.geometry("200x35")
            self.root.resizable(False, False)
            self.root.update_idletasks()
            
            # Ensure top_frame is visible
            self.top_frame.pack(fill=tk.X)
            
            # Re-apply minimize mode UI state
            for element in self.full_ui_elements:
                element.pack_forget()
            
            self.hud_label.pack(side=tk.LEFT, padx=2)
            if hasattr(self, 'minimize_capture_btn'):
                self.minimize_capture_btn.pack(side=tk.LEFT, padx=2)
            self.minimize_btn.config(text="⛶", width=3)
            self.minimize_btn.pack(side=tk.RIGHT, padx=2)
            
            # Force update to ensure everything is applied
            self.root.update_idletasks()
    
    def _hide_all_windows(self):
        """Hide all application windows including toplevels."""
        # Hide all toplevel windows (settings, view windows, etc.)
        def hide_toplevels(parent):
            for widget in parent.winfo_children():
                if isinstance(widget, tk.Toplevel):
                    widget.withdraw()
                    widget.update_idletasks()
                # Recursively check children
                hide_toplevels(widget)
        
        hide_toplevels(self.root)
        
        # Hide main window
        self.root.withdraw()
        # Lower window to ensure it's behind everything
        self.root.lower()
        # Force multiple updates to ensure window is fully hidden
        self.root.update_idletasks()
        self.root.update()
        # Additional update to ensure Windows has processed the hide
        self.root.after(10, lambda: self.root.update_idletasks())
    
    def _capture_full_screen(self):
        """Capture full screen screenshot."""
        try:
            # Store window state before hiding
            was_minimized = self.minimize_mode
            
            # Only hide window if not in minimize mode (minimized window is small enough)
            if not was_minimized:
                # Hide all windows
                self._hide_all_windows()
                # Longer delay to ensure window is completely removed from screen
                # Windows may need extra time to fully hide the window
                self.root.after(300, lambda: self._do_full_capture(was_minimized))
            else:
                # In minimize mode, just capture without hiding
                self.root.after(50, lambda: self._do_full_capture(was_minimized))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to capture screenshot: {str(e)}")
            if not was_minimized:
                self._restore_window()
    
    def _do_full_capture(self, was_minimized=False):
        """Perform the actual full screen capture."""
        try:
            img = capture_full_screen()
            self._add_to_queue(img)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to capture screenshot: {str(e)}")
        finally:
            # Only restore if we actually hid the window
            if not was_minimized:
                self.root.after(50, lambda: self._restore_window_with_state(was_minimized))
    
    def _restore_window_with_state(self, was_minimized):
        """Restore window with specific minimize state."""
        # Deiconify first
        self.root.deiconify()
        
        if was_minimized:
            # Force minimize mode by directly calling the toggle logic
            # but first ensure we're in the right state
            if not self.minimize_mode:
                # Something went wrong, force it
                self.minimize_mode = True
            
            # Immediately set geometry
            self.root.minsize(200, 35)
            self.root.geometry("200x35")
            self.root.resizable(False, False)
            self.root.update_idletasks()
            self.root.update()
            
            # Now apply the minimize UI - do it synchronously
            self._force_minimize_ui()
        else:
            # Normal restore
            self.root.update_idletasks()
    
    def _force_minimize_ui(self):
        """Force apply minimize mode UI - synchronous version."""
        # Ensure we're in minimize mode
        self.minimize_mode = True
        
        # Ensure top_frame is packed and visible
        try:
            self.top_frame.pack_forget()
        except:
            pass
        self.top_frame.pack(fill=tk.X)
        # Reduce padding for compact mode
        self.top_frame.configure(padding="2")
        
        # Hide all full UI elements
        for element in self.full_ui_elements:
            try:
                element.pack_forget()
            except:
                pass
        
        # Repack minimize mode widgets - unpack first to avoid conflicts
        try:
            self.hud_label.pack_forget()
        except:
            pass
        self.hud_label.pack(side=tk.LEFT, padx=2)
        
        if not hasattr(self, 'minimize_capture_btn'):
            self.minimize_capture_btn = ttk.Button(
                self.top_frame,
                text="⚡",
                width=3,
                command=self.capture_screenshot
            )
        try:
            self.minimize_capture_btn.pack_forget()
        except:
            pass
        self.minimize_capture_btn.pack(side=tk.LEFT, padx=2)
        
        try:
            self.minimize_btn.pack_forget()
        except:
            pass
        self.minimize_btn.config(text="⛶", width=3)
        self.minimize_btn.pack(side=tk.RIGHT, padx=2)
        
        # Update HUD to show buffer info
        self._update_hud()
        
        # Force multiple updates to ensure everything is visible
        self.root.update_idletasks()
        self.root.update()
        self.root.update_idletasks()
        
        # One more update after a short delay to ensure HUD is visible
        self.root.after(50, lambda: self.root.update_idletasks())
    
    def _capture_region(self):
        """Capture region screenshot."""
        try:
            # Store window state before hiding
            was_minimized = self.minimize_mode
            
            # Only hide window if not in minimize mode
            if not was_minimized:
                # Hide main window
                self.root.withdraw()
                self.root.update()
            
            # Create region selector
            self.region_selector = RegionSelector(
                lambda x1, y1, x2, y2: self.on_region_selected(x1, y1, x2, y2, was_minimized),
                cancel_callback=lambda: self.on_region_cancelled(was_minimized)
            )
            self.root.after(100, self.region_selector.start_selection)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start region selection: {str(e)}")
            if not was_minimized:
                self._restore_window()
    
    def on_region_selected(self, x1, y1, x2, y2, was_minimized=False):
        """Handle region selection completion."""
        try:
            img = capture_region(x1, y1, x2, y2)
            self._add_to_queue(img)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to capture region: {str(e)}")
        finally:
            # Only restore if we actually hid the window
            if not was_minimized:
                self.root.after(50, lambda: self._restore_window_with_state(was_minimized))
            self.region_selector = None
    
    def on_region_cancelled(self, was_minimized=False):
        """Handle region selection cancellation."""
        # Only restore if we actually hid the window
        if not was_minimized:
            self.root.after(50, lambda: self._restore_window_with_state(was_minimized))
        self.region_selector = None
    
    def _add_to_queue(self, img: Image.Image):
        """
        Add screenshot to queue (FIFO - append to end).
        
        Args:
            img: PIL Image object
        """
        self.screenshot_queue.append(img)
        self._update_hud()
        self._refresh_display()
    
    def _refresh_display(self):
        """Refresh the screenshot display."""
        # Clear existing widgets
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        # Display screenshots (oldest first, newest last - queue order)
        for idx, img in enumerate(self.screenshot_queue):
            self._create_screenshot_widget(idx, img)
        
        # Update canvas scroll region
        self.canvas.update_idletasks()
        
        # Handle empty queue case - set proper scroll region
        if len(self.screenshot_queue) == 0:
            # When empty, ensure scrollable_frame has minimum size and set scroll region
            # This ensures the canvas background renders properly
            self.canvas.update_idletasks()
            canvas_width = max(self.canvas.winfo_width(), 1)
            canvas_height = max(self.canvas.winfo_height(), 1)
            
            # Ensure scrollable_frame has minimum width to match canvas
            # This helps with proper background rendering
            if canvas_width > 1:
                self.scrollable_frame.configure(width=canvas_width)
            
            # Set scroll region to match canvas viewport size
            if canvas_width > 1 and canvas_height > 1:
                self.canvas.configure(scrollregion=(0, 0, canvas_width, canvas_height))
            else:
                # Fallback: use a reasonable default size that matches typical viewport
                self.canvas.configure(scrollregion=(0, 0, 900, 400))
        else:
            # When there are screenshots, use bbox of all widgets
            # Reset scrollable_frame width to auto (let it size to content)
            self.scrollable_frame.configure(width=0)
            bbox = self.canvas.bbox("all")
            if bbox:
                self.canvas.configure(scrollregion=bbox)
            else:
                # Fallback if bbox is None - use canvas viewport size
                canvas_width = max(self.canvas.winfo_width(), 1)
                canvas_height = max(self.canvas.winfo_height(), 1)
                if canvas_width > 1 and canvas_height > 1:
                    self.canvas.configure(scrollregion=(0, 0, canvas_width, canvas_height))
                else:
                    self.canvas.configure(scrollregion=(0, 0, 900, 400))
        
        # Force canvas update to ensure proper rendering
        self.canvas.update_idletasks()
    
    def _create_screenshot_widget(self, index: int, img: Image.Image):
        """
        Create a widget for displaying a screenshot.
        
        Args:
            index: Index in queue
            img: PIL Image object
        """
        frame = ttk.Frame(self.scrollable_frame, relief=tk.RAISED, borderwidth=2)
        frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Create thumbnail (max 200px width)
        # IMPORTANT: Create a copy before thumbnailing to avoid modifying the original
        thumbnail_size = (200, 150)
        thumb_img = img.copy()
        thumb_img.thumbnail(thumbnail_size, Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(thumb_img)
        
        # Thumbnail label
        thumb_label = ttk.Label(frame, image=photo)
        thumb_label.image = photo  # Keep a reference
        thumb_label.pack(side=tk.LEFT, padx=5, pady=5)
        
        # Info and buttons frame
        info_frame = ttk.Frame(frame)
        info_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        # Screenshot info
        info_text = f"Screenshot #{index + 1}\nSize: {img.width}x{img.height}"
        info_label = ttk.Label(info_frame, text=info_text)
        info_label.pack(anchor=tk.W, pady=2)
        
        # Buttons frame
        btn_frame = ttk.Frame(info_frame)
        btn_frame.pack(anchor=tk.W, pady=5)
        
        # View button
        view_btn = ttk.Button(
            btn_frame,
            text="View",
            command=lambda idx=index: self.view_screenshot(idx)
        )
        view_btn.pack(side=tk.LEFT, padx=2)
        
        # Export button
        export_btn = ttk.Button(
            btn_frame,
            text="Export",
            command=lambda idx=index: self.export_screenshot(idx)
        )
        export_btn.pack(side=tk.LEFT, padx=2)
        
        # Delete button
        delete_btn = ttk.Button(
            btn_frame,
            text="Delete",
            command=lambda idx=index: self.delete_screenshot(idx)
        )
        delete_btn.pack(side=tk.LEFT, padx=2)
    
    def view_screenshot(self, index: int):
        """
        View a screenshot in full size.
        
        Args:
            index: Index in queue
        """
        if 0 <= index < len(self.screenshot_queue):
            img = self.screenshot_queue[index]
            
            # Create new window
            view_window = tk.Toplevel(self.root)
            view_window.title(f"Screenshot #{index + 1}")
            
            # Convert to PhotoImage
            photo = ImageTk.PhotoImage(img)
            
            # Create label with image
            img_label = ttk.Label(view_window, image=photo)
            img_label.image = photo  # Keep a reference
            img_label.pack(padx=10, pady=10)
            
            # Close button
            close_btn = ttk.Button(
                view_window,
                text="Close",
                command=view_window.destroy
            )
            close_btn.pack(pady=5)
    
    def export_screenshot(self, index: int):
        """
        Export a screenshot to file.
        
        Args:
            index: Index in queue
        """
        if 0 <= index < len(self.screenshot_queue):
            img = self.screenshot_queue[index]
            
            # Ask for file location
            filename = filedialog.asksaveasfilename(
                defaultextension=".png",
                filetypes=[
                    ("PNG files", "*.png"),
                    ("JPEG files", "*.jpg"),
                    ("All files", "*.*")
                ],
                title="Save Screenshot"
            )
            
            if filename:
                try:
                    img.save(filename)
                    messagebox.showinfo("Success", f"Screenshot saved to {filename}")
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to save screenshot: {str(e)}")
    
    def delete_screenshot(self, index: int):
        """
        Delete a screenshot from queue (FIFO - remove from front).
        
        Args:
            index: Index in queue
        """
        if 0 <= index < len(self.screenshot_queue):
            # Remove from queue (FIFO - pop from front)
            self.screenshot_queue.pop(index)
            self._update_hud()
            self._refresh_display()
    
    def export_all(self):
        """Export all screenshots as ZIP or PDF."""
        if len(self.screenshot_queue) == 0:
            messagebox.showwarning("No Screenshots", "No screenshots to export.")
            return
        
        # Create dialog to choose format and filename
        format_window = tk.Toplevel(self.root)
        format_window.title("Export All Screenshots")
        format_window.geometry("350x220")
        format_window.minsize(350, 220)  # Ensure all buttons are visible
        format_window.transient(self.root)
        format_window.grab_set()
        
        # Center the window
        format_window.update_idletasks()
        x = (format_window.winfo_screenwidth() // 2) - (350 // 2)
        y = (format_window.winfo_screenheight() // 2) - (220 // 2)
        format_window.geometry(f"350x220+{x}+{y}")
        
        ttk.Label(
            format_window,
            text=f"Export {len(self.screenshot_queue)} screenshot(s) as:",
            font=("Arial", 10)
        ).pack(pady=10)
        
        format_var = tk.StringVar(value="zip")
        
        format_frame = ttk.Frame(format_window)
        format_frame.pack(pady=5)
        
        ttk.Radiobutton(
            format_frame,
            text="ZIP Archive",
            variable=format_var,
            value="zip"
        ).pack(side=tk.LEFT, padx=10)
        
        ttk.Radiobutton(
            format_frame,
            text="PDF Document",
            variable=format_var,
            value="pdf"
        ).pack(side=tk.LEFT, padx=10)
        
        # Filename input
        filename_frame = ttk.Frame(format_window)
        filename_frame.pack(pady=15, padx=20, fill=tk.X)
        
        ttk.Label(
            filename_frame,
            text="File name:",
            font=("Arial", 9)
        ).pack(anchor=tk.W, pady=2)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"screenshots_{timestamp}"
        filename_var = tk.StringVar(value=default_name)
        
        filename_entry = ttk.Entry(filename_frame, textvariable=filename_var, width=30)
        filename_entry.pack(fill=tk.X, pady=2)
        filename_entry.select_range(0, tk.END)
        filename_entry.focus()
        
        def do_export():
            """Perform the export based on selected format."""
            custom_filename = filename_var.get().strip()
            if not custom_filename:
                messagebox.showwarning("Invalid Filename", "Please enter a filename.")
                return
            
            format_window.destroy()
            if format_var.get() == "zip":
                self.export_all_as_zip(custom_filename)
            else:
                self.export_all_as_pdf(custom_filename)
        
        button_frame = ttk.Frame(format_window)
        button_frame.pack(pady=10)
        
        ttk.Button(
            button_frame,
            text="Export",
            command=do_export
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            button_frame,
            text="Cancel",
            command=format_window.destroy
        ).pack(side=tk.LEFT, padx=5)
        
        # Bind Enter key to export
        format_window.bind('<Return>', lambda e: do_export())
    
    def export_all_as_zip(self, custom_filename: str = None):
        """Export all screenshots as a ZIP archive.
        
        Args:
            custom_filename: Custom filename (without extension) provided by user
        """
        if len(self.screenshot_queue) == 0:
            return
        
        # Use custom filename or generate default
        if custom_filename:
            default_filename = f"{custom_filename}.zip"
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_filename = f"screenshots_{timestamp}.zip"
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".zip",
            filetypes=[
                ("ZIP files", "*.zip"),
                ("All files", "*.*")
            ],
            title="Export All Screenshots as ZIP",
            initialfile=default_filename
        )
        
        if filename:
            try:
                with zipfile.ZipFile(filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for idx, img in enumerate(self.screenshot_queue):
                        # Convert image to bytes
                        img_bytes = io.BytesIO()
                        img.save(img_bytes, format='PNG')
                        img_bytes.seek(0)
                        
                        # Add to ZIP with numbered filename
                        zipf.writestr(
                            f"screenshot_{idx + 1:04d}.png",
                            img_bytes.read()
                        )
                
                messagebox.showinfo(
                    "Success",
                    f"Exported {len(self.screenshot_queue)} screenshot(s) to {filename}"
                )
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export ZIP: {str(e)}")
    
    def export_all_as_pdf(self, custom_filename: str = None):
        """Export all screenshots as a PDF document.
        
        Args:
            custom_filename: Custom filename (without extension) provided by user
        """
        if len(self.screenshot_queue) == 0:
            return
        
        # Use custom filename or generate default
        if custom_filename:
            default_filename = f"{custom_filename}.pdf"
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_filename = f"screenshots_{timestamp}.pdf"
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[
                ("PDF files", "*.pdf"),
                ("All files", "*.*")
            ],
            title="Export All Screenshots as PDF",
            initialfile=default_filename
        )
        
        if filename:
            try:
                # Convert all images to RGB if needed (PDF requires RGB)
                rgb_images = []
                for img in self.screenshot_queue:
                    if img.mode != 'RGB':
                        rgb_img = img.convert('RGB')
                    else:
                        rgb_img = img
                    rgb_images.append(rgb_img)
                
                # Save first image as PDF
                if len(rgb_images) > 0:
                    rgb_images[0].save(
                        filename,
                        "PDF",
                        resolution=100.0,
                        save_all=True,
                        append_images=rgb_images[1:] if len(rgb_images) > 1 else []
                    )
                
                messagebox.showinfo(
                    "Success",
                    f"Exported {len(self.screenshot_queue)} screenshot(s) to {filename}"
                )
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export PDF: {str(e)}")
    
    def clear_all(self):
        """Clear all screenshots from queue."""
        if len(self.screenshot_queue) > 0:
            if messagebox.askyesno("Confirm", "Clear all screenshots?"):
                self.screenshot_queue.clear()
                self._update_hud()
                self._refresh_display()
    
    def open_settings(self):
        """Open settings window for hotkey configuration."""
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Settings")
        settings_window.geometry("450x280")
        settings_window.minsize(450, 280)  # Ensure all buttons are visible
        settings_window.transient(self.root)
        settings_window.grab_set()
        
        # Current hotkey display
        current_hotkey = self.hotkey_manager.get_hotkey()
        hotkey_str = "+".join(current_hotkey).upper()
        
        ttk.Label(
            settings_window,
            text=f"Current Hotkey: {hotkey_str}",
            font=("Arial", 10, "bold")
        ).pack(pady=10)
        
        # Instructions
        instructions = (
            "Click the field below and press your desired hotkey combination.\n"
            "The keys will be detected automatically.\n"
            "Press Escape to cancel or clear the input."
        )
        ttk.Label(settings_window, text=instructions, justify=tk.LEFT).pack(pady=10, padx=20)
        
        # Input frame
        input_frame = ttk.Frame(settings_window)
        input_frame.pack(pady=10)
        
        ttk.Label(input_frame, text="New Hotkey:").pack(side=tk.LEFT, padx=5)
        hotkey_entry = ttk.Entry(input_frame, width=35, font=("Arial", 10), state="readonly")
        hotkey_entry.insert(0, "+".join(current_hotkey).upper())
        hotkey_entry.pack(side=tk.LEFT, padx=5)
        
        # Status label
        status_label = ttk.Label(
            settings_window,
            text="Click 'Press to Set' and then press your hotkey combination",
            font=("Arial", 9),
            foreground="gray"
        )
        status_label.pack(pady=5)
        
        # Key capture state
        capture_listener = None
        pressed_keys = set()
        detected_keys = []
        
        def convert_key_to_name(key):
            """Convert pynput key to string name."""
            from pynput import keyboard
            
            # Modifier keys
            if key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
                return 'ctrl'
            elif key == keyboard.Key.alt_l or key == keyboard.Key.alt_r:
                return 'alt'
            elif key == keyboard.Key.shift_l or key == keyboard.Key.shift_r:
                return 'shift'
            elif key == keyboard.Key.cmd_l or key == keyboard.Key.cmd_r:
                return 'win' if sys.platform == 'win32' else 'cmd'
            elif hasattr(key, 'char') and key.char:
                return key.char.lower()
            elif hasattr(key, 'name'):
                return key.name.lower()
            else:
                return None
        
        def on_key_press(key):
            """Handle key press during capture."""
            try:
                key_name = convert_key_to_name(key)
                if key_name:
                    if key_name in ['ctrl', 'alt', 'shift', 'win', 'cmd']:
                        pressed_keys.add(key_name)
                    elif key_name == 'esc':
                        # Cancel capture
                        stop_capture()
                        hotkey_entry.config(state="normal")
                        hotkey_entry.delete(0, tk.END)
                        hotkey_entry.insert(0, "+".join(current_hotkey).upper())
                        hotkey_entry.config(state="readonly")
                        status_label.config(text="Cancelled. Click 'Press to Set' to try again.", foreground="orange")
                    else:
                        # Final key pressed - complete the combination
                        if key_name not in pressed_keys:
                            all_keys = sorted(list(pressed_keys)) + [key_name]
                            detected_keys.clear()
                            detected_keys.extend(all_keys)
                            
                            # Update display
                            display_str = "+".join([k.upper() for k in all_keys])
                            hotkey_entry.config(state="normal")
                            hotkey_entry.delete(0, tk.END)
                            hotkey_entry.insert(0, display_str)
                            hotkey_entry.config(state="readonly")
                            status_label.config(text="Hotkey detected! Click Save to apply.", foreground="green")
                            
                            # Stop capture after a short delay
                            settings_window.after(200, stop_capture)
            except Exception:
                pass
        
        def on_key_release(key):
            """Handle key release during capture."""
            try:
                key_name = convert_key_to_name(key)
                if key_name in ['ctrl', 'alt', 'shift', 'win', 'cmd']:
                    pressed_keys.discard(key_name)
            except Exception:
                pass
        
        def start_capture(event=None):
            """Start capturing key presses."""
            nonlocal capture_listener, pressed_keys, detected_keys
            
            # Clear previous state
            pressed_keys.clear()
            detected_keys.clear()
            hotkey_entry.config(state="normal")
            hotkey_entry.delete(0, tk.END)
            hotkey_entry.insert(0, "Press your hotkey combination...")
            hotkey_entry.config(state="readonly")
            status_label.config(text="Listening for keys... (Press Escape to cancel)", foreground="blue")
            capture_btn.config(text="Listening...", state="disabled")
            
            # Temporarily stop the global hotkey listener
            was_running = self.hotkey_manager._running
            if was_running:
                self.hotkey_manager.stop()
            
            # Start temporary listener for key capture
            try:
                from pynput import keyboard
                capture_listener = keyboard.Listener(
                    on_press=on_key_press,
                    on_release=on_key_release,
                    suppress=False
                )
                capture_listener.start()
            except Exception as e:
                status_label.config(text=f"Error starting capture: {str(e)}", foreground="red")
                capture_btn.config(text="Press to Set", state="normal")
                if was_running:
                    self.hotkey_manager.start(self.on_hotkey_pressed)
        
        def stop_capture():
            """Stop capturing key presses."""
            nonlocal capture_listener
            
            if capture_listener:
                try:
                    capture_listener.stop()
                    capture_listener = None
                except Exception:
                    pass
            
            capture_btn.config(text="Press to Set", state="normal")
            
            # Restart global hotkey listener if it was running
            if not self.hotkey_manager._running:
                try:
                    self.hotkey_manager.start(self.on_hotkey_pressed)
                except Exception:
                    pass
        
        # Button to start capture (defined after functions)
        capture_btn = ttk.Button(
            input_frame,
            text="Press to Set",
            command=start_capture
        )
        capture_btn.pack(side=tk.LEFT, padx=5)
        
        def save_hotkey():
            """Save new hotkey configuration."""
            stop_capture()
            
            try:
                # Get keys from detected_keys or parse from entry
                if detected_keys:
                    keys = detected_keys
                else:
                    hotkey_str = hotkey_entry.get().strip()
                    if not hotkey_str or hotkey_str == "Press your hotkey combination...":
                        messagebox.showwarning("No Hotkey", "Please press a hotkey combination first.")
                        return
                    # Parse from display format (e.g., "CTRL+SHIFT+S")
                    keys = [k.strip().lower() for k in hotkey_str.replace("+", ",").split(",")]
                
                if len(keys) < 1:
                    messagebox.showerror("Error", "Hotkey must have at least one key")
                    return
                
                self.hotkey_manager.set_hotkey(keys)
                hotkey_str_display = "+".join([k.upper() for k in keys])
                messagebox.showinfo("Success", f"Hotkey set to: {hotkey_str_display}")
                self._update_hotkey_status()
                settings_window.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to set hotkey: {str(e)}")
        
        # Button frame
        button_frame = ttk.Frame(settings_window)
        button_frame.pack(pady=15)
        
        # Save button
        save_btn = ttk.Button(
            button_frame,
            text="Save",
            command=save_hotkey
        )
        save_btn.pack(side=tk.LEFT, padx=5)
        
        # Cancel button
        cancel_btn = ttk.Button(
            button_frame,
            text="Cancel",
            command=lambda: (stop_capture(), settings_window.destroy())
        )
        cancel_btn.pack(side=tk.LEFT, padx=5)
        
        # Clean up on window close
        def on_settings_close():
            stop_capture()
            settings_window.destroy()
        
        settings_window.protocol("WM_DELETE_WINDOW", on_settings_close)
    
    def on_closing(self):
        """Handle window closing - minimize to tray instead."""
        if TRAY_AVAILABLE and self.tray_icon:
            # Store minimize state before hiding
            self.was_minimized_before_tray = self.minimize_mode
            # Hide window to tray
            self.root.withdraw()
        else:
            # No tray available, actually quit
            self.hotkey_manager.stop()
            self.root.destroy()


def main():
    """Main entry point."""
    root = tk.Tk()
    app = ScreenshotApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

