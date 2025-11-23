// Global state
let currentSessionId = null;
let frames = [];
let selectedFrames = new Set();
let stepHistory = []; // Track navigation history

// DOM Elements
const uploadArea = document.getElementById('upload-area');
const videoInput = document.getElementById('video-input');
const thresholdSlider = document.getElementById('threshold');
const thresholdValue = document.getElementById('threshold-value');
const minIntervalInput = document.getElementById('min-interval');
const uploadStatus = document.getElementById('upload-status');
const processStatus = document.getElementById('process-status');
const progressFill = document.getElementById('progress-fill');
const progressText = document.getElementById('progress-text');
const progressStage = document.getElementById('progress-stage');
const progressPercentage = document.getElementById('progress-percentage');
const progressFrames = document.getElementById('progress-frames');
const progressScenes = document.getElementById('progress-scenes');
const progressElapsed = document.getElementById('progress-elapsed');
const progressRemaining = document.getElementById('progress-remaining');
const progressSpeed = document.getElementById('progress-speed');
const framesGrid = document.getElementById('frames-grid');
const selectAllBtn = document.getElementById('select-all-btn');
const deselectAllBtn = document.getElementById('deselect-all-btn');
const selectedCount = document.getElementById('selected-count');
const generateBtn = document.getElementById('generate-btn');
const previewHtmlBtn = document.getElementById('preview-html-btn');
const convertPdfBtn = document.getElementById('convert-pdf-btn');
const downloadBtn = document.getElementById('download-btn');
const downloadPdfBtn = document.getElementById('download-pdf-btn');
const viewBtn = document.getElementById('view-btn');
const downloadMessage = document.getElementById('download-message');
const slideCount = document.getElementById('slide-count');
const stopBtn = document.getElementById('stop-btn');
const continueBtn = document.getElementById('continue-btn');
const startProcessingBtn = document.getElementById('start-processing-btn');
const navigationBar = document.getElementById('navigation-bar');
const backBtn = document.getElementById('back-btn');
const homeBtn = document.getElementById('home-btn');
const imageModal = document.getElementById('image-modal');
const modalImage = document.getElementById('modal-image');
const modalInfo = document.getElementById('modal-info');
const modalClose = document.querySelector('.modal-close');
const helpPopup = document.getElementById('help-popup');
const helpPopupBody = document.getElementById('help-popup-body');
const helpPopupClose = document.querySelector('.help-popup-close');
const helpButtons = document.querySelectorAll('.help-btn');

// Sections
const uploadSection = document.getElementById('upload-section');
const processSection = document.getElementById('process-section');
const framesSection = document.getElementById('frames-section');
const downloadSection = document.getElementById('download-section');

// Event Listeners
uploadArea.addEventListener('click', () => videoInput.click());
uploadArea.addEventListener('dragover', handleDragOver);
uploadArea.addEventListener('dragleave', handleDragLeave);
uploadArea.addEventListener('drop', handleDrop);
videoInput.addEventListener('change', handleFileSelect);
thresholdSlider.addEventListener('input', (e) => {
    thresholdValue.textContent = e.target.value;
});
selectAllBtn.addEventListener('click', selectAllFrames);
deselectAllBtn.addEventListener('click', deselectAllFrames);
generateBtn.addEventListener('click', generatePPTX);
previewHtmlBtn.addEventListener('click', previewHTML);
convertPdfBtn.addEventListener('click', convertToPDF);
downloadBtn.addEventListener('click', downloadPPTX);
downloadPdfBtn.addEventListener('click', downloadPDF);
viewBtn.addEventListener('click', viewPresentation);
stopBtn.addEventListener('click', stopProcessing);
continueBtn.addEventListener('click', () => {
    // Show info that processing will restart from beginning
    showStatus(processStatus, 'Continuing processing... This will process the entire video file again.', 'info');
    processVideo();
});
startProcessingBtn.addEventListener('click', processVideo);
backBtn.addEventListener('click', goBack);
homeBtn.addEventListener('click', goHome);
modalClose.addEventListener('click', closeImageModal);
imageModal.addEventListener('click', (e) => {
    // Close modal if clicking on the backdrop (not the image)
    if (e.target === imageModal) {
        closeImageModal();
    }
});

