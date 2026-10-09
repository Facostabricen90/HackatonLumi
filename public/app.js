import { GoogleGenAI, StartSensitivity } from "https://esm.run/@google/genai";

const inputSampleRate = 16000;
const outputSampleRate = 24000;
const introPrompt = "[SISTEMA: Saludo inicial automático. Da la bienvenida al ciudadano y preséntate brevemente como Lumi. Esta instrucción es un comando técnico interno y NO es una pregunta del usuario].";

const spriteFolder = "sprites";
const exitDurationMs = 34 * 80;
const liveStates = ["listening", "thinking", "speaking"];
const spriteByState = {
  idle: "default",
  listening: "default",
  speaking: "talking",
  connecting: "loading",
  thinking: "thinking",
  error: "error",
  exit: "exit",
};
const stateText = {
  idle: { prompt: "Pulsa para hablar", label: "Listo para escuchar", status: "Servicio disponible" },
  connecting: { prompt: "Conectando con Lumi...", label: "Conectando", status: "Conectando" },
  listening: { prompt: "Te escucho... pulsa para terminar", label: "Conversación en vivo", status: "Escuchando" },
  thinking: { prompt: "Consultando los datos...", label: "Consultando datos", status: "Consultando datos" },
  speaking: { prompt: "Lumi está respondiendo", label: "Conversación en vivo", status: "Lumi está hablando" },
  error: { prompt: "Algo falló. Pulsa para intentar de nuevo", label: "Sin conexión", status: "Sin conexión" },
  exit: { prompt: "Hasta pronto", label: "Sesión cerrada", status: "Sesión cerrada" },
};

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

const conversation = document.querySelector("#conversation");
const messageCount = document.querySelector("#message-count");
const queryForm = document.querySelector("#query-form");
const queryInput = document.querySelector("#query-input");
const micButton = document.querySelector("#mic-button");
const voiceStage = document.querySelector("#voice-stage");
const voicePrompt = document.querySelector("#voice-prompt");
const recordingState = document.querySelector("#recording-state");
const mascot = document.querySelector("#mascot");
const statusPill = document.querySelector("#status-pill");
const statusText = document.querySelector("#status-text");
const moodSummary = document.querySelector("#mood-summary");
const moodEmotion = document.querySelector("#mood-emotion");
const moodSentiment = document.querySelector("#mood-sentiment");
const moodBarFill = document.querySelector("#mood-bar-fill");
const moodIntensityPct = document.querySelector("#mood-intensity-pct");
const moodAvatarIcon = document.querySelector("#mood-avatar-icon");
const countPositive = document.querySelector("#count-positive");
const countNeutral = document.querySelector("#count-neutral");
const countNegative = document.querySelector("#count-negative");
const newSessionBtn = document.querySelector("#new-session");

// Sesión efímera de la pestaña actual (sin historiales compartidos ni persistencia global)
let currentSession = {
  id: Date.now().toString(),
  messages: [],
};

let liveSession = null;
let isConnecting = false;
let micStream = null;
let micContext = null;
let speakerContext = null;
let nextPlayTime = 0;
let playingSources = [];
let userMessage = null;
let agentMessage = null;

function activeSession() {
  return currentSession;
}

function resetConversation() {
  currentSession = {
    id: Date.now().toString(),
    messages: [],
  };
  userMessage = null;
  agentMessage = null;
  renderAll();
  if (queryInput) {
    queryInput.value = "";
    queryInput.focus();
  }
}

function renderConversation() {
  const messages = activeSession()?.messages || [];
  if (messageCount) {
    messageCount.textContent = `${messages.length} ${messages.length === 1 ? "mensaje" : "mensajes"}`;
  }
  if (conversation) {
    conversation.innerHTML = messages.length ? messages.map((message) => `
      <article class="message ${message.role}">
        <div class="message-meta">
          <span>${message.role === "user" ? "Tú" : "Lumi"} · ${message.time}</span>
          ${moodBadge(message)}
        </div>
        <div class="message-text">${escapeHtml(message.text)}</div>
      </article>`).join("") : `<div class="empty-state">Tu conversación aparecerá aquí en tiempo real cuando hables con Lumi.</div>`;

    // Auto-scroll al final del recuadro fijo
    conversation.scrollTop = conversation.scrollHeight;
  }
}

