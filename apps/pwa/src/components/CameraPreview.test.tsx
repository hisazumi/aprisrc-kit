import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CameraPreview } from "./CameraPreview";

function fakeStream() {
  const stop = vi.fn();
  const stream = { getTracks: () => [{ stop }] } as unknown as MediaStream;
  return { stop, stream };
}

function buttonWithText(container: HTMLElement, text: string): HTMLButtonElement {
  const button = [...container.querySelectorAll("button")]
    .find((candidate) => candidate.textContent?.includes(text));
  if (!button) throw new Error(`Button not found: ${text}`);
  return button;
}

describe("CameraPreview", () => {
  const mediaDevicesDescriptor = Object.getOwnPropertyDescriptor(navigator, "mediaDevices");

  beforeEach(() => {
    (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean })
      .IS_REACT_ACT_ENVIRONMENT = true;
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  });

  afterEach(() => {
    if (mediaDevicesDescriptor) {
      Object.defineProperty(navigator, "mediaDevices", mediaDevicesDescriptor);
    } else {
      Reflect.deleteProperty(navigator, "mediaDevices");
    }
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("starts the rear camera, switches cameras, and stops all tracks", async () => {
    const first = fakeStream();
    const second = fakeStream();
    const getUserMedia = vi.fn()
      .mockResolvedValueOnce(first.stream)
      .mockResolvedValueOnce(second.stream);
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia }
    });

    const container = document.createElement("div");
    const root = createRoot(container);
    await act(async () => root.render(<CameraPreview />));

    await act(async () => {
      buttonWithText(container, "Start camera").click();
      await Promise.resolve();
    });

    expect(getUserMedia).toHaveBeenNthCalledWith(1, {
      audio: false,
      video: {
        facingMode: { ideal: "environment" },
        width: { ideal: 1280 },
        height: { ideal: 720 }
      }
    });
    expect(container.textContent).toContain("Camera active");
    expect(container.querySelector("video")?.srcObject).toBe(first.stream);

    await act(async () => {
      buttonWithText(container, "Use front camera").click();
      await Promise.resolve();
    });

    expect(first.stop).toHaveBeenCalledOnce();
    expect(getUserMedia).toHaveBeenNthCalledWith(2, expect.objectContaining({
      video: expect.objectContaining({ facingMode: { ideal: "user" } })
    }));
    expect(container.textContent).toContain("Front camera");
    expect(container.querySelector("video")?.srcObject).toBe(second.stream);

    await act(async () => root.unmount());
    expect(second.stop).toHaveBeenCalledOnce();
  });

  it("shows a useful permission error", async () => {
    const getUserMedia = vi.fn().mockRejectedValue(
      new DOMException("Permission denied", "NotAllowedError")
    );
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia }
    });

    const container = document.createElement("div");
    const root = createRoot(container);
    await act(async () => root.render(<CameraPreview />));

    await act(async () => {
      buttonWithText(container, "Start camera").click();
      await Promise.resolve();
    });

    expect(container.querySelector('[role="alert"]')?.textContent)
      .toContain("Camera permission was denied");

    await act(async () => root.unmount());
  });

  it("uses the front camera and simplified controls in service mode", async () => {
    const camera = fakeStream();
    const getUserMedia = vi.fn().mockResolvedValue(camera.stream);
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia }
    });
    const container = document.createElement("div");
    const root = createRoot(container);
    await act(async () => root.render(
      <CameraPreview variant="service" initialFacing="user" />
    ));

    expect(container.textContent).toContain("Vision is off");
    expect(container.textContent).not.toContain("Open recorded video");
    await act(async () => {
      buttonWithText(container, "Start vision").click();
      await Promise.resolve();
    });

    expect(getUserMedia).toHaveBeenCalledWith({
      audio: false,
      video: {
        facingMode: { ideal: "user" },
        width: { ideal: 1280 },
        height: { ideal: 720 }
      }
    });
    expect(container.textContent).toContain("Preparing upper-body tracking");

    await act(async () => root.unmount());
    expect(camera.stop).toHaveBeenCalledOnce();
  });

  it("uses a recorded video as the same on-device perception input", async () => {
    const createObjectURL = vi.fn(() => "blob:recorded-video");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    const container = document.createElement("div");
    const root = createRoot(container);
    await act(async () => root.render(<CameraPreview />));

    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    const file = new File(["video"], "recorded.mp4", { type: "video/mp4" });
    Object.defineProperty(input, "files", { configurable: true, value: [file] });
    await act(async () => {
      input?.dispatchEvent(new Event("change", { bubbles: true }));
      await Promise.resolve();
    });

    expect(createObjectURL).toHaveBeenCalledWith(file);
    expect(container.textContent).toContain("Recorded video");

    await act(async () => root.unmount());
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:recorded-video");
  });

  it("renders the Lab virtual person using normalized camera measurements", async () => {
    const container = document.createElement("div");
    const root = createRoot(container);
    await act(async () => root.render(
      <CameraPreview virtualPerson={{
        visible: true,
        distanceM: 1.35,
        bearingDeg: 8,
        centerX: 0.4,
        centerY: 0.5,
        width: 0.25,
        height: 0.59
      }} />
    ));

    const overlay = container.querySelector<HTMLElement>('[aria-label="Virtual camera person detection"]');
    const box = container.querySelector<HTMLElement>(".virtual-camera__detection");
    expect(overlay).not.toBeNull();
    expect(box?.style.left).toBe("27.5%");
    expect(box?.style.width).toBe("25%");
    expect(container.textContent).toContain("Simulation active");
    expect(container.textContent).toContain("1.35 m · 8.0°");
    expect(container.textContent).toContain("person detected · 0.95");

    await act(async () => root.unmount());
  });

  it("shows target loss without drawing a stale person box", async () => {
    const container = document.createElement("div");
    const root = createRoot(container);
    await act(async () => root.render(
      <CameraPreview virtualPerson={{
        visible: false,
        distanceM: 2,
        bearingDeg: 50,
        centerX: 0,
        centerY: 0.5,
        width: 0.17,
        height: 0.4
      }} />
    ));

    expect(container.querySelector(".virtual-camera__detection")).toBeNull();
    expect(container.textContent).toContain("TARGET OUT OF VIEW");
    expect(container.textContent).toContain("person outside view");

    await act(async () => root.unmount());
  });
});
