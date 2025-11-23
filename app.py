"""
Flask application for video to PowerPoint converter.
"""

from flask import Flask, request, jsonify, send_file, send_from_directory, Response
from werkzeug.utils import secure_filename
import os
import uuid
import base64
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from video_processor import VideoProcessor
from pptx_generator import PPTXGenerator
from pdf_generator import PDFGenerator
from html_generator import HTMLGenerator
from PIL import Image
import io

app = Flask(__name__, static_folder='static')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'outputs'

# Create necessary directories
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

# In-memory storage for processing sessions
sessions = {}


@app.route('/')
def index():
    """Serve the main HTML page."""
    return send_from_directory('static', 'index.html')


@app.route('/static/<path:filename>')
def static_files(filename):
    """Serve static files."""
    return send_from_directory('static', filename)


@app.route('/upload', methods=['POST'])
def upload_video():
    """Upload video file and create a processing session."""
    if 'video' not in request.files:
        return jsonify({'error': 'No video file provided'}), 400
    
    file = request.files['video']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Generate unique session ID
    session_id = str(uuid.uuid4())
    
    # Save uploaded file
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"{session_id}_{filename}")
    file.save(filepath)
    
    # Initialize session
    sessions[session_id] = {
        'filepath': filepath,
        'filename': filename,
        'processor': None,
        'frames': None,
        'pptx_bytes': None,
        'pdf_bytes': None,
        'html_content': None,
        'progress': {
            'stage': 'idle',
            'current_frame': 0,
            'total_frames': 0,
            'percentage': 0.0,
            'frames_detected': 0,
            'fps': 0,
            'video_duration': 0,
            'elapsed_time': 0.0,
            'estimated_remaining': 0.0,
            'processing_speed': 0.0,
            'error': None,
            'completed': False
        },
        'processing_thread': None,
        'stop_requested': False
    }
    
    return jsonify({
        'session_id': session_id,
        'filename': filename
    })


