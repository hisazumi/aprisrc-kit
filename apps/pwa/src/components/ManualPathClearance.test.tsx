import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";
import { ManualPathClearance } from "./ManualPathClearance";

afterEach(() => vi.useRealTimers());

async function setup() {
  (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  vi.useFakeTimers();
  const container = document.createElement("div"), root = createRoot(container);
  const props = { eligible: true, blocked: false, onChange: vi.fn() };
  const render = async () => act(async () => root.render(<ManualPathClearance {...props} />));
  await render();
  const click = async () => act(async () => container.querySelector("button")!.click());
  return { root, container, props, render, click };
}

it("starts disabled, renews only after confirmation, and expires without rearming", async () => {
  const t = await setup();
  expect(t.props.onChange).not.toHaveBeenCalled();
  await t.click();
  expect(t.props.onChange).toHaveBeenLastCalledWith(true);
  await act(async () => vi.advanceTimersByTimeAsync(30_000));
  expect(t.props.onChange).toHaveBeenLastCalledWith(false);
  const n = t.props.onChange.mock.calls.length;
  await act(async () => vi.advanceTimersByTimeAsync(1000));
  expect(t.props.onChange).toHaveBeenCalledTimes(n);
  await act(async () => t.root.unmount());
});

it.each(["eligibility", "blocked", "blur", "unmount", "click"])("revokes on %s", async (reason) => {
  const t = await setup();
  await t.click();
  if (reason === "eligibility") { t.props.eligible = false; await t.render(); }
  if (reason === "blocked") { t.props.blocked = true; await t.render(); }
  if (reason === "blur") await act(async () => window.dispatchEvent(new Event("blur")));
  if (reason === "click") await t.click();
  if (reason === "unmount") await act(async () => t.root.unmount());
  expect(t.props.onChange).toHaveBeenLastCalledWith(false);
  if (reason !== "unmount") await act(async () => t.root.unmount());
});
