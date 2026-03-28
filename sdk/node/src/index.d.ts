/**
 * TypeScript type declarations for acp-sdk v2.4.0
 */

export interface AcpPart {
  type: 'text' | 'file' | 'data';
  content?: string;
  url?: string;
  data?: unknown;
  mime_type?: string;
}

export interface AcpMessage {
  type: string;
  message_id?: string;
  server_seq?: number;
  ts?: string;
  from?: string;
  role?: string;
  parts: AcpPart[];
  context_id?: string;
  task_id?: string;
  reply_to?: string;
  sig?: string;
  [key: string]: unknown;
}

export interface AcpPeer {
  peer_id: string;
  name?: string;
  link?: string;
  connected_at?: string;
  [key: string]: unknown;
}

export interface AcpTask {
  task_id: string;
  state: 'submitted' | 'working' | 'completed' | 'failed' | 'input_required' | 'canceled';
  description?: string;
  type?: string;
  result?: unknown;
  error?: string;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface AcpStatus {
  version: string;
  session_id?: string;
  peer_count?: number;
  peers?: AcpPeer[];
  last_active?: string;
  [key: string]: unknown;
}

export interface AcpSkill {
  name: string;
  description?: string;
  category?: string;
  [key: string]: unknown;
}

export declare class Extension {
  uri: string;
  required: boolean;
  params: Record<string, unknown>;
  constructor(uri: string, required?: boolean, params?: Record<string, unknown>);
  toDict(): { uri: string; required: boolean; params: Record<string, unknown> };
  static fromDict(data: { uri?: string; required?: boolean; params?: Record<string, unknown> }): Extension;
  toString(): string;
}

export interface AgentCard {
  name: string;
  version: string;
  link?: string;
  capabilities?: Record<string, boolean>;
  limitations?: string[];
  extensions: Extension[];
  transport_modes?: string[];
  supported_transports?: string[];
  [key: string]: unknown;
}

export interface SseEvent {
  type: string;
  data: string;
  id: string | null;
  retry: number | null;
}

export interface RelayClientOptions {
  timeout?: number;
}

export interface RecvOptions {
  after_id?: string;
}

export interface StreamOptions {
  timeout?: number;
}

export interface WaitForPeerOptions {
  timeout?: number;
  interval?: number;
}

export interface SendAndRecvOptions {
  timeout?: number;
}

export interface TasksOptions {
  /** Filter by task state: submitted | working | completed | failed | input_required | canceled */
  status?: 'submitted' | 'working' | 'completed' | 'failed' | 'input_required' | 'canceled' | string;
  /** Filter by peer agent id */
  peer_id?: string;
  /** ISO-8601 timestamp: return only tasks created after this time */
  created_after?: string;
  /** ISO-8601 timestamp: return only tasks updated after this time */
  updated_after?: string;
  /** Sort order: "asc" | "desc" (default "desc") */
  sort?: 'asc' | 'desc';
  /** Pagination cursor from a previous response */
  cursor?: string;
  /** Maximum number of tasks to return */
  limit?: number;
}

export interface CancelTaskOptions {
  /** If true, throw an Error when the task is in a terminal state (409 ERR_TASK_NOT_CANCELABLE) */
  raiseOnTerminal?: boolean;
}

export interface AcpIdentity {
  did?: string;
  public_key_b64?: string;
  scheme?: string;
  [key: string]: unknown;
}

export declare class RelayClient {
  baseUrl: string;
  timeout: number;

  constructor(baseUrl: string, options?: RelayClientOptions);

  // Status & discovery
  status(): Promise<AcpStatus>;
  agentCard(): Promise<AgentCard>;
  hasExtension(uri: string): Promise<boolean>;
  requiredExtensions(): Promise<Extension[]>;

  // Capability helpers (v1.6+)
  link(): Promise<string>;
  capabilities(): Promise<Record<string, boolean>>;
  identity(): Promise<AcpIdentity>;
  didDocument(): Promise<object>;
  supportedInterfaces(): Promise<string[]>;
  sseSeqEnabled(): Promise<boolean>;

  // Messaging
  send(text: string, extra?: Record<string, unknown>): Promise<{ ok: boolean; message_id: string }>;
  sendParts(parts: AcpPart[], extra?: Record<string, unknown>): Promise<{ ok: boolean; message_id: string }>;
  sendToPeer(peerId: string, text: string, extra?: Record<string, unknown>): Promise<{ ok: boolean; message_id: string }>;
  recv(options?: RecvOptions): Promise<AcpMessage[]>;

  // Peer management
  peers(): Promise<AcpPeer[]>;
  peer(peerId: string): Promise<AcpPeer>;
  discover(): Promise<AcpPeer[]>;

  // SSE streaming
  stream(options?: StreamOptions): AsyncGenerator<SseEvent>;

  // Task management (v1.4+)
  tasks(options?: TasksOptions): Promise<AcpTask[]>;
  createTask(task: { description: string; type?: string; metadata?: unknown }): Promise<AcpTask>;
  updateTask(taskId: string, update: Partial<AcpTask>): Promise<AcpTask>;
  cancelTask(taskId: string, options?: CancelTaskOptions): Promise<AcpTask | { error: string; task_id: string }>;

  // Skill discovery
  querySkills(filter?: { category?: string; name?: string }): Promise<AcpSkill[]>;

  // Convenience
  waitForPeer(options?: WaitForPeerOptions): Promise<AcpStatus>;
  sendAndRecv(text: string, options?: SendAndRecvOptions): Promise<AcpMessage>;
  reply(messageId: string, text: string): Promise<{ ok: boolean; message_id: string }>;
}

export declare function httpGet(url: string, options?: { timeout?: number }): Promise<unknown>;
export declare function httpPost(url: string, body: Record<string, unknown>, options?: { timeout?: number }): Promise<unknown>;
export declare function sseStream(url: string, options?: StreamOptions): AsyncGenerator<SseEvent>;