// Help popup event listeners
helpPopupClose.addEventListener('click', closeHelpPopup);
helpPopup.addEventListener('click', (e) => {
    // Close popup if clicking on the backdrop
    if (e.target === helpPopup) {
        closeHelpPopup();
    }
});

// Add click handlers to help buttons
helpButtons.forEach(btn => {
    btn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const helpType = btn.getAttribute('data-help');
        showHelpPopup(helpType);
    });
});

// Drag and Drop
function handleDragOver(e) {
    e.preventDefault();
    uploadArea.classList.add('dragover');
}

function handleDragLeave(e) {
    e.preventDefault();
    uploadArea.classList.remove('dragover');
}

function handleDrop(e) {
    e.preventDefault();
    uploadArea.classList.remove('dragover');
    const files = e.dataTransfer.files;
    if (files.length > 0 && files[0].type.startsWith('video/')) {
        handleFile(files[0]);
    } else {
        showStatus(uploadStatus, 'Please drop a video file', 'error');
    }
}

function handleFileSelect(e) {
    const file = e.target.files[0];
    if (file) {
        handleFile(file);
    }
}

// Upload Video
async function handleFile(file) {
    showStatus(uploadStatus, 'Uploading video...', 'info');
    
    const formData = new FormData();
    formData.append('video', file);
    
    try {
        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (response.ok) {
            currentSessionId = data.session_id;
            showStatus(uploadStatus, `Video uploaded: ${data.filename}`, 'success');
            // Enable start processing button
            startProcessingBtn.disabled = false;
        } else {
            showStatus(uploadStatus, data.error || 'Upload failed', 'error');
            startProcessingBtn.disabled = true;
        }
    } catch (error) {
        showStatus(uploadStatus, `Error: ${error.message}`, 'error');
        startProcessingBtn.disabled = true;
    }
}

// Process Video
let progressPollInterval = null;

async function processVideo() {
    // Disable start button when processing starts
    startProcessingBtn.disabled = true;
    showSection(processSection);
    
    // Reset progress display
    progressFill.style.width = '0%';
    progressFill.classList.remove('processing');
    progressText.textContent = 'Starting video processing...';
    stopBtn.style.display = 'none';
    stopBtn.disabled = false;
    stopBtn.textContent = 'Stop Processing';
    continueBtn.style.display = 'none'; // Hide continue button when starting new processing
    updateProgressDetails({
        stage: 'starting',
        current_frame: 0,
        total_frames: 0,
        percentage: 0.0,
        frames_detected: 0,
        elapsed_time: 0.0,
        estimated_remaining: 0.0,
        processing_speed: 0.0
    });
    
    const threshold = parseFloat(thresholdSlider.value);
    const minInterval = parseInt(minIntervalInput.value);
    
    try {
        const response = await fetch('/process', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                session_id: currentSessionId,
                threshold: threshold,
                min_interval: minInterval
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            // Show stop button
            stopBtn.style.display = 'block';
            // Start polling for progress
            startProgressPolling();
        } else {
            showStatus(processStatus, data.error || 'Processing failed', 'error');
        }
    } catch (error) {
        showStatus(processStatus, `Error: ${error.message}`, 'error');
    }
}

