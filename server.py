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

# --- API Key Check ---
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    logger.error("🔴 Error: The GOOGLE_API_KEY environment variable was not found.")
    logger.error("Please set it in your terminal before running the script:")
    logger.error("   export GOOGLE_API_KEY='YOUR_API_KEY_HERE'")
    exit()
logger.info("✅ API Key successfully found.")

# --- Gemini Client for Token Management ---
try:
    management_client = genai.Client(
        api_key=api_key,
        http_options={'api_version': 'v1alpha'}
    )
    model = "gemini-2.5-flash-preview-native-audio-dialog"
    logger.info("✅ Management client initialized.")
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
                session_resumption=types.SessionResumptionConfig(handle=session_handle),
            ),
        ) as session:
            logger.info("✅ Connection to Gemini Live API successful.")
            await websocket.send("STATUS: Connected to Gemini. Ready to record.")

            # Task to stream Gemini's response back to the client
            async def receive_from_gemini():
                try:
                    async for response in session.receive():
                        if response.data:
                            await websocket.send(response.data)
                        if response.session_resumption_update:
                            update = response.session_resumption_update
                            if update.resumable and update.new_handle:
                                logger.info(f"✅ Received new resumable handle: {update.new_handle[:10]}...")
                                SESSION_HANDLES[websocket.remote_address] = update.new_handle
                        if response.server_content and response.server_content.turn_complete:
                            logger.info("✅ Gemini indicated the turn is complete.")
                            await websocket.send("STATUS: Gemini turn complete. Ready to record.")
                except Exception as e:
                    logger.error(f"Error receiving from Gemini: {e}")
                    await websocket.send(f"ERROR: Gemini connection error: {e}")

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
                        audio_segment = AudioSegment.from_file(audio_buffer, format="webm")
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