import { Button, Spinner } from "@fluentui/react-components";
import { bundleIcon, DeleteFilled, DeleteRegular } from "@fluentui/react-icons";
import { CopilotMessageV2 as CopilotMessage } from "@fluentui-copilot/react-copilot-chat";
import { Suspense } from "react";

import { Markdown } from "../core/Markdown";   // assuming this is your markdown renderer
import { UsageInfo } from "./UsageInfo";
import { AgentIcon } from "./AgentIcon";
import { IAssistantMessageProps } from "./chatbot/types";

import styles from "./AgentPreviewChatBot.module.css";

const DeleteIcon = bundleIcon(DeleteFilled, DeleteRegular);

export function AssistantMessage({
  message,
  agentLogo,
  loadingState,
  agentName,
  showUsageInfo,
  onDelete,
}: IAssistantMessageProps): React.JSX.Element {
  // Clean inline citation markers
  const cleanContent = message.content.replace(/【[^】]+†source】/g, "");

  // Prepare sources - using 'label' as the display name
  const annotations = Array.isArray(message.annotations) ? message.annotations : [];

  // Optional: deduplicate by label (like you did with new Set)
  const uniqueSources = Array.from(
    new Map(annotations.map(a => [a.label, a])).values()
  );
  console.log("DEBUG - message.annotations:", message.annotations);
  console.log("DEBUG - annotations length:", annotations.length);
  console.log("DEBUG - uniqueSources:", uniqueSources);
  return (
    <CopilotMessage
      id={"msg-" + message.id}
      key={message.id}
      actions={
        <span>
          {onDelete && message.usageInfo && (
            <Button
              appearance="subtle"
              icon={<DeleteIcon />}
              onClick={() => {
                void onDelete(message.id);
              }}
            />
          )}
        </span>
      }
      avatar={<AgentIcon alt="" iconName={agentLogo} />}
      className={styles.copilotChatMessage}
      disclaimer={<span>AI-generated content may be incorrect</span>}
      footnote={
        <>
          {/* Custom sources section - similar to your previous project */}
          {uniqueSources.length > 0 && (
            <div className={styles.citationsContainer}>
              <div className={styles.citationsHeader}>Sources:</div>
              <div className={styles.citationsList}>
                {uniqueSources.map((annotation, i) => (
                  <div key={i} className={styles.citationItem}>
                    <span className={styles.citationNumber}>[{i + 1}]</span>
                    <span className={styles.citationTitle}>
                      {annotation.label || "Document"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {showUsageInfo && message.usageInfo && (
            <UsageInfo info={message.usageInfo} duration={message.duration} />
          )}
        </>
      }
      loadingState={loadingState}
      name={agentName ?? "Bot"}
    >
      <Suspense fallback={<Spinner size="small" />}>
        <Markdown content={cleanContent} />
      </Suspense>
    </CopilotMessage>
  );
}