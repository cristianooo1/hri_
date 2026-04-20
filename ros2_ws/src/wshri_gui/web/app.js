const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const chatLog = document.getElementById("chatLog");
const micBtn = document.getElementById("micBtn");
const cameraStream = document.getElementById("cameraStream");
const cameraStatus = document.getElementById("cameraStatus");
const cameraFrame = document.querySelector(".camera-frame");
const inputHint = document.querySelector(".input-hint");
const sendBtn = chatForm?.querySelector(".send-btn");
const micIndicator = document.getElementById("micIndicator");
const llmStatus = document.getElementById("llmStatus");

let micState = "idle";
let uiLocked = false;
let chatPending = false;
let activeStream = null;

function addMessage(type, text) {
  const msg = document.createElement("div");
  msg.className = `msg ${type}`;

  const label = document.createElement("div");
  label.className = "msg-label";
  label.textContent = type === "user" ? "You" : "Assistant";
  if (type === "system") {
    label.textContent = "System";
  }

  const body = document.createElement("div");
  body.className = "msg-body";
  body.textContent = text;

  msg.append(label, body);
  chatLog.appendChild(msg);
  chatLog.scrollTop = chatLog.scrollHeight;
}

function setChatPending(isPending) {
  chatPending = isPending;
  applyInteractivity();
}

function setMicState(state, message) {
  micState = state;
  if (micBtn) {
    micBtn.classList.toggle("listening", state === "recording");
    const label = micBtn.querySelector("span");
    if (label) {
      label.textContent =
        state === "recording" ? "Listening" : state === "processing" ? "Processing" : "Mic";
    }
  }

  if (micIndicator) {
    micIndicator.classList.remove("recording", "processing");
    if (state === "recording") {
      micIndicator.classList.add("recording");
    } else if (state === "processing") {
      micIndicator.classList.add("processing");
    }
  }

  if (llmStatus) {
    llmStatus.textContent =
      message ||
      (state === "recording"
        ? "Recording... release Mic to stop"
        : state === "processing"
          ? "Transcribing + generating response"
          : "Mic idle · Whisper ready on first use");
  }

  applyInteractivity();
}

function setUiLocked(isLocked) {
  uiLocked = isLocked;
  document.body.classList.toggle("ui-locked", isLocked);
  applyInteractivity();
}

function applyInteractivity() {
  const elements = document.querySelectorAll("button, input, select, textarea");
  elements.forEach((element) => {
    if (element === micBtn) {
      return;
    }

    if (element === chatInput || element === sendBtn) {
      element.disabled = uiLocked || chatPending;
      return;
    }

    element.disabled = uiLocked;
  });

  if (micBtn) {
    micBtn.disabled = micState === "processing";
  }

  if (sendBtn) {
    sendBtn.textContent = chatPending ? "Thinking..." : "Send";
  }
}

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = chatInput.value.trim();
  if (!text) {
    return;
  }

  addMessage("user", text);
  chatInput.value = "";
  setChatPending(true);

  try {
    const response = await fetch("/api/llm", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ prompt: text }),
    });

    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "The assistant request failed.");
    }

    addMessage("assistant", payload.reply);
  } catch (error) {
    console.error("LLM request failed:", error);
    addMessage("system", error.message || "The assistant is unavailable.");
  } finally {
    setChatPending(false);
    chatInput.focus();
  }
});

async function startRecording() {
  setUiLocked(true);
  setMicState("processing", "Starting mic...");
  try {
    const response = await fetch("/api/listen/start", { method: "POST" });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Failed to start recording.");
    }
    setMicState("recording", "Recording... release Mic to stop");
  } catch (error) {
    console.error("Start recording failed:", error);
    addMessage("system", error.message || "Unable to start recording.");
    setMicState("idle");
    setUiLocked(false);
  }
}

async function stopRecording() {
  setMicState("processing", "Transcribing + generating response");
  try {
    const response = await fetch("/api/listen/stop", { method: "POST" });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Failed to process audio.");
    }

    if (payload.user_said) {
      addMessage("user", payload.user_said);
    }

    if (payload.reply) {
      const target = payload.user_said ? "assistant" : "system";
      addMessage(target, payload.reply);
    }

    if (payload.audio_error) {
      addMessage("system", `Voice playback failed: ${payload.audio_error}`);
    }
  } catch (error) {
    console.error("Stop recording failed:", error);
    addMessage("system", error.message || "Unable to process the recording.");
  } finally {
    setMicState("idle");
    setUiLocked(false);
  }
}

if (micBtn) {
  micBtn.addEventListener("pointerdown", (event) => {
    if (micState !== "idle") {
      return;
    }
    if (micBtn.setPointerCapture) {
      micBtn.setPointerCapture(event.pointerId);
    }
    startRecording();
  });

  const handlePointerRelease = () => {
    if (micState === "recording") {
      stopRecording();
    }
  };

  micBtn.addEventListener("pointerup", handlePointerRelease);
  micBtn.addEventListener("pointerleave", handlePointerRelease);
  micBtn.addEventListener("pointercancel", handlePointerRelease);
  window.addEventListener("pointerup", handlePointerRelease);
}

async function startCamera() {
  if (!cameraStream || !cameraStatus || !cameraFrame) {
    return;
  }

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    cameraStatus.textContent = "Camera unavailable";
    return;
  }

  try {
    activeStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment" },
      audio: false,
    });
    cameraStream.srcObject = activeStream;
    cameraFrame.classList.add("live");
    cameraStatus.textContent = "Live camera";
  } catch (error) {
    console.warn("Camera access failed:", error);
    cameraStatus.textContent = "Camera blocked";
  }
}

window.addEventListener("beforeunload", () => {
  if (!activeStream) {
    return;
  }
  activeStream.getTracks().forEach((track) => track.stop());
});

startCamera();

if (inputHint) {
  inputHint.textContent = "Hold Mic to talk (Whisper + TTS). Send uses /api/llm text-only.";
}
