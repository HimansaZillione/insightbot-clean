import { ReactNode, useState, useMemo, useEffect } from "react";
import {
  Body1,
  Button,
  Caption1,
  Spinner,
  Title3,
} from "@fluentui/react-components";
import { ChatRegular, MoreHorizontalRegular } from "@fluentui/react-icons";
import clsx from "clsx";

import { AgentIcon } from "./AgentIcon";
import { SettingsPanel } from "../core/SettingsPanel";
import { AgentPreviewChatBot } from "./AgentPreviewChatBot";
import { MenuButton } from "../core/MenuButton/MenuButton";
import { IChatItem } from "./chatbot/types";
import { Waves } from "./Waves";
import { BuiltWithBadge } from "./BuiltWithBadge";

import styles from "./AgentPreview.module.css";

interface IAgent {
  id: string;
  object: string;
  created_at: number;
  name: string;
  description?: string | null;
  model: string;
  instructions?: string;
  tools?: Array<{ type: string }>;
  top_p?: number;
  temperature?: number;
  tool_resources?: {
    file_search?: {
      vector_store_ids?: string[];
    };
    [key: string]: any;
  };
  metadata?: Record<string, any>;
  response_format?: "auto" | string;
  agentPlaygroundUrl: string;
}

interface IAgentPreviewProps {
  resourceId: string;
  agentDetails: IAgent;
}

interface IAnnotation {
  label: string;
  index: number;
  url?: string;
}

/** Strip "for SLIIT" (and any trailing whitespace) from the displayed agent name */
const toDisplayName = (name: string | undefined): string =>
  (name ?? "").replace(/\s*for\s+SLIIT\b/gi, "").trim();

const preprocessContent = (
  content: string,
  annotations?: IAnnotation[]
): string => {
  if (!annotations || annotations.length === 0) {
    return content;
  }

  let processedContent = content;
  annotations
    .slice()
    .sort((a, b) => {
      if (b.index !== a.index) {
        return b.index - a.index;
      }
      return b.label.localeCompare(a.label);
    })
    .filter((annotation, index, self) =>
      index === self.findIndex(a => a.label === annotation.label && a.index === annotation.index))
    .forEach((annotation) => {
      if (annotation.index >= 0 && annotation.index <= processedContent.length) {
        processedContent =
          processedContent.slice(0, annotation.index + 1) +
          ` [${annotation.label}]` +
          processedContent.slice(annotation.index + 1);
      }
    });
  return processedContent;
};

const formatTimestampToLocalTime = (timestampStr: string): string => {
  let localTime = new Date().toLocaleString();
  if (timestampStr) {
    try {
      const timestamp = parseFloat(timestampStr);
      if (!isNaN(timestamp)) {
        const date = new Date(timestamp * 1000);
        localTime = date.toLocaleDateString('en-US', {
          month: '2-digit',
          day: '2-digit',
          year: '2-digit'
        }) + ', ' + date.toLocaleTimeString('en-US', {
          hour: 'numeric',
          minute: '2-digit',
          hour12: true
        });
      }
    } catch (e) {
      console.error('Error parsing timestamp:', e);
    }
  }
  return localTime;
};

export function AgentPreview({ agentDetails }: IAgentPreviewProps): ReactNode {
  const [isSettingsPanelOpen, setIsSettingsPanelOpen] = useState(false);
  const [messageList, setMessageList] = useState<IChatItem[]>([]);
  const [isResponding, setIsResponding] = useState(false);
  const [isLoadingChatHistory, setIsLoadingChatHistory] = useState(true);

  // Cleaned name — never shows "SLIIT" in the UI
  const displayName = toDisplayName(agentDetails.name);

  const loadChatHistory = async () => {
    try {
      const response = await fetch("/chat/history", {
        method: "GET",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
      });

      if (response.ok) {
        const json_response: Array<{
          role: string;
          content: string;
          created_at: string;
          annotations?: IAnnotation[];
        }> = await response.json();

        const historyMessages: IChatItem[] = [];
        const reversedResponse = [...json_response].reverse();

        for (const entry of reversedResponse) {
          const localTime = formatTimestampToLocalTime(entry.created_at);
          if (entry.role === "user") {
            historyMessages.push({
              id: crypto.randomUUID(),
              content: entry.content,
              role: "user",
              more: { time: localTime },
            });
          } else {
            historyMessages.push({
              id: `assistant-hist-${Date.now()}-${Math.random()}`,
              content: preprocessContent(entry.content, entry.annotations),
              role: "assistant",
              isAnswer: true,
              more: { time: localTime },
            });
          }
        }
        setMessageList((prev) => [...historyMessages, ...prev]);
      } else {
        const errorMessage: IChatItem = {
          id: crypto.randomUUID(),
          content: "Error occurs while loading chat history!",
          isAnswer: true,
          more: { time: new Date().toISOString() },
        };
        setMessageList(prev => [...prev, errorMessage]);
      }
      setIsLoadingChatHistory(false);
    } catch (error) {
      console.error("Failed to load chat history:", error);
      const errorMessage: IChatItem = {
        id: crypto.randomUUID(),
        content: "Error occurs while loading chat history!",
        isAnswer: true,
        more: { time: new Date().toISOString() },
      };
      setMessageList(prev => [...prev, errorMessage]);
      setIsLoadingChatHistory(false);
    }
  };

  useEffect(() => {
    loadChatHistory();
  }, []);

  const handleSettingsPanelOpenChange = (isOpen: boolean) => {
    setIsSettingsPanelOpen(isOpen);
  };

  const newThread = () => {
    setMessageList([]);
    deleteAllCookies();
  };

  const deleteAllCookies = (): void => {
    document.cookie.split(";").forEach((cookieStr: string) => {
      const trimmedCookieStr = cookieStr.trim();
      const eqPos = trimmedCookieStr.indexOf("=");
      const name =
        eqPos > -1 ? trimmedCookieStr.substring(0, eqPos) : trimmedCookieStr;
      document.cookie = name + "=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/";
    });
  };

  const onSend = async (message: string) => {
    const userMessage: IChatItem = {
      id: `user-${Date.now()}`,
      content: message,
      role: "user",
      more: { time: new Date().toISOString() },
    };

    setMessageList((prev) => [...prev, userMessage]);

    try {
      setIsResponding(true);
      const response = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
        credentials: "include",
      });

      console.log("[ChatClient] Response status:", response.status, response.statusText);

      if (!response.ok) {
        console.error("[ChatClient] Response not OK:", response.status, response.statusText);
        return;
      }

      if (!response.body) {
        throw new Error("ReadableStream not supported or response.body is null");
      }

      console.log("[ChatClient] Starting to handle streaming response...");
      handleMessages(response.body);
    } catch (error: any) {
      setIsResponding(false);
      if (error.name === "AbortError") {
        console.log("[ChatClient] Fetch request aborted by user.");
      } else {
        console.error("[ChatClient] Fetch failed:", error);
      }
    }
  };

  const handleMessages = (stream: ReadableStream<Uint8Array<ArrayBufferLike>>) => {
    let chatItem: IChatItem | null = null;
    let accumulatedContent = "";
    let isStreaming = true;
    let buffer = "";
    let annotations: IAnnotation[] = [];
    let hasReceivedCompletedMessage = false;

    const reader = stream.getReader();
    const decoder = new TextDecoder();

    const readStream = async () => {
      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          console.log("[ChatClient] SSE stream ended by server.");
          break;
        }

        const textChunk = decoder.decode(value, { stream: true });
        buffer += textChunk;
        let boundary = buffer.indexOf("\n");

        while (boundary !== -1) {
          const chunk = buffer.slice(0, boundary).trim();
          buffer = buffer.slice(boundary + 1);

          if (chunk.startsWith("data: ")) {
            const jsonStr = chunk.slice(6);
            let data;
            try {
              data = JSON.parse(jsonStr);
            } catch (err) {
              console.error("[ChatClient] Failed to parse JSON:", jsonStr, err);
              boundary = buffer.indexOf("\n");
              continue;
            }

            if (data.type === "stream_end") {
              setIsResponding(false);
              break;
            } else if (data.type === "thread_run") {
              console.log("[ChatClient] Run status info:", data.content);
            } else {
              if (!chatItem) {
                chatItem = createAssistantMessageDiv();
              }

              if (data.type === "completed_message") {
                if (hasReceivedCompletedMessage) {
                  chatItem = createAssistantMessageDiv();
                  accumulatedContent = data.content;
                  annotations = data.annotations || [];
                } else {
                  clearAssistantMessage(chatItem);
                  accumulatedContent = data.content;
                  annotations = data.annotations || [];
                  hasReceivedCompletedMessage = true;
                }
                isStreaming = false;
                setIsResponding(false);
              } else {
                if (hasReceivedCompletedMessage) {
                  chatItem = createAssistantMessageDiv();
                  annotations = [];
                  accumulatedContent = "";
                  hasReceivedCompletedMessage = false;
                }
                accumulatedContent += data.content;
                isStreaming = true;
              }

              appendAssistantMessage(chatItem, accumulatedContent, isStreaming, annotations);
            }
          }

          boundary = buffer.indexOf("\n");
        }
      }
    };

    readStream().catch((error) => {
      console.error("[ChatClient] Stream reading failed:", error);
    });
  };

  const createAssistantMessageDiv: () => IChatItem = () => {
    const item = {
      id: crypto.randomUUID(),
      content: "",
      isAnswer: true,
      more: { time: new Date().toISOString() },
    };
    setMessageList((prev) => [...prev, item]);
    return item;
  };

  const appendAssistantMessage = (
    chatItem: IChatItem,
    accumulatedContent: string,
    isStreaming: boolean,
    annotations?: IAnnotation[]
  ) => {
    try {
      const preprocessedContent = preprocessContent(accumulatedContent, annotations);
      chatItem.content = preprocessedContent;
      chatItem.annotations = annotations ?? [];
      setMessageList((prev) => [...prev.slice(0, -1), { ...chatItem }]);

      if (!isStreaming) {
        requestAnimationFrame(() => {
          const lastChild = document.getElementById(`msg-${chatItem.id}`);
          if (lastChild) {
            lastChild.scrollIntoView({ behavior: "smooth", block: "end" });
          }
        });
      }
    } catch (error) {
      console.error("Error in appendAssistantMessage:", error);
    }
  };

  const clearAssistantMessage = (chatItem: IChatItem) => {
    if (chatItem) {
      chatItem.content = "";
    }
  };

  const menuItems = [
    {
      key: "settings",
      children: "Settings",
      onClick: () => { setIsSettingsPanelOpen(true); },
    },
    {
      key: "terms",
      children: (
        <a
          className={styles.externalLink}
          href="https://aka.ms/aistudio/terms"
          target="_blank"
          rel="noopener noreferrer"
        >
          Terms of Use
        </a>
      ),
    },
    {
      key: "privacy",
      children: (
        <a
          className={styles.externalLink}
          href="https://go.microsoft.com/fwlink/?linkid=521839"
          target="_blank"
          rel="noopener noreferrer"
        >
          Privacy
        </a>
      ),
    },
    {
      key: "feedback",
      children: "Send Feedback",
      onClick: () => { alert("Thank you for your feedback!"); },
    },
  ];

  const chatContext = useMemo(
    () => ({ messageList, isResponding, onSend }),
    [messageList, isResponding]
  );

  const isEmpty = (messageList?.length ?? 0) === 0;

  return (
    <div className={styles.container}>
      <div className={styles.wavesContainer}>
        <Waves paused={!isEmpty} />
      </div>

      {/* ── Top bar ── */}
      <div className={styles.topBar}>
        <div className={styles.leftSection}>
          {agentDetails.name ? (
            <div className={styles.agentIconContainer}>
              <AgentIcon
                alt=""
                iconClassName={styles.agentIcon}
                iconName={agentDetails.metadata?.logo}
              />
              <Body1 as="h1" className={styles.agentName}>
                {displayName}
              </Body1>
            </div>
          ) : (
            <div className={styles.agentIconContainer}>
              <div className={clsx(styles.agentIcon, styles.newAgent)} />
              <Body1 as="h1" className={clsx(styles.agentName, styles.newAgent)}>
                Agent Name
              </Body1>
            </div>
          )}
        </div>

        <div className={styles.rightSection}>
          {/* Contact and About us — same appearance as New Chat */}
          <Button
            appearance="subtle"
            onClick={() => { /* TODO: navigate to contact page */ }}
          >
            Contact
          </Button>
          <Button
            appearance="subtle"
            onClick={() => { /* TODO: navigate to about page */ }}
          >
            About us
          </Button>

          <Button
            appearance="subtle"
            icon={<ChatRegular aria-hidden={true} />}
            onClick={newThread}
          >
            New Chat
          </Button>
          <MenuButton
            menuButtonText=""
            menuItems={menuItems}
            menuButtonProps={{
              appearance: "subtle",
              icon: <MoreHorizontalRegular />,
              "aria-label": "Settings",
            }}
          />
        </div>
      </div>

      {/* ── Main content ── */}
      <div className={styles.content}>
        <div className={styles.chatbot}>
          {isLoadingChatHistory ? (
            <Spinner label={"Loading chat history..."} />
          ) : (
            <>
              {isEmpty && (
                <div className={styles.emptyChatContainer}>
                  <AgentIcon
                    alt=""
                    iconClassName={styles.emptyStateAgentIcon}
                    iconName={agentDetails.metadata?.logo}
                  />
                  {/* Show cleaned name only — no description, no SLIIT */}
                  <Caption1 className={styles.agentName}>
                    {displayName}
                  </Caption1>
                  <Title3>How can I help you today?</Title3>
                </div>
              )}
              <AgentPreviewChatBot
                agentName={displayName}
                agentLogo={agentDetails.metadata?.logo}
                chatContext={chatContext}
              />
            </>
          )}
        </div>

        {agentDetails.agentPlaygroundUrl && agentDetails.agentPlaygroundUrl.length > 0 && (
          <BuiltWithBadge
            className={styles.builtWithBadge}
            agentPlaygroundUrl={agentDetails.agentPlaygroundUrl}
          />
        )}
      </div>

      <SettingsPanel
        isOpen={isSettingsPanelOpen}
        onOpenChange={handleSettingsPanelOpenChange}
      />
    </div>
  );
}