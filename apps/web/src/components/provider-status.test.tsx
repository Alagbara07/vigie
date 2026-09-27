/// <reference types="vitest/globals" />
import { render, screen } from "@testing-library/react";

import { ProviderIndicator } from "@/components/provider-status";

describe("provider indicator", () => {
  it("shows NVIDIA only when that provider is configured", () => {
    render(<ProviderIndicator status={{ provider: "nvidia", configured: true, model: "example-model" }} />);

    expect(screen.getByText("Understanding is active")).toBeInTheDocument();
    expect(screen.queryByText("NVIDIA")).not.toBeInTheDocument();
    expect(screen.queryByText("example-model")).not.toBeInTheDocument();
  });

  it("does not claim NVIDIA is active when configuration is missing", () => {
    const { container } = render(<ProviderIndicator status={{ provider: "nvidia", configured: false, model: null }} />);

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByText("NVIDIA is not connected")).not.toBeInTheDocument();
  });

  it("keeps the local provider off the command center", () => {
    const { container } = render(<ProviderIndicator status={{ provider: "heuristic", configured: true, model: null }} />);

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByText("Heuristic")).not.toBeInTheDocument();
  });

  it("shows nothing when the status cannot be loaded", () => {
    const { container } = render(<ProviderIndicator status={null} />);

    expect(container).toBeEmptyDOMElement();
  });
});
