import { ReactNode } from "react";
import { Button } from "@fluentui/react-components";
import { AgentIcon } from "./AgentIcon";
import styles from "./StarterMessages.module.css";

interface IStarterMessageProps {
  agentName?: string;
  agentLogo?: string;
  agentDescription?: string;
  onPromptClick?: (prompt: string) => void;
}

export function StarterMessages({
  agentName,
  agentLogo,
  agentDescription,
  onPromptClick,
}: IStarterMessageProps): ReactNode {
  const defaultStarterPrompts = [
    "What are the academic regulations?",
    "How do I apply for medical leave?",
    "Explain the credit transfer process",
    "What are my graduation requirements?",
  ];

  return (
    <div className={styles.zeroprompt}>
      <div className={styles.content}>
        <AgentIcon
          alt={agentName ?? "BOT-SLIIT"}
          iconClassName={styles.emptyStateAgentIcon}
          iconName={agentLogo}
        />

        <h2 className={styles.welcome}>
          {agentName
            ? `Hello! I'm ${agentName}`
            : "How can I help you today?"}
        </h2>

        {agentDescription ? (
          <p className={styles.caption}>{agentDescription}</p>
        ) : (
          <p className={styles.caption}>
            Ask me anything about SLIIT academic policies, regulations,
            and procedures. I'll do my best to assist you.
          </p>
        )}

        <div className={styles.notice}>
          ⚡ All interactions logged · verify with Academic Affairs Division
        </div>
      </div>

      {onPromptClick && (
        <div className={styles.promptStarters}>
          {defaultStarterPrompts.map((prompt, index) => (
            <Button
              key={`prompt-${index}`}
              appearance="subtle"
              onClick={() => onPromptClick(prompt)}
            >
              {prompt}
            </Button>
          ))}
        </div>
      )}
    </div>
  );
}