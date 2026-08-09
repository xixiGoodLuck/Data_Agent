import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { LocalModelConfig } from "./types";

export type { LocalModelConfig } from "./types";

export const DEEPSEEK_API_KEY_HEADER = "X-DeepSeek-API-Key";
const LOCAL_MODEL_STORAGE_KEY = "data-agent-local-model";

interface TemporaryCredentialsValue {
  deepseekApiKey: string;
  setDeepseekApiKey: (value: string) => void;
  clearDeepseekApiKey: () => void;
  hasDeepseekApiKey: boolean;
  localModel: LocalModelConfig;
  saveLocalModel: (value: LocalModelConfig) => void;
  restoreDefaultModel: () => void;
}

const fallbackValue: TemporaryCredentialsValue = {
  deepseekApiKey: "",
  setDeepseekApiKey: () => undefined,
  clearDeepseekApiKey: () => undefined,
  hasDeepseekApiKey: false,
  localModel: { enabled: false, base_url: "", model: "" },
  saveLocalModel: () => undefined,
  restoreDefaultModel: () => undefined,
};

const TemporaryCredentialsContext = createContext<TemporaryCredentialsValue>(fallbackValue);

export function deepseekRequestHeaders(apiKey: string): Record<string, string> {
  const key = apiKey.trim();
  return key ? { [DEEPSEEK_API_KEY_HEADER]: key } : {};
}

export function TemporaryCredentialsProvider({ children }: { children: ReactNode }) {
  const [deepseekApiKey, setDeepseekApiKey] = useState("");
  const clearDeepseekApiKey = useCallback(() => setDeepseekApiKey(""), []);
  const [localModel, setLocalModel] = useState<LocalModelConfig>(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(LOCAL_MODEL_STORAGE_KEY) ?? "{}") as Partial<LocalModelConfig>;
      return { enabled: saved.enabled === true, base_url: saved.base_url ?? "", model: saved.model ?? "" };
    } catch {
      return { enabled: false, base_url: "", model: "" };
    }
  });
  const saveLocalModel = useCallback((value: LocalModelConfig) => {
    localStorage.setItem(LOCAL_MODEL_STORAGE_KEY, JSON.stringify(value));
    setLocalModel(value);
  }, []);
  const restoreDefaultModel = useCallback(() => {
    setLocalModel((current) => {
      const restored = { ...current, enabled: false };
      localStorage.setItem(LOCAL_MODEL_STORAGE_KEY, JSON.stringify(restored));
      return restored;
    });
  }, []);

  useEffect(() => {
    const clear = () => clearDeepseekApiKey();
    const clearRestoredPage = (event: PageTransitionEvent) => {
      if (event.persisted) clear();
    };
    window.addEventListener("pagehide", clear);
    window.addEventListener("beforeunload", clear);
    window.addEventListener("pageshow", clearRestoredPage);
    return () => {
      window.removeEventListener("pagehide", clear);
      window.removeEventListener("beforeunload", clear);
      window.removeEventListener("pageshow", clearRestoredPage);
    };
  }, [clearDeepseekApiKey]);

  const value = useMemo<TemporaryCredentialsValue>(
    () => ({
      deepseekApiKey,
      setDeepseekApiKey,
      clearDeepseekApiKey,
      hasDeepseekApiKey: Boolean(deepseekApiKey.trim()),
      localModel,
      saveLocalModel,
      restoreDefaultModel,
    }),
    [clearDeepseekApiKey, deepseekApiKey, localModel, restoreDefaultModel, saveLocalModel],
  );

  return (
    <TemporaryCredentialsContext.Provider value={value}>
      {children}
    </TemporaryCredentialsContext.Provider>
  );
}

export function useTemporaryCredentials(): TemporaryCredentialsValue {
  return useContext(TemporaryCredentialsContext);
}
