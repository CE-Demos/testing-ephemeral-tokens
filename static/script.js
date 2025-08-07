document.addEventListener('DOMContentLoaded', () => {
    const recordButton = document.getElementById('recordButton');
    const statusDiv = document.getElementById('status');
    const WEBSOCKET_URL = 'ws://localhost:8765';

    let websocket;
    let mediaRecorder;
    let isRecording = false;
    let audioContext;
    let audioQueue = [];
    let isPlaying = false;

    function connectWebSocket() {
        statusDiv.textContent = 'Connecting to server...';
        websocket = new WebSocket(WEBSOCKET_URL);

        websocket.onopen = () => {
            console.log('WebSocket connection established.');
            // The server will send a status update when it's ready
            statusDiv.textContent = 'Connected. Waiting for server ready signal.';
        };

        websocket.onmessage = (event) => {
            if (typeof event.data === 'string') {
                console.log('Received text message:', event.data);
                handleTextMessage(event.data);
            } else {
                // Assuming binary data is audio from Gemini
                handleAudioMessage(event.data);
            }
        };

        websocket.onerror = (error) => {
            console.error('WebSocket error:', error);
            statusDiv.textContent = 'Connection error. Please check the server.';
            recordButton.disabled = true;
        };

        websocket.onclose = () => {
            console.log('WebSocket connection closed.');
            statusDiv.textContent = 'Disconnected. Please refresh to reconnect.';
            recordButton.disabled = true;
            if (isRecording) {
                stopRecording();
            }
        };
    }

    function handleTextMessage(message) {
        if (message.startsWith('STATUS:')) {
            const newStatus = message.substring('STATUS:'.length).trim();
            statusDiv.textContent = newStatus;
            // Enable the button only when Gemini is ready for a new turn
            if (newStatus.includes('Ready to record')) {
                recordButton.disabled = false;
                recordButton.textContent = 'Start Recording';
            }
        } else if (message.startsWith('ERROR:')) {
            const errorMsg = message.substring('ERROR:'.length).trim();
            statusDiv.textContent = `Error: ${errorMsg}`;
            recordButton.disabled = true;
        }
    }

    async function handleAudioMessage(audioData) {
        if (!audioContext) {
            // Create AudioContext on the first audio message to support browser autoplay policies
            audioContext = new (window.AudioContext || window.webkitAudioContext)();
        }
        const arrayBuffer = await audioData.arrayBuffer();
        audioQueue.push(arrayBuffer);
        if (!isPlaying) {
            playNextInQueue();
        }
    }

    async function playNextInQueue() {
        if (audioQueue.length === 0) {
            isPlaying = false;
            return;
        }
        isPlaying = true;
        const arrayBuffer = audioQueue.shift();
        try {
            const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
            const source = audioContext.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(audioContext.destination);
            source.onended = playNextInQueue; // Chain playback
            source.start();
        } catch (e) {
            console.error('Error decoding audio data:', e);
            playNextInQueue(); // Try the next chunk
        }
    }

    async function startRecording() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            alert('Your browser does not support audio recording.');
            return;
        }
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
            mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0 && websocket.readyState === WebSocket.OPEN) {
                    websocket.send(event.data);
                }
            };
            mediaRecorder.onstop = () => {
                if (websocket.readyState === WebSocket.OPEN) {
                    websocket.send('END_OF_STREAM');
                }
                statusDiv.textContent = 'Processing audio...';
                recordButton.disabled = true; // Disable until Gemini turn is complete
            };
            mediaRecorder.start(250); // Timeslice to stream audio chunks
            isRecording = true;
            recordButton.textContent = 'Stop Recording';
            recordButton.classList.add('recording');
            statusDiv.textContent = 'Recording... Speak now.';
        } catch (err) {
            console.error('Error getting user media:', err);
            statusDiv.textContent = 'Could not access microphone. Please grant permission.';
        }
    }

    function stopRecording() {
        if (mediaRecorder && mediaRecorder.state !== 'inactive') {
            mediaRecorder.stop();
        }
        isRecording = false;
        recordButton.textContent = 'Start Recording';
        recordButton.classList.remove('recording');
    }

    recordButton.addEventListener('click', () => {
        if (isRecording) {
            stopRecording();
        } else {
            startRecording();
        }
    });

    // Initial connection
    connectWebSocket();
});