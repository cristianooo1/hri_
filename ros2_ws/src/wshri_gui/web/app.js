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
const locationChoices = document.querySelectorAll("[data-location]");
const surfaceChoices = document.querySelectorAll("[data-surface]");
const catalogButtons = document.querySelectorAll(".catalog-main");
const infoButtons = document.querySelectorAll(".catalog-info");
const confirmModal = document.getElementById("confirmModal");
const confirmText = document.getElementById("confirmText");
const confirmYes = document.getElementById("confirmYes");
const confirmNo = document.getElementById("confirmNo");
const infoModal = document.getElementById("infoModal");
const infoTitle = document.getElementById("infoTitle");
const infoBody = document.getElementById("infoBody");
const infoClose = document.getElementById("infoClose");
const errorModal = document.getElementById("errorModal");
const errorText = document.getElementById("errorText");
const errorClose = document.getElementById("errorClose");

let micState = "idle";
let uiLocked = false;
let chatPending = false;
let cameraTimer = null;
let cameraFramePending = false;
let lastCameraFrameAt = 0;
let latestDetections = [];
let selectionState = {
  location: "kitchen",
  surface: "countertop",
  fruit: "",
};

const fruitIcons = {
  apple: "🍎",
  banana: "🍌",
  orange: "🍊",
  broccoli: "🥦",
  carrot: "🥕",
};

const itemMetadata = {
  apple: {
    nutrition: "Contains fiber and vitamin C.",
    handling: "Firm grip near the center.",
    use_case: "Good candidate for top-layer pick tasks.",
  },
  banana: {
    nutrition: "High in potassium and carbohydrates.",
    handling: "Avoid squeezing the curved sides.",
    use_case: "Useful for gentle grasp tests.",
  },
  orange: {
    nutrition: "Rich in vitamin C and water.",
    handling: "Round profile supports symmetric grasping.",
    use_case: "Reliable for spherical object pickups.",
  },
  broccoli: {
    nutrition: "High in fiber and vitamins K and C.",
    handling: "Stem-side grasp is more stable than crown-side.",
    use_case: "Tests irregular geometry handling.",
  },
  carrot: {
    nutrition: "High in beta-carotene.",
    handling: "Long thin profile needs aligned grasping.",
    use_case: "Good for narrow object validation.",
  },
};

function setView(view) {
  if (!grid) {
    return;
  }

  grid.classList.remove("view-overview", "view-camera", "view-manual");
  if (view === "camera") {
    grid.classList.add("view-camera");
  } else if (view === "manual") {
    grid.classList.add("view-manual");
  } else {
    grid.classList.add("view-overview");
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
          : "Mic idle · Whisper ready");
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
    micBtn.disabled = false;
  }

  if (sendBtn) {
    sendBtn.textContent = chatPending ? "Thinking..." : "Send";
  }
}

function openModal(modal) {
  if (!modal) {
    return;
  }
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
}

function closeModal(modal) {
  if (!modal) {
    return;
  }
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
}

function openConfirmModal(fruit) {
  selectionState.fruit = fruit;
  if (confirmText) {
    confirmText.textContent = `Request item: ${fruit[0].toUpperCase()}${fruit.slice(1)}`;
  }
  openModal(confirmModal);
}

function openInfoModal(fruit) {
  const metadata = itemMetadata[fruit];
  if (!metadata || !infoTitle || !infoBody) {
    return;
  }

  infoTitle.textContent = `${fruit[0].toUpperCase()}${fruit.slice(1)} info`;
  infoBody.replaceChildren();

  Object.entries(metadata).forEach(([key, value]) => {
    const row = document.createElement("div");
    row.className = "info-row";

    const label = document.createElement("span");
    label.className = "info-key";
    label.textContent = key.replaceAll("_", " ");

    const content = document.createElement("div");
    content.textContent = value;

    row.append(label, content);
    infoBody.appendChild(row);
  });

  openModal(infoModal);
}

function openErrorModal(fruit) {
  if (errorText) {
    errorText.textContent = `Item Out of Stock: No ${fruit[0].toUpperCase()}${fruit.slice(1)} detected.`;
  }
  openModal(errorModal);
}

function updateChoiceButtons(buttons, activeValue, attributeName) {
  buttons.forEach((button) => {
    button.classList.toggle(
      "active",
      button.dataset[attributeName] === activeValue,
    );
  });
}

