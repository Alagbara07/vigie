/// <reference types="vitest/globals" />
import { render, screen } from "@testing-library/react";

import { ProviderIndicator } from "@/components/provider-status";

describe("provider indicator", () => {
  it("shows NVIDIA only when that provider is configured", () => {
    render(<ProviderIndicator status={{ provider: "nvidia", configured: true, model: "example-model" }} />);

    expect(screen.getByText("Intelligence")).toBeInTheDocument();
    expect(screen.getByText("NVIDIA")).toBeInTheDocument();
    expect(screen.queryByText("example-model")).not.toBeInTheDocument();
  });

  it("does not claim NVIDIA is active when configuration is missing", () => {
    render(<ProviderIndicator status={{ provider: "nvidia", configured: false, model: null }} />);

    expect(screen.getByText("NVIDIA is not configured")).toBeInTheDocument();
    expect(screen.queryByText("●")).not.toBeInTheDocument();
  });

  it("shows the heuristic provider when that is what is running", () => {
    render(<ProviderIndicator status={{ provider: "heuristic", configured: true, model: null }} />);

    expect(screen.getByText("Heuristic")).toBeInTheDocument();
    expect(screen.queryByText("NVIDIA")).not.toBeInTheDocument();
  });

  it("shows nothing when the status cannot be loaded", () => {
    const { container } = render(<ProviderIndicator status={null} />);

    expect(container).toBeEmptyDOMElement();
  });
});
