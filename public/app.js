import { GoogleGenAI } from "https://esm.run/@google/genai";

const storageKey = "ips-vocal-sessions";
const inputSampleRate = 16000;
const outputSampleRate = 24000;
const introPrompt = "Inicia la conversación: preséntate y explica de qué trata el dataset y qué se puede preguntar.";

const micProcessorCode = `
class MicProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.chunk = new Float32Array(1024);
    this.position = 0;
  }
  process(inputs) {
    const channel = inputs[0][0];
    if (!channel) return true;
    for (let i = 0; i < channel.length; i++) {
      this.chunk[this.position++] = channel[i];
      if (this.position === this.chunk.length) {
        this.port.postMessage(this.chunk.slice());
        this.position = 0;
      }
    }
    return true;
  }
}
registerProcessor("mic-processor", MicProcessor);
`;

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
let activeSessionId = sessions[0]?.id ?? null;
if (!activeSessionId) createSession("Primera consulta");

let liveSession = null;
let micStream = null;
let micContext = null;
let speakerContext = null;
let nextPlayTime = 0;
let playingSources = [];
let userMessage = null;
let agentMessage = null;

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

function timeNow() {
  return new Date().toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function addMessage(role, text) {
  const message = { role, text, time: timeNow() };
  activeSession().messages.push(message);
  saveSessions();
  renderAll();
  return message;
}

function appendText(message, fragment) {
  message.text += fragment;
  const session = activeSession();
  const firstUserMessage = session.messages.find((item) => item.role === "user");
  if (firstUserMessage?.text.trim()) session.title = firstUserMessage.text.trim().slice(0, 30);
  saveSessions();
  renderAll();
}

function escapeHtml(value) {
  return value.replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[character]);
}

function formatDate(date) {
  return new Date(date).toLocaleDateString("es-CO", { day: "numeric", month: "short" });
}

function bytesToBase64(bytes) {
  let binary = "";
  bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
  return btoa(binary);
}

function floatsToBase64(floats) {
  const pcm = new Int16Array(floats.length);
  floats.forEach((sample, index) => {
    const clamped = Math.max(-1, Math.min(1, sample));
    pcm[index] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
  });
  return bytesToBase64(new Uint8Array(pcm.buffer));
}

function base64ToFloats(base64) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return Float32Array.from(new Int16Array(bytes.buffer), (value) => value / 0x8000);
}

function playAudio(base64) {
  const floats = base64ToFloats(base64);
  const buffer = speakerContext.createBuffer(1, floats.length, outputSampleRate);
  buffer.copyToChannel(floats, 0);
  const source = speakerContext.createBufferSource();
  source.buffer = buffer;
  source.connect(speakerContext.destination);
  nextPlayTime = Math.max(nextPlayTime, speakerContext.currentTime);
  source.start(nextPlayTime);
  nextPlayTime += buffer.duration;
  playingSources.push(source);
  source.onended = () => { playingSources = playingSources.filter((item) => item !== source); };
}

function stopAudio() {
  playingSources.forEach((source) => source.stop());
  playingSources = [];
  nextPlayTime = 0;
}

async function openMicrophone() {
  micStream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
  });
  micContext = new AudioContext({ sampleRate: inputSampleRate });
  const processorUrl = URL.createObjectURL(new Blob([micProcessorCode], { type: "application/javascript" }));
  await micContext.audioWorklet.addModule(processorUrl);
  const source = micContext.createMediaStreamSource(micStream);
  const processor = new AudioWorkletNode(micContext, "mic-processor");
  processor.port.onmessage = (event) => {
    liveSession?.sendRealtimeInput({
      audio: { data: floatsToBase64(event.data), mimeType: `audio/pcm;rate=${inputSampleRate}` },
    });
  };
  source.connect(processor);
}

async function answerToolCalls(calls) {
  const functionResponses = [];
  for (const call of calls) {
    console.log("Herramienta:", call.name, call.args);
    const response = await fetch("/api/consulta", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(call.args || {}),
    });
    functionResponses.push({ id: call.id, name: call.name, response: { result: await response.json() } });
  }
  liveSession?.sendToolResponse({ functionResponses });
}

function addTranscription(role, fragment) {
  if (role === "user") {
    agentMessage = null;
    if (!userMessage) userMessage = addMessage("user", "");
    appendText(userMessage, fragment);
  } else {
    userMessage = null;
    if (!agentMessage) agentMessage = addMessage("assistant", "");
    appendText(agentMessage, fragment);
  }
}

function handleServerMessage(message) {
  if (message.toolCall) answerToolCalls(message.toolCall.functionCalls);

  const content = message.serverContent;
  if (!content) return;

  if (content.interrupted) {
    stopAudio();
    agentMessage = null;
  }
  content.modelTurn?.parts?.forEach((part) => {
    if (part.inlineData?.data) playAudio(part.inlineData.data);
  });
  if (content.inputTranscription?.text) addTranscription("user", content.inputTranscription.text);
  if (content.outputTranscription?.text) addTranscription("assistant", content.outputTranscription.text);
  if (content.turnComplete) {
    userMessage = null;
    agentMessage = null;
  }
}

function setVoiceActive(isActive) {
  micButton.classList.toggle("recording", isActive);
  voiceStage.classList.toggle("is-recording", isActive);
  voicePrompt.textContent = isActive ? "Te estoy escuchando... pulsa para terminar" : "Pulsa para hablar";
  recordingState.textContent = isActive ? "Conversación en vivo" : "Listo para escuchar";
}

async function startVoice() {
  voicePrompt.textContent = "Conectando...";
  recordingState.textContent = "Conectando";
  try {
    speakerContext = new AudioContext({ sampleRate: outputSampleRate });
    const response = await fetch("/api/sesion");
    const settings = await response.json();
    const ai = new GoogleGenAI({ apiKey: settings.token, httpOptions: { apiVersion: "v1beta" } });
    liveSession = await ai.live.connect({
      model: settings.modelo,
      config: {
        responseModalities: ["AUDIO"],
        systemInstruction: settings.instruccion,
        tools: [{ functionDeclarations: settings.herramientas }],
        inputAudioTranscription: {},
        outputAudioTranscription: {},
      },
      callbacks: {
        onmessage: handleServerMessage,
        onerror: (error) => console.error("Error Live:", error),
        onclose: () => stopVoice(),
      },
    });
    await openMicrophone();
    setVoiceActive(true);
    liveSession.sendRealtimeInput({ text: introPrompt });
  } catch (error) {
    console.error(error);
    stopVoice();
    voicePrompt.textContent = "No pude conectar. Revisa la consola.";
  }
}

function stopVoice() {
  const session = liveSession;
  liveSession = null;
  session?.close();
  micStream?.getTracks().forEach((track) => track.stop());
  micContext?.close();
  stopAudio();
  speakerContext?.close();
  micStream = null;
  micContext = null;
  speakerContext = null;
  userMessage = null;
  agentMessage = null;
  setVoiceActive(false);
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
  const text = queryInput.value.trim();
  if (!text) return;
  if (!liveSession) {
    voicePrompt.textContent = "Pulsa el micrófono para conectar primero.";
    return;
  }
  addMessage("user", text);
  liveSession.sendRealtimeInput({ text });
  queryInput.value = "";
});

micButton.addEventListener("click", () => (liveSession ? stopVoice() : startVoice()));

renderAll();