import { useCallback, useRef, useState } from "react";
import { createParser } from "eventsource-parser";

/**
 * Custom hook that manages SSE streaming from the backend.
 * Returns streaming state plus an async function to send messages.
 */
export function useAgentStream() {
    const [isStreaming, setIsStreaming] = useState(false);
    const [messages, setMessages] = useState([]);
    const [agentState, setAgentState] = useState("idle");
    const [lastQuery, setLastQuery] = useState("");
    // agentState: "idle" | "thinking" | "searching" | "responding"

    const abortRef = useRef(null);

    const handleSSEEvent = useCallback((eventType, data, assistantId) => {
        switch (eventType) {
            case "thinking":
                setAgentState("thinking");
                break;

            case "token":
                setMessages((prev) =>
                    prev.map((m) =>
                        m.id === assistantId
                            ? { ...m, content: (m.content || "") + data }
                            : m
                    )
                );
                setAgentState("responding");
                break;

            case "tool_call_start":
                setAgentState("searching");
                if (data?.arguments?.query) {
                    setLastQuery(data.arguments.query);
                }
                setMessages((prev) =>
                    prev.map((m) =>
                        m.id === assistantId
                            ? {
                                ...m,
                                toolCalls: [
                                    ...(m.toolCalls || []),
                                    { ...data, status: "running" },
                                ],
                            }
                            : m
                    )
                );
                break;

            case "tool_call_result":
                setMessages((prev) =>
                    prev.map((m) =>
                        m.id === assistantId
                            ? {
                                ...m,
                                toolCalls: (m.toolCalls || []).map((tc) =>
                                    tc.name === data.name
                                        ? { ...tc, status: "complete", result: data.result }
                                        : tc
                                ),
                            }
                            : m
                    )
                );
                break;

            case "done":
                setAgentState("idle");
                break;

            case "error":
                setMessages((prev) =>
                    prev.map((m) =>
                        m.id === assistantId
                            ? { ...m, content: (m.content || "") + `\n[Error: ${data.message}]` }
                            : m
                    )
                );
                setAgentState("idle");
                break;
            default:
                break;
        }
    }, []);

    const sendMessage = useCallback(async (text) => {
        if (isStreaming) return;

        // Add user message immediately
        const userMsg = { role: "user", content: text, id: crypto.randomUUID() };
        setMessages((prev) => [...prev, userMsg]);
        setIsStreaming(true);
        setAgentState("thinking");

        // Build history from current messages
        const history = messages.map((m) => ({
            role: m.role,
            content: m.content || "",
        }));

        const controller = new AbortController();
        abortRef.current = controller;

        // Placeholder for the assistant response
        const assistantId = crypto.randomUUID();
        setMessages((prev) => [
            ...prev,
            { role: "assistant", content: "", id: assistantId, toolCalls: [] },
        ]);

        try {
            const response = await fetch("/api/chat/stream", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: text, history, stream: true }),
                signal: controller.signal,
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            const parser = createParser({
                onEvent(event) {
                    if (event.type === "event" || event.event) {
                        try {
                            const parsed = JSON.parse(event.data);
                            handleSSEEvent(event.event, parsed, assistantId);
                        } catch {
                            // Skip unparseable SSE data
                        }
                    }
                },
            });

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value, { stream: true });
                parser.feed(chunk);
            }
        } catch (err) {
            if (err.name !== "AbortError") {
                setMessages((prev) =>
                    prev.map((m) =>
                        m.id === assistantId
                            ? { ...m, content: (m.content || "") + `\n[Error: ${err.message}]` }
                            : m
                    )
                );
            }
        } finally {
            setIsStreaming(false);
            setAgentState("idle");
            abortRef.current = null;
        }
    }, [messages, isStreaming, handleSSEEvent]);

    const stopStream = useCallback(() => {
        abortRef.current?.abort();
    }, []);

    return { messages, isStreaming, agentState, lastQuery, sendMessage, stopStream };
}