def process_video_background(session_id, filepath, threshold, min_interval, frame_skip):
    """Background thread function to process video."""
    session = sessions.get(session_id)
    if not session:
        return
    
    try:
        # Reset stop flag
        session['stop_requested'] = False
        
        # Initialize processor with configurable threshold and frame skip
        processor = VideoProcessor(change_threshold=threshold, min_frame_interval=min_interval, frame_skip=frame_skip)
        
        # Progress callback to update session
        def update_progress(progress_data):
            if session_id in sessions:
                sessions[session_id]['progress'].update(progress_data)
        
        # Stop check callback
        def should_stop():
            if session_id not in sessions:
                return True
            return sessions[session_id].get('stop_requested', False)
        
        # Extract frames with scene changes
        frames = processor.extract_frames_with_changes(filepath, progress_callback=update_progress, stop_check=should_stop)
        
        # Remove duplicates from extracted frames (automatically select only unique frames)
        if frames and len(frames) > 1:
            original_count = len(frames)
            print(f"Reviewing {original_count} extracted frames for duplicates...")
            unique_frames = processor.remove_duplicate_frames(frames, similarity_threshold=0.95, progress_callback=update_progress)
            frames = unique_frames
            duplicates_removed = original_count - len(frames)
            print(f"After duplicate removal: {len(frames)} unique frames (removed {duplicates_removed} duplicates)")
        
        # Store in session - ensure frames are valid before storing
        if frames:
            # Validate frames have PIL Images
            validated_frames = []
            for idx, frame in enumerate(frames):
                if 'image' not in frame:
                    print(f"Warning: Frame {idx} ({frame.get('frame_number', 'unknown')}) missing 'image' field")
                    continue
                
                frame_image = frame['image']
                frame_type = type(frame_image).__name__
                print(f"Storing frame {idx}: image type = {frame_type}, is PIL Image = {isinstance(frame_image, Image.Image)}")
                
                if isinstance(frame_image, Image.Image):
                    # Validate the PIL Image is accessible
                    try:
                        test_size = frame_image.size
                        print(f"Frame {idx} PIL Image validated: {test_size[0]}x{test_size[1]}")
                        validated_frames.append(frame)
                    except Exception as e:
                        print(f"Warning: Frame {idx} PIL Image is invalid: {e}")
                        continue
                else:
                    print(f"Warning: Skipping invalid frame {idx} ({frame.get('frame_number', 'unknown')}) - not PIL Image, type: {frame_type}")
            
            print(f"Stored {len(validated_frames)} valid frames out of {len(frames)} total frames")
            if validated_frames:
                session['frames'] = validated_frames
                session['processor'] = processor
            else:
                session['frames'] = []
                print("Warning: No valid frames to store after validation")
        else:
            session['frames'] = []
            print("No frames extracted to store")
        
        # Check if stop was requested after frame extraction
        if session.get('stop_requested', False):
            if session_id in sessions:
                # Still generate thumbnails for frames extracted so far
                stored_frames = session.get('frames', [])
                if stored_frames:
                    thumbnails = []
                    total_frames = len(stored_frames)
                    for idx, frame in enumerate(stored_frames):
                        try:
                            thumbnail_bytes = processor.get_frame_thumbnail(frame)
                            thumbnail_b64 = base64.b64encode(thumbnail_bytes).decode('utf-8')
                            thumbnails.append({
                                'frame_number': frame['frame_number'],
                                'timestamp': frame['timestamp'],
                                'width': frame['width'],
                                'height': frame['height'],
                                'thumbnail': f"data:image/jpeg;base64,{thumbnail_b64}"
                            })
                        except Exception as e:
                            print(f"Error generating thumbnail for frame {frame.get('frame_number', idx)} when stopping: {e}")
                            # Continue with other frames even if one fails
                            continue
                    # Only store thumbnails if we successfully generated at least one
                    if thumbnails:
                        session['thumbnails'] = thumbnails
                sessions[session_id]['progress']['stage'] = 'stopped'
                sessions[session_id]['progress']['stopped'] = True
                sessions[session_id]['progress']['message'] = 'Processing stopped by user. You can continue processing to extract more frames.'
                # Explicitly clear error field so it's not treated as an error
                if 'error' in sessions[session_id]['progress']:
                    del sessions[session_id]['progress']['error']
                sessions[session_id]['progress']['error'] = None
            return
        
        session['progress']['stage'] = 'generating_thumbnails'
        session['progress']['percentage'] = 90.0  # Start thumbnail generation at 90%
        
        # Generate thumbnails for preview in parallel
        thumbnails = [None] * len(frames)
        total_frames = len(frames)
        
        def generate_thumbnail(idx, frame):
            """Generate thumbnail for a single frame."""
            try:
                thumbnail_bytes = processor.get_frame_thumbnail(frame)
                thumbnail_b64 = base64.b64encode(thumbnail_bytes).decode('utf-8')
                return idx, {
                    'frame_number': frame['frame_number'],
                    'timestamp': frame['timestamp'],
                    'width': frame['width'],
                    'height': frame['height'],
                    'thumbnail': f"data:image/jpeg;base64,{thumbnail_b64}"
                }
            except Exception as e:
                print(f"Error generating thumbnail for frame {frame['frame_number']}: {e}")
                return idx, None
        
        # Use thread pool for parallel thumbnail generation
        with ThreadPoolExecutor(max_workers=min(8, total_frames)) as executor:
            futures = {executor.submit(generate_thumbnail, idx, frame): idx 
                      for idx, frame in enumerate(frames)}
            
            completed = 0
            for future in as_completed(futures):
                idx, thumbnail_data = future.result()
                if thumbnail_data:
                    thumbnails[idx] = thumbnail_data
                
                completed += 1
                # Update progress for thumbnail generation (90-100% range)
                if session_id in sessions:
                    sessions[session_id]['progress'].update({
                        'stage': 'generating_thumbnails',
                        'percentage': 90.0 + (completed / total_frames * 10) if total_frames > 0 else 100.0,
                        'frames_detected': total_frames
                    })
        
        # Filter out None values (failed thumbnails) and maintain order
        thumbnails = [t for t in thumbnails if t is not None]
        
        # Store thumbnails in session for quick access
        session['thumbnails'] = thumbnails
        session['progress']['stage'] = 'completed'
        session['progress']['percentage'] = 100.0
        session['progress']['completed'] = True
        
    except Exception as e:
        if session_id in sessions:
            sessions[session_id]['progress']['error'] = str(e)
            sessions[session_id]['progress']['stage'] = 'error'


