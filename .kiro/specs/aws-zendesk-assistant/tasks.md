# Implementation Plan

- [x] 1. Set up project structure and core dependencies




  - Create directory structure for WebSocket server, LangGraph agent, and AWS tools
  - Install dependencies: websockets, langgraph, boto3, requests, hypothesis
  - Set up logging configuration with [DEBUG]/[ERROR] prefixes and flush=True
  - _Requirements: 7.1, 8.1_

- [x] 2. Implement WebSocket server foundation



  - [x] 2.1 Create WebSocket server with connection management


    - Implement WebSocketServer class with processing_questions tracking
    - Handle connection lifecycle and message routing
    - _Requirements: 1.1, 7.1_

  - [ ]* 2.2 Write property test for WebSocket message handling
    - **Property 14: System initialization consistency**
    - **Validates: Requirements 7.1, 7.5**

  - [x] 2.3 Implement real-time progress update system


    - Create send_progress_update() and send_result() methods
    - Ensure progress messages are sent at regular intervals
    - _Requirements: 1.2, 2.3_

  - [ ]* 2.4 Write property test for progress updates
    - **Property 2: Real-time progress updates**
    - **Validates: Requirements 1.2, 2.3**

- [x] 3. Create cross-account authentication system



  - [x] 3.1 Implement reference authentication logic reuse


    - Import and wrap get_crossaccount_session() from reference_slack_bot.py
    - Implement extract_account_id() for 12-digit account detection
    - _Requirements: 1.4, 6.1, 6.2_

  - [ ]* 3.2 Write property test for mandatory authentication
    - **Property 3: Mandatory cross-account authentication**
    - **Validates: Requirements 1.4, 2.1, 6.2**

  - [x] 3.3 Implement Parameter Store + 2-stage STS assume role


    - Reuse get_crossaccount_credentials() logic exactly
    - Implement User method → Role method fallback with ExternalId
    - _Requirements: 6.2_

  - [ ]* 3.4 Write property test for authentication flow
    - **Property 3: Mandatory cross-account authentication**
    - **Validates: Requirements 1.4, 2.1, 6.2**

- [x] 4. Build LangGraph agent architecture



  - [x] 4.1 Create AgentState data model


    - Define TypedDict with question, websocket, credentials, results fields
    - Implement state management for workflow tracking
    - _Requirements: 1.1_

  - [x] 4.2 Implement question analysis and routing


    - Reuse analyze_question_type() from reference implementation
    - Create route_question() with keyword matching logic
    - _Requirements: 1.1, 6.4_

  - [ ]* 4.3 Write property test for question routing
    - **Property 1: Question routing consistency**
    - **Validates: Requirements 1.1, 6.4**

  - [x] 4.4 Create LangGraph workflow with mandatory authentication


    - Build StateGraph with analyze_question → cross_account_auth → AWS operations
    - Ensure all AWS operations go through authentication first
    - _Requirements: 1.1, 1.4_

  - [ ]* 4.5 Write property test for workflow execution
    - **Property 11: Concurrent processing with threading**
    - **Validates: Requirements 7.2**

- [ ] 5. Implement Service Screener integration
  - [ ] 5.1 Create Service Screener execution wrapper
    - Reuse run_service_screener() logic from reference implementation
    - Execute /root/service-screener-v2/Screener.py with crossAccounts.json
    - _Requirements: 2.2, 6.1_

  - [ ]* 5.2 Write property test for Service Screener execution
    - **Property 5: Service Screener execution path**
    - **Validates: Requirements 2.2, 2.4**

  - [ ] 5.3 Implement result processing and URL generation
    - Copy results to /tmp/reports directory
    - Generate web-accessible URLs for HTML reports
    - _Requirements: 2.4_

  - [ ] 5.4 Add Well-Architected analysis integration
    - Integrate wa-ss-summarizer execution with Q_CLI
    - Handle Korean language output configuration
    - _Requirements: 2.5_

  - [ ]* 5.5 Write property test for timeout handling
    - **Property 12: Timeout enforcement**
    - **Validates: Requirements 7.3**

- [ ] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Build security report generation system
  - [x] 7.1 Implement raw data collection wrapper


    - Reuse collect_raw_security_data() from reference implementation
    - Collect EC2, S3, RDS, Lambda, IAM, Security Groups, CloudTrail, CloudWatch, Trusted Advisor data
    - _Requirements: 3.1, 3.2, 6.1_

  - [ ]* 7.2 Write property test for data collection completeness
    - **Property 6: Security data collection completeness**
    - **Validates: Requirements 3.2**



  - [ ] 7.3 Implement Q_CLI analysis integration
    - Process collected JSON data through Q_CLI with proper context


    - Generate structured security insights
    - _Requirements: 3.3_

  - [ ] 7.4 Create HTML report generation wrapper
    - Reuse generate_html_report() with templates/json_report_template.html
    - Ensure identical HTML structure and CSS styling
    - _Requirements: 3.4, 6.3_



  - [ ]* 7.5 Write property test for report generation consistency
    - **Property 7: HTML report generation consistency**
    - **Validates: Requirements 3.4, 6.3**

  - [ ] 7.6 Handle Trusted Advisor availability gracefully
    - Implement Business/Enterprise plan requirement handling
    - Continue processing with unavailable status
    - _Requirements: 3.5_

