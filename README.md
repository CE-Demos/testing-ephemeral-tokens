# Gemini Live Voice Chat

This application demonstrates a real-time voice chat with the Gemini Live API using a web-based frontend and a Python WebSocket backend.

## Features

- **Live Audio Streaming**: Captures audio from your microphone in the browser.
- **Real-time Communication**: Uses WebSockets for low-latency communication between the frontend and backend.
- **Gemini Live API**: Streams audio to the Gemini API and plays back the generated audio response in real-time.
- **Session Resumption**: (Handled on the backend) Can resume previous sessions to maintain context.
- **Ephemeral Tokens**: The backend creates short-lived, single-use tokens for connecting to the Gemini API, enhancing security.

## How it Works

1.  **Frontend (`index.html`, `static/script.js`)**: A simple web page captures audio from the user's microphone using the `MediaRecorder` API. This audio (in WebM format) is streamed over a WebSocket connection to the Python backend. It also receives audio back from the server and plays it using the Web Audio API.
2.  **Backend (`server.py`)**: A Python server using the `websockets` library listens for client connections.
    - When a client connects, it creates a secure, ephemeral token to communicate with the Gemini API.
    - It receives the WebM audio chunks from the frontend.
    - It uses `pydub` to convert the audio to the raw PCM format required by the Gemini API. **This requires `ffmpeg` to be installed on the server machine.**
    - It streams the PCM audio to the Gemini Live API session.
    - It receives the audio response from Gemini and streams it back to the frontend client over the WebSocket.
    - It manages session handles for conversation continuity.

## Prerequisites

1.  **Python 3.9+**
2.  **Google Cloud Project** with the Gemini API enabled.
3.  **Authenticated gcloud CLI**: You need to be authenticated. Run `gcloud auth application-default login`.
4.  **`ffmpeg`**: The backend requires `ffmpeg` for audio conversion. You must install it on the system where you run `server.py`.
    - **macOS (using Homebrew):** `brew install ffmpeg`
    - **Ubuntu/Debian:** `sudo apt update && sudo apt install ffmpeg`
    - **Windows:** Download from the official site and add it to your system's PATH.

## Setup and Running

1.  **Set your API Key**: The backend script requires your Google API key. Set it as an environment variable.

    ```bash
    export GOOGLE_API_KEY='YOUR_API_KEY_HERE'
    ```

2.  **Install Python dependencies**:

    ```bash
    pip install -r requirements.txt
    ```

3.  **Run the backend server**:

    ```bash
    python server.py
    ```

    The server will start on `ws://localhost:8765`.

4.  **Open the frontend**: Open the `index.html` file in your web browser.

5.  **Start Chatting**: Click the "Start Recording" button, speak, and then click "Stop Recording". You should hear Gemini's response played back.