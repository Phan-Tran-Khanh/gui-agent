import { AgentEvent } from "../types";

interface StreamOptions {
  onEvent: (event: AgentEvent) => void;
  onConnection: (connected: boolean) => void;
}

export class AgentWsClient {
  private socket?: WebSocket;

  connect(url: string, options: StreamOptions): void {
    this.socket = new WebSocket(url);

    this.socket.onopen = () => {
      options.onConnection(true);
    };

    this.socket.onclose = () => {
      options.onConnection(false);
    };

    this.socket.onerror = () => {
      options.onConnection(false);
    };

    this.socket.onmessage = (message) => {
      try {
        const payload = JSON.parse(message.data as string) as AgentEvent;
        options.onEvent(payload);
      } catch {
        options.onConnection(false);
      }
    };
  }

  disconnect(): void {
    this.socket?.close();
  }
}
