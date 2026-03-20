/**
 * TypeScript type declarations for acp-sdk v0.8.0
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

export declare class RelayClient {
  baseUrl: string;
  timeout: number;

  constructor(baseUrl: string, options?: RelayClientOptions);

  // Status & discovery
  status(): Promise<AcpStatus>;
  agentCard(): Promise<unknown>;

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

  // Task management
  tasks(): Promise<AcpTask[]>;
  createTask(task: { description: string; type?: string; metadata?: unknown }): Promise<AcpTask>;
  updateTask(taskId: string, update: Partial<AcpTask>): Promise<AcpTask>;
  cancelTask(taskId: string): Promise<AcpTask>;

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
