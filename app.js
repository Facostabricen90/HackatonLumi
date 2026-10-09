const storageKey = "ips-vocal-sessions";
const sessionList = document.querySelector("#session-list");
const conversation = document.querySelector("#conversation");
const messageCount = document.querySelector("#message-count");
const queryForm = document.querySelector("#query-form");
const queryInput = document.querySelector("#query-input");
const micButton = document.querySelector("#mic-button");
const voiceStage = document.querySelector("#voice-stage");
const voicePrompt = document.querySelector("#voice-prompt");
const recordingState = document.querySelector("#recording-state");

let sessions = JSON.parse(localStorage.getItem(storageKey) || "[]");
let activeSessionId = sessions[0]?.id || createSession("Primera consulta");
let recognition;

function createSession(title = "Nueva consulta") {
  const session = { id: Date.now().toString(), title, createdAt: new Date().toISOString(), messages: [] };
  sessions.unshift(session);
  activeSessionId = session.id;
  saveSessions();
  return session.id;
}

function saveSessions() {
  localStorage.setItem(storageKey, JSON.stringify(sessions));
}

function activeSession() {
  return sessions.find((session) => session.id === activeSessionId);
}

function renderSessions() {
  sessionList.innerHTML = sessions.length ? sessions.map((session) => `
    <button class="session-item ${session.id === activeSessionId ? "active" : ""}" data-session-id="${session.id}">
      <strong>${escapeHtml(session.title)}</strong>
      <span>${formatDate(session.createdAt)} · ${session.messages.length} mensajes</span>
    </button>`).join("") : `<div class="empty-state">Crea una sesión para comenzar.</div>`;

  sessionList.querySelectorAll(".session-item").forEach((button) => {
    button.addEventListener("click", () => {
      activeSessionId = button.dataset.sessionId;
      renderAll();
    });
  });
}

function renderConversation() {
  const messages = activeSession()?.messages || [];
  messageCount.textContent = `${messages.length} ${messages.length === 1 ? "mensaje" : "mensajes"}`;
  conversation.innerHTML = messages.length ? messages.map((message) => `
    <article class="message ${message.role}">
      <span class="message-meta">${message.role === "user" ? "Tú" : "Agente Vocal"} · ${message.time}</span>
      ${escapeHtml(message.text)}
    </article>`).join("") : `<div class="empty-state">Tu conversación aparecerá aquí.</div>`;
}

function renderAll() {
  renderSessions();
  renderConversation();
}

function addMessage(role, text) {
  const session = activeSession();
  if (!session) return;
  session.messages.push({ role, text, time: new Date().toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit" }) });
  if (role === "user" && session.messages.length === 1) session.title = text.slice(0, 30) + (text.length > 30 ? "..." : "");
  saveSessions();
  renderAll();
}

function submitQuery(text) {
  const cleanText = text.trim();
  if (!cleanText) return;
  addMessage("user", cleanText);
  queryInput.value = "";
  window.setTimeout(() => addMessage("assistant", "He recibido tu consulta. Conectaré esta vista con el agente IPS para darte una respuesta precisa."), 350);
}

function startRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    voicePrompt.textContent = "Tu navegador no admite voz. Escribe tu consulta abajo.";
    recordingState.textContent = "Usa el campo de texto";
    return;
  }
  recognition = new SpeechRecognition();
  recognition.lang = "es-CO";
  recognition.interimResults = false;
  recognition.onstart = () => {
    micButton.classList.add("recording");
    voiceStage.classList.add("is-recording");
    voicePrompt.textContent = "Te estoy escuchando...";
    recordingState.textContent = "Grabando ahora";
  };
  recognition.onresult = (event) => {
    const text = event.results[0][0].transcript;
    queryInput.value = text;
    submitQuery(text);
  };
  recognition.onerror = () => {
    voicePrompt.textContent = "No pude escuchar eso. Intenta de nuevo.";
    recordingState.textContent = "Listo para escuchar";
  };
  recognition.onend = () => {
    micButton.classList.remove("recording");
    voiceStage.classList.remove("is-recording");
    if (recordingState.textContent === "Grabando ahora") recordingState.textContent = "Listo para escuchar";
    voicePrompt.textContent = "Pulsa para hablar";
  };
  recognition.start();
}

function escapeHtml(value) {
  return value.replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[character]);
}

function formatDate(date) {
  return new Date(date).toLocaleDateString("es-CO", { day: "numeric", month: "short" });
}

document.querySelectorAll("#new-session, #new-session-secondary").forEach((button) => {
  button.addEventListener("click", () => {
    createSession();
    renderAll();
    queryInput.focus();
  });
});
queryForm.addEventListener("submit", (event) => {
  event.preventDefault();
  submitQuery(queryInput.value);
});
micButton.addEventListener("click", startRecognition);
renderAll();
