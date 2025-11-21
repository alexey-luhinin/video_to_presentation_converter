#!/bin/bash
# Build script for creating executable from Python application

echo "Installing build dependencies..."
pip install -r build-requirements.txt

echo ""
echo "Building executable..."
pyinstaller app.spec --clean

echo ""
echo "Build complete! The executable is in the 'dist' folder."
echo "You can find it at: dist/MultiScreenshotQueue"