@app.route('/process', methods=['POST'])
def process_video():
    """Start processing video and detect scene changes in background."""
    data = request.get_json()
    session_id = data.get('session_id')
    
    if not session_id or session_id not in sessions:
        return jsonify({'error': 'Invalid session ID'}), 400
    
    session = sessions[session_id]
    
    # Check if already processing
    if session.get('processing_thread') and session['processing_thread'].is_alive():
        return jsonify({'error': 'Processing already in progress'}), 400
    
    filepath = session['filepath']
    threshold = data.get('threshold', 0.3)
    min_interval = data.get('min_interval', 30)
    frame_skip = data.get('frame_skip', 1)  # Default to 1 (process every frame)
    
    # Reset progress
    session['progress'] = {
        'stage': 'starting',
        'current_frame': 0,
        'total_frames': 0,
        'percentage': 0.0,
        'frames_detected': 0,
        'fps': 0,
        'video_duration': 0,
        'elapsed_time': 0.0,
        'estimated_remaining': 0.0,
        'processing_speed': 0.0,
        'error': None,
        'completed': False
    }
    
    # Start processing in background thread
    thread = threading.Thread(
        target=process_video_background,
        args=(session_id, filepath, threshold, min_interval, frame_skip),
        daemon=True
    )
    thread.start()
    session['processing_thread'] = thread
    
    return jsonify({'success': True, 'message': 'Processing started'})


@app.route('/stop', methods=['POST'])
def stop_processing():
    """Stop the current video processing."""
    data = request.get_json()
    session_id = data.get('session_id')
    
    if not session_id or session_id not in sessions:
        return jsonify({'error': 'Invalid session ID'}), 400
    
    session = sessions[session_id]
    
    # Set stop flag
    session['stop_requested'] = True
    
    return jsonify({'success': True, 'message': 'Stop requested'})


@app.route('/progress', methods=['GET'])
def get_progress():
    """Get current processing progress."""
    session_id = request.args.get('session_id')
    
    if not session_id or session_id not in sessions:
        return jsonify({'error': 'Invalid session ID'}), 400
    
    session = sessions[session_id]
    progress = session['progress']
    
    # If completed or stopped, return frames as well (if available)
    response = {'progress': progress}
    
    if progress.get('completed') or progress.get('stage') == 'stopped':
        # If thumbnails exist, use them
        if 'thumbnails' in session and session['thumbnails']:
            response['frames'] = session['thumbnails']
            response['frame_count'] = len(session['thumbnails'])
        # If no thumbnails but frames exist, generate thumbnails on the fly
        elif 'frames' in session and session['frames'] and 'processor' in session:
            try:
                frames = session['frames']
                processor = session['processor']
                thumbnails = []
                for frame in frames:
                    try:
                        thumbnail_bytes = processor.get_frame_thumbnail(frame)
                        thumbnail_b64 = base64.b64encode(thumbnail_bytes).decode('utf-8')
                        thumbnails.append({
                            'frame_number': frame['frame_number'],
                            'timestamp': frame['timestamp'],
                            'width': frame['width'],
                            'height': frame['height'],
                            'thumbnail': f"data:image/jpeg;base64,{thumbnail_b64}"
                        })
                    except Exception as e:
                        print(f"Error generating thumbnail for frame {frame.get('frame_number', 'unknown')}: {e}")
                        # Continue with other frames even if one fails
                        continue
                
                # Store generated thumbnails for future requests
                if thumbnails:
                    session['thumbnails'] = thumbnails
                    response['frames'] = thumbnails
                    response['frame_count'] = len(thumbnails)
            except Exception as e:
                print(f"Error generating thumbnails in progress endpoint: {e}")
    
    return jsonify(response)


