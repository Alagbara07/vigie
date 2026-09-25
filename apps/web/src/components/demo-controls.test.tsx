/// <reference types="vitest/globals" />
import { fireEvent, render, screen } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ push: () => undefined }),
}));

import { DemoControls, DemoControlsLoader } from "@/components/demo-controls";
import { ApiError } from "@/lib/api/client";

describe("demo controls", () => {
  it("shows the demo controls only in demo mode", () => {
    render(<DemoControls />);

    expect(screen.getByText("Demo mode")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run demo" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reset demo" })).toBeInTheDocument();
  });

  it("explains when the demo cannot be prepared", async () => {
    render(
      <DemoControls
        onRun={async () => {
          throw new ApiError();
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Run demo" }));

    expect(await screen.findByText("The demo could not be prepared.")).toBeInTheDocument();
  });

  it("does not mount controls before demo mode is known", () => {
    render(<DemoControlsLoader />);

    expect(screen.queryByText("Demo mode")).not.toBeInTheDocument();
  });
});
