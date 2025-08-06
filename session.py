import asyncio
import io
import argparse
import os
import datetime
import wave
from google import genai
from google.genai import types
import soundfile as sf
import librosa

# --- API Key Check ---
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    print("🔴 Error: The GOOGLE_API_KEY environment variable was not found.")
    print("Please set it in your terminal before running the script:")
    print("   export GOOGLE_API_KEY='YOUR_API_KEY_HERE'")
    exit()  # Stop the script if the key is missing
print("✅ API Key successfully found. Initializing client...")

# --- Initialization for Token Management ---
# This client uses the main API key and is only for creating ephemeral tokens.
management_client = genai.Client(
    api_key=api_key,
    http_options={'api_version': 'v1alpha'}
)
HANDLE_FILE = "session_handle.txt"
# Use the native audio model for audio I/O
model = "gemini-2.5-flash-preview-native-audio-dialog"

async def main():
    # --- NEW: Create an Ephemeral Token for this session ---
    print("🔑 Creating an ephemeral token...")
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    token = management_client.auth_tokens.create(
        config = {
            'uses': 1, # The token can only be used to start a single session
            'expire_time': now + datetime.timedelta(minutes=30), # The token itself expires in 30 minutes
            'new_session_expire_time': now + datetime.timedelta(minutes=1), # The session must be started within 1 minute
        }
    )
    print(f"✅ Ephemeral token created. Session must start before {now + datetime.timedelta(minutes=1)}.")
    session_client = genai.Client(
        api_key=token.name,
        http_options={'api_version': 'v1alpha'}
    )

    # --- 0. PARSE ARGUMENTS ---
    parser = argparse.ArgumentParser(description="Connect to Gemini Live API with session resumption.")
    parser.add_argument(
        "--new-session",
        action="store_true",
        help="Force a new session by ignoring any existing session handle.",
    )
    parser.add_argument(
        "--input-file",
        type=str,
        default="download.wav",
        help="Path to the input audio file to process.",
    )
    args = parser.parse_args()

    # --- 1. HANDLE SESSION RESUMPTION ---
    previous_session_handle = None
    if not args.new_session and os.path.exists(HANDLE_FILE):
        with open(HANDLE_FILE, "r") as f:
            previous_session_handle = f.read().strip()
        print(f"✅ Found handle. Attempting to resume session: {previous_session_handle[:10]}...")
    else:
        if args.new_session:
            print("✅ --new-session flag detected. Forcing a new session.")
        else:
            print("✅ No previous session file found. Starting a new session.")

    # --- 2. CONNECT TO THE API ---
    print("Connecting to the service with the ephemeral token...")
    async with session_client.aio.live.connect(
        model=model,
        config=types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction="You are a helpful assistant and answer in a friendly tone",
            session_resumption=types.SessionResumptionConfig(
                # The handle of the session to resume is passed here,
                # or else None to start a new session.
                handle=previous_session_handle
            ),
        ),
    ) as session:
        print("✅ Connection successful.")

        # --- 3. SEND AUDIO FILE ---
        input_filename = args.input_file
        print(f"🔊 Loading and processing '{input_filename}'...")
        buffer = io.BytesIO()
        try:
            y, sr = librosa.load(input_filename, sr=16000)
            sf.write(buffer, y, sr, format='RAW', subtype='PCM_16')
            buffer.seek(0)
            audio_bytes = buffer.read()
            print("✅ Audio file processed.")
        except Exception as e:
            print(f"🔴 Error loading audio file: {e}")
            print(f"Please make sure '{input_filename}' is a valid audio file.")
            return

        print("▶️  Sending audio data to Gemini...")
        await session.send_realtime_input(
            audio=types.Blob(data=audio_bytes, mime_type="audio/pcm;rate=16000")
        )

        print("✅ Finished sending audio. Notifying Gemini that input has ended.")
        await session.send_realtime_input(audio_stream_end=True)

        # --- 4. RECEIVE AUDIO RESPONSE ---
        new_session_handle = None
        output_audio_file = f"gemini_response_{os.path.basename(input_filename)}"

        print(f"🎧 Preparing to receive audio response and save to '{output_audio_file}'...")
        with wave.open(output_audio_file, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)  # Output is 24kHz

            print("👂 Listening for response from Gemini...")
            async for response in session.receive():
                # Handle audio data
                if response.data is not None:
                    print("   ...writing audio chunk.")
                    wf.writeframes(response.data)

                # Handle session resumption updates
                if response.session_resumption_update:
                    update = response.session_resumption_update
                    if update.resumable and update.new_handle:
                        new_session_handle = update.new_handle
                        print(f"✅ Received new resumable handle: {new_session_handle[:10]}...")

                # Check if the model's turn is complete
                if response.server_content and response.server_content.turn_complete:
                    print("✅ Gemini indicated the turn is complete.")
                    break

        print(f"✅ Finished writing response to '{output_audio_file}'.")

        # --- 5. SAVE the new handle ---
        if new_session_handle:
            with open(HANDLE_FILE, "w") as f:
                f.write(new_session_handle)
            print(f"✅ Saved new handle to {HANDLE_FILE} for the next session.")
        else:
            print("⚠️ No new session handle was received from the server.")

if __name__ == "__main__":
    asyncio.run(main())