function handleManualConfirm() {
  if (!selectionState.fruit) {
    closeModal(confirmModal);
    return;
  }

  const matchingObjects = latestDetections.filter(
    (item) => item.label === selectionState.fruit,
  );

  closeModal(confirmModal);

  if (matchingObjects.length > 0) {
    const item = matchingObjects[0];
    addMessage(
      "assistant",
      `Request confirmed for ${selectionState.fruit} from ${selectionState.location} / ${selectionState.surface}. ${selectionState.fruit[0].toUpperCase()}${selectionState.fruit.slice(1)} detected${item.position_tag ? ` at ${item.position_tag}` : ""}. Execution can proceed.`,
    );
  } else {
    openErrorModal(selectionState.fruit);
  }

  selectionState.fruit = "";
}

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  // NEW: Clear any stuck audio states before sending text
  if (micState !== "idle") {
    setMicState("idle");
    setUiLocked(false);
  }

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
    addMessage("system", error.message || "The assistant is unavailable.");
  } finally {
    setChatPending(false);
    chatInput.focus();
  }
});
let cancelRecording = false;

async function startRecording() {
  setUiLocked(true);
  setMicState("processing", "Starting mic...");
  cancelRecording = false; // Reset the flag

  try {
    const response = await fetch("/api/listen/start", { method: "POST" });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Failed to start recording.");
    }

    // Catch the race condition: If the user already released the mouse
    // while we were waiting for the server, stop immediately!
    if (cancelRecording) {
      stopRecording();
      return;
    }

    setMicState("recording", "Recording... release Mic to stop");
  } catch (error) {
    addMessage("system", error.message || "Unable to start recording.");
    setMicState("idle");
    setUiLocked(false);
  }
}

// 2. Update your micBtn event listeners
if (micBtn) {
  // CRITICAL: Force the mic button to NOT act as a form submit button
  // in case it sits inside the <form> tags.
  micBtn.type = "button";

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
    if (micState === "processing") {
      // The user released the button before the mic fully started.
      // Flag it so startRecording() knows to abort immediately.
      cancelRecording = true;
    } else if (micState === "recording") {
      stopRecording();
    }
  };

  micBtn.addEventListener("pointerup", handlePointerRelease);
  micBtn.addEventListener("pointerleave", handlePointerRelease);
  micBtn.addEventListener("pointercancel", handlePointerRelease);
  window.addEventListener("pointerup", handlePointerRelease);
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
    addMessage("system", error.message || "Unable to process the recording.");
  } finally {
    setMicState("idle");
    setUiLocked(false);
  }
}

// if (micBtn) {
//   micBtn.addEventListener("pointerdown", (event) => {
//     if (micState !== "idle") {
//       return;
//     }
//     if (micBtn.setPointerCapture) {
//       micBtn.setPointerCapture(event.pointerId);
//     }
//     startRecording();
//   });

//   const handlePointerRelease = () => {
//     if (micState === "recording") {
//       stopRecording();
//     }
//   };

//   micBtn.addEventListener("pointerup", handlePointerRelease);
//   micBtn.addEventListener("pointerleave", handlePointerRelease);
//   micBtn.addEventListener("pointercancel", handlePointerRelease);
//   window.addEventListener("pointerup", handlePointerRelease);
// }

tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    setView(tab.dataset.view || "overview");
  });
});

locationChoices.forEach((button) => {
  button.addEventListener("click", () => {
    selectionState.location = button.dataset.location || "kitchen";
    updateChoiceButtons(locationChoices, selectionState.location, "location");
  });
});

surfaceChoices.forEach((button) => {
  button.addEventListener("click", () => {
    selectionState.surface = button.dataset.surface || "countertop";
    updateChoiceButtons(surfaceChoices, selectionState.surface, "surface");
  });
});

catalogButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const fruit = button.dataset.fruit || "";
    if (!fruit) {
      return;
    }
    openConfirmModal(fruit);
  });
});

infoButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const fruit = button.dataset.info || "";
    if (!fruit) {
      return;
    }
    openInfoModal(fruit);
  });
});

if (confirmYes) {
  confirmYes.addEventListener("click", handleManualConfirm);
}

if (confirmNo) {
  confirmNo.addEventListener("click", () => {
    selectionState.fruit = "";
    closeModal(confirmModal);
  });
}

if (infoClose) {
  infoClose.addEventListener("click", () => closeModal(infoModal));
}

if (errorClose) {
  errorClose.addEventListener("click", () => {
    selectionState.fruit = "";
    closeModal(errorModal);
  });
}

[confirmModal, infoModal, errorModal].forEach((modal) => {
  if (!modal) {
    return;
  }
  modal.addEventListener("click", (event) => {
    if (event.target !== modal) {
      return;
    }

    if (modal === infoModal) {
      closeModal(infoModal);
    }
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
    cameraStatus.textContent = "Camera live";
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
  latestDetections = objects;

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
updateChoiceButtons(locationChoices, selectionState.location, "location");
updateChoiceButtons(surfaceChoices, selectionState.surface, "surface");

window.addEventListener("beforeunload", () => {
  if (cameraTimer) {
    window.clearInterval(cameraTimer);
  }
});

if (inputHint) {
  inputHint.textContent =
    "Hold Mic to talk, or use manual pick-up to browse the item catalog.";
}
