#!/bin/bash

# Check if .venv exists
if [ -d ".venv" ]; then
    echo "Using virtual environment..."
    PYTHON_CMD="./.venv/bin/python"
    UVICORN_CMD="./.venv/bin/uvicorn"
else
    echo "Virtual environment not found. Falling back to system python..."
    PYTHON_CMD="python3"
    UVICORN_CMD="uvicorn"
fi

# Install requirements if needed (optional, commented out for speed)
# $PYTHON_CMD -m pip install -r requirements.txt

# Run the server
echo "Starting Hacking Health API..."
$UVICORN_CMD src.main:app --reload --host 0.0.0.0 --port 8000
