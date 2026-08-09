import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "../i18n";
import { ConversationSidebar } from "./ConversationSidebar";

describe("ConversationSidebar deletion", () => {
  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  it("shows a delete button and reports the selected conversation id", () => {
    localStorage.setItem("insightops-language", "en");
    const onDelete = vi.fn();
    const onParentClick = vi.fn();
    render(
      <div onClick={onParentClick}>
        <I18nProvider>
          <ConversationSidebar
            conversations={[
              {
                id: "conversation-1",
                title: "Delete me",
                dataset_id: "sales",
                dataset_name: "Sales",
                created_at: "2026-01-01T00:00:00Z",
                updated_at: "2026-01-01T00:00:00Z",
                message_count: 2,
              },
            ]}
            activeId="conversation-1"
            onSelect={vi.fn()}
            onNew={vi.fn()}
            onDelete={onDelete}
          />
        </I18nProvider>
      </div>,
    );

    const deleteButton = screen.getByRole("button", { name: "Delete Delete me" });
    fireEvent.click(deleteButton);

    expect(onDelete).toHaveBeenCalledWith("conversation-1");
    expect(onParentClick).not.toHaveBeenCalled();
    expect(deleteButton).toHaveAttribute("type", "button");
  });
});
