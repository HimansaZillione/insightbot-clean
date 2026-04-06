import { ReactNode, useState, useMemo, useEffect } from "react";
import {
  Body1,
  Button,  
  Spinner,
 
} from "@fluentui/react-components";
import { ChatRegular, MoreHorizontalRegular } from "@fluentui/react-icons";
import clsx from "clsx";

import { AgentIcon } from "./AgentIcon";
import { SettingsPanel } from "../core/SettingsPanel";
import { AgentPreviewChatBot } from "./AgentPreviewChatBot";
import { MenuButton } from "../core/MenuButton/MenuButton";
import { IChatItem, IGeneratedImage } from "./chatbot/types";
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
}

const preprocessContent = (
  content: string,
  annotations?: IAnnotation[]
): string => {
  if (!annotations || annotations.length === 0) {
    return content;
  }

  // Process annotations in descending order index, ascending label, remove duplicates
  let processedContent = content;
  annotations
    .slice()
    .sort((a, b) => {
      // Primary sort: descending index
      if (b.index !== a.index) {
        return b.index - a.index;
      }
      // Secondary sort: descending label (as tiebreaker)
      return b.label.localeCompare(a.label);
    })
    .filter((annotation, index, self) => 
      index === self.findIndex(a => a.label === annotation.label && a.index === annotation.index))
    .forEach((annotation) => {
      // Only process if the index is valid and within bounds
      if (annotation.index >= 0 && annotation.index <= processedContent.length) {
        // If there's a label, show it (wrapped in brackets), inserting after the index
        processedContent =
          processedContent.slice(0, annotation.index + 1) +
          ` [${annotation.label}]` +
          processedContent.slice(annotation.index + 1);
      }
    });
  return processedContent;
};

