document.addEventListener('DOMContentLoaded', () => {
    // --- Clock & Connection Manager ---
    const connStatus = document.getElementById('conn-status');
    const sysTime = document.getElementById('sys-time');
    const chatHistory = document.getElementById('chat-history');
    const chatInput = document.getElementById('chat-input');
    const sendBtn = document.getElementById('send-btn');
    const micBtn = document.getElementById('mic-btn');
    const micLabel = document.getElementById('mic-label');

    setInterval(() => {
        const now = new Date();
        sysTime.textContent = now.toTimeString().split(' ')[0];
    }, 1000);

    let ws;
    function connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;

        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            connStatus.innerHTML = '<span class="dot"></span> ONLINE';
            connStatus.className = 'status-badge';
        };

        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                handleServerEvent(msg.event, msg.data);
            } catch (e) {
                console.error("Failed to parse WS payload:", e);
            }
        };

        ws.onclose = () => {
            connStatus.innerHTML = '<span class="dot" style="background:#ef4444"></span> DISCONNECTED';
            connStatus.className = 'status-badge red';
            setTimeout(connectWebSocket, 3000);
        };
    }

    connectWebSocket();

    // --- Web Audio API UI Sound Cue Synthesizer ---
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    let audioCtx = null;

    function initAudioContext() {
        if (!audioCtx && AudioContext) {
            audioCtx = new AudioContext();
        }
    }

    function playSoundCue(cueType) {
        initAudioContext();
        if (!audioCtx) return;

        const now = audioCtx.currentTime;
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();

        osc.connect(gain);
        gain.connect(audioCtx.destination);

        if (cueType === 'wake_word') {
            osc.type = 'sine';
            osc.frequency.setValueAtTime(880, now);
            osc.frequency.exponentialRampToValueAtTime(1760, now + 0.15);
            gain.gain.setValueAtTime(0.15, now);
            gain.gain.exponentialRampToValueAtTime(0.01, now + 0.25);
            osc.start(now);
            osc.stop(now + 0.25);
        } else if (cueType === 'task_complete') {
            osc.type = 'triangle';
            osc.frequency.setValueAtTime(523.25, now);
            osc.frequency.setValueAtTime(659.25, now + 0.1);
            osc.frequency.setValueAtTime(783.99, now + 0.2);
            gain.gain.setValueAtTime(0.15, now);
            gain.gain.exponentialRampToValueAtTime(0.01, now + 0.4);
            osc.start(now);
            osc.stop(now + 0.4);
        } else if (cueType === 'alert') {
            osc.type = 'sawtooth';
            osc.frequency.setValueAtTime(440, now);
            osc.frequency.setValueAtTime(330, now + 0.15);
            gain.gain.setValueAtTime(0.1, now);
            gain.gain.exponentialRampToValueAtTime(0.01, now + 0.3);
            osc.start(now);
            osc.stop(now + 0.3);
        }
    }

    // --- Web Speech Synthesis (Male / Female Persona) & Instant Barge-In ---
    let voiceGender = 'male'; // Default JARVIS persona is Male

    function selectVoice(gender) {
        if (!('speechSynthesis' in window)) return null;
        const voices = window.speechSynthesis.getVoices();
        if (!voices || voices.length === 0) return null;
        
        if (gender === 'male') {
            // Explicitly search for Male British / English voices
            return voices.find(v => (v.lang.includes('en') || v.lang.includes('GB')) && 
                                    (v.name.includes('George') || v.name.includes('Alan') || v.name.includes('Oliver') || v.name.includes('Male') || v.name.includes('David') || v.name.includes('James') || v.name.includes('Mark'))) ||
                   voices.find(v => (v.lang === 'en-GB' || v.lang === 'en_GB') && !v.name.includes('Hazel') && !v.name.includes('Susan') && !v.name.includes('Female')) ||
                   voices.find(v => v.lang.startsWith('en')) ||
                   voices[0];
        } else {
            // Search for Female voices
            return voices.find(v => (v.lang.includes('en') || v.lang.includes('GB')) && 
                                    (v.name.includes('Hazel') || v.name.includes('Female') || v.name.includes('Zira') || v.name.includes('Susan') || v.name.includes('Catherine'))) ||
                   voices.find(v => v.lang.startsWith('en')) ||
                   voices[0];
        }
    }

    if ('speechSynthesis' in window) {
        window.speechSynthesis.onvoiceschanged = () => selectVoice(voiceGender);
    }

    // --- Self-Learning Engine Manager ---
    let isSelfLearningActive = false;
    const selfLearningBtn = document.getElementById('btn-self-learning');

    if (selfLearningBtn) {
        selfLearningBtn.addEventListener('click', () => {
            isSelfLearningActive = !isSelfLearningActive;
            setSelfLearningUI(isSelfLearningActive);
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ event: 'toggle_self_learning', enabled: isSelfLearningActive }));
            }
        });
    }

    function setSelfLearningUI(active) {
        isSelfLearningActive = active;
        if (!selfLearningBtn) return;
        if (active) {
            selfLearningBtn.classList.add('active');
            selfLearningBtn.textContent = '🧠 SELF-LEARNING: ACTIVE';
            document.getElementById('learning-status-badge').textContent = 'CRAWLING INTERNET';
            document.getElementById('learning-status-badge').className = 'badge green';
        } else {
            selfLearningBtn.classList.remove('active');
            selfLearningBtn.textContent = '🧠 SELF-LEARNING: INACTIVE';
            document.getElementById('learning-status-badge').textContent = 'IDLE';
            document.getElementById('learning-status-badge').className = 'badge';
        }
    }

    function updateLearningProgress(data) {
        setSelfLearningUI(data.active);
        if (data.current_topic) {
            document.getElementById('learning-topic').textContent = `"${data.current_topic}"`;
        }
        if (data.progress_percent !== undefined) {
            document.getElementById('learning-progress-fill').style.width = `${data.progress_percent}%`;
        }
        if (data.pages_scraped !== undefined) {
            document.getElementById('pages-scraped-val').textContent = data.pages_scraped;
        }
        if (data.total_records !== undefined) {
            document.getElementById('total-records-val').textContent = data.total_records;
        }
    }
    let activePersonaMode = 'jarvis';
    const personaBtns = document.querySelectorAll('.persona-btn');

    personaBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const persona = btn.getAttribute('data-persona');
            setPersonaUI(persona);
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ event: 'change_persona', persona: persona }));
            }
        });
    });

    function setPersonaUI(persona) {
        activePersonaMode = persona;
        personaBtns.forEach(b => {
            if (b.getAttribute('data-persona') === persona) {
                b.classList.add('active');
            } else {
                b.classList.remove('active');
            }
        });
    }

    function speakText(text) {
        if (!('speechSynthesis' in window) || !text) return;
        
        window.speechSynthesis.cancel();

        const utterance = new SpeechSynthesisUtterance(text);
        const selectedVoice = selectVoice(voiceGender);
        if (selectedVoice) {
            utterance.voice = selectedVoice;
        }
        
        // Dynamic Persona Vocal Tuning
        if (activePersonaMode === 'grok') {
            utterance.rate = 1.15; // Faster cadence for Grok
            utterance.pitch = 1.1;  // Punchy, dynamic inflection
        } else if (activePersonaMode === 'blended') {
            utterance.rate = 1.08;
            utterance.pitch = 0.95;
        } else {
            utterance.rate = 1.0;  // Composed British cadence
            utterance.pitch = 0.9;  // Steady deep pitch for JARVIS Prime
        }

        utterance.onstart = () => { isSpeaking = true; };
        utterance.onend = () => { isSpeaking = false; };
        utterance.onerror = () => { isSpeaking = false; };

        window.speechSynthesis.speak(utterance);
    }

    function triggerBargeIn() {
        if ('speechSynthesis' in window) {
            window.speechSynthesis.cancel();
        }
        isSpeaking = false;
    }

    // --- Interactive Chat & Command Submission ---
    function sendCommand(text) {
        const cmd = text.trim();
        if (!cmd) return;

        triggerBargeIn();
        playSoundCue('wake_word');

        appendChatMessage('user', 'YOU', cmd);
        chatInput.value = '';

        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ event: 'user_command', text: cmd }));
        } else {
            appendChatMessage('assistant', 'JARVIS', 'Connection offline. Please ensure main.py is running.');
        }
    }

    sendBtn.addEventListener('click', () => sendCommand(chatInput.value));
    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') sendCommand(chatInput.value);
    });

    function appendChatMessage(role, senderName, text) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `chat-message ${role}`;
        msgDiv.innerHTML = `<span class="sender">${senderName}</span><p>${escapeHtml(text)}</p>`;
        chatHistory.appendChild(msgDiv);
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }

    // --- Web Speech API Microphone Voice Input ---
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    let recognition = null;
    let isRecording = false;

    if (SpeechRecognition) {
        recognition = new SpeechRecognition();
        recognition.continuous = false;
        recognition.interimResults = false;

        recognition.onstart = () => {
            triggerBargeIn();
            isRecording = true;
            micBtn.classList.add('recording');
            micLabel.textContent = 'LISTENING...';
        };

        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            chatInput.value = transcript;
            sendCommand(transcript);
        };

        recognition.onerror = (e) => {
            console.warn("Speech recognition error:", e.error);
            stopRecording();
        };

        recognition.onend = () => {
            stopRecording();
        };
    }

    function stopRecording() {
        isRecording = false;
        micBtn.classList.remove('recording');
        micLabel.textContent = 'VOICE INPUT';
    }

    micBtn.addEventListener('click', () => {
        triggerBargeIn();
        if (!recognition) {
            alert("Web Speech API is not supported in this browser. Please type commands in the text box.");
            return;
        }
        if (isRecording) {
            recognition.stop();
        } else {
            try {
                recognition.start();
            } catch (e) {
                console.error("Mic start error:", e);
            }
        }
    });

    // --- Audio Canvas Visualizer ---
    const canvas = document.getElementById('audio-visualizer');
    const ctx = canvas ? canvas.getContext('2d') : null;
    let isSpeaking = false;

    function resizeCanvas() {
        if (!canvas) return;
        canvas.width = canvas.parentElement.clientWidth;
        canvas.height = canvas.parentElement.clientHeight;
    }
    window.addEventListener('resize', resizeCanvas);
    resizeCanvas();

    function drawVisualizer() {
        requestAnimationFrame(drawVisualizer);
        if (!canvas || !ctx) return;
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        const bars = 40;
        const width = canvas.width / bars;

        for (let i = 0; i < bars; i++) {
            let height = 5;
            if (isSpeaking) {
                height = Math.sin(Date.now() * 0.005 + i * 0.3) * 35 + 40;
            } else {
                height = Math.sin(Date.now() * 0.002 + i * 0.1) * 6 + 10;
            }

            const gradient = ctx.createLinearGradient(0, canvas.height, 0, 0);
            gradient.addColorStop(0, '#8b0000');
            gradient.addColorStop(0.6, '#cc1c1c');
            gradient.addColorStop(1, '#e83232');

            ctx.fillStyle = gradient;
            ctx.fillRect(i * width, canvas.height - height, width - 2, height);
        }
    }
    drawVisualizer();

    // --- Server Event Dispatcher ---
    function handleServerEvent(event, data) {
        if (event === 'telemetry') {
            updateTelemetryGauges(data);
        } else if (event === 'voice_state') {
            document.getElementById('voice-state').textContent = data.state.toUpperCase();
            isSpeaking = (data.state === 'speaking' || data.state === 'listening' || data.state === 'thinking');
            if (data.latest_query) {
                document.getElementById('latest-query').textContent = `"${data.latest_query}"`;
            }
        } else if (event === 'chat_response') {
            if (data.response) {
                appendChatMessage('assistant', 'JARVIS', data.response);
                speakText(data.response);
            }
        } else if (event === 'voice_gender_update') {
            if (data.gender) {
                voiceGender = data.gender;
                selectVoice(voiceGender);
            }
        } else if (event === 'persona_update') {
            if (data.persona) {
                setPersonaUI(data.persona);
            }
        } else if (event === 'self_learning_state') {
            setSelfLearningUI(data.active);
        } else if (event === 'learning_progress') {
            updateLearningProgress(data);
        } else if (event === 'sound_cue') {
            playSoundCue(data.cue_type);
        } else if (event === 'barge_in') {
            triggerBargeIn();
        } else if (event === 'vision_frame' || event === 'vision_update') {
            isVisionFramePending = false;
            const b64 = data.image_b64 || data.b64_image;
            if (b64) {
                document.getElementById('vision-frame').src = `data:image/jpeg;base64,${b64}`;
            }
            if (data.mode) {
                document.getElementById('vision-mode').textContent = data.mode.toUpperCase();
            }
        } else if (event === 'vision_update') {
            if (data.image_b64) {
                const imgEl = document.getElementById('vision-frame');
                if (imgEl) imgEl.src = `data:image/jpeg;base64,${data.image_b64}`;
                const vMode = document.getElementById('vision-mode');
                if (vMode && isLiveStreaming) vMode.textContent = `🔴 LIVE ${data.mode}`;
            }
            isVisionFramePending = false;
        } else if (event === 'vision_stopped') {
            console.log('[BAT-VISION] Camera hardware released by server.');
        } else if (event === 'tasks_update') {
            updateTasksList(data.tasks);
        } else if (event === 'code_diff') {
            renderCodeDiff(data);
        }
    }

    let activeVisionMode = 'screen';
    let isLiveStreaming = false;
    let isVisionFramePending = false;
    let liveStreamTimer = null;

    window.triggerVision = function(mode) {
        playSoundCue('wake_word');
        activeVisionMode = mode;
        const screenBtn = document.getElementById('btn-vision-screen');
        const webcamBtn = document.getElementById('btn-vision-webcam');
        if (mode === 'webcam') {
            if (screenBtn) screenBtn.classList.remove('active');
            if (webcamBtn) webcamBtn.classList.add('active');
        } else {
            if (webcamBtn) webcamBtn.classList.remove('active');
            if (screenBtn) screenBtn.classList.add('active');
        }
        if (ws && ws.readyState === WebSocket.OPEN) {
            isVisionFramePending = true;
            ws.send(JSON.stringify({ event: 'request_vision_frame', mode: mode }));
        }
        
        // Auto-start continuous streaming loop when camera/screen feed is selected
        if (!isLiveStreaming) {
            window.toggleLiveVisionStream();
        }
    };

    window.captureSingleFrame = function() {
        playSoundCue('wake_word');
        if (ws && ws.readyState === WebSocket.OPEN) {
            isVisionFramePending = true;
            ws.send(JSON.stringify({ event: 'request_vision_frame', mode: activeVisionMode }));
        }
    };

    window.toggleLiveVisionStream = function() {
        const liveBtn = document.getElementById('btn-vision-live');
        const modeBadge = document.getElementById('vision-mode');
        
        if (isLiveStreaming) {
            isLiveStreaming = false;
            if (liveStreamTimer) clearInterval(liveStreamTimer);
            liveStreamTimer = null;
            if (liveBtn) {
                liveBtn.classList.remove('active');
                liveBtn.textContent = '▶️ Continuous Live';
            }
            if (modeBadge) modeBadge.textContent = `${activeVisionMode.toUpperCase()} FEED`;
            playSoundCue('alert');
        } else {
            isLiveStreaming = true;
            if (liveBtn) {
                liveBtn.classList.add('active');
                liveBtn.textContent = '⏸️ Pause Live';
            }
            if (modeBadge) modeBadge.textContent = `🔴 LIVE ${activeVisionMode.toUpperCase()}`;
            playSoundCue('wake_word');
            
            // Zero-backlog, non-blocking poll loop (only requests next frame when previous frame arrives)
            liveStreamTimer = setInterval(() => {
                if (isLiveStreaming && !isVisionFramePending && ws && ws.readyState === WebSocket.OPEN) {
                    isVisionFramePending = true;
                    ws.send(JSON.stringify({ event: 'request_vision_frame', mode: activeVisionMode }));
                }
            }, 80);
        }
    };

    // --- Stop All Vision Feeds ---
    window.stopVisionFeed = function() {
        // 1. Stop live stream timer if running
        if (isLiveStreaming) {
            isLiveStreaming = false;
            if (liveStreamTimer) clearInterval(liveStreamTimer);
            liveStreamTimer = null;
        }
        isVisionFramePending = false;

        // 2. Tell the SERVER to release the camera hardware (turns off the camera light)
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ event: 'stop_vision_feed' }));
        }

        // 3. Deactivate all vision buttons immediately
        document.querySelectorAll('.vision-btn').forEach(btn => {
            btn.classList.remove('active');
            if (btn.id === 'btn-vision-live') btn.textContent = '▶️ Continuous Live';
        });

        // 4. Reset vision frame to idle placeholder right away
        const visionFrame = document.getElementById('vision-frame');
        if (visionFrame) {
            visionFrame.src = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='800' height='420'><rect width='100%' height='100%' fill='%2308020a'/><text x='50%' y='46%' fill='%23cc1c1c' font-family='monospace' font-size='18' text-anchor='middle'>FEED TERMINATED</text><text x='50%' y='56%' fill='%237a5a5a' font-family='monospace' font-size='12' text-anchor='middle'>SELECT SCREEN OR WEBCAM INPUT TO RESTART</text></svg>";
        }

        // 5. Update mode badge
        const modeBadge = document.getElementById('vision-mode');
        if (modeBadge) {
            modeBadge.textContent = 'OFFLINE';
            modeBadge.className = 'badge red';
        }

        playSoundCue('alert');
    };

    // --- Gauge Updates ---
    function updateTelemetryGauges(data) {
        if (data.cpu_percent !== undefined) {
            document.getElementById('cpu-val').textContent = `${Math.round(data.cpu_percent)}%`;
            document.getElementById('cpu-gauge').style.setProperty('--percent', data.cpu_percent);
        }
        if (data.ram_percent !== undefined) {
            document.getElementById('ram-val').textContent = `${Math.round(data.ram_percent)}%`;
            document.getElementById('ram-gauge').style.setProperty('--percent', data.ram_percent);
        }
        if (data.disk_percent !== undefined) {
            document.getElementById('disk-val').textContent = `${Math.round(data.disk_percent)}%`;
            document.getElementById('disk-gauge').style.setProperty('--percent', data.disk_percent);
        }
        if (data.status) {
            document.getElementById('port-status').textContent = data.status;
        }
        if (data.vault_status) {
            updateApiVaultGrid(data.vault_status);
        }
        if (data.tasks !== undefined) {
            updateTasksList(data.tasks);
        }
    }

    function updateApiVaultGrid(providers) {
        const gridEl = document.getElementById('api-vault-grid');
        if (!gridEl) return;

        if (!providers || providers.length === 0) {
            gridEl.innerHTML = '<div class="empty-state">No free cloud API keys currently configured in Vault. (Ollama / Local Search Fallback active)</div>';
            return;
        }

        let html = '';
        providers.forEach(p => {
            let badgeClass = 'yellow';
            if (p.status === 'ONLINE') badgeClass = 'green';
            if (p.status === 'RATE-LIMITED' || p.status === 'REVOKED') badgeClass = 'red';

            html += `
                <div class="provider-item">
                    <div class="p-header">
                        <span class="p-name">${escapeHtml(p.name)}</span>
                        <span class="badge ${badgeClass}">${p.status}</span>
                    </div>
                    <div class="p-model">Model: ${escapeHtml(p.model)}</div>
                    <div class="p-meta">
                        <span>Latency: ${p.latency_ms}ms</span>
                        <span>Quota: ${p.quota_rpm} RPM</span>
                    </div>
                </div>
            `;
        });
        gridEl.innerHTML = html;
    }

    // --- Task List ---
    function updateTasksList(tasks) {
        const taskListEl = document.getElementById('task-list');
        document.getElementById('active-tasks-count').textContent = `${tasks ? tasks.length : 0} ACTIVE`;

        if (!tasks || tasks.length === 0) {
            taskListEl.innerHTML = '<div class="empty-state">No background tasks currently running.</div>';
            return;
        }

        let html = '';
        tasks.forEach(t => {
            const percent = t.progress || 50;
            html += `
                <div class="task-item">
                    <div class="title">${escapeHtml(t.name)} (ID: ${t.task_id})</div>
                    <div class="progress-bar-bg">
                        <div class="progress-bar-fill" style="width: ${percent}%"></div>
                    </div>
                    <div class="meta">
                        <span>Status: ${t.status}</span>
                        <span>Elapsed: ${t.elapsed}s</span>
                    </div>
                </div>
            `;
        });
        taskListEl.innerHTML = html;
    }

    // --- Code Diff Viewer ---
    function renderCodeDiff(data) {
        const diffBox = document.getElementById('diff-content');
        const diffStatus = document.getElementById('diff-status');

        if (!data || !data.diff_text) {
            diffBox.innerHTML = '<div class="diff-placeholder">No self-modification patch currently pending review.</div>';
            diffStatus.textContent = 'NO PROPOSED DIFF';
            diffStatus.className = 'badge yellow';
            return;
        }

        diffStatus.textContent = `PATCH FOR: ${data.filepath}`;
        diffStatus.className = 'badge green';

        const lines = data.diff_text.split('\n');
        let html = '';
        lines.forEach(line => {
            if (line.startsWith('+') && !line.startsWith('+++')) {
                html += `<span class="diff-add">${escapeHtml(line)}</span>`;
            } else if (line.startsWith('-') && !line.startsWith('---')) {
                html += `<span class="diff-remove">${escapeHtml(line)}</span>`;
            } else {
                html += `<span>${escapeHtml(line)}</span>\n`;
            }
        });
        diffBox.innerHTML = html;
    }

    function escapeHtml(text) {
        return (text || '')
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");
    }
});