@app.route('/frames', methods=['GET'])
def get_frames():
    """Get list of extracted frames with thumbnails."""
    session_id = request.args.get('session_id')
    
    if not session_id or session_id not in sessions:
        return jsonify({'error': 'Invalid session ID'}), 400
    
    session = sessions[session_id]
    
    if not session['frames']:
        return jsonify({'error': 'Video not processed yet'}), 400
    
    frames = session['frames']
    processor = session.get('processor')
    
    # Generate thumbnails
    thumbnails = []
    for frame in frames:
        try:
            # Validate frame has image
            if 'image' not in frame:
                print(f"Warning: Frame {frame.get('frame_number', 'unknown')} missing image field")
                continue
            
            # Ensure image is a PIL Image
            frame_image = frame['image']
            if not isinstance(frame_image, Image.Image):
                if hasattr(frame_image, 'read'):
                    if hasattr(frame_image, 'seek'):
                        frame_image.seek(0)
                    image_bytes = frame_image.read()
                    if not image_bytes:
                        print(f"Warning: Frame {frame.get('frame_number', 'unknown')} has empty image data")
                        continue
                    frame_image = Image.open(io.BytesIO(image_bytes))
                    # Update frame with converted image
                    frame['image'] = frame_image
                else:
                    print(f"Warning: Frame {frame.get('frame_number', 'unknown')} has invalid image type: {type(frame_image)}")
                    continue
            
            # Generate thumbnail
            if processor:
                thumbnail_bytes = processor.get_frame_thumbnail(frame)
            else:
                # Generate thumbnail directly if processor not available
                img_copy = frame_image.copy()
                img_copy.thumbnail((400, 300), Image.Resampling.LANCZOS)
                thumb_io = io.BytesIO()
                img_copy.save(thumb_io, format='JPEG', quality=92)
                thumbnail_bytes = thumb_io.getvalue()
            
            thumbnail_b64 = base64.b64encode(thumbnail_bytes).decode('utf-8')
            thumbnails.append({
                'frame_number': frame['frame_number'],
                'timestamp': frame['timestamp'],
                'width': frame['width'],
                'height': frame['height'],
                'thumbnail': f"data:image/jpeg;base64,{thumbnail_b64}"
            })
        except Exception as e:
            print(f"Error generating thumbnail for frame {frame.get('frame_number', 'unknown')}: {e}")
            import traceback
            print(traceback.format_exc())
            continue
    
    return jsonify({
        'frame_count': len(frames),
        'frames': thumbnails
    })


@app.route('/frame_image/<session_id>/<int:frame_index>', methods=['GET'])
def get_frame_image(session_id, frame_index):
    """Get full-resolution image for a specific frame."""
    if session_id not in sessions:
        return jsonify({'error': 'Invalid session ID'}), 400
    
    session = sessions[session_id]
    
    if not session['frames']:
        return jsonify({'error': 'Video not processed yet'}), 400
    
    frames = session['frames']
    
    if frame_index < 0 or frame_index >= len(frames):
        return jsonify({'error': 'Invalid frame index'}), 400
    
    frame = frames[frame_index]
    
    # Get the full-resolution image (make a copy to avoid modifying the original)
    image = frame.get('image')
    
    # Validate and convert to PIL Image if needed
    if not isinstance(image, Image.Image):
        if hasattr(image, 'read'):
            # It's a file-like object (BytesIO, file handle, etc.)
            if hasattr(image, 'seek'):
                image.seek(0)
            image_bytes = image.read()
            if not image_bytes:
                return jsonify({'error': 'Frame image is empty'}), 400
            image = Image.open(io.BytesIO(image_bytes))
        else:
            return jsonify({'error': f'Invalid image type: {type(image)}'}), 400
    
    # Make a copy to avoid modifying the original
    image = image.copy()
    
    # Convert to bytes
    img_bytes = io.BytesIO()
    image.save(img_bytes, format='JPEG', quality=95)
    img_bytes.seek(0)
    
    return Response(img_bytes.getvalue(), mimetype='image/jpeg')


