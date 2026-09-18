import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import Dashboard from "../Dashboard";
import * as api from "../api";

vi.mock("../api");

const summary = {
  learner_id: "rhea",
  has_curriculum: true,
  goal_text: "learn testing",
  current_concept_id: "basics",
  completed_concept_ids: [],
  stages: [
    {
      concept_id: "basics",
      reason: "the foundation",
      prerequisites: [],
      estimated_minutes: 20,
      mastery: "not_started",
      primary_resource: null,
      alternative_resources: [],
      reference_resources: [],
      practice_resources: [],
      is_current: true,
    },
    {
      concept_id: "advanced",
      reason: "builds on basics",
      prerequisites: ["basics"],
      estimated_minutes: 30,
      mastery: "not_started",
      primary_resource: null,
      alternative_resources: [],
      reference_resources: [],
      practice_resources: [],
      is_current: false,
    },
  ],
};

const practiceItem = {
  id: "item-1",
  concept_id: "basics",
  type: "conceptual_question",
  prompt: "What is a basic?",
  starter_code: null,
};

beforeEach(() => {
  vi.resetAllMocks();
});

describe("Dashboard", () => {
  it("renders both stages and loads practice for the current one", async () => {
    api.getPractice.mockResolvedValue({
      done: false,
      concept_id: "basics",
      items: [practiceItem],
      results: [],
      answered_item_ids: [],
    });

    render(<Dashboard learnerId="rhea" summary={summary} onRefresh={() => {}} />);

    expect(screen.getByRole("heading", { name: "basics" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "advanced" })).toBeInTheDocument();

    await waitFor(() => expect(screen.getByText(/what is a basic\?/i)).toBeInTheDocument());
  });

  it("submits an answer, shows the score, and calls onRefresh when the stage completes", async () => {
    api.getPractice.mockResolvedValue({
      done: false,
      concept_id: "basics",
      items: [practiceItem],
      results: [],
      answered_item_ids: [],
    });
    api.submitAnswer.mockResolvedValue({
      score: 9,
      feedback: "Nicely done.",
      stage_complete: true,
      mastery: "mastered",
      advanced: true,
      curriculum_complete: false,
    });

    const onRefresh = vi.fn();
    render(<Dashboard learnerId="rhea" summary={summary} onRefresh={onRefresh} />);

    await waitFor(() => expect(screen.getByText(/what is a basic\?/i)).toBeInTheDocument());

    fireEvent.change(screen.getByPlaceholderText(/your answer/i), {
      target: { value: "It's the foundational stuff." },
    });
    fireEvent.click(screen.getByRole("button", { name: /submit/i }));

    await waitFor(() => expect(screen.getByText(/nicely done/i)).toBeInTheDocument());
    expect(api.submitAnswer).toHaveBeenCalledWith("rhea", "item-1", "It's the foundational stuff.");
    await waitFor(() => expect(onRefresh).toHaveBeenCalled());
  });
});
