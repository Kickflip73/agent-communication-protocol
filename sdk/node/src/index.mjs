/**
 * acp-relay-client — ESM entry point
 * Agent Communication Protocol (ACP) Node.js SDK v2.4.0
 *
 * @example
 * import { RelayClient } from 'acp-relay-client';
 * const client = new RelayClient('http://localhost:7901');
 * const resp = await client.send('Hello, Agent!');
 */

// Re-export from CJS module via createRequire (Node >=12)
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

const { RelayClient, Extension, httpGet, httpPost, sseStream } = require('./relay_client.js');

export { RelayClient, Extension, httpGet, httpPost, sseStream };
export default RelayClient;
