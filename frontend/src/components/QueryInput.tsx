import { Send, Square } from "lucide-react";
import { useState } from "react";

import { useI18n } from "../i18n";

export function QueryInput({
  onSubmit,
  onCancel,
  streaming,
  disabled,
  initialValue = "",
}: {
  onSubmit: (question: string) => void;
  onCancel: () => void;
  streaming: boolean;
  disabled?: boolean;
  initialValue?: string;
}) {
  const { t } = useI18n();
  const [value, setValue] = useState(initialValue);

  function submit() {
    const question = value.trim();
    if (!question || streaming || disabled) return;
    onSubmit(question);
    setValue("");
  }

  return (
    <div className="border-t border-zinc-200 bg-white p-3">
      <div className="flex items-end gap-2">
        <textarea
          className="field min-h-[44px] max-h-36 resize-y"
          rows={1}
          value={value}
          disabled={disabled}
          placeholder={t("query.placeholder")}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
        />
        {streaming ? (
          <button className="icon-button border-red-200 text-red-700" title={t("common.cancel")} aria-label={t("query.cancel")} onClick={onCancel}>
            <Square size={17} fill="currentColor" />
          </button>
        ) : (
          <button className="command-button h-11 w-11 px-0" title={t("common.send")} aria-label={t("query.send")} disabled={disabled || !value.trim()} onClick={submit}>
            <Send size={18} />
          </button>
        )}
      </div>
    </div>
  );
}
