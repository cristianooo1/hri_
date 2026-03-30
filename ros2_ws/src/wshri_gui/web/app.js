const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const chatLog = document.getElementById("chatLog");
const micBtn = document.getElementById("micBtn");
const cameraStream = document.getElementById("cameraStream");
const cameraStatus = document.getElementById("cameraStatus");
const cameraFrame = document.querySelector(".camera-frame");
const inputHint = document.querySelector(".input-hint");
const sendBtn = chatForm?.querySelector(".send-btn");

let listening = false;
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
  if (sendBtn) {
    sendBtn.disabled = isPending;
    sendBtn.textContent = isPending ? "Thinking..." : "Send";
  }

  if (chatInput) {
    chatInput.disabled = isPending;
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

micBtn.addEventListener("click", () => {
  listening = !listening;
  micBtn.classList.toggle("listening", listening);
  micBtn.querySelector("span").textContent = listening ? "Listening" : "Mic";
});

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
  inputHint.textContent = "Chat requests are sent to /api/llm on this GUI server.";
}
