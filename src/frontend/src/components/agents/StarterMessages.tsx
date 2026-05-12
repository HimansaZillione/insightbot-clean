import { ReactNode } from "react";
import { Body1, Subtitle1, Button } from "@fluentui/react-components";
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
  // Default starter prompts for demonstration
  const defaultStarterPrompts = [
    "Summarize the last team meeting",
    "What was decided in the board meeting on [date]?",
    "Find all action items assigned to me",
    "Which meetings mentioned the project budget?",
  ];

  return (
    <div className={styles.zeroprompt}>
      <div className={styles.content}>
        <AgentIcon
          alt={agentName ?? "Agent"}
          iconClassName={styles.emptyStateAgentIcon}
          iconName={agentLogo}
        />
        <Subtitle1 className={styles.welcome}>
          {agentName ? `Hello! I'm ${agentName}` : "Hello! How can I help you today?"}
        </Subtitle1>
        {agentDescription && (
          <Body1 className={styles.caption}>{agentDescription}</Body1>
        )}
      </div>

      {onPromptClick && (
        <div className={styles.promptStarters}>
          {defaultStarterPrompts.map((prompt, index) => (
            <Button
              key={`prompt-${index}`}
              appearance="subtle"
              onClick={() => onPromptClick(prompt)}
            >
              <Body1>{prompt}</Body1>
            </Button>
          ))}
        </div>
      )}
    </div>
  );
}