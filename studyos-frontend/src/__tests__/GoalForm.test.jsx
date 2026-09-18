import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import GoalForm from "../GoalForm";

describe("GoalForm", () => {
  it("submits the trimmed goal text", () => {
    const onSubmit = vi.fn();
    render(<GoalForm onSubmit={onSubmit} disabled={false} />);
    fireEvent.change(screen.getByPlaceholderText(/i want to learn/i), {
      target: { value: "  teach me Rust  " },
    });
    fireEvent.click(screen.getByRole("button", { name: /build my learning path/i }));
    expect(onSubmit).toHaveBeenCalledWith("teach me Rust");
  });

  it("disables the submit button while disabled prop is true", () => {
    render(<GoalForm onSubmit={() => {}} disabled={true} />);
    expect(screen.getByRole("button", { name: /build my learning path/i })).toBeDisabled();
  });
});