@app.route('/generate', methods=['POST'])
def generate_pptx():
    """Generate PPTX from selected frames."""
    data = request.get_json()
    session_id = data.get('session_id')
    selected_indices = data.get('selected_indices', [])
    
    if not session_id or session_id not in sessions:
        return jsonify({'error': 'Invalid session ID'}), 400
    
    session = sessions[session_id]
    
    if not session['frames']:
        return jsonify({'error': 'Video not processed yet. Please process the video first.'}), 400
    
    if not selected_indices:
        return jsonify({'error': 'No frames selected'}), 400
    
    try:
        # Get selected frames
        all_frames = session['frames']
        
        # Validate frames exist and have required structure
        if not all_frames or len(all_frames) == 0:
            return jsonify({'error': 'No frames available. The video may not have been processed yet, or processing was stopped before any frames were extracted.'}), 400
        
        # Get selected frames and validate they have images
        selected_frames = []
        for i in selected_indices:
            if 0 <= i < len(all_frames):
                frame = all_frames[i]
                # Validate frame has required fields
                if 'image' not in frame:
                    print(f"Warning: Frame {i} missing 'image' field")
                    continue
                # Validate image is a PIL Image (or can be converted)
                frame_image = frame.get('image')
                if not frame_image:
                    print(f"Warning: Frame {i} has no image")
                    continue
                
                # Debug: Print the type of the image
                print(f"Frame {i} image type: {type(frame_image)}")
                
                if not isinstance(frame_image, Image.Image):
                    print(f"Frame {i} is not PIL Image, attempting conversion...")
                    # Try to handle BytesIO or other types
                    if hasattr(frame_image, 'read'):
                        # It's a file-like object, try to convert
                        try:
                            if hasattr(frame_image, 'seek'):
                                frame_image.seek(0)
                            # Read bytes and create fresh BytesIO to avoid state issues
                            image_bytes = frame_image.read()
                            if not image_bytes:
                                print(f"Warning: Frame {i} has empty image data")
                                continue
                            # Create fresh PIL Image from bytes
                            frame_image = Image.open(io.BytesIO(image_bytes))
                            print(f"Frame {i} successfully converted to PIL Image")
                        except Exception as e:
                            print(f"Warning: Could not convert frame {i} image: {e}")
                            import traceback
                            print(traceback.format_exc())
                            continue
                    else:
                        print(f"Warning: Frame {i} has invalid image type: {type(frame_image)}")
                        continue
                
                # Validate the PIL Image is valid and can be accessed
                try:
                    # Test if we can access image properties
                    test_width, test_height = frame_image.size
                    print(f"Frame {i} validated: {test_width}x{test_height} PIL Image")
                except Exception as e:
                    print(f"Warning: Frame {i} PIL Image is invalid: {e}")
                    continue
                
                # Make a copy to ensure we don't modify the original
                try:
                    frame_image_copy = frame_image.copy()
                    frame['image'] = frame_image_copy
                    selected_frames.append(frame)
                    print(f"Frame {i} added to selected frames")
                except Exception as e:
                    print(f"Warning: Could not copy frame {i} image: {e}")
                    import traceback
                    print(traceback.format_exc())
                    continue
        
        if not selected_frames:
            return jsonify({'error': 'No valid frames selected. Selected frames may be invalid or corrupted.'}), 400
        
        # Generate PPTX
        try:
            print(f"Generating PPTX with {len(selected_frames)} frames...")
            pptx_generator = PPTXGenerator()
            pptx_bytes = pptx_generator.create_presentation(selected_frames)
            print("PPTX generation successful")
        except Exception as e:
            print(f"Error generating PPTX: {e}")
            import traceback
            print(traceback.format_exc())
            raise
        
        # Generate PDF
        try:
            print(f"Generating PDF with {len(selected_frames)} frames...")
            pdf_generator = PDFGenerator()
            pdf_bytes = pdf_generator.create_presentation(selected_frames)
            print("PDF generation successful")
        except Exception as e:
            print(f"Error generating PDF: {e}")
            import traceback
            print(traceback.format_exc())
            raise
        
        # Generate HTML slideshow
        try:
            print(f"Generating HTML with {len(selected_frames)} frames...")
            html_generator = HTMLGenerator()
            filename = session['filename']
            title = os.path.splitext(filename)[0]
            html_content = html_generator.create_slideshow(selected_frames, title=title)
            print("HTML generation successful")
        except Exception as e:
            print(f"Error generating HTML: {e}")
            import traceback
            print(traceback.format_exc())
            raise
        
        # Store in session
        session['pptx_bytes'] = pptx_bytes
        session['pdf_bytes'] = pdf_bytes
        session['html_content'] = html_content
        
        return jsonify({
            'success': True,
            'slide_count': len(selected_frames),
            'session_id': session_id
        })
    
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        error_type = type(e).__name__
        error_msg = str(e)
        print(f"Error in generate_pptx ({error_type}): {error_msg}")
        print(f"Traceback: {error_trace}")
        
        # Provide user-friendly error message based on error type
        if 'BytesIO' in error_msg or 'expected str, bytes or os.PathLike' in error_msg:
            user_msg = "Image processing error: Invalid image format. Please try processing the video again."
        elif 'PIL' in error_msg or 'Image' in error_msg:
            user_msg = f"Image processing error: {error_msg}"
        else:
            user_msg = f"Error generating presentation: {error_msg}"
        
        return jsonify({
            'error': user_msg,
            'error_type': error_type,
            'details': error_msg,
            'traceback': error_trace if app.debug else None
        }), 500


