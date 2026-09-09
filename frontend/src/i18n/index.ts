import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import zh from "./locales/zh";
import en from "./locales/en";

export type Lang = "zh" | "en";

const STORAGE_KEY = "aipm-lang";

const saved =
  (typeof localStorage !== "undefined" && (localStorage.getItem(STORAGE_KEY) as Lang)) || "zh";

i18n.use(initReactI18next).init({
  resources: {
    zh: { translation: zh },
    en: { translation: en },
  },
  lng: saved,
  fallbackLng: "zh",
  interpolation: { escapeValue: false },
});

export const setLanguage = (lang: Lang) => {
  i18n.changeLanguage(lang);
  try { localStorage.setItem(STORAGE_KEY, lang); } catch { /* ignore */ }
  document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
};

export default i18n;
