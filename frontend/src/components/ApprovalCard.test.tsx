import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApprovalCard } from "./ApprovalCard";

describe("ApprovalCard", () => {
  it("renders risk details and submits an approval note", () => {
    const decide = vi.fn();
    render(
      <ApprovalCard
        approval={{
          id: "approval-1",
          question: "List salary values",
          risk_level: "high",
          reasons: ["Individual salary values"],
          sql_preview: "SELECT employee_name, salary FROM employees",
          selected_columns: ["employees.salary"],
        }}
        onDecision={decide}
      />,
    );
    expect(screen.getByText(/Individual salary values/)).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("Decision note (optional)"), {
      target: { value: "Reviewed" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(decide).toHaveBeenCalledWith(true, "Reviewed");
  });
});
