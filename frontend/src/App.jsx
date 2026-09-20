import React from "react";
import AgentScene from "./components/AgentScene";
import ChatInterface from "./components/ChatInterface";
import { useAgentStream } from "./hooks/useAgentStream";
import "./styles/index.css";

export default function App() {
  const {
    messages,
    isStreaming,
    agentState,
    lastQuery,
    sendMessage,
    stopStream,
  } = useAgentStream();

  return (
    <div className="app-container">
      <div className="scene-panel">
        <AgentScene agentState={agentState} lastQuery={lastQuery} />
      </div>
      <div className="chat-panel">
        <ChatInterface
          messages={messages}
          isStreaming={isStreaming}
          agentState={agentState}
          onSend={sendMessage}
          onStop={stopStream}
        />
      </div>
    </div>
  );
}
