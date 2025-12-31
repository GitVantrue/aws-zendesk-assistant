/**
 * AWS AgentCore Proxy Server
 * Handles AWS API calls from Zendesk app to avoid CORS issues
 */

const express = require('express');
const cors = require('cors');
const { BedrockAgentRuntimeClient, InvokeAgentCommand } = require('@aws-sdk/client-bedrock-agent-runtime');
const dotenv = require('dotenv');

dotenv.config();

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(cors({
  origin: process.env.ALLOWED_ORIGINS?.split(',') || '*',
  methods: ['GET', 'POST'],
  allowedHeaders: ['Content-Type', 'Authorization', 'X-Zendesk-Token']
}));
app.use(express.json());

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({ status: 'healthy', timestamp: new Date().toISOString() });
});

// AgentCore invocation endpoint
app.post('/api/agent/invoke', async (req, res) => {
  try {
    const { inputText, sessionId, agentId, agentAliasId } = req.body;

    // Validate required fields
    if (!inputText || !sessionId || !agentId || !agentAliasId) {
      return res.status(400).json({
        error: 'Missing required fields',
        required: ['inputText', 'sessionId', 'agentId', 'agentAliasId']
      });
    }

    // Initialize Bedrock Agent Runtime client
    const client = new BedrockAgentRuntimeClient({
      region: process.env.AWS_REGION || 'us-east-1',
      credentials: {
        accessKeyId: process.env.AWS_ACCESS_KEY_ID,
        secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY
      }
    });

    // Invoke the agent
    const command = new InvokeAgentCommand({
      agentId: agentId,
      agentAliasId: agentAliasId,
      sessionId: sessionId,
      inputText: inputText,
      enableTrace: false
    });

    const response = await client.send(command);

    // Parse streaming response
    let completion = '';
    
    if (response.completion) {
      for await (const chunk of response.completion) {
        if (chunk.chunk?.bytes) {
          const text = new TextDecoder().decode(chunk.chunk.bytes);
          completion += text;
        }
      }
    }

    res.json({
      success: true,
      completion: completion,
      sessionId: sessionId
    });

  } catch (error) {
    console.error('AgentCore invocation error:', error);
    
    res.status(500).json({
      error: 'Failed to invoke agent',
      message: error.message,
      code: error.code || 'UNKNOWN_ERROR'
    });
  }
});

// Start session endpoint
app.post('/api/agent/session', (req, res) => {
  const sessionId = `session-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  res.json({ sessionId });
});

// Error handling middleware
app.use((err, req, res, next) => {
  console.error('Unhandled error:', err);
  res.status(500).json({
    error: 'Internal server error',
    message: err.message
  });
});

// Start server
app.listen(PORT, () => {
  console.log(`🚀 AgentCore Proxy Server running on port ${PORT}`);
  console.log(`📍 Health check: http://localhost:${PORT}/health`);
});

module.exports = app;

