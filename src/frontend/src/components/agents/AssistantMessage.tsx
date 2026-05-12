import { Button, Spinner } from "@fluentui/react-components";
import { bundleIcon, DeleteFilled, DeleteRegular } from "@fluentui/react-icons";
import { CopilotMessageV2 as CopilotMessage } from "@fluentui-copilot/react-copilot-chat";
import { Suspense } from "react";

import { Markdown } from "../core/Markdown";
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
  // Clean inline citation markers like 【4:1†source】
  const cleanContent = message.content.replace(/【[^】]+†source】/g, "");

  // Deduplicate annotations by label
  const annotations = Array.isArray(message.annotations) ? message.annotations : [];
  const uniqueSources = Array.from(
    new Map(annotations.map((a) => [a.label, a])).values()
  );

  // Code Interpreter images
  const images = Array.isArray(message.images) ? message.images : [];

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
          {/* ── Sources / Citations ── */}
          {uniqueSources.length > 0 && (
            <div className={styles.citationsContainer}>
              <div className={styles.citationsHeader}>Sources:</div>
              <div className={styles.citationsList}>
                {uniqueSources.map((annotation, i) => (
                  <div key={i} className={styles.citationItem}>
                    <span className={styles.citationNumber}>[{i + 1}]</span>
                    {annotation.url ? (
                      // Clickable link — opens the doc via the backend SAS proxy
                      <a
                        href={annotation.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={styles.citationLink}
                        title={`Open: ${annotation.label}`}
                      >
                        {annotation.label || "Document"}
                      </a>
                    ) : (
                      // Fallback: plain text when no URL available
                      <span className={styles.citationTitle}>
                        {annotation.label || "Document"}
                      </span>
                    )}
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

        {/* ── Code Interpreter images ── */}
        {images.length > 0 && (
          <div className={styles.imagesContainer}>
            {images.map((image, index) => (
              <div key={image.file_id || index} className={styles.imageWrapper}>
                <img
                  src={`data:${image.mime_type || "image/png"};base64,${image.data}`}
                  alt={image.filename || `Generated chart ${index + 1}`}
                  className={styles.generatedImage}
                  onError={(e) => {
                    console.error("Image failed to load:", image.file_id);
                    e.currentTarget.style.display = "none";
                  }}
                />
                {image.filename && (
                  <div className={styles.imageCaption}>{image.filename}</div>
                )}
              </div>
            ))}
          </div>
        )}
      </Suspense>
    </CopilotMessage>
  );
}