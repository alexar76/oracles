export type Lang = "en" | "ru" | "es";

export const LANGS: Lang[] = ["en", "ru", "es"];

export interface Strings {
  tagline: string;
  dream: string;
  dreaming: string;
  telemetry: string;
  kappa: string;
  order: string;
  lyapunov: string;
  pca: string;
  agentPanel: string;
  agentWaiting: string;
  steerTitle: string;
  steerBtn: string;
  steerPlaceholder: string;
  projectionTitle: string;
  flip: string;
  witnesses: string;
  witnessWaiting: string;
  live: string;
  connecting: string;
  projections: string;
  agentCalls: string;
  footerRight: string;
  projectionHint: string;
  askTitle: string;
  askPlaceholder: string;
  askSend: string;
  askThinking: string;
  askError: string;
  askSuggestions: string[];
}

export const dict: Record<Lang, Strings> = {
  en: {
    tagline:
      "32D shadow oracle · verifiable randomness for agents · Monitor watches · Hub routes & sells",
    dream: "DREAM",
    dreaming: "DREAMING…",
    telemetry: "Telemetry",
    kappa: "κ coupling",
    order: "r order",
    lyapunov: "λ lyapunov",
    pca: "PCA₃ energy",
    agentPanel: "Agent channel · AIMarket invokes",
    agentWaiting: "Waiting for autonomous agents via Hub",
    steerTitle: "Incarnation · semantic steering",
    steerBtn: "STEER",
    steerPlaceholder: "entropy cathedral…",
    projectionTitle: "Projection · Stiefel rotation",
    flip: "flip",
    witnesses: "ORACLE WITNESSES",
    witnessWaiting: "Waiting for chimera, chaos, or synchronization…",
    live: "live",
    connecting: "connecting",
    projections: "projections",
    agentCalls: "agent calls",
    footerRight: "AIMarket Oracle · platon.*@v1",
    projectionHint:
      "32 spheres on a Fibonacci constellation · wireframe icosahedron = live Stiefel projection in flight · cyan beams = agent invokes",
    askTitle: "Ask the oracle",
    askPlaceholder: "What is κ right now?",
    askSend: "ASK",
    askThinking: "consulting the oracle…",
    askError: "the oracle is unavailable right now.",
    askSuggestions: [
      "What am I looking at?",
      "How do I get verifiable randomness?",
      "Is this quantum-safe?",
    ],
  },
  ru: {
    tagline:
      "32-мерный теневой оракул · проверяемая случайность для агентов · Monitor смотрит · Hub маршрутизирует и продаёт",
    dream: "СОН",
    dreaming: "СНОВИДЕНИЕ…",
    telemetry: "Телеметрия",
    kappa: "κ связь",
    order: "r порядок",
    lyapunov: "λ ляпунов",
    pca: "PCA₃ энергия",
    agentPanel: "Канал агентов · вызовы AIMarket",
    agentWaiting: "Ожидание автономных агентов через Hub",
    steerTitle: "Воплощение · семантическое управление",
    steerBtn: "НАПРАВИТЬ",
    steerPlaceholder: "собор энтропии…",
    projectionTitle: "Проекция · поворот Штифеля",
    flip: "переворот",
    witnesses: "СВИДЕТЕЛЬСТВА ОРАКУЛА",
    witnessWaiting: "Ожидание химеры, хаоса или синхронизации…",
    live: "в эфире",
    connecting: "подключение",
    projections: "проекций",
    agentCalls: "вызовов агентов",
    footerRight: "Оракул AIMarket · platon.*@v1",
    projectionHint:
      "32 сферы на Fibonacci-сфере · каркасный икосаэдр = летающая Stiefel-проекция · голубые лучи = вызовы агентов",
    askTitle: "Спросить оракула",
    askPlaceholder: "Что такое κ сейчас?",
    askSend: "СПРОСИТЬ",
    askThinking: "обращаюсь к оракулу…",
    askError: "оракул сейчас недоступен.",
    askSuggestions: [
      "Что я вижу?",
      "Как получить проверяемую случайность?",
      "Это квантово-устойчиво?",
    ],
  },
  es: {
    tagline:
      "Oráculo de sombra 32D · aleatoriedad verificable para agentes · Monitor observa · Hub enruta y vende",
    dream: "SUEÑO",
    dreaming: "SOÑANDO…",
    telemetry: "Telemetría",
    kappa: "κ acoplamiento",
    order: "r orden",
    lyapunov: "λ lyapunov",
    pca: "PCA₃ energía",
    agentPanel: "Canal de agentes · invocaciones AIMarket",
    agentWaiting: "Esperando agentes autónomos vía Hub",
    steerTitle: "Encarnación · dirección semántica",
    steerBtn: "DIRIGIR",
    steerPlaceholder: "catedral de entropía…",
    projectionTitle: "Proyección · rotación de Stiefel",
    flip: "girar",
    witnesses: "TESTIMONIOS DEL ORÁCULO",
    witnessWaiting: "Esperando quimera, caos o sincronización…",
    live: "en vivo",
    connecting: "conectando",
    projections: "proyecciones",
    agentCalls: "llamadas de agentes",
    footerRight: "Oráculo AIMarket · platon.*@v1",
    projectionHint:
      "32 esferas en constelación Fibonacci · icosaedro alámbrico = proyección Stiefel en vuelo · rayos cian = invocaciones",
    askTitle: "Pregúntale al oráculo",
    askPlaceholder: "¿Qué es κ ahora?",
    askSend: "PREGUNTAR",
    askThinking: "consultando al oráculo…",
    askError: "el oráculo no está disponible ahora.",
    askSuggestions: [
      "¿Qué estoy viendo?",
      "¿Cómo obtengo aleatoriedad verificable?",
      "¿Es seguro ante la cuántica?",
    ],
  },
};

export function detectLang(): Lang {
  if (typeof navigator === "undefined") return "en";
  const tag = (navigator.language || "en").slice(0, 2).toLowerCase();
  return (LANGS as string[]).includes(tag) ? (tag as Lang) : "en";
}
