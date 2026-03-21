/**
 * acp-relay-client — Node.js SDK for the Agent Communication Protocol
 *
 * @version 0.9.0-dev
 * @license Apache-2.0
 *
 * @example
 * const { RelayClient } = require('acp-relay-client');
 * const client = new RelayClient('http://localhost:7901');
 * const resp = await client.send('Hello, Agent!');
 */

'use strict';

const { RelayClient, httpGet, httpPost, sseStream } = require('./relay_client');

module.exports = {
  RelayClient,
  // Low-level utilities (for power users / custom integrations)
  httpGet,
  httpPost,
  sseStream,
};