function startProgressPolling() {
    // Clear any existing interval
    if (progressPollInterval) {
        clearInterval(progressPollInterval);
    }
    
    // Poll every 200ms for smooth updates
    progressPollInterval = setInterval(async () => {
        try {
            const response = await fetch(`/progress?session_id=${currentSessionId}`);
            const data = await response.json();
            
            if (response.ok && data.progress) {
                const progress = data.progress;
                
                // Check if stopped first, before updating display (to avoid showing errors)
                if (progress.stage === 'stopped') {
                    clearInterval(progressPollInterval);
                    progressPollInterval = null;
                    stopBtn.style.display = 'none';
                    continueBtn.style.display = 'block';
                    startProcessingBtn.disabled = false; // Allow restarting processing
                    
                    // If frames were extracted before stopping, show them
                    if (data.frames && data.frames.length > 0) {
                        frames = data.frames;
                        selectedFrames.clear();
                        const message = progress.message || `Processing stopped. ${data.frame_count} frames extracted. You can continue processing to extract more frames.`;
                        showStatus(processStatus, message, 'info');
                        progressText.textContent = `Processing stopped - ${data.frame_count} frames found. Click "Continue Processing" to extract more.`;
                        
                        setTimeout(() => {
                            showFrames();
                        }, 500);
                    } else {
                        // Even if no frames extracted, show the frames section (will be empty)
                        frames = [];
                        selectedFrames.clear();
                        const message = progress.message || 'Processing stopped by user. No frames extracted yet. Click "Continue Processing" to start extracting frames.';
                        showStatus(processStatus, message, 'info');
                        progressText.textContent = 'Processing stopped - no frames found. Click "Continue Processing" to start.';
                        
                        setTimeout(() => {
                            showFrames();
                        }, 500);
                    }
                    return; // Exit early to avoid processing other conditions
                }
                
                // Update progress display (only if not stopped)
                updateProgressDisplay(progress);
                
                // Check if completed
                if (progress.completed || progress.stage === 'completed') {
                    clearInterval(progressPollInterval);
                    progressPollInterval = null;
                    stopBtn.style.display = 'none';
                    continueBtn.style.display = 'none';
                    
                    if (data.frames) {
                        frames = data.frames;
                        selectedFrames.clear();
                        
                        progressFill.style.width = '100%';
                        progressText.textContent = `Found ${data.frame_count} scene changes`;
                        
                        setTimeout(() => {
                            showFrames();
                        }, 500);
                    }
                } else if (progress.error) {
                    // Only show error if not stopped (stopped is handled above)
                    clearInterval(progressPollInterval);
                    progressPollInterval = null;
                    stopBtn.style.display = 'none';
                    continueBtn.style.display = 'none'; // Don't show continue button on errors
                    showStatus(processStatus, `Error: ${progress.error}`, 'error');
                }
            }
        } catch (error) {
            console.error('Error polling progress:', error);
        }
    }, 200);
}

function updateProgressDisplay(progress) {
    // Update progress bar (cap at 100% for main progress, show thumbnail generation separately)
    const percentage = Math.min(progress.percentage || 0, 100);
    progressFill.style.width = `${percentage}%`;
    
    // Add/remove processing class for animation
    if (progress.stage === 'completed' || progress.stage === 'error') {
        progressFill.classList.remove('processing');
    } else if (percentage > 0) {
        progressFill.classList.add('processing');
    }
    
    // Update main text based on stage
    const stageMessages = {
        'starting': 'Starting video processing...',
        'initializing': 'Initializing video analysis...',
        'extracting': 'Extracting frames and detecting scene changes...',
        'generating_thumbnails': 'Generating frame thumbnails...',
        'completed': 'Processing completed!',
        'stopped': 'Processing stopped',
        'error': 'An error occurred during processing'
    };
    
    progressText.textContent = stageMessages[progress.stage] || 'Processing...';
    
    // Update detailed progress
    updateProgressDetails(progress);
}

function updateProgressDetails(progress) {
    // Stage
    const stageNames = {
        'starting': 'Starting',
        'initializing': 'Initializing',
        'extracting': 'Extracting Frames',
        'generating_thumbnails': 'Generating Thumbnails',
        'completed': 'Completed',
        'stopped': 'Stopped',
        'error': 'Error'
    };
    progressStage.textContent = stageNames[progress.stage] || progress.stage || '-';
    
    // Percentage
    const percentage = Math.min(progress.percentage || 0, 100);
    progressPercentage.textContent = `${percentage.toFixed(1)}%`;
    
    // Frames
    const currentFrame = progress.current_frame || 0;
    const totalFrames = progress.total_frames || 0;
    progressFrames.textContent = `${currentFrame.toLocaleString()} / ${totalFrames.toLocaleString()}`;
    
    // Scene changes detected
    progressScenes.textContent = (progress.frames_detected || 0).toLocaleString();
    
    // Elapsed time
    const elapsed = progress.elapsed_time || 0;
    progressElapsed.textContent = formatDuration(elapsed);
    
    // Estimated remaining
    const remaining = progress.estimated_remaining || 0;
    if (remaining > 0 && remaining < 3600) { // Less than 1 hour
        progressRemaining.textContent = formatDuration(remaining);
    } else {
        progressRemaining.textContent = '-';
    }
    
    // Processing speed
    const speed = progress.processing_speed || 0;
    progressSpeed.textContent = `${speed.toFixed(1)} fps`;
}