function renderAll() {
  renderConversation();
  renderMood();
}

function moodBadge(message) {
  if (!message.mood) return "";
  return `<span class="message-mood ${message.mood.sentimiento}">${escapeHtml(String(message.mood.emocion))}</span>`;
}

function renderMood() {
  const analyzed = (activeSession()?.messages || []).filter((message) => message.role === "user" && message.mood);
  const counts = { positivo: 0, neutral: 0, negativo: 0 };
  analyzed.forEach((message) => {
    if (message.mood.sentimiento in counts) counts[message.mood.sentimiento]++;
  });
  const last = analyzed.at(-1);

  if (countPositive) countPositive.textContent = counts.positivo;
  if (countNeutral) countNeutral.textContent = counts.neutral;
  if (countNegative) countNegative.textContent = counts.negativo;
  if (moodSummary) moodSummary.textContent = `${analyzed.length} ${analyzed.length === 1 ? "mensaje analizado" : "mensajes analizados"}`;
  if (moodEmotion) moodEmotion.textContent = last ? last.mood.emocion : "—";
  if (moodSentiment) moodSentiment.textContent = last ? `Sentimiento ${last.mood.sentimiento}` : "Habla para ver el análisis";

  if (moodBarFill) {
    moodBarFill.className = last ? last.mood.sentimiento : "";
    moodBarFill.style.width = last ? `${Math.round(Number(last.mood.intensidad) * 100)}%` : "0";
  }
  if (moodIntensityPct) {
    moodIntensityPct.textContent = last ? `${Math.round(Number(last.mood.intensidad) * 100)}%` : "0%";
  }
  if (moodAvatarIcon) {
    if (!last) {
      moodAvatarIcon.textContent = "💬";
    } else if (last.mood.sentimiento === "positivo") {
      moodAvatarIcon.textContent = "😊";
    } else if (last.mood.sentimiento === "negativo") {
      moodAvatarIcon.textContent = "😟";
    } else {
      moodAvatarIcon.textContent = "😐";
    }
  }
}

async function analyzeMessage(message) {
  // Solo se analiza al ciudadano, una vez por mensaje (ahorra cuota de la API)
  if (!message || message.role !== "user" || message.analyzing || message.mood) return;
  if (!message.text.trim()) return;
  message.analyzing = true;
  try {
    const response = await fetch("/api/sentimiento", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ texto: message.text }),
    });
    const mood = await response.json();
    if (!response.ok || mood.error) throw new Error(mood.error || `respondió ${response.status}`);
    message.mood = mood;
    renderAll();
  } catch (error) {
    console.error("Sentimiento:", error);
  } finally {
    message.analyzing = false;
  }
}

function timeNow() {
  return new Date().toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function addMessage(role, text) {
  const message = { role, text, time: timeNow() };
  activeSession().messages.push(message);
  renderAll();
  return message;
}

function appendText(message, fragment) {
  message.text += fragment;
  renderAll();
}

function escapeHtml(value) {
  return value.replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[character]);
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
  if (liveSession && voiceStage.dataset.state !== "speaking") setState("speaking");
  source.onended = () => {
    playingSources = playingSources.filter((item) => item !== source);
    if (!playingSources.length && liveSession) setState("listening");
  };
}

function stopAudio() {
  playingSources.forEach((source) => {
    source.onended = null;
    try {
      source.stop();
    } catch (error) {
      console.warn("Audio ya detenido:", error);
    }
  });
  playingSources = [];
  nextPlayTime = 0;
}

function closeContext(context) {
  if (context && context.state !== "closed") context.close().catch((error) => console.warn(error));
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
  setState("thinking");
  const functionResponses = [];
  for (const call of calls) {
    console.log("Herramienta:", call.name, call.args);
    let result;
    try {
      const response = await fetch("/api/consulta", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(call.args || {}),
      });
      result = await response.json();
    } catch (error) {
      console.error("Consulta de datos:", error);
      result = { error: "No pude consultar los datos en este momento. Intenta de nuevo." };
    }
    functionResponses.push({ id: call.id, name: call.name, response: { result } });
  }
  liveSession?.sendToolResponse({ functionResponses });
}

