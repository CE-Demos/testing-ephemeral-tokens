import streamlit as st
import subprocess
import os
import sys

def run_script(input_file_path, new_session=False):
    """
    Runs the session.py script as a subprocess and streams its output to the UI.
    """
    # --- Construct the command to run the script ---
    # Use sys.executable to ensure we're using the same Python interpreter
    # as the one running Streamlit.
    command = [sys.executable, "session.py", "--input-file", input_file_path]
    if new_session:
        command.append("--new-session")

    # --- Prepare for subprocess execution ---
    # Set the working directory to the script's location to ensure it finds
    # 'download.wav' and 'session_handle.txt'.
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # A placeholder for the real-time output
    output_placeholder = st.empty()
    output_text = ""

    try:
        # --- Execute the script ---
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Redirect stderr to stdout to capture all output
            text=True,
            encoding='utf-8',
            cwd=script_dir,
            bufsize=1  # Line-buffered
        )

        # --- Stream the output to the UI in real-time ---
        with output_placeholder.container():
            st.write("### Script Output")
            log_box = st.code("", language="log")
            for line in iter(process.stdout.readline, ''):
                output_text += line
                log_box.text(output_text)
        
        process.stdout.close()
        return_code = process.wait()

        # --- Display final status and audio player ---
        if return_code == 0:
            st.success("✅ Script finished successfully!")
            output_filename = f"gemini_response_{os.path.basename(input_file_path)}"
            audio_file_path = os.path.join(script_dir, output_filename)
            if os.path.exists(audio_file_path):
                st.write("#### 🔊 Gemini's Response:")
                with open(audio_file_path, "rb") as f:
                    st.audio(f.read(), format="audio/wav")
        else:
            st.error(f"🔴 Script failed with return code {return_code}.")

    except FileNotFoundError:
        st.error("🔴 Error: `session.py` not found. Make sure this app is in the same directory as the script.")
    except Exception as e:
        st.error(f"An unexpected error occurred: {e}")

# --- Streamlit App UI ---
st.set_page_config(page_title="Gemini Live Session", layout="wide")
st.title("🎙️ Gemini Live API Session Manager")

# Check for GOOGLE_API_KEY before showing buttons
if not os.getenv("GOOGLE_API_KEY"):
    st.error("🔴 **Error:** The `GOOGLE_API_KEY` environment variable is not set.")
    st.warning("Please set it in your terminal before running this Streamlit app:\n\n`export GOOGLE_API_KEY='YOUR_API_KEY'`")
else:
    uploaded_file = st.file_uploader(
        "Upload an audio file to send to Gemini...",
        type=["wav", "mp3", "m4a", "flac", "ogg"]
    )

    if uploaded_file is not None:
        # Save the uploaded file to disk so the subprocess can access it
        script_dir = os.path.dirname(os.path.abspath(__file__))
        input_file_path = os.path.join(script_dir, uploaded_file.name)
        with open(input_file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        st.write("#### Your Uploaded Audio:")
        st.audio(uploaded_file)
        st.divider()

        col1, col2 = st.columns(2)
        if col1.button("▶️ Process and Resume Session", use_container_width=True, type="secondary"):
            run_script(input_file_path, new_session=False)

        if col2.button("🔁 Process and Start New Session", use_container_width=True, type="primary"):
            run_script(input_file_path, new_session=True)