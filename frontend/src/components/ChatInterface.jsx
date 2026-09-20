import { useState, useRef, useEffect } from "react";

export default function ChatInterface({
    messages,
    isStreaming,
    agentState,
    onSend,
    onStop,
}) {
    const [input, setInput] = useState("");
    const messagesEndRef = useRef(null);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages]);

    const handleSubmit = (e) => {
        e.preventDefault();
        if (!input.trim() || isStreaming) return;
        onSend(input.trim());
        setInput("");
    };

    const stateLabel = {
        idle: "Ready",
        thinking: "Thinking...",
        searching: "Searching the web...",
        responding: "Responding...",
    }[agentState];

    return (
        <div className="chat-container">
            <div className="chat-header">
                <h2>Agentic Search</h2>
                <span className={`status-badge status-${agentState}`}>
                    {stateLabel}
                </span>
            </div>

            <div className="messages-list">
                {messages.map((msg) => (
                    <div key={msg.id} className={`message message-${msg.role}`}>
                        <div className="message-content">{msg.content}</div>

                        {/* Tool call visualization */}
                        {msg.toolCalls?.map((tc, i) => (
                            <div key={i} className={`tool-call tool-${tc.status}`}>
                                <span className="tool-icon">🔍</span>
                                <span className="tool-name">
                                    {tc.name === "web_search" ? "Web Search" : tc.name}
                                </span>
                                {tc.arguments?.query && (
                                    <code className="tool-query">"{tc.arguments.query}"</code>
                                )}
                                {tc.status === "complete" && tc.result?.results && (
                                    <div className="tool-results">
                                        {tc.result.results.slice(0, 3).map((r, j) => (
                                            <a
                                                key={j}
                                                href={r.url}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="result-link"
                                            >
                                                {r.title}
                                            </a>
                                        ))}
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                ))}
                <div ref={messagesEndRef} />
            </div>

            <form onSubmit={handleSubmit} className="chat-input-form">
                <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder="Ask anything — the agent will search if needed..."
                    disabled={isStreaming}
                    className="chat-input"
                />
                {isStreaming ? (
                    <button type="button" onClick={onStop} className="btn-stop">
                        Stop
                    </button>
                ) : (
                    <button type="submit" className="btn-send" disabled={!input.trim()}>
                        Send
                    </button>
                )}
            </form>
        </div>
    );
}