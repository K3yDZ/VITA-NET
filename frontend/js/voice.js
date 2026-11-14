// voice.js — Web Speech API wrapper (TTS + STT)
// TTS: advisor mesajlarını sesli okur, STT: sesli komut dinler.
// Dil otomatik olarak getLang() ile belirlenir.

import { getLang } from "./i18n.js";

const LANG_VOICE = {
  en: "en-US", tr: "tr-TR", es: "es-ES", fr: "fr-FR",
  de: "de-DE", ja: "ja-JP", zh: "zh-CN", ru: "ru-RU",
  ar: "ar-SA", pt: "pt-BR", it: "it-IT", ko: "ko-KR",
  hi: "hi-IN", nl: "nl-NL", pl: "pl-PL",
};

let speaking = false;
let listening = false;
let recognition = null;

export function isSpeaking() { return speaking; }
export function isListening() { return listening; }

export function ttsSupported() {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

export function sttSupported() {
  return typeof window !== "undefined" && ("webkitSpeechRecognition" in window || "SpeechRecognition" in window);
}

// Advisor metnini sesli oku
export function speak(text) {
    text = String(text || "").trim();
  if (!ttsSupported() || !text) return;
  stopSpeaking();
  const lang = LANG_VOICE[getLang()] || "en-US";
  const utter = new SpeechSynthesisUtterance(text);
  utter.lang = lang;
  utter.rate = 0.95;
  utter.pitch = 1;
  // En uygun sesi seç (varsa locale'e özel)
  const match = _pickVoice(lang);
  if (match) utter.voice = match;
  utter.onstart = () => { speaking = true; };
  utter.onend = () => { speaking = false; };
  utter.onerror = () => { speaking = false; };
  speechSynthesis.speak(utter);
}

export function stopSpeaking() {
  if (ttsSupported()) speechSynthesis.cancel();
  speaking = false;
}

export function toggleSpeak(text) {
  if (speaking) stopSpeaking();
  else speak(text);
}

// Sesli komut dinleme — callback(transcript)
export function startListening(onResult, onEnd) {
  if (!sttSupported()) return null;
  if (listening) { stopListening(); return null; }

  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new SR();
  const lang = LANG_VOICE[getLang()] || "en-US";
  recognition.lang = lang;
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  recognition.continuous = false;

  listening = true;
  recognition.onresult = (e) => {
    const transcript = e.results[0][0].transcript.trim();
    if (onResult) onResult(transcript);
  };
  recognition.onerror = () => { listening = false; if (onEnd) onEnd(); };
  recognition.onend = () => { listening = false; if (onEnd) onEnd(); };
  try { recognition.start(); } catch { listening = false; }
  return recognition;
}

export function stopListening() {
  if (recognition) { try { recognition.abort(); } catch {} recognition = null; }
  listening = false;
}

// Preload voices — Chrome loads async, so cache them
let _voices = [];
function _loadVoices() { try { _voices = speechSynthesis.getVoices(); } catch {} }
if (ttsSupported()) {
  _loadVoices();
  try { speechSynthesis.onvoiceschanged = _loadVoices; } catch {}
}
function _pickVoice(lang) {
  if (!_voices.length) _loadVoices();
  if (!_voices.length) return null;
  const code = lang.slice(0, 2).toLowerCase();
  return _voices.find(v => v.lang.toLowerCase().startsWith(code)) || null;
}
