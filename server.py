import asyncio
import websockets
import os
import datetime
from google import genai
from google.genai import types
import logging
from pydub import AudioSegment
from pydub.utils import get_prober_name
import io
import wave

# --- Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Dependency Check ---
try:
    get_prober_name()
    logger.info("✅ FFMPEG/AVCONV found for audio conversion.")
except Exception:
    logger.error("🔴 FFMPEG or AVCONV not found. Please install it to proceed.")
    logger.error("   - On macOS (Homebrew): brew install ffmpeg")
    logger.error("   - On Ubuntu/Debian: sudo apt update && sudo apt install ffmpeg")
    exit()

# --- Gemini Client for Token Management ---
try:
    # When no api_key is provided, the client will use Application Default Credentials.
    # Ensure you have run `gcloud auth application-default login` as per the README.
    management_client = genai.Client(
        http_options={'api_version': 'v1alpha'}
    )
    model = "gemini-2.5-flash-preview-native-audio-dialog"
    logger.info("✅ Management client initialized using Application Default Credentials.")
except Exception as e:
    logger.error(f"🔴 Failed to initialize management client: {e}")
    exit()

# In-memory session management for simplicity.
# For production, you'd use a more persistent store (e.g., Redis, a database).
SESSION_HANDLES = {}

async def gemini_audio_session(websocket, session_handle):
    """Manages a single Gemini Live API session."""
    logger.info("🔑 Creating an ephemeral token for the session...")
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    try:
        token = management_client.auth_tokens.create(
            config={
                'uses': 1,
                'expire_time': now + datetime.timedelta(minutes=30),
                'new_session_expire_time': now + datetime.timedelta(minutes=1),
            }
        )
        logger.info(f"✅ Ephemeral token created. Session must start before {now + datetime.timedelta(minutes=1)}.")
    except Exception as e:
        logger.error(f"🔴 Failed to create ephemeral token: {e}")
        await websocket.send("ERROR: Could not create an API token.")
        return

    session_client = genai.Client(
        api_key=token.name,
        http_options={'api_version': 'v1alpha'}
    )

    try:
        async with session_client.aio.live.connect(
            model=model,
            config=types.LiveConnectConfig(
                response_modalities=["AUDIO"],
                system_instruction="You are a helpful assistant and answer in a friendly tone.",
                session_resumption=types.SessionResumptionConfig(handle=session_handle),
            ),
        ) as session:
            logger.info("✅ Connection to Gemini Live API successful.")
            await websocket.send("STATUS: Connected to Gemini. Ready to record.")

            # Task to stream Gemini's response back to the client
            async def receive_from_gemini():
                # This outer loop handles multiple conversational turns.
                while True:
                    # Buffer to hold raw PCM data from Gemini for one turn
                    turn_audio_buffer = io.BytesIO()
                    try:
                        # This inner loop receives data for a single turn.
                        async for response in session.receive():
                            if response.data:
                                turn_audio_buffer.write(response.data)

                            if response.session_resumption_update:
                                update = response.session_resumption_update
                                if update.resumable and update.new_handle:
                                    logger.info(f"✅ Received new resumable handle: {update.new_handle[:10]}...")
                                    SESSION_HANDLES[websocket.remote_address] = update.new_handle
                            
                            # When the turn is complete, process the audio and break the inner loop.
                            if response.server_content and response.server_content.turn_complete:
                                logger.info("✅ Gemini indicated the turn is complete.")
                                
                                turn_audio_buffer.seek(0)
                                pcm_data = turn_audio_buffer.read()

                                if pcm_data:
                                    logger.info(f"Packaging {len(pcm_data)} bytes of PCM data into a WAV file.")
                                    wav_in_memory = io.BytesIO()
                                    with wave.open(wav_in_memory, "wb") as wf:
                                        wf.setnchannels(1)
                                        wf.setsampwidth(2)
                                        wf.setframerate(24000)
                                        wf.writeframes(pcm_data)
                                    
                                    wav_in_memory.seek(0)
                                    await websocket.send(wav_in_memory.read())
                                
                                await websocket.send("STATUS: Gemini turn complete. Ready to record.")
                                # Break from the inner `async for` to wait for the next turn in the `while True` loop.
                                break
                    except Exception as e:
                        logger.error(f"Error receiving from Gemini: {e}")
                        await websocket.send(f"ERROR: Gemini connection error: {e}")
                        # On error, break the outer while loop to terminate the task.
                        break

            gemini_task = asyncio.create_task(receive_from_gemini())

            # Receive audio from the client and forward to Gemini
            audio_buffer = io.BytesIO()
            async for message in websocket:
                if isinstance(message, bytes):
                    audio_buffer.write(message)
                elif message == "END_OF_STREAM":
                    logger.info("Client indicated end of audio stream. Processing...")
                    audio_buffer.seek(0)

                    try:
                        # Be more specific about the input format to help ffmpeg
                        audio_segment = AudioSegment.from_file(
                            audio_buffer, format="webm", codec="opus"
                        )
                        audio_segment = audio_segment.set_frame_rate(16000).set_channels(1)
                        pcm_data = audio_segment.raw_data
                        
                        logger.info(f"Sending {len(pcm_data)} bytes of PCM data to Gemini.")
                        await session.send_realtime_input(
                            audio=types.Blob(data=pcm_data, mime_type="audio/pcm;rate=16000")
                        )
                        await session.send_realtime_input(audio_stream_end=True)
                        logger.info("✅ Finished sending processed audio to Gemini.")
                    except Exception as e:
                        logger.error(f"Error processing audio: {e}")
                        await websocket.send(f"ERROR: Could not process audio. Is ffmpeg installed? Details: {e}")
                    
                    audio_buffer = io.BytesIO() # Reset for next message

            await gemini_task

    except Exception as e:
        logger.error(f"Error in Gemini session: {e}")
        await websocket.send(f"ERROR: Failed to connect to Gemini: {e}")

async def handler(websocket):
    """Handles a new WebSocket connection from a client."""
    client_addr = websocket.remote_address
    logger.info(f"Client connected: {client_addr}")
    
    session_handle = SESSION_HANDLES.get(client_addr)
    if session_handle:
        logger.info(f"Resuming session for {client_addr}")
    else:
        logger.info(f"Starting new session for {client_addr}")

    try:
        await gemini_audio_session(websocket, session_handle)
    finally:
        logger.info(f"Client disconnected: {client_addr}")

async def main_server():
    """Starts the WebSocket server."""
    host = "localhost"
    port = 8765
    async with websockets.serve(handler, host, port):
        logger.info(f"🚀 WebSocket server started on ws://{host}:{port}")
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    try:
        asyncio.run(main_server())
    except KeyboardInterrupt:
        logger.info("Server shutting down.")
