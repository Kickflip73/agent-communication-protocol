/**
 * acp-sdk — Node.js SDK for the Agent Communication Protocol
 *
 * @version 0.8.0
 * @license MIT
 *
 * @example
 * const { RelayClient } = require('acp-sdk');
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
