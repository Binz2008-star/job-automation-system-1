import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: any) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

import CommandPage from "@/app/command/page";

type JsonValue = Record<string, unknown>;

function jsonResponse(body: JsonValue, status = 200): ResponseLike {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

type ResponseLike = {
  ok: boolean;
  status: number;
  json: () => Promise<JsonValue>;
};

const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<ResponseLike>>();

beforeEach(() => {
  fetchMock.mockReset();
  localStorage.clear();
  localStorage.setItem("rico_sid", "test-session-01");
  vi.stubGlobal("fetch", fetchMock);
});

describe("handleConfirmProfile", () => {
  it("calls confirm endpoint with proxy path, not absolute http URL", async () => {
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);

      if (url.includes("/api/v1/me")) {
        return jsonResponse({ authenticated: false, role: "guest", email: null, guest: true });
      }

      if (url.includes("/api/v1/rico/upload-cv")) {
        return jsonResponse({
          ok: true,
          status: "preview_ready",
          preview: {
            name: "Test",
            email: "t@t.com",
            phone: "0501234567",
            current_role: "HSE Manager",
            experience_years: 5,
            target_roles: [],
            skills_detected: ["hse"],
            existing_skills: [],
            skills: ["hse"],
            certifications: [],
            languages: [],
          },
          filename: "cv.pdf",
          extraction_quality: "good",
          user_id: "public:test-session-01",
        });
      }

      if (url.includes("/api/v1/rico/confirm-cv-profile")) {
        return jsonResponse({ ok: true, status: "confirmed", message: "Profile confirmed", profile: {} });
      }

      throw new Error(`Unhandled fetch: ${url}`);
    });

    render(<CommandPage />);

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(fileInput, new File(["%PDF-1.4"], "cv.pdf", { type: "application/pdf" }));

    await userEvent.click(await screen.findByText("Use this profile"));

    await waitFor(() => {
      const confirmCall = fetchMock.mock.calls.find(([url]) =>
        String(url).includes("confirm-cv-profile")
      );

      expect(confirmCall).toBeDefined();
      expect(String(confirmCall?.[0])).toMatch(
        /^\/proxy\/api\/v1\/rico\/confirm-cv-profile\?user_id=public%3Atest-session-01/
      );
      expect(String(confirmCall?.[0])).not.toMatch(/^http/);
    });
  });
});

describe("Edit before saving", () => {
  it("does not call /chat/public when Edit button is clicked", async () => {
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);

      if (url.includes("/api/v1/me")) {
        return jsonResponse({ authenticated: false, role: "guest", email: null, guest: true });
      }

      if (url.includes("/api/v1/rico/upload-cv")) {
        return jsonResponse({
          ok: true,
          status: "preview_ready",
          preview: {
            name: "Test",
            email: "t@t.com",
            phone: "0501234567",
            current_role: null,
            experience_years: 3,
            target_roles: [],
            skills_detected: ["safety"],
            existing_skills: [],
            skills: ["safety"],
            certifications: [],
            languages: [],
          },
          filename: "cv.pdf",
          extraction_quality: "good",
          user_id: "public:test-session-01",
        });
      }

      if (url.includes("/api/v1/rico/chat/public")) {
        return jsonResponse({ reply: "unexpected" }, 500);
      }

      throw new Error(`Unhandled fetch: ${url}`);
    });

    render(<CommandPage />);

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(fileInput, new File(["%PDF-1.4"], "cv.pdf", { type: "application/pdf" }));

    const editButton = await screen.findByText("Edit before saving");
    const callsBefore = fetchMock.mock.calls.length;

    await userEvent.click(editButton);

    await waitFor(() => {
      expect(screen.getByText("Edit profile")).toBeInTheDocument();
    });

    expect(fetchMock.mock.calls.length).toBe(callsBefore);
    expect(screen.queryByText("Edit before saving")).not.toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([url]) => String(url).includes("/api/v1/rico/chat/public"))
    ).toBe(false);
  });

  it("calls confirm-cv-profile with edited draft when Save profile is clicked", async () => {
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);

      if (url.includes("/api/v1/me")) {
        return jsonResponse({ authenticated: false, role: "guest", email: null, guest: true });
      }

      if (url.includes("/api/v1/rico/upload-cv")) {
        return jsonResponse({
          ok: true,
          status: "preview_ready",
          preview: {
            name: "",
            email: "t@t.com",
            phone: "0501234567",
            current_role: "",
            experience_years: 3,
            target_roles: [],
            skills_detected: ["safety"],
            existing_skills: [],
            skills: ["safety"],
            certifications: [],
            languages: [],
          },
          filename: "cv.pdf",
          extraction_quality: "good",
          user_id: "public:test-session-01",
        });
      }

      if (url.includes("/api/v1/rico/confirm-cv-profile")) {
        return jsonResponse({ ok: true, status: "confirmed", message: "Profile confirmed", profile: {} });
      }

      throw new Error(`Unhandled fetch: ${url}`);
    });

    render(<CommandPage />);

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(fileInput, new File(["%PDF-1.4"], "cv.pdf", { type: "application/pdf" }));

    await userEvent.click(await screen.findByText("Edit before saving"));

    const nameInput = screen.getByLabelText("Name");
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, "Roben Edwan");

    await userEvent.click(screen.getByText("Save profile"));

    await waitFor(() => {
      const confirmCall = fetchMock.mock.calls.find(([url]) =>
        String(url).includes("confirm-cv-profile")
      );

      expect(confirmCall).toBeDefined();
      const body = JSON.parse(String((confirmCall?.[1] as RequestInit | undefined)?.body ?? "{}"));
      expect(body.preview.name).toBe("Roben Edwan");
    });
  });
});
