import { ChangeEvent, FormEvent, useState } from "react";
import { ChatMessage } from "../types";

interface ChatPanelProps {
  messages: ChatMessage[];
  onSubmit: (prompt: string) => void;
  isRunning: boolean;
}

export default function ChatPanel({ messages, onSubmit, isRunning }: ChatPanelProps) {
  const [input, setInput] = useState("");

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const prompt = input.trim();
    if (!prompt) {
      return;
    }

    onSubmit(prompt);
    setInput("");
  };

  return (
    <section className="panel chat-panel">
      <header className="panel-header">
        <h2>Mission Chat</h2>
        <span className={`badge ${isRunning ? "badge-live" : "badge-idle"}`}>{isRunning ? "running" : "idle"}</span>
      </header>

      <div className="chat-list" role="log" aria-live="polite">
        {messages.map((message) => (
          <article key={message.id} className={`chat-bubble ${message.role === "user" ? "chat-user" : "chat-system"}`}>
            <p>{message.text}</p>
            <time dateTime={message.timestamp}>{new Date(message.timestamp).toLocaleTimeString()}</time>
          </article>
        ))}
      </div>

      <form className="chat-form" onSubmit={handleSubmit}>
        <textarea
          value={input}
          onChange={(event: ChangeEvent<HTMLTextAreaElement>) => setInput(event.target.value)}
          placeholder="Example: Open settings, go to notifications, and enable updates"
          rows={3}
        />
        <button type="submit" disabled={isRunning}>Run Task</button>
      </form>
    </section>
  );
}