function formatDuration(seconds) {
    if (seconds < 60) {
        return `${Math.floor(seconds)}s`;
    } else if (seconds < 3600) {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}m ${secs}s`;
    } else {
        const hours = Math.floor(seconds / 3600);
        const mins = Math.floor((seconds % 3600) / 60);
        return `${hours}h ${mins}m`;
    }
}

// Display Frames
function showFrames() {
    showSection(framesSection);
    framesGrid.innerHTML = '';
    
    // Show message if no frames available
    if (frames.length === 0) {
        const emptyMessage = document.createElement('div');
        emptyMessage.className = 'empty-frames-message';
        emptyMessage.style.cssText = 'grid-column: 1 / -1; text-align: center; padding: 40px; color: #666; font-size: 1.1em;';
        emptyMessage.innerHTML = `
            <p style="margin-bottom: 20px;">No frames were extracted.</p>
            <p style="font-size: 0.9em; color: #999;">Processing was stopped before any scene changes were detected.</p>
        `;
        framesGrid.appendChild(emptyMessage);
        updateSelectedCount();
        return;
    }
    
    frames.forEach((frame, index) => {
        const frameItem = document.createElement('div');
        frameItem.className = 'frame-item';
        frameItem.innerHTML = `
            <input type="checkbox" id="frame-${index}" data-index="${index}" onchange="toggleFrame(${index})">
            <img src="${frame.thumbnail}" alt="Frame ${frame.frame_number}" class="frame-thumbnail" data-index="${index}">
            <div class="frame-info">
                Frame ${frame.frame_number}<br>
                ${formatTime(frame.timestamp)}
            </div>
        `;
        framesGrid.appendChild(frameItem);
        
        // Prevent checkbox clicks from triggering thumbnail modal
        const checkbox = frameItem.querySelector('input[type="checkbox"]');
        checkbox.addEventListener('click', (e) => {
            e.stopPropagation();
        });
        
        // Add click handler to thumbnail
        const thumbnail = frameItem.querySelector('.frame-thumbnail');
        thumbnail.addEventListener('click', (e) => {
            // Don't trigger if clicking on checkbox or checkbox area
            if (e.target.closest('input[type="checkbox"]')) {
                return;
            }
            e.stopPropagation();
            showFullImage(index);
        });
    });
    
    updateSelectedCount();
}

// Toggle Frame Selection
function toggleFrame(index) {
    const checkbox = document.getElementById(`frame-${index}`);
    const frameItem = checkbox.closest('.frame-item');
    
    if (checkbox.checked) {
        selectedFrames.add(index);
        frameItem.classList.add('selected');
    } else {
        selectedFrames.delete(index);
        frameItem.classList.remove('selected');
    }
    
    updateSelectedCount();
}

function selectAllFrames() {
    frames.forEach((_, index) => {
        selectedFrames.add(index);
        const checkbox = document.getElementById(`frame-${index}`);
        if (checkbox) {
            checkbox.checked = true;
            checkbox.closest('.frame-item').classList.add('selected');
        }
    });
    updateSelectedCount();
}

function deselectAllFrames() {
    selectedFrames.clear();
    frames.forEach((_, index) => {
        const checkbox = document.getElementById(`frame-${index}`);
        if (checkbox) {
            checkbox.checked = false;
            checkbox.closest('.frame-item').classList.remove('selected');
        }
    });
    updateSelectedCount();
}

function updateSelectedCount() {
    const count = selectedFrames.size;
    selectedCount.textContent = `${count} frame${count !== 1 ? 's' : ''} selected`;
    const hasSelection = count > 0;
    generateBtn.disabled = !hasSelection;
    previewHtmlBtn.disabled = !hasSelection;
    convertPdfBtn.disabled = !hasSelection;
}

// Generate PPTX
async function generatePPTX() {
    if (selectedFrames.size === 0) {
        alert('Please select at least one frame');
        return;
    }
    
    generateBtn.disabled = true;
    generateBtn.textContent = 'Generating...';
    
    try {
        const response = await fetch('/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                session_id: currentSessionId,
                selected_indices: Array.from(selectedFrames)
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showDownloadSection(data.slide_count);
        } else {
            alert(data.error || 'Generation failed');
            generateBtn.disabled = false;
            generateBtn.textContent = 'Generate PowerPoint';
        }
    } catch (error) {
        alert(`Error: ${error.message}`);
        generateBtn.disabled = false;
        generateBtn.textContent = 'Generate PowerPoint';
    }
}

// Preview HTML
async function previewHTML() {
    if (selectedFrames.size === 0) {
        alert('Please select at least one frame');
        return;
    }
    
    previewHtmlBtn.disabled = true;
    previewHtmlBtn.textContent = 'Generating...';
    
    try {
        const response = await fetch('/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                session_id: currentSessionId,
                selected_indices: Array.from(selectedFrames)
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            // Open HTML preview in new tab
            window.open(`/view/${currentSessionId}`, '_blank');
            previewHtmlBtn.disabled = false;
            previewHtmlBtn.textContent = 'Preview HTML';
        } else {
            alert(data.error || 'Generation failed');
            previewHtmlBtn.disabled = false;
            previewHtmlBtn.textContent = 'Preview HTML';
        }
    } catch (error) {
        alert(`Error: ${error.message}`);
        previewHtmlBtn.disabled = false;
        previewHtmlBtn.textContent = 'Preview HTML';
    }
}

// Convert to PDF
async function convertToPDF() {
    if (selectedFrames.size === 0) {
        alert('Please select at least one frame');
        return;
    }
    
    convertPdfBtn.disabled = true;
    convertPdfBtn.textContent = 'Converting...';
    
    try {
        const response = await fetch('/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                session_id: currentSessionId,
                selected_indices: Array.from(selectedFrames)
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            // Download PDF directly
            window.location.href = `/download_pdf/${currentSessionId}`;
            convertPdfBtn.disabled = false;
            convertPdfBtn.textContent = 'Convert to PDF';
        } else {
            alert(data.error || 'Conversion failed');
            convertPdfBtn.disabled = false;
            convertPdfBtn.textContent = 'Convert to PDF';
        }
    } catch (error) {
        alert(`Error: ${error.message}`);
        convertPdfBtn.disabled = false;
        convertPdfBtn.textContent = 'Convert to PDF';
    }
}

// Show Download Section
function showDownloadSection(slideCountValue) {
    showSection(downloadSection);
    slideCount.textContent = `Generated ${slideCountValue} slide${slideCountValue !== 1 ? 's' : ''}`;
}

// Stop Processing
async function stopProcessing() {
    if (!currentSessionId) {
        return;
    }
    
    stopBtn.disabled = true;
    stopBtn.textContent = 'Stopping...';
    
    try {
        const response = await fetch('/stop', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                session_id: currentSessionId
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            // Stop button will be hidden when progress polling detects stopped state
        } else {
            alert(data.error || 'Failed to stop processing');
            stopBtn.disabled = false;
            stopBtn.textContent = 'Stop Processing';
        }
    } catch (error) {
        alert(`Error: ${error.message}`);
        stopBtn.disabled = false;
        stopBtn.textContent = 'Stop Processing';
    }
}

// View Presentation in Browser
function viewPresentation() {
    if (!currentSessionId) {
        alert('No session available');
        return;
    }
    
    // Open in new tab
    window.open(`/view/${currentSessionId}`, '_blank');
}

// Download PPTX
function downloadPPTX() {
    if (!currentSessionId) {
        alert('No session available');
        return;
    }
    
    window.location.href = `/download/${currentSessionId}`;
}

// Download PDF
function downloadPDF() {
    if (!currentSessionId) {
        alert('No session available');
        return;
    }
    
    window.location.href = `/download_pdf/${currentSessionId}`;
}

// Navigation Functions
function goBack() {
    // If processing is in progress, ask for confirmation
    if (progressPollInterval) {
        if (!confirm('Processing is in progress. Going back will stop the current processing. Continue?')) {
            return;
        }
        // Stop processing
        if (stopBtn && !stopBtn.disabled) {
            stopProcessing();
        }
    }
    
    if (stepHistory.length > 1) {
        // Remove current step from history
        stepHistory.pop();
        // Get previous step
        const previousStep = stepHistory[stepHistory.length - 1];
        navigateToSection(previousStep, false); // false = don't add to history
    } else {
        // If no history, go to home
        goHome();
    }
}

function goHome() {
    // If processing is in progress, ask for confirmation
    if (progressPollInterval) {
        if (!confirm('Processing is in progress. Going home will stop the current processing. Continue?')) {
            return;
        }
        // Stop processing
        if (stopBtn && !stopBtn.disabled) {
            stopProcessing();
        }
    }
    
    // Clear history and reset to upload section
    stepHistory = [uploadSection];
    navigateToSection(uploadSection, false);
    
    // Reset start processing button state
    if (currentSessionId) {
        startProcessingBtn.disabled = false;
    } else {
        startProcessingBtn.disabled = true;
    }
    
    // Optionally reset state if needed
    // Note: We keep the session ID and frames in case user wants to continue
}

function navigateToSection(section, addToHistory = true) {
    // Hide all sections
    [uploadSection, processSection, framesSection, downloadSection].forEach(s => {
        s.classList.remove('active');
    });
    
    // Show target section
    section.classList.add('active');
    
    // Update navigation bar visibility
    if (section === uploadSection) {
        navigationBar.style.display = 'none';
    } else {
        navigationBar.style.display = 'flex';
    }
    
    // Update history
    if (addToHistory) {
        // Remove any future steps if we're going back and then forward
        const currentIndex = stepHistory.findIndex(s => s === section);
        if (currentIndex !== -1) {
            stepHistory = stepHistory.slice(0, currentIndex + 1);
        } else {
            stepHistory.push(section);
        }
    }
}

// Utility Functions
function showSection(section) {
    navigateToSection(section, true);
}

function showStatus(element, message, type) {
    element.textContent = message;
    element.className = `status-message ${type}`;
    element.style.display = 'block';
}

function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

// Show Full Image Modal
function showFullImage(index) {
    if (index >= 0 && index < frames.length) {
        const frame = frames[index];
        // Show loading state
        modalImage.src = '';
        modalImage.style.opacity = '0.5';
        modalInfo.textContent = `Loading Frame ${frame.frame_number} • ${formatTime(frame.timestamp)}...`;
        imageModal.classList.add('active');
        // Prevent body scroll when modal is open
        document.body.style.overflow = 'hidden';
        
        // Load full-resolution image
        const fullImageUrl = `/frame_image/${currentSessionId}/${index}`;
        const img = new Image();
        img.onload = function() {
            modalImage.src = fullImageUrl;
            modalImage.style.opacity = '1';
            modalInfo.textContent = `Frame ${frame.frame_number} • ${formatTime(frame.timestamp)}`;
        };
        img.onerror = function() {
            // Fallback to thumbnail if full image fails to load
            modalImage.src = frame.thumbnail;
            modalImage.style.opacity = '1';
            modalInfo.textContent = `Frame ${frame.frame_number} • ${formatTime(frame.timestamp)}`;
            console.error('Failed to load full-resolution image, using thumbnail');
        };
        img.src = fullImageUrl;
    }
}

// Close Image Modal
function closeImageModal() {
    imageModal.classList.remove('active');
    document.body.style.overflow = '';
}

// Close modal on Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        if (imageModal.classList.contains('active')) {
            closeImageModal();
        } else if (helpPopup.classList.contains('active')) {
            closeHelpPopup();
        }
    }
});

// Make toggleFrame available globally
window.toggleFrame = toggleFrame;

// Show Help Popup
function showHelpPopup(helpType) {
    const helpContent = document.getElementById(`help-${helpType}`);
    if (helpContent) {
        helpPopupBody.innerHTML = helpContent.innerHTML;
        helpPopup.classList.add('active');
        // Prevent body scroll when popup is open
        document.body.style.overflow = 'hidden';
    }
}

// Close Help Popup
function closeHelpPopup() {
    helpPopup.classList.remove('active');
    document.body.style.overflow = '';
}

// Initialize: Add upload section to history on page load
document.addEventListener('DOMContentLoaded', () => {
    stepHistory = [uploadSection];
});
