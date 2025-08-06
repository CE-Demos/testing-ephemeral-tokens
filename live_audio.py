# Test file: https://storage.googleapis.com/generativeai-downloads/data/16000.wav
# Install helpers for converting files: pip install librosa soundfile
import argparse
import asyncio
import io
import os
from pathlib import Path
import wave
from google import genai
from google.genai import types
import soundfile as sf
import librosa

client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

# Half cascade model:
# model = "gemini-live-2.5-flash-preview"

# Native audio output model:
model = "gemini-2.5-flash-preview-native-audio-dialog"

# The script will store the session handle in this file
HANDLE_FILE = "session_handle.txt"

# config = {
#   "response_modalities": ["AUDIO"],
#   "system_instruction": "You are a helpful assistant and answer in a friendly tone.",
#   "session_resumption": {
#         "handle": previous_session_handle
#     }
# }

async def main():
    # --- 0. PARSE ARGUMENTS ---
    parser = argparse.ArgumentParser(description="Connect to Gemini Live API with session resumption.")
    parser.add_argument(
        "--new-session",
        action="store_true",
        help="Force a new session by ignoring any existing session handle.",
    )
    args = parser.parse_args()

    # Read the previous session handle from the file, if it exists.
    previous_session_handle = None
    if not args.new_session and os.path.exists(HANDLE_FILE):
        with open(HANDLE_FILE, "r") as f:
            previous_session_handle = f.read().strip()
        print(f"✅ Found previous session handle. Attempting to resume.")
    else:
        if args.new_session:
            print("✅ --new-session flag detected. Forcing a new session.")
        else:
            print("✅ No previous session handle found. Starting a new session.")

    async with client.aio.live.connect(model=model, config=types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction="You are a helpful assistant and answer in a friendly tone",
            session_resumption=types.SessionResumptionConfig(
                # The handle of the session to resume is passed here,
                # or else None to start a new session.
                handle=previous_session_handle,
            ),
        ),) as session:

        # The `while True` loop below appears to be from a different example
        # and was preventing the audio processing code from running.
        # while True:
        #     await session.send_client_content(
        #         turns=types.Content(
        #             role="user", parts=[types.Part(text="Hello world!")]
        #         )
        #     )

        buffer = io.BytesIO()
        y, sr = librosa.load("download.wav", sr=16000)
        print("✅ Audio file 'download.wav' loaded and processed.")
        sf.write(buffer, y, sr, format='RAW', subtype='PCM_16')
        buffer.seek(0)
        audio_bytes = buffer.read()

        # If already in correct format, you can use this:
        # audio_bytes = Path("sample.pcm").read_bytes()

        print("▶️  Sending audio data to Gemini...")
        await session.send_realtime_input(
            audio=types.Blob(data=audio_bytes, mime_type="audio/pcm;rate=16000")
        )

        print("✅ Finished sending audio. Notifying Gemini that input has ended.")
        await session.send_realtime_input(audio_stream_end=True)

        print("🎧 Preparing to receive audio response...")
        wf = wave.open("audio.wav", "wb")
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)  # Output is 24kHz

        new_session_handle = None

        print("👂 Listening for response from Gemini...")
        async for response in session.receive():
            if response.data is not None:
                print("   ...writing audio chunk to 'audio.wav'")
                wf.writeframes(response.data)
            if response.session_resumption_update:
                    update = response.session_resumption_update
                    if update.resumable and update.new_handle:
                        print(f"✅ Received new resumable session handle.")
                        # The handle should be retained and linked to the session.
                        new_session_handle = update.new_handle

                # For the purposes of this example, placeholder input is continually fed
                # to the model. In non-sample code, the model inputs would come from
                # the user.
            if response.server_content and response.server_content.turn_complete:
                print("✅ Gemini indicated the turn is complete.")
                break


            # Un-comment this code to print audio data info
            # if response.server_content.model_turn is not None:
            #      print(response.server_content.model_turn.parts[0].inline_data.mime_type)

        wf.close()
        print("✅ Finished writing response to 'audio.wav'.")

        # If we got a new handle, save it to the file for the next run.
        if new_session_handle:
            with open(HANDLE_FILE, "w") as f:
                f.write(new_session_handle)
            print(f"✅ Saved new handle to {HANDLE_FILE} for next time.")

if __name__ == "__main__":
    asyncio.run(main())