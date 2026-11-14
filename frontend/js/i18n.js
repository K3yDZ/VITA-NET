// i18n.js — native 16-language pack. No Google widget.
// Browser language is detected on first visit; user can override via selector (persisted).

const SUPPORTED = ["en","tr","es","fr","de","ja","zh","ru","ar","pt","it","ko","hi","nl","pl","id"];
const LANG_LABELS = {
  en: "English", tr: "Türkçe", es: "Español", fr: "Français",
  de: "Deutsch", ja: "日本語", zh: "中文", ru: "Русский",
  ar: "العربية", pt: "Português", it: "Italiano", ko: "한국어",
  hi: "हिन्दी", nl: "Nederlands", pl: "Polski", id: "Indonesia"
};
const DEFAULT_LANG = "en";
const STORAGE_KEY = "vitanet.lang";

let dict = {};
let currentLang = DEFAULT_LANG;
const listeners = [];

function detectInitialLang() {
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved && SUPPORTED.includes(saved)) return saved;
  // Check navigator.languages in order, match by prefix
  const cands = [];
  try {
    const langs = navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language || "en"];
    for (const raw of langs) {
      const code = String(raw).toLowerCase().split("-")[0].split("_")[0].trim();
      if (SUPPORTED.includes(code)) return code;
      cands.push(code);
    }
  } catch {}
  // zh variants
  if (cands.some(c => c === "zh")) return "zh";
  return DEFAULT_LANG;
}

export function getSupported() { return [...SUPPORTED]; }
export function getLangLabels() { return { ...LANG_LABELS }; }

async function loadLocale(lang) {
  const res = await fetch(`locales/${lang}.json`);
  if (!res.ok) throw new Error(`locale ${lang} failed to load`);
  return res.json();
}

export async function initI18n() {
  currentLang = detectInitialLang();
  try {
    dict = await loadLocale(currentLang);
  } catch (e) {
    console.warn("[i18n] falling back to English:", e);
    currentLang = DEFAULT_LANG;
    dict = await loadLocale(DEFAULT_LANG);
  }
  document.documentElement.lang = currentLang;
  // RTL for Arabic
  document.documentElement.dir = currentLang === "ar" ? "rtl" : "ltr";
  applyToDom();
  return currentLang;
}

export async function setLang(lang) {
  if (!SUPPORTED.includes(lang)) return;
  if (lang === currentLang) return;
  try {
    dict = await loadLocale(lang);
    currentLang = lang;
    localStorage.setItem(STORAGE_KEY, lang);
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
    applyToDom();
    listeners.forEach((fn) => fn(lang));
  } catch (e) {
    console.warn("[i18n] could not switch language:", e);
  }
}

export function getLang() {
  return currentLang;
}

export function onLangChange(fn) {
  listeners.push(fn);
}

// t("alert_hr_high", { name: "Reyes", value: 118 })
export function t(key, vars) {
  let str = dict[key] ?? key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      str = str.replaceAll(`{${k}}`, v);
    }
  }
  return str;
}

export function applyToDom(root = document) {
  root.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    el.textContent = t(key);
  });
  root.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    el.setAttribute("placeholder", t(el.getAttribute("data-i18n-placeholder")));
  });
  root.querySelectorAll("[data-i18n-title]").forEach((el) => {
    el.setAttribute("title", t(el.getAttribute("data-i18n-title")));
  });
  root.querySelectorAll("[data-i18n-aria]").forEach((el) => {
    el.setAttribute("aria-label", t(el.getAttribute("data-i18n-aria")));
  });
}
