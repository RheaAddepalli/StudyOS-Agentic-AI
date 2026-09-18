import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import LearnerGate from "../LearnerGate";

describe("LearnerGate", () => {
  it("disables continue until a name is entered", () => {
    render(<LearnerGate onEnter={() => {}} />);
    expect(screen.getByRole("button", { name: /continue/i })).toBeDisabled();
  });

  it("calls onEnter with the trimmed name on submit", () => {
    const onEnter = vi.fn();
    render(<LearnerGate onEnter={onEnter} />);
    fireEvent.change(screen.getByPlaceholderText(/your name/i), { target: { value: "  rhea  " } });
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(onEnter).toHaveBeenCalledWith("rhea");
  });
});