@app.route('/download/<session_id>', methods=['GET'])
def download_pptx(session_id):
    """Download generated PPTX file."""
    if session_id not in sessions:
        return jsonify({'error': 'Invalid session ID'}), 404
    
    session = sessions[session_id]
    
    if not session['pptx_bytes']:
        return jsonify({'error': 'PPTX not generated yet'}), 400
    
    # Create file-like object from bytes
    pptx_bytes = session['pptx_bytes']
    filename = session['filename']
    pptx_filename = os.path.splitext(filename)[0] + '.pptx'
    
    return send_file(
        io.BytesIO(pptx_bytes),
        mimetype='application/vnd.openxmlformats-officedocument.presentationml.presentation',
        as_attachment=True,
        download_name=pptx_filename
    )


@app.route('/download_pdf/<session_id>', methods=['GET'])
def download_pdf(session_id):
    """Download generated PDF file."""
    if session_id not in sessions:
        return jsonify({'error': 'Invalid session ID'}), 404
    
    session = sessions[session_id]
    
    if not session.get('pdf_bytes'):
        return jsonify({'error': 'PDF not generated yet'}), 400
    
    # Create file-like object from bytes
    pdf_bytes = session['pdf_bytes']
    filename = session['filename']
    pdf_filename = os.path.splitext(filename)[0] + '.pdf'
    
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=pdf_filename
    )


@app.route('/view/<session_id>', methods=['GET'])
def view_presentation(session_id):
    """View generated presentation in browser."""
    if session_id not in sessions:
        return jsonify({'error': 'Invalid session ID'}), 404
    
    session = sessions[session_id]
    
    if not session['html_content']:
        return jsonify({'error': 'Presentation not generated yet'}), 400
    
    # Return HTML content
    return Response(session['html_content'], mimetype='text/html')


@app.route('/cleanup/<session_id>', methods=['POST'])
def cleanup_session(session_id):
    """Clean up session data and files."""
    if session_id not in sessions:
        return jsonify({'error': 'Invalid session ID'}), 404
    
    session = sessions[session_id]
    
    # Delete uploaded file
    if os.path.exists(session['filepath']):
        os.remove(session['filepath'])
    
    # Clear processor frames from memory
    if session['processor']:
        session['processor'].clear()
    
    # Remove session
    del sessions[session_id]
    
    return jsonify({'success': True})


if __name__ == '__main__':
    print("Starting Video to PPTX Converter...")
    print("Open http://localhost:5000 in your browser")
    app.run(debug=True, host='0.0.0.0', port=5000)
