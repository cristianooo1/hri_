const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const chatLog = document.getElementById("chatLog");
const micBtn = document.getElementById("micBtn");
const cameraStream = document.getElementById("cameraStream");
const cameraStatus = document.getElementById("cameraStatus");
const cameraFrame = document.querySelector(".camera-frame");
const grid = document.querySelector(".grid");
const tabs = document.querySelectorAll(".tab[data-view]");
const objectShelf = document.getElementById("objectShelf");
const objectMeta = document.getElementById("objectMeta");
const detectionStatus = document.getElementById("detectionStatus");
const inputHint = document.querySelector(".input-hint");
const sendBtn = chatForm?.querySelector(".send-btn");
const micIndicator = document.getElementById("micIndicator");
const llmStatus = document.getElementById("llmStatus");

let micState = "idle";
let uiLocked = false;
let chatPending = false;
let cameraTimer = null;
let cameraFramePending = false;
let lastCameraFrameAt = 0;

const fruitIcons = {
  apple: "🍎",
  banana: "🍌",
  orange: "🍊",
  broccoli: "🥦",
  carrot: "🥕",
};

function setView(view) {
  if (!grid) {
    return;
  }

  grid.classList.remove("view-camera", "view-manual");
  if (view === "camera") {
    grid.classList.add("view-camera");
  } else if (view === "manual") {
    grid.classList.add("view-manual");
  }

  tabs.forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.view === view);
  });
}

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
        state === "recording"
          ? "Listening"
          : state === "processing"
            ? "Processing"
            : "Mic";
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

tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    setView(tab.dataset.view || "overview");
  });
});

async function startCamera() {
  if (!cameraStream || !cameraStatus || !cameraFrame) {
    return;
  }

  const refreshFrame = () => {
    if (cameraFramePending) {
      return;
    }

    cameraFramePending = true;
    cameraStream.src = `/api/cv_frame?t=${Date.now()}`;
  };

  cameraStream.onload = () => {
    cameraFramePending = false;
    lastCameraFrameAt = Date.now();
    cameraFrame.classList.add("live");
    // cameraStatus.textContent = "Camera live";
  };

  cameraStream.onerror = () => {
    cameraFramePending = false;
    cameraStatus.textContent = "Camera frame unavailable";
  };

  if (cameraTimer) {
    window.clearInterval(cameraTimer);
  }

  cameraTimer = window.setInterval(() => {
    refreshFrame();
    if (lastCameraFrameAt && Date.now() - lastCameraFrameAt > 1500) {
      cameraStatus.textContent = "Camera stream stalled";
    }
  }, 200);

  refreshFrame();
}

function renderDetections(payload) {
  if (!objectShelf || !objectMeta || !detectionStatus) {
    return;
  }

  const objects = Array.isArray(payload.objects) ? payload.objects : [];
  const counts = objects.reduce((acc, item) => {
    acc[item.label] = (acc[item.label] || 0) + 1;
    return acc;
  }, {});

  detectionStatus.textContent =
    payload.status === "error"
      ? `CV error: ${payload.error || "unknown"}`
      : payload.status === "loading"
        ? "Loading detection model..."
        : `${objects.length} stable object${objects.length === 1 ? "" : "s"} detected`;

  objectShelf.replaceChildren();
  objectMeta.replaceChildren();

  if (!objects.length) {
    const emptyCard = document.createElement("div");
    emptyCard.className = "meta-card";
    emptyCard.textContent =
      payload.status === "running"
        ? "No stable detections yet"
        : "Waiting for detections";
    objectShelf.appendChild(emptyCard);
  }

  objects.forEach((item) => {
    const card = document.createElement("div");
    card.className = `fruit ${item.label || ""}`;
    card.title = `${item.label} ${item.confidence}`;

    const icon = document.createElement("div");
    icon.textContent = fruitIcons[item.label] || "📦";
    icon.style.fontSize = "32px";

    const info = document.createElement("div");
    info.className = "fruit-info";

    const label = document.createElement("div");
    label.className = "fruit-label";
    label.textContent = item.label || "unknown";

    const sub = document.createElement("div");
    sub.className = "fruit-sub";
    sub.textContent = `${item.position_tag || "unknown"} · ${Math.round((item.confidence || 0) * 100)}%`;

    info.append(label, sub);
    card.replaceChildren(icon, info);
    objectShelf.appendChild(card);
  });

  Object.entries(counts)
    .sort(([left], [right]) => left.localeCompare(right))
    .forEach(([label, count]) => {
      const meta = document.createElement("div");
      meta.className = "meta-card";
      meta.textContent = `${label}: ${count}`;
      objectMeta.appendChild(meta);
    });
}

async function pollDetections() {
  try {
    const response = await fetch("/api/detections", { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Failed to load detections.");
    }
    renderDetections(payload);
    // if (cameraStatus) {
    //   if (payload.status === "error") {
    //     cameraStatus.textContent = "Camera live · CV error";
    //   } else if (payload.frame_id > 0 && lastCameraFrameAt) {
    //     cameraStatus.textContent = `Camera live · CV frame ${payload.frame_id}`;
    //   }
    // }
  } catch (error) {
    if (detectionStatus) {
      detectionStatus.textContent =
        error.message || "Failed to load detections.";
    }
  } finally {
    window.setTimeout(pollDetections, 800);
  }
}

startCamera();
pollDetections();
setView("overview");

window.addEventListener("beforeunload", () => {
  if (cameraTimer) {
    window.clearInterval(cameraTimer);
  }
});

if (inputHint) {
  inputHint.textContent =
    "Hold Mic to talk (Whisper + TTS). Send uses /api/llm text-only.";
}