function addTranscription(role, fragment) {
  if (role === "user") {
    if (agentMessage) {
      analyzeMessage(agentMessage);
      agentMessage = null;
    }
    if (!userMessage) userMessage = addMessage("user", "");
    appendText(userMessage, fragment);
  } else {
    if (userMessage) {
      analyzeMessage(userMessage);
      userMessage = null;
    }
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
    if (userMessage) analyzeMessage(userMessage);
    if (agentMessage) analyzeMessage(agentMessage);
    userMessage = null;
    agentMessage = null;
  }
}

function setState(state, message = "") {
  voiceStage.dataset.state = state;
  statusPill.dataset.state = state;
  const isLive = liveStates.includes(state);
  const text = stateText[state] || stateText.idle;
  const sprite = `${spriteFolder}/lumi-${spriteByState[state] || "default"}.gif`;
  const micLabel = isLive ? "Terminar conversación" : "Comenzar a hablar";

  micButton.classList.toggle("recording", isLive);
  micButton.title = micLabel;
  micButton.setAttribute("aria-label", micLabel);
  voicePrompt.textContent = message || text.prompt;
  recordingState.textContent = text.label;
  statusText.textContent = text.status;
  if (!mascot.src.endsWith(sprite)) mascot.src = sprite;
}

async function startVoice() {
  if (isConnecting) return;
  isConnecting = true;
  setState("connecting");
  let session = null;
  try {
    speakerContext = new AudioContext({ sampleRate: outputSampleRate });
    const response = await fetch("/api/sesion", { cache: "no-store" });
    if (!response.ok) throw new Error(`/api/sesion respondió ${response.status}`);
    const settings = await response.json();
    const ai = new GoogleGenAI({ apiKey: settings.token, httpOptions: { apiVersion: "v1beta" } });
    session = await ai.live.connect({
      model: settings.modelo,
      config: {
        responseModalities: ["AUDIO"],
        systemInstruction: settings.instruccion,
        tools: [{ functionDeclarations: settings.herramientas }],
        inputAudioTranscription: {},
        outputAudioTranscription: {},
        realtimeInputConfig: {
          automaticActivityDetection: {
            startOfSpeechSensitivity: StartSensitivity.START_SENSITIVITY_LOW,
          },
        },
      },
      callbacks: {
        onmessage: handleServerMessage,
        onerror: (error) => console.error("Error Live:", error),
        onclose: (event) => {
          console.log("Live cerrado:", event?.code, event?.reason);
          if (liveSession === session) {
            stopVoice();
            setState("error", "La conversación se cerró. Pulsa para reconectar.");
          }
        },
      },
    });
    liveSession = session;
    await openMicrophone();
    setState("listening");
    liveSession.sendRealtimeInput({ text: introPrompt });
  } catch (error) {
    console.error("Error al conectar:", error);
    session?.close();
    stopVoice();
    setState("error", `No pude conectar: ${error.message}`);
  } finally {
    isConnecting = false;
  }
}

function stopVoice() {
  const session = liveSession;
  liveSession = null;
  try {
    session?.close();
  } catch (error) {
    console.warn("Cierre de sesión:", error);
  }
  micStream?.getTracks().forEach((track) => track.stop());
  closeContext(micContext);
  stopAudio();
  closeContext(speakerContext);
  micStream = null;
  micContext = null;
  speakerContext = null;
  userMessage = null;
  agentMessage = null;
  setState("exit");
  window.setTimeout(() => {
    if (voiceStage.dataset.state === "exit") setState("idle");
  }, exitDurationMs);
}

if (newSessionBtn) {
  newSessionBtn.addEventListener("click", () => {
    resetConversation();
  });
}

queryForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = queryInput.value.trim();
  if (!text) return;
  if (!liveSession) {
    voicePrompt.textContent = "Pulsa el micrófono para conectar primero.";
    return;
  }
  analyzeMessage(addMessage("user", text));
  liveSession.sendRealtimeInput({ text });
  queryInput.value = "";
});

micButton.addEventListener("click", () => {
  if (isConnecting) return;
  if (liveSession) stopVoice();
  else startVoice();
});

window.addEventListener("load", () => {
  Object.values(spriteByState).forEach((name) => {
    new Image().src = `${spriteFolder}/lumi-${name}.gif`;
  });
});

setState("idle");
renderAll();