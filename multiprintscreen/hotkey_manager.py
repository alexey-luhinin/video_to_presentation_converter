"""Hotkey manager for global hotkey registration."""
import json
import os
import sys
import time
from typing import List, Callable, Optional
from pynput import keyboard


class HotkeyManager:
    """Manages global hotkey registration and handling."""
    
    def __init__(self, config_path: str = 'config.json'):
        """
        Initialize the hotkey manager.
        
        Args:
            config_path: Path to configuration file
        """
        self.config_path = config_path
        self.hotkey = self._load_config()
        self.callback: Optional[Callable] = None
        self.hotkey_obj: Optional[keyboard.HotKey] = None
        self.listener: Optional[keyboard.Listener] = None
        self._running = False
        
    def _load_config(self) -> List[str]:
        """
        Load hotkey configuration from file.
        
        Returns:
            List of key names (default: ['shift', 's'])
        """
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                    return config.get('hotkey', ['shift', 's'])
            except (json.JSONDecodeError, IOError):
                pass
        return ['shift', 's']
    
    def _save_config(self):
        """Save hotkey configuration to file."""
        config = {
            'hotkey': self.hotkey,
            'capture_mode': getattr(self, 'capture_mode', 'full')
        }
        try:
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)
        except IOError:
            pass
    
    def set_hotkey(self, keys: List[str]):
        """
        Set a new hotkey combination.
        
        Args:
            keys: List of key names (e.g., ['ctrl', 'shift', 's'])
        """
        self.hotkey = keys
        self._save_config()
        if self._running:
            self.stop()
            self.start(self.callback)
    
    def get_hotkey(self) -> List[str]:
        """
        Get current hotkey combination.
        
        Returns:
            List of key names
        """
        return self.hotkey.copy()
    
    def _on_activate(self):
        """Handle hotkey activation."""
        print("Hotkey activated!")  # Debug output
        if self.callback:
            try:
                self.callback()
            except Exception as e:
                print(f"Error in hotkey callback: {e}")
    
    def start(self, callback: Callable):
        """
        Start listening for hotkey presses.
        
        Args:
            callback: Function to call when hotkey is pressed
        """
        if self._running:
            self.stop()
            
        self.callback = callback
        
        # Convert hotkey list to pynput format
        # Map modifier names to pynput key objects
        modifier_map = {
            'ctrl': keyboard.Key.ctrl,
            'alt': keyboard.Key.alt,
            'shift': keyboard.Key.shift,
            'cmd': keyboard.Key.cmd,
        }
        
        # Windows key handling - use cmd on Windows, cmd on macOS
        if sys.platform == 'win32':
            modifier_map['win'] = keyboard.Key.cmd
        else:
            modifier_map['win'] = keyboard.Key.cmd
        
        # Build hotkey combination
        hotkey_combo = []
        has_shift = 'shift' in [k.lower().strip() for k in self.hotkey]
        
        for k in self.hotkey:
            k_lower = k.lower().strip()
            if k_lower in modifier_map:
                hotkey_combo.append(modifier_map[k_lower])
            else:
                # Regular key - convert to KeyCode
                if len(k_lower) == 1:
                    # If shift is in the combo, use the character as-is (pynput handles case)
                    # Otherwise use lowercase
                    char_to_use = k_lower
                    hotkey_combo.append(keyboard.KeyCode.from_char(char_to_use))
                else:
                    # Try to find special key (like 'f1', 'space', etc.)
                    try:
                        # Convert to proper attribute name (e.g., 'f1' -> 'f1', 'space' -> 'space')
                        key_attr = k_lower
                        hotkey_combo.append(getattr(keyboard.Key, key_attr))
                    except AttributeError:
                        # If not found, try as a single character
                        if len(k_lower) == 1:
                            hotkey_combo.append(keyboard.KeyCode.from_char(k_lower))
                        else:
                            # Last resort: try to use the first character
                            hotkey_combo.append(keyboard.KeyCode.from_char(k_lower[0]))
        
        # Debug: print the hotkey combo
        print(f"DEBUG: Hotkey combo created: {[str(k) for k in hotkey_combo]}")
        
        # Create HotKey object
        self.hotkey_obj = keyboard.HotKey(
            hotkey_combo,
            self._on_activate
        )
        
        # Start listener with proper error handling
        # Track pressed keys for debugging and manual detection
        self._debug_keys_pressed = set()
        self._currently_pressed = set()
        
        # Store expected keys for manual matching
        self._expected_keys = set()
        for k in hotkey_combo:
            self._expected_keys.add(k)
        
        def normalize_key(key):
            """Normalize key for comparison."""
            # Handle Key objects
            if isinstance(key, keyboard.Key):
                return key
            # Handle KeyCode objects
            elif hasattr(key, 'char') and key.char:
                # For character keys, compare the char
                return keyboard.KeyCode.from_char(key.char.lower())
            elif hasattr(key, 'vk'):
                # For virtual key codes, use the vk
                return key
            return key
        
        def check_hotkey_match():
            """Manually check if currently pressed keys match the hotkey."""
            try:
                if len(self._currently_pressed) < len(hotkey_combo):
                    return
                
                # Get currently pressed keys as a set for comparison
                pressed_set = set()
                for key in self._currently_pressed:
                    # Normalize modifier keys
                    if key == keyboard.Key.shift_l or key == keyboard.Key.shift_r:
                        pressed_set.add(keyboard.Key.shift)
                    elif key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
                        pressed_set.add(keyboard.Key.ctrl)
                    elif key == keyboard.Key.alt_l or key == keyboard.Key.alt_r:
                        pressed_set.add(keyboard.Key.alt)
                    elif key == keyboard.Key.cmd_l or key == keyboard.Key.cmd_r:
                        pressed_set.add(keyboard.Key.cmd)
                    else:
                        pressed_set.add(key)
                
                # Check if all required keys are pressed
                required_set = set(hotkey_combo)
                
                # For character keys, compare by char value
                pressed_chars = {k.char.lower() if hasattr(k, 'char') and k.char else None for k in pressed_set if not isinstance(k, keyboard.Key)}
                required_chars = {k.char.lower() if hasattr(k, 'char') and k.char else None for k in required_set if not isinstance(k, keyboard.Key)}
                
                # Check modifiers match
                pressed_mods = {k for k in pressed_set if isinstance(k, keyboard.Key)}
                required_mods = {k for k in required_set if isinstance(k, keyboard.Key)}
                
                # Check regular keys match (by char)
                chars_match = len(required_chars) == 0 or (pressed_chars & required_chars) == required_chars
                mods_match = pressed_mods == required_mods
                
                if chars_match and mods_match and len(pressed_set) == len(required_set):
                    print("DEBUG: Manual hotkey match detected!")
                    # Use a small delay to avoid multiple triggers
                    import threading
                    if not hasattr(self, '_last_trigger_time') or time.time() - self._last_trigger_time > 0.5:
                        self._last_trigger_time = time.time()
                        self._on_activate()
            except Exception as e:
                print(f"DEBUG: Error in check_hotkey_match: {e}")
                import traceback
                traceback.print_exc()
        
        def on_press(key):
            try:
                # Debug: show what keys are being pressed
                key_str = str(key)
                if key_str not in self._debug_keys_pressed:
                    self._debug_keys_pressed.add(key_str)
                    print(f"DEBUG: Key pressed: {key_str}")
                
                # Track currently pressed keys
                self._currently_pressed.add(key)
                
                # Try pynput's HotKey first
                if self.hotkey_obj:
                    try:
                        self.hotkey_obj.press(key)
                    except:
                        pass
                
                # Also try manual matching as fallback
                check_hotkey_match()
            except (AttributeError, Exception) as e:
                print(f"DEBUG: Error in on_press: {e}")
                
        def on_release(key):
            try:
                key_str = str(key)
                if key_str in self._debug_keys_pressed:
                    self._debug_keys_pressed.remove(key_str)
                    print(f"DEBUG: Key released: {key_str}")
                
                # Remove from currently pressed
                self._currently_pressed.discard(key)
                
                if self.hotkey_obj:
                    try:
                        self.hotkey_obj.release(key)
                    except:
                        pass
            except (AttributeError, Exception) as e:
                print(f"DEBUG: Error in on_release: {e}")
        
        # Store hotkey combo for debugging
        self._hotkey_combo = hotkey_combo
        
        try:
            self.listener = keyboard.Listener(
                on_press=on_press,
                on_release=on_release,
                suppress=False
            )
            # Don't set as daemon on Windows - it can cause issues with keyboard listeners
            if sys.platform != 'win32':
                self.listener.daemon = True
            self.listener.start()
            # Give the listener more time to initialize (especially important on Windows)
            time.sleep(0.3)
            # Verify listener is running
            if not self.listener.running:
                raise RuntimeError("Keyboard listener failed to start - it may be blocked by another application or require administrator privileges")
            self._running = True
            # Debug: print hotkey info
            hotkey_str = "+".join([str(k) for k in hotkey_combo])
            print(f"Hotkey listener started successfully. Listening for: {hotkey_str}")
            print(f"DEBUG: Press your hotkey combination to test. You should see 'DEBUG: Key pressed' messages.")
        except Exception as e:
            self._running = False
            if self.listener:
                try:
                    self.listener.stop()
                except:
                    pass
            self.listener = None
            error_msg = str(e)
            if "OSError" in str(type(e)) or "Permission" in error_msg:
                error_msg += " (May need administrator privileges on Windows)"
            raise RuntimeError(f"Failed to start hotkey listener: {error_msg}")
    
    def stop(self):
        """Stop listening for hotkey presses."""
        if self.listener:
            try:
                self.listener.stop()
                # Wait a moment for the listener to stop (especially important on Windows)
                time.sleep(0.1)
            except Exception:
                pass
            self.listener = None
        self.hotkey_obj = None
        self._running = False

