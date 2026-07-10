import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export const DEEPSEEK_API_KEY_HEADER = "X-DeepSeek-API-Key";

interface TemporaryCredentialsValue {
  deepseekApiKey: string;
  setDeepseekApiKey: (value: string) => void;
  clearDeepseekApiKey: () => void;
  hasDeepseekApiKey: boolean;
}

const fallbackValue: TemporaryCredentialsValue = {
  deepseekApiKey: "",
  setDeepseekApiKey: () => undefined,
  clearDeepseekApiKey: () => undefined,
  hasDeepseekApiKey: false,
};

const TemporaryCredentialsContext = createContext<TemporaryCredentialsValue>(fallbackValue);

export function deepseekRequestHeaders(apiKey: string): Record<string, string> {
  const key = apiKey.trim();
  return key ? { [DEEPSEEK_API_KEY_HEADER]: key } : {};
}

export function TemporaryCredentialsProvider({ children }: { children: ReactNode }) {
  const [deepseekApiKey, setDeepseekApiKey] = useState("");
  const clearDeepseekApiKey = useCallback(() => setDeepseekApiKey(""), []);

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
    }),
    [clearDeepseekApiKey, deepseekApiKey],
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
