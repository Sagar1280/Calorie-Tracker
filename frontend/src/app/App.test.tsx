/* @vitest-environment jsdom */
import "@testing-library/jest-dom/vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getMe } from "@/shared/api";
import { todayISO } from "@/shared/lib";
import App from "./App";

vi.mock("@/shared/api", () => ({
  ApiError: class ApiError extends Error {
    status: number;

    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
  getMe: vi.fn(),
  logout: vi.fn(),
}));

vi.mock("@/features/admin", () => ({
  AdminReviewScreen: () => <div>Admin review</div>,
}));

vi.mock("@/features/auth", () => ({
  AuthScreen: () => <div>Auth screen</div>,
}));

vi.mock("@/features/profile", () => ({
  ProfileScreen: () => <div>Profile screen</div>,
}));

vi.mock("./TrackerScreen", () => ({
  default: ({
    view,
    date,
    month,
    nav,
  }: {
    view: string;
    date: string;
    month: string;
    nav: ReactNode;
  }) => (
    <div data-testid="tracker">
      {`${view}|${date}|${month}`}
      {nav}
    </div>
  ),
}));

const mockedGetMe = vi.mocked(getMe);

function LocationProbe() {
  const location = useLocation();
  return (
    <output data-testid="location">
      {location.pathname}
      {location.search}
    </output>
  );
}

function renderAt(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
      <LocationProbe />
    </MemoryRouter>,
  );
}

describe("app routes", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    mockedGetMe.mockResolvedValue({
      id: 1,
      username: "tester",
      role: "user",
      created_at: "2026-01-01T00:00:00Z",
    });
  });

  it("loads date and month state from a calendar deep link", async () => {
    renderAt("/calendar?month=2026-09&date=2026-09-15");

    expect(await screen.findByTestId("tracker")).toHaveTextContent(
      "calendar|2026-09-15|2026-09",
    );
    expect(screen.getByTestId("location")).toHaveTextContent(
      "/calendar?month=2026-09&date=2026-09-15",
    );
  });

  it("preserves date and month when switching tabs", async () => {
    renderAt("/calendar?month=2026-09&date=2026-09-15");
    await screen.findByTestId("tracker");

    fireEvent.click(screen.getByRole("link", { name: "Intake" }));
    await waitFor(() =>
      expect(screen.getByTestId("location")).toHaveTextContent(
        "/intake?date=2026-09-15",
      ),
    );
    expect(screen.getByTestId("tracker")).toHaveTextContent(
      "intake|2026-09-15|2026-09",
    );

    fireEvent.click(screen.getByRole("link", { name: "Calendar" }));
    await waitFor(() =>
      expect(screen.getByTestId("location")).toHaveTextContent(
        "/calendar?month=2026-09&date=2026-09-15",
      ),
    );
    expect(screen.getByTestId("tracker")).toHaveTextContent(
      "calendar|2026-09-15|2026-09",
    );
  });

  it("falls back to today for invalid date and month values", async () => {
    const today = todayISO();
    renderAt("/calendar?month=2026-13&date=2026-02-30");

    expect(await screen.findByTestId("tracker")).toHaveTextContent(
      `calendar|${today}|${today.slice(0, 7)}`,
    );
  });

  it("redirects non-admin users away from review", async () => {
    renderAt("/review");

    expect(await screen.findByTestId("tracker")).toHaveTextContent(
      "intake|",
    );
    expect(screen.getByTestId("location")).toHaveTextContent(
      "/intake?date=",
    );
  });

  it("keeps review available to admins", async () => {
    mockedGetMe.mockResolvedValue({
      id: 1,
      username: "admin",
      role: "admin",
      created_at: "2026-01-01T00:00:00Z",
    });
    renderAt("/review");

    expect(await screen.findByText("Admin review")).toBeInTheDocument();
  });
});
