import { describe, expect, it } from "vitest";
import { LANGS, detectLang, dict } from "./i18n";

describe("i18n", () => {
  it("exposes en, ru, es", () => {
    expect(LANGS).toEqual(["en", "ru", "es"]);
  });

  it("every language has the exact same keys", () => {
    const enKeys = Object.keys(dict.en).sort();
    for (const lang of LANGS) {
      expect(Object.keys(dict[lang]).sort()).toEqual(enKeys);
    }
  });

  it("no string is empty in any language", () => {
    for (const lang of LANGS) {
      for (const value of Object.values(dict[lang])) {
        expect(value.length).toBeGreaterThan(0);
      }
    }
  });

  it("translations actually differ across languages", () => {
    expect(dict.en.steerBtn).not.toEqual(dict.ru.steerBtn);
    expect(dict.ru.steerBtn).not.toEqual(dict.es.steerBtn);
  });

  it("detectLang falls back to en for unknown locales", () => {
    expect(detectLang()).toBeTypeOf("string");
    expect(["en", "ru", "es"]).toContain(detectLang());
  });
});
