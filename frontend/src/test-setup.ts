import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";
HTMLDialogElement.prototype.showModal = function () {
  this.open = true;
};
HTMLDialogElement.prototype.close = function () {
  this.open = false;
  this.dispatchEvent(new Event("close"));
};
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

window.scrollTo = vi.fn();
