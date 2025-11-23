"""
Video processing module for extracting frames and detecting scene changes.
Optimized for large static videos like webinars.
Uses ML-based feature extraction for accurate and fast scene change detection.
"""

import cv2
import numpy as np
from typing import List, Tuple, Dict, Optional, Callable
import io
from PIL import Image
import time
from skimage.metrics import structural_similarity as ssim

# Optional TensorFlow imports - will be imported only if available
try:
    import tensorflow as tf
    from tensorflow.keras.applications import MobileNet
    from tensorflow.keras.applications.mobilenet import preprocess_input
    from tensorflow.keras.models import Model
    TENSORFLOW_AVAILABLE = True
except (ImportError, OSError, RuntimeError) as e:
    # Catch ImportError, DLL load errors (OSError), and other runtime errors
    TENSORFLOW_AVAILABLE = False
    print(f"TensorFlow not available: {e}. ML-based feature extraction will be disabled.")
    print("The application will use SSIM-based scene detection instead.")


class VideoProcessor:
    """Processes video files and detects scene changes using ML-based feature extraction."""
    
    def __init__(self, change_threshold: float = 0.3, min_frame_interval: int = 30, use_ml: bool = True, frame_skip: int = 1):
        """
        Initialize video processor.
        
        Args:
            change_threshold: Threshold for scene change detection (0.0-1.0)
                              Lower values = more sensitive (detects smaller changes)
            min_frame_interval: Minimum frames between scene changes (prevents duplicates)
            use_ml: Whether to use ML-based feature extraction (faster and more accurate)
            frame_skip: Process every Nth frame (1 = every frame, 2 = every other frame, etc.)
                       Higher values = faster processing but may miss rapid scene changes
        """
        self.change_threshold = change_threshold
        self.min_frame_interval = min_frame_interval
        self.frame_skip = max(1, frame_skip)  # Ensure at least 1
        self.frames = []
        self.frame_metadata = []
        self.use_ml = use_ml
        
        # Initialize MobileNet feature extractor if using ML
        self.feature_model = None
        self.feature_extract_fn = None
        if self.use_ml:
            if not TENSORFLOW_AVAILABLE:
                print("TensorFlow is not available. Falling back to SSIM-only mode.")
                self.use_ml = False
            else:
                try:
                    # Load MobileNet without top classification layer
                    base_model = MobileNet(weights='imagenet', include_top=False, input_shape=(224, 224, 3), pooling='avg')
                    # MobileNet with pooling='avg' already includes global average pooling
                    self.feature_model = base_model
                    # Disable training to speed up inference
                    self.feature_model.trainable = False
                    # Compile with optimizations for faster inference
                    self.feature_model.compile()
                    # Create optimized inference function using tf.function for faster execution
                    @tf.function(reduce_retracing=True)
                    def extract_features(images):
                        return self.feature_model(images, training=False)
                    self.feature_extract_fn = extract_features
                    print("ML-based feature extractor initialized (MobileNet) with optimizations")
                except Exception as e:
                    print(f"Warning: Could not initialize ML model: {e}. Falling back to SSIM-only mode.")
                    self.use_ml = False
    
    
    def extract_frames_with_changes(self, video_path: str, progress_callback: Optional[Callable] = None, stop_check: Optional[Callable] = None) -> List[Dict]:
        """
        Extract frames from video where scene changes are detected.
        
        Args:
            video_path: Path to video file
            progress_callback: Optional callback function to report progress.
                             Called with dict containing: stage, current_frame, total_frames,
                             percentage, frames_detected, fps, elapsed_time, estimated_remaining
            stop_check: Optional callback function to check if processing should stop.
                       Should return True if processing should stop.
            
        Returns:
            List of frame dictionaries with image data and metadata
        """
        start_time = time.time()
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            raise ValueError(f"Could not open video file: {video_path}")
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        video_duration = total_frames / fps if fps > 0 else 0
        
        # Report initial progress
        if progress_callback:
            progress_callback({
                'stage': 'initializing',
                'current_frame': 0,
                'total_frames': total_frames,
                'percentage': 0.0,
                'frames_detected': 0,
                'fps': fps,
                'video_duration': video_duration,
                'elapsed_time': 0.0,
                'estimated_remaining': 0.0,
                'processing_speed': 0.0
            })
        
        frames = []
        prev_frame_rgb = None
        prev_frame_features = None
        frame_count = 0
        processed_frame_count = 0  # Count of frames actually processed (after skipping)
        last_change_processed_frame = -self.min_frame_interval  # Track processed frame number of last change
        last_progress_update = 0
        
        # Adjust total frames estimate based on frame skipping
        effective_total_frames = total_frames // self.frame_skip + (1 if total_frames % self.frame_skip > 0 else 0)
        
        print(f"Processing video: {total_frames} frames at {fps} FPS (processing every {self.frame_skip} frame(s))")
        
        while True:
            # Check if stop was requested
            if stop_check and stop_check():
                print("Processing stopped by user request")
                cap.release()
                if progress_callback:
                    progress_callback({
                        'stage': 'stopped',
                        'current_frame': frame_count,
                        'total_frames': total_frames,
                        'percentage': (frame_count / total_frames) * 100 if total_frames > 0 else 0,
                        'frames_detected': len(frames),
                        'fps': fps,
                        'video_duration': video_duration,
                        'elapsed_time': time.time() - start_time,
                        'estimated_remaining': 0.0,
                        'processing_speed': 0.0,
                        'stopped': True,
                        'message': 'Processing stopped by user. You can continue processing to extract more frames.'
                    })
                return frames
            
            ret, frame = cap.read()
            if not ret:
                break
            
            # Skip frames based on frame_skip parameter
            if frame_count % self.frame_skip != 0:
                frame_count += 1
                continue
            
            # Convert BGR to RGB for consistency
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            processed_frame_count += 1
            
            # Early exit optimization: skip feature extraction if we're within min_frame_interval
            # Calculate minimum processed frames needed between changes
            min_processed_interval = max(1, self.min_frame_interval // self.frame_skip)
            frames_since_last_change = processed_frame_count - last_change_processed_frame - 1
            if frames_since_last_change < min_processed_interval:
                # Skip processing, just update frame count
                frame_count += 1
                continue
            
            # Check for scene change using ML-based or SSIM-based detection
            is_scene_change = False
            if self.use_ml and self.feature_model is not None:
                # ML-based detection using MobileNet features
                if prev_frame_features is not None:
                    # Extract features from current frame using optimized function
                    frame_resized = cv2.resize(frame_rgb, (224, 224))
                    frame_preprocessed = preprocess_input(frame_resized[np.newaxis, ...])
                    
                    # Use optimized tf.function for faster inference
                    if self.feature_extract_fn is not None:
                        current_features = self.feature_extract_fn(tf.constant(frame_preprocessed)).numpy()[0]
                    else:
                        current_features = self.feature_model(frame_preprocessed, training=False).numpy()[0]
                    
                    # Normalize features for cosine similarity
                    current_features_norm = current_features / (np.linalg.norm(current_features) + 1e-8)
                    prev_features_norm = prev_frame_features / (np.linalg.norm(prev_frame_features) + 1e-8)
                    
                    # Calculate cosine similarity (1.0 = identical, 0.0 = completely different)
                    cosine_sim = np.dot(current_features_norm, prev_features_norm)
                    difference = 1.0 - cosine_sim
                    
                    # Check if enough frames have passed and change is significant
                    # Note: Removed redundant SSIM computation for speed
                    if difference > self.change_threshold:
                        is_scene_change = True
                        last_change_frame = frame_count
                        last_change_processed_frame = processed_frame_count
                    
                    prev_frame_features = current_features
                else:
                    # Always include first frame
                    is_scene_change = True
                    last_change_frame = frame_count
                    last_change_processed_frame = processed_frame_count
                    # Extract features for first frame
                    frame_resized = cv2.resize(frame_rgb, (224, 224))
                    frame_preprocessed = preprocess_input(frame_resized[np.newaxis, ...])
                    # Use optimized function for faster inference
                    if self.feature_extract_fn is not None:
                        prev_frame_features = self.feature_extract_fn(tf.constant(frame_preprocessed)).numpy()[0]
                    else:
                        prev_frame_features = self.feature_model(frame_preprocessed, training=False).numpy()[0]
            else:
                # Fallback to SSIM-based detection (faster than histogram, more accurate)
                if prev_frame_rgb is not None:
                    # Convert to grayscale for SSIM
                    frame_gray = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2GRAY)
                    prev_gray = cv2.cvtColor(prev_frame_rgb, cv2.COLOR_RGB2GRAY)
                    
                    # Resize for faster computation (SSIM is computationally expensive)
                    frame_gray_small = cv2.resize(frame_gray, (256, 256))
                    prev_gray_small = cv2.resize(prev_gray, (256, 256))
                    
                    # Calculate SSIM (1.0 = identical, 0.0 = completely different)
                    ssim_score = ssim(prev_gray_small, frame_gray_small, data_range=255)
                    difference = 1.0 - ssim_score
                    
                    # Check if enough frames have passed and change is significant
                    if difference > self.change_threshold:
                        is_scene_change = True
                        last_change_frame = frame_count
                        last_change_processed_frame = processed_frame_count
                else:
                    # Always include first frame
                    is_scene_change = True
                    last_change_frame = frame_count
                    last_change_processed_frame = processed_frame_count
                
                # Store current frame for next comparison
                prev_frame_rgb = frame_rgb.copy()
            
            # Store frame if scene change detected
            if is_scene_change:
                timestamp = frame_count / fps if fps > 0 else 0
                
                # Convert to PIL Image for easy handling
                pil_image = Image.fromarray(frame_rgb)
                
                # Store frame data
                frame_data = {
                    'frame_number': frame_count,
                    'timestamp': timestamp,
                    'image': pil_image,
                    'width': frame_rgb.shape[1],
                    'height': frame_rgb.shape[0]
                }
                frames.append(frame_data)
                print(f"Scene change detected at frame {frame_count} (time: {timestamp:.2f}s)")
            
            frame_count += 1
            
            # Update progress more frequently (every 10 processed frames or every 0.5 seconds)
            current_time = time.time()
            elapsed_time = current_time - start_time
            time_since_last_update = current_time - last_progress_update
            
            if processed_frame_count % 10 == 0 or time_since_last_update >= 0.5:
                percentage = (frame_count / total_frames) * 100 if total_frames > 0 else 0
                processing_speed = processed_frame_count / elapsed_time if elapsed_time > 0 else 0
                estimated_remaining = (effective_total_frames - processed_frame_count) / processing_speed if processing_speed > 0 else 0
                
                if progress_callback:
                    progress_callback({
                        'stage': 'extracting',
                        'current_frame': frame_count,
                        'total_frames': total_frames,
                        'percentage': percentage,
                        'frames_detected': len(frames),
                        'fps': fps,
                        'video_duration': video_duration,
                        'elapsed_time': elapsed_time,
                        'estimated_remaining': estimated_remaining,
                        'processing_speed': processing_speed
                    })
                
                last_progress_update = current_time
        
        cap.release()
        total_elapsed = time.time() - start_time
        
        # Report completion
        if progress_callback:
            progress_callback({
                'stage': 'completed',
                'current_frame': total_frames,
                'total_frames': total_frames,
                'percentage': 100.0,
                'frames_detected': len(frames),
                'fps': fps,
                'video_duration': video_duration,
                'elapsed_time': total_elapsed,
                'estimated_remaining': 0.0,
                'processing_speed': total_frames / total_elapsed if total_elapsed > 0 else 0
            })
        
        print(f"Extracted {len(frames)} frames from {frame_count} total frames in {total_elapsed:.2f}s")
        
        self.frames = frames
        return frames
    
    def get_frame_thumbnail(self, frame_data: Dict, max_size: Tuple[int, int] = (400, 300)) -> bytes:
        """
        Generate thumbnail bytes for a frame.
        
        Args:
            frame_data: Frame dictionary with 'image' key
            max_size: Maximum thumbnail size (width, height)
            
        Returns:
            JPEG image bytes
        """
        image = frame_data['image'].copy()  # Copy to avoid modifying original
        # Use LANCZOS resampling for high quality thumbnails
        image.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Convert to bytes with high quality
        img_bytes = io.BytesIO()
        image.save(img_bytes, format='JPEG', quality=92, optimize=True)
        img_bytes.seek(0)
        return img_bytes.getvalue()
    
    def get_all_thumbnails(self, max_size: Tuple[int, int] = (400, 300)) -> List[bytes]:
        """Get thumbnails for all extracted frames."""
        return [self.get_frame_thumbnail(frame, max_size) for frame in self.frames]
    
    def get_frame_by_index(self, index: int) -> Dict:
        """Get frame data by index."""
        if 0 <= index < len(self.frames):
            return self.frames[index]
        raise IndexError(f"Frame index {index} out of range")
    
    def remove_duplicate_frames(self, frames: List[Dict], similarity_threshold: float = 0.95, progress_callback: Optional[Callable] = None) -> List[Dict]:
        """
        Remove duplicate frames from extracted frames by comparing visual similarity.
        
        Args:
            frames: List of frame dictionaries with image data
            similarity_threshold: Threshold for considering frames as duplicates (0.0-1.0)
                                 Higher values = more strict (0.95 = 95% similar = duplicate)
            progress_callback: Optional callback function to report progress
        
        Returns:
            List of unique frames (duplicates removed)
        """
        if not frames or len(frames) <= 1:
            return frames
        
        if progress_callback:
            progress_callback({
                'stage': 'removing_duplicates',
                'current_frame': 0,
                'total_frames': len(frames),
                'percentage': 0.0,
                'frames_detected': len(frames),
                'frames_after_dedup': 0
            })
        
        print(f"Reviewing {len(frames)} frames for duplicates (similarity threshold: {similarity_threshold})...")
        
        unique_frames = [frames[0]]  # Always keep the first frame
        total_frames = len(frames)
        
        # Extract features or prepare comparison data for all frames
        # Use dictionary mapping for easier lookup
        frame_features_dict = {}  # Maps frame index to features
        frame_images_dict = {}    # Maps frame index to numpy array
        
        for idx, frame in enumerate(frames):
            if 'image' not in frame:
                continue
            
            frame_image = frame['image']
            if not isinstance(frame_image, Image.Image):
                continue
            
            # Convert PIL Image to numpy array for comparison
            frame_array = np.array(frame_image)
            frame_images_dict[idx] = frame_array
            
            # Extract features if ML is available, otherwise prepare for SSIM
            if self.use_ml and self.feature_model is not None and TENSORFLOW_AVAILABLE:
                try:
                    # Resize and preprocess for feature extraction
                    # PIL Image is already RGB, so convert to BGR for OpenCV if needed
                    if len(frame_array.shape) == 3:
                        frame_bgr = cv2.cvtColor(frame_array, cv2.COLOR_RGB2BGR)
                    else:
                        frame_bgr = frame_array
                    frame_resized = cv2.resize(frame_bgr, (224, 224))
                    frame_preprocessed = preprocess_input(frame_resized[np.newaxis, ...])
                    
                    # Extract features
                    if self.feature_extract_fn is not None:
                        features = self.feature_extract_fn(tf.constant(frame_preprocessed)).numpy()[0]
                    else:
                        features = self.feature_model(frame_preprocessed, training=False).numpy()[0]
                    
                    # Normalize features
                    features_norm = features / (np.linalg.norm(features) + 1e-8)
                    frame_features_dict[idx] = features_norm
                except (NameError, Exception) as e:
                    print(f"Warning: Could not extract ML features for frame {idx}: {e}")
                    frame_features_dict[idx] = None
            else:
                frame_features_dict[idx] = None
        
        # Compare each frame with unique frames already selected
        duplicates_removed = 0
        
        for idx in range(1, len(frames)):
            if progress_callback and idx % 10 == 0:
                progress_callback({
                    'stage': 'removing_duplicates',
                    'current_frame': idx,
                    'total_frames': total_frames,
                    'percentage': (idx / total_frames) * 100,
                    'frames_detected': total_frames,
                    'frames_after_dedup': len(unique_frames)
                })
            
            current_frame = frames[idx]
            if 'image' not in current_frame:
                continue
            
            current_image = current_frame['image']
            if not isinstance(current_image, Image.Image):
                continue
            
            is_duplicate = False
            
            # Get features/image for current frame
            current_features = frame_features_dict.get(idx)
            current_array = frame_images_dict.get(idx)
            
            # Compare with all unique frames
            for unique_frame_idx, unique_frame in enumerate(unique_frames):
                # Get the index of the unique frame in the original frames list
                # Find it by matching frame_number or by position
                unique_list_idx = None
                for i, f in enumerate(frames):
                    if f == unique_frame:
                        unique_list_idx = i
                        break
                
                if unique_list_idx is None:
                    continue
                
                # Get features/image for unique frame
                unique_features = frame_features_dict.get(unique_list_idx)
                unique_array = frame_images_dict.get(unique_list_idx)
                
                # Compare using ML features if available
                if self.use_ml and current_features is not None and unique_features is not None:
                    try:
                        # Calculate cosine similarity
                        cosine_sim = np.dot(current_features, unique_features)
                        similarity = cosine_sim  # 1.0 = identical, 0.0 = completely different
                        
                        if similarity >= similarity_threshold:
                            is_duplicate = True
                            duplicates_removed += 1
                            print(f"Duplicate detected: Frame {current_frame['frame_number']} (t={current_frame['timestamp']:.2f}s) is similar to Frame {unique_frame['frame_number']} (t={unique_frame['timestamp']:.2f}s) [similarity: {similarity:.3f}]")
                            break
                    except Exception as e:
                        print(f"Warning: Error comparing frames {idx} and {unique_list_idx} with ML features: {e}")
                        # Fall back to SSIM
                        pass
                
                # Fallback to SSIM comparison
                if not is_duplicate and current_array is not None and unique_array is not None:
                    try:
                        # Convert to grayscale for SSIM
                        if len(current_array.shape) == 3:
                            current_gray = cv2.cvtColor(current_array, cv2.COLOR_RGB2GRAY)
                        else:
                            current_gray = current_array
                        
                        if len(unique_array.shape) == 3:
                            unique_gray = cv2.cvtColor(unique_array, cv2.COLOR_RGB2GRAY)
                        else:
                            unique_gray = unique_array
                        
                        # Resize for faster computation
                        current_gray_small = cv2.resize(current_gray, (256, 256))
                        unique_gray_small = cv2.resize(unique_gray, (256, 256))
                        
                        # Calculate SSIM
                        ssim_score = ssim(unique_gray_small, current_gray_small, data_range=255)
                        
                        if ssim_score >= similarity_threshold:
                            is_duplicate = True
                            duplicates_removed += 1
                            print(f"Duplicate detected: Frame {current_frame['frame_number']} (t={current_frame['timestamp']:.2f}s) is similar to Frame {unique_frame['frame_number']} (t={unique_frame['timestamp']:.2f}s) [SSIM: {ssim_score:.3f}]")
                            break
                    except Exception as e:
                        print(f"Warning: Error comparing frames {idx} and {unique_list_idx} with SSIM: {e}")
            
            # Add frame if it's not a duplicate
            if not is_duplicate:
                unique_frames.append(current_frame)
        
        print(f"Removed {duplicates_removed} duplicate frames. Kept {len(unique_frames)} unique frames out of {total_frames} total frames.")
        
        if progress_callback:
            progress_callback({
                'stage': 'removing_duplicates',
                'current_frame': total_frames,
                'total_frames': total_frames,
                'percentage': 100.0,
                'frames_detected': total_frames,
                'frames_after_dedup': len(unique_frames),
                'duplicates_removed': duplicates_removed
            })
        
        return unique_frames
    
    def clear(self):
        """Clear stored frames to free memory."""
        self.frames = []
        self.frame_metadata = []
