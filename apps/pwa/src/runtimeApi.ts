export type RoverAdapterType = "simulator" | "websocket_rover" | "factory_http"
  | "ros2_readonly" | "ironx" | "ironx_network";

interface RuntimeStatus {
  adapter: {
    type: RoverAdapterType;
    healthy: boolean;
    connected: boolean;
  };
}

export const runtimeApi = {
  async status(): Promise<RuntimeStatus> {
    const response = await fetch("/api/status");
    const body = await response.json() as RuntimeStatus;
    if (!response.ok) throw new Error(`Runtime status returned ${response.status}`);
    return body;
  }
};
