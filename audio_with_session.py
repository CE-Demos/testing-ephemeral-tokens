# Test file: https://storage.googleapis.com/generativeai-downloads/data/16000.wav
# Install helpers for converting files: pip install librosa soundfile
import asyncio
import io
import os
from pathlib import Path
import wave
from google import genai
from google.genai import types
import soundfile as sf
import librosa

# The script will store the session handle in this file
HANDLE_FILE = "session_handle.txt"
model = "gemini-2.5-flash-preview-native-audio-dialog"

async def main():
    # <<< MODIFIED: Read the previous session handle from the file, if it exists.
    previous_session_handle = None
    if os.path.exists(HANDLE_FILE):
        with open(HANDLE_FILE, "r") as f:
            previous_session_handle = f.read().strip()
        print(f"✅ Found previous session handle. Attempting to resume.")
    else:
        print("✅ No previous session handle found. Starting a new session.")
    
    # <<< MODIFIED: The config is now a structured object to include session resumption.
    async with client.aio.live.connect(
        model=model,
        config=types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            session_resumption=types.SessionResumptionConfig(
                # The handle of the session to resume is passed here,
                # or else None to start a new session.
                handle=previous_session_handle
            ),
        ),
    ) as session:
        while True:
            await session.send_client_content(
                turns=types.Content(
                    role="user", parts=[types.Part(text="Hello world!")]
                )
            )
    
    # The API key is usually handled by the environment variable GOOGLE_API_KEY
    # No need to explicitly create a client instance if the env var is set.
    async with genai.live.connect(model="gemini-2.5-flash-preview-native-audio-dialog", config=config) as session:

            buffer = io.BytesIO()
            y, sr = librosa.load("download.wav", sr=16000)
            sf.write(buffer, y, sr, format='RAW', subtype='PCM_16')
            buffer.seek(0)
            audio_bytes = buffer.read()

            await session.send_realtime_input(
                audio=genai.types.Blob(data=audio_bytes, mime_type="audio/pcm;rate=16000")
            )

            wf = wave.open("audio.wav", "wb")
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)  # Output is 24kHz

            new_session_handle = None # <<< MODIFIED: Variable to store the new handle

            async for response in session.receive():
                # <<< MODIFIED: Check for a session resumption update.
                if response.session_resumption_update:
                    update = response.session_resumption_update
                    if update.resumable and update.new_handle:
                        print(f"✅ Received new resumable session handle.")
                        new_session_handle = update.new_handle

                if response.data is not None:
                    wf.writeframes(response.data)

            wf.close()

        # <<< MODIFIED: If we got a new handle, save it to the file for the next run.
            if new_session_handle:
                with open(HANDLE_FILE, "w") as f:
                    f.write(new_session_handle)
                print(f"✅ Saved new handle to {HANDLE_FILE} for next time.")


if __name__ == "__main__":
    # Ensure you are using a preview version of the SDK, e.g., 0.6.0.dev2
    # pip install --upgrade google-generativeai==0.6.0.dev2
    asyncio.run(main())