const formatTimestampToLocalTime = (timestampStr: string): string => {
  // Convert timestamp string to local timezone with specific format
  let localTime = new Date().toLocaleString();
  if (timestampStr) {
    try {
      // Parse timestamp (assuming it's a Unix timestamp in seconds as string, could be float)
      const timestamp = parseFloat(timestampStr);
      if (!isNaN(timestamp)) {
        const date = new Date(timestamp * 1000); // Convert to milliseconds
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

  const loadChatHistory = async () => {
    try {
      const response = await fetch("/chat/history", {
        method: "GET",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",
      });

      if (response.ok) {
        const json_response: Array<{
          role: string;
          content: string;
          created_at: string;
          annotations?: IAnnotation[];
          images?: IGeneratedImage[]; // ← Handle images from history
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
              annotations: entry.annotations,
              images: entry.images || [], // ← Save images from history
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
      const postData = { message: message };

      setIsResponding(true);
      const response = await fetch("/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(postData),
        credentials: "include",
      });

      //console.log("[ChatClient] Response status:", response.status, response.statusText);

      if (!response.ok) {
        console.error("[ChatClient] Response not OK:", response.status, response.statusText);
        return;
      }

      if (!response.body) {
        throw new Error("ReadableStream not supported or response.body is null");
      }

      //console.log("[ChatClient] Starting to handle streaming response...");
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

  // ─── ORIGINAL handleMessages — restored exactly ───────────────────────────
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
        console.log("[ChatClient] Raw chunk from stream:", textChunk);

        buffer += textChunk;
        let boundary = buffer.indexOf("\n");

        while (boundary !== -1) {
          const chunk = buffer.slice(0, boundary).trim();
          buffer = buffer.slice(boundary + 1);

          console.log("[ChatClient] SSE line:", chunk);

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

            console.log("[ChatClient] Parsed SSE event:", data);

            if (data.type === "stream_end") {
              console.log("[ChatClient] Stream end marker received.");
              setIsResponding(false);
              break;
            } else if (data.type === "thread_run") {
              console.log("[ChatClient] Run status info:", data.content);
            } else {
              if (!chatItem) {
                chatItem = createAssistantMessageDiv();
              }

              if (data.type === "completed_message") {
                // ═══════════════════════════════════════════════════════════
                // COMPLETED MESSAGE - SAVE IMAGES HERE
                // ═══════════════════════════════════════════════════════════
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

                // ═══════════════════════════════════════════════════════════
                // CRITICAL: Save BOTH annotations AND images
                // ═══════════════════════════════════════════════════════════
                if (chatItem) {
                  chatItem.annotations = annotations;
                  chatItem.images = data.images || []; // ← THIS IS CRITICAL

                  if (chatItem.images && chatItem.images.length > 0) {
                    // image debug logging omitted
                  }
                }

                isStreaming = false;
                setIsResponding(false);

                // Pass images to appendAssistantMessage
                appendAssistantMessage(
                  chatItem,
                  accumulatedContent,
                  isStreaming,
                  annotations,
                  data.images || [] // ← PASS IMAGES HERE
                );
              } else {
                // Streaming content
                if (hasReceivedCompletedMessage) {
                  chatItem = createAssistantMessageDiv();
                  annotations = [];
                  accumulatedContent = "";
                  hasReceivedCompletedMessage = false;
                }

                accumulatedContent += data.content;
                isStreaming = true;

                appendAssistantMessage(
                  chatItem,
                  accumulatedContent,
                  isStreaming,
                  annotations,
                  [] // No images during streaming
                );
              }
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
  // ─────────────────────────────────────────────────────────────────────────

  const createAssistantMessageDiv: () => IChatItem = () => {
    var item = {
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
    annotations?: IAnnotation[],
    images?: IGeneratedImage[] // ← MUST HAVE THIS PARAMETER
  ) => {
    try {
      const preprocessedContent = preprocessContent(accumulatedContent, annotations);
      let htmlContent = preprocessedContent;

      if (!chatItem) {
        throw new Error("Message content div not found in the template.");
      }

      // ═══════════════════════════════════════════════════════════
      // CRITICAL: Save content, annotations, AND images
      // ═══════════════════════════════════════════════════════════
      chatItem.content = htmlContent;
      chatItem.annotations = annotations || [];
      chatItem.images = images || []; // ← THIS IS CRITICAL

      // Update the message list
      setMessageList((prev) => {
        return [...prev.slice(0, -1), { ...chatItem }];
      });

      // Scroll to bottom if not streaming
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
      onClick: () => {
        setIsSettingsPanelOpen(true);
      },
    },
    {
      key: "Need Help?",
      children: (
        <a
          className={styles.externalLink}
          href="https://zillione-prod.powerappsportals.com/"
          target="_blank"
          rel="noopener noreferrer"
        >
          Need Help?
        </a>
      ),
    },
  ];

  const chatContext = useMemo(
    () => ({
      messageList,
      isResponding,
      onSend,
    }),
    [messageList, isResponding]
  );

  const isEmpty = (messageList?.length ?? 0) === 0;

  return (
    <div className={styles.container}>
      {/* Animated wave background — paused when chat is active */}
      <div className={styles.wavesContainer}>
        <Waves paused={!isEmpty} />
      </div>

      {/* ── Top bar ── */}
      <div className={styles.topBar}>
        {/* Left: SLIIT logo + live badge + agent name */}
        <div className={styles.leftSection}>
          <div className={styles.agentIconContainer}>
            {/* SLIIT crest */}
            <img
              src="/static/assets/template-images/SLIIT-UNI-LOGO.png"
              alt="SLIIT"
              style={{
                height: 36,
                width: "auto",
                display: "block",
                filter: "drop-shadow(0 0 8px rgba(0,0,0,0.30))",
              }}
              onError={(e) => {
                (e.currentTarget as HTMLImageElement).style.display = "none";
              }}
            />
            {agentDetails.name ? (
              <Body1 as="h1" className={styles.agentName}>
                {agentDetails.name}
              </Body1>
            ) : (
              <Body1
                as="h1"
                className={clsx(styles.agentName, styles.newAgent)}
              >
                BOT-SLIIT
              </Body1>
            )}
          </div>

          {/* Live pulse badge */}
          <div className={styles.liveBadge}>
            <div className={styles.livePulse} />
            <span>live · BOT-SLIIT</span>
          </div>
        </div>

        {/* Right: nav chips + new chat + menu */}
        <div className={styles.rightSection}>
          <button
            className={styles.navChip}
            type="button"
            onClick={() => window.open("https://sliit.lk/contact", "_blank")}
          >
            Contact
          </button>
          <button
            className={styles.navChip}
            type="button"
            onClick={() => window.open("https://sliit.lk", "_blank")}
          >
            About&nbsp;us
          </button>
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

                  <h1
                    style={{
                      margin: "0 0 6px",
                      fontFamily: "'Albert Sans', 'Space Grotesk', system-ui, sans-serif",
                      fontWeight: 800,
                      fontSize: "clamp(20px, 3vw, 30px)",
                      letterSpacing: "0.05em",
                      textTransform: "uppercase",
                      color: "#d6e0ff",
                      lineHeight: 1.15,
                      textAlign: "center",
                    }}
                  >
                    Academic Copilot for SLIIT
                  </h1>

                  <p
                    style={{
                      margin: 0,
                      fontSize: 13,
                      color: "rgba(255,255,255,0.50)",
                      maxWidth: 440,
                      lineHeight: 1.6,
                      textAlign: "center",
                    }}
                  >
                    Information provided for reference only. Verify decisions
                    through the Academic Affairs Division (AA).
                  </p>

                  <div
                    style={{
                      marginTop: 10,
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 7,
                      padding: "6px 13px",
                      borderRadius: 999,
                      background: "rgba(255,255,255,0.03)",
                      border: "1px solid rgba(255,179,71,0.18)",
                      fontSize: 11,
                      fontFamily: "'JetBrains Mono', monospace",
                      color: "rgba(255,217,133,0.70)",
                      letterSpacing: "0.05em",
                      textTransform: "uppercase",
                    }}
                  >
                    All interactions are logged for policy compliance
                  </div>
                </div>
              )}

              <AgentPreviewChatBot
                agentName={agentDetails.name}
                agentLogo={agentDetails.metadata?.logo}
                chatContext={chatContext}
              />
            </>
          )}
        </div>

        {agentDetails.agentPlaygroundUrl && agentDetails.agentPlaygroundUrl.length > 0 ? (
          <BuiltWithBadge
            className={styles.builtWithBadge}
            agentPlaygroundUrl={agentDetails.agentPlaygroundUrl}
          />
        ) : (
          <></>
        )}
      </div>

      <SettingsPanel
        isOpen={isSettingsPanelOpen}
        onOpenChange={handleSettingsPanelOpenChange}
      />
    </div>
  );
}