- [ ] 8. Implement CloudTrail query system
  - [ ] 8.1 Create CloudTrail MCP integration
    - Load /root/core_contexts/cloudtrail_mcp.md context
    - Integrate with Q_CLI using MCP CloudTrail server
    - _Requirements: 4.1, 4.2_

  - [ ]* 8.2 Write property test for MCP integration
    - **Property 8: MCP integration with context**
    - **Validates: Requirements 4.1, 4.2, 5.1, 5.3**

  - [ ] 8.3 Implement critical event filtering
    - Focus on DeleteBucket, TerminateInstances, DeleteUser, CreateAccessKey events
    - Process events with security implications analysis
    - _Requirements: 4.3_

  - [ ]* 8.4 Write property test for critical event filtering
    - **Property 9: Critical event filtering**
    - **Validates: Requirements 4.3**

  - [ ] 8.5 Add UTC+9 timezone handling
    - Implement Korean timezone conversion for time-based queries
    - Ensure proper UTC conversion for AWS API calls
    - _Requirements: 4.4_

  - [ ]* 8.6 Write property test for timezone handling
    - **Property 10: Timezone handling accuracy**
    - **Validates: Requirements 4.4**

- [ ] 9. Build CloudWatch monitoring system
  - [ ] 9.1 Create CloudWatch MCP integration
    - Load /root/core_contexts/cloudwatch_mcp.md context
    - Use describe_alarms() with StateValue categorization
    - _Requirements: 5.1, 5.2_

  - [ ] 9.2 Implement alarm analysis and formatting
    - Process raw CloudWatch data with MCP integration
    - Provide alarm status summaries with state-based color coding
    - _Requirements: 5.3, 5.4, 5.5_

- [ ] 10. Add general AWS query handling
  - [ ] 10.1 Implement general AWS context loading
    - Load /root/core_contexts/general_aws.md for non-specific queries
    - Route through Q_CLI with appropriate context
    - _Requirements: 1.1_

  - [ ]* 10.2 Write property test for reference function reuse
    - **Property 4: Reference function reuse**
    - **Validates: Requirements 6.1, 6.3, 6.5**

- [ ] 11. Implement error handling and recovery
  - [ ] 11.1 Create exception hierarchy
    - Define AWSZendeskError, AuthenticationError, ServiceScreenerError, etc.
    - Implement error recovery strategies for each type
    - _Requirements: 8.1, 8.3_

  - [ ]* 11.2 Write property test for error handling
    - **Property 13: Error handling and cleanup**
    - **Validates: Requirements 8.1, 8.3, 8.5**

  - [ ] 11.3 Add WebSocket reconnection logic
    - Implement exponential backoff for connection failures
    - Ensure graceful error recovery and client notification
    - _Requirements: 8.2_

  - [ ] 11.4 Implement detailed logging and debugging
    - Add traceback.print_exc() for detailed error information
    - Provide step-by-step operation logging
    - _Requirements: 8.4_

- [ ] 12. Add system maintenance and monitoring
  - [ ] 12.1 Implement file cleanup system
    - Reuse cleanup_old_screener_results() to remove files older than 3 days
    - Schedule regular maintenance operations
    - _Requirements: 7.4_

  - [ ]* 12.2 Write property test for file cleanup
    - **Property 15: File cleanup maintenance**
    - **Validates: Requirements 7.4**

  - [ ] 12.3 Create health monitoring endpoint
    - Implement /health endpoint for system status
    - Provide detailed system metrics and status information
    - _Requirements: 7.5_

- [ ] 13. Final integration and testing
  - [ ] 13.1 Integrate all components into main application
    - Wire WebSocket server with LangGraph agent
    - Ensure all reference functions are properly integrated
    - _Requirements: 6.1, 6.5_

  - [ ] 13.2 Add concurrent request handling
    - Implement threading.Thread with daemon=True for async processing
    - Ensure proper resource management for multiple requests
    - _Requirements: 7.2_

  - [ ]* 13.3 Write integration tests for end-to-end workflows
    - Test complete Service Screener workflow
    - Test security report generation workflow
    - Test CloudTrail and CloudWatch query workflows

- [ ] 14. Final Checkpoint - Make sure all tests are passing
  - Ensure all tests pass, ask the user if questions arise.