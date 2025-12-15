# AWS Zendesk Assistant - Requirements Document

## Introduction

WebSocket 기반 실시간 통신을 통해 Zendesk 환경에서 AWS 보안 분석 도구를 제공하는 챗봇 시스템을 개발합니다. 기존 reference_slack_bot.py의 모든 AWS 분석 기능을 100% 재사용하되, Slack API 대신 WebSocket 통신과 LangGraph Agent 오케스트레이션으로 전환합니다.

## Glossary

- **WebSocket_Server**: Zendesk 앱과 실시간 양방향 통신을 담당하는 서버
- **LangGraph_Agent**: AWS 작업을 오케스트레이션하는 상태 머신 기반 에이전트 (Flask 라우팅 대체)
- **Q_CLI**: 사용자 질문 분석 및 AWS 작업 실행의 핵심 LLM 엔진 (모든 AWS 분석의 중심)
- **Service_Screener**: Python 스크립트 직접 실행 후 Q CLI로 결과 분석하는 유일한 예외 케이스
- **Cross_Account_Auth**: Parameter Store + 2단계 STS assume role 인증 (User 방식 → Role 방식 폴백)
- **Raw_Data_Collection**: boto3로 AWS 서비스별 Raw 데이터 수집 후 Q CLI 분석용 JSON 생성
- **HTML_Report_Generation**: 템플릿 기반 완전한 HTML 보고서 생성 및 웹 서빙
- **MCP_Integration**: CloudTrail, CloudWatch, General AWS MCP 서버 활용

## Requirements

### Requirement 1

**User Story:** As a Zendesk agent, I want to analyze AWS security through a chat interface, so that I can provide immediate security insights to customers within the ticket context.

#### Acceptance Criteria

1. WHEN an agent sends an AWS query through WebSocket, THE LangGraph_Agent SHALL analyze question type and route to Q_CLI or Service_Screener
2. WHEN processing begins, THE WebSocket_Server SHALL send real-time progress updates to the Zendesk client
3. WHEN Q_CLI analysis completes, THE system SHALL return formatted results with downloadable HTML reports
4. WHERE account ID is detected in query, THE system SHALL use Cross_Account_Auth for multi-account access
5. WHEN errors occur, THE system SHALL provide clear error messages and recovery suggestions with context

### Requirement 2

**User Story:** As a security analyst, I want to execute Service Screener scans on AWS accounts, so that I can identify security vulnerabilities and compliance issues.

#### Acceptance Criteria

1. WHEN Service Screener keywords are detected, THE system SHALL authenticate using Cross_Account_Auth
2. WHEN scanning begins, THE system SHALL execute /root/service-screener-v2/Screener.py directly with crossAccounts.json
3. WHILE scanning is in progress, THE system SHALL provide real-time progress updates every 30 seconds
4. WHEN scanning completes, THE system SHALL copy results to /tmp/reports and generate web-accessible URLs
5. WHERE Well-Architected analysis is requested, THE system SHALL run wa-ss-summarizer with Q_CLI integration

### Requirement 3

**User Story:** As a compliance officer, I want to generate monthly security reports, so that I can track security posture and compliance status across AWS accounts.

#### Acceptance Criteria

1. WHEN security report keywords are detected, THE system SHALL use collect_raw_security_data() function with boto3 clients
2. WHEN data collection begins, THE system SHALL gather EC2, S3, RDS, Lambda, IAM, Security Groups, CloudTrail, CloudWatch, Trusted Advisor raw data
3. WHEN raw data collection completes, THE Q_CLI SHALL analyze JSON data and generate structured security insights
4. WHEN Q_CLI analysis completes, THE system SHALL use generate_html_report() with templates/json_report_template.html
5. WHERE Trusted Advisor requires Business/Enterprise plan, THE system SHALL handle unavailable status gracefully

### Requirement 4

**User Story:** As a DevOps engineer, I want to query CloudTrail logs for security events, so that I can investigate suspicious activities and audit user actions.

#### Acceptance Criteria

1. WHEN CloudTrail keywords are detected, THE system SHALL load /root/core_contexts/cloudtrail_mcp.md context
2. WHEN processing CloudTrail queries, THE Q_CLI SHALL use MCP CloudTrail integration with proper context
3. WHEN critical events are analyzed, THE system SHALL focus on DeleteBucket, TerminateInstances, DeleteUser, CreateAccessKey events
4. WHERE UTC+9 time conversion is needed, THE system SHALL handle Korean timezone properly
5. WHEN queries complete, THE system SHALL provide formatted results with event details and security implications

### Requirement 5

**User Story:** As a system administrator, I want to monitor CloudWatch metrics and alarms, so that I can track system performance and respond to alerts.

#### Acceptance Criteria

1. WHEN CloudWatch keywords are detected, THE system SHALL load /root/core_contexts/cloudwatch_mcp.md context
2. WHEN retrieving alarm data, THE system SHALL use describe_alarms() and categorize by StateValue (OK, ALARM, INSUFFICIENT_DATA)
3. WHEN alarm analysis is requested, THE Q_CLI SHALL process raw CloudWatch data with MCP integration
4. WHERE performance monitoring is needed, THE system SHALL provide alarm status summaries and trend analysis
5. WHEN monitoring data is processed, THE system SHALL format results with proper state-based color coding

### Requirement 6

**User Story:** As a security team lead, I want all AWS analysis to use identical logic to our existing Slack bot, so that I can ensure consistency and reliability across platforms.

#### Acceptance Criteria

1. WHEN implementing functions, THE system SHALL reuse get_crossaccount_session(), collect_raw_security_data(), generate_html_report() logic exactly
2. WHEN performing authentication, THE system SHALL use Parameter Store + 2-stage STS assume role with ExternalId fallback
3. WHEN generating reports, THE system SHALL use identical HTML templates and CSS styling from reference implementation
4. WHERE question analysis is needed, THE system SHALL use analyze_question_type() with same keyword matching logic
5. WHEN processing completes, THE system SHALL provide identical data structures, URLs, and file serving capabilities

### Requirement 7

**User Story:** As a platform engineer, I want the system to run efficiently on EC2 with proper resource management, so that I can ensure stable operation and cost control.

#### Acceptance Criteria

1. WHEN the WebSocket_Server starts, THE system SHALL initialize with /tmp/reports directory and processing_questions tracking
2. WHEN multiple concurrent requests are processed, THE system SHALL use threading.Thread with daemon=True for async processing
3. WHEN long-running operations execute, THE system SHALL implement 600s timeout for Service Screener and 900s for WA Summarizer
4. WHERE cleanup is needed, THE system SHALL run cleanup_old_screener_results() to remove files older than 3 days
5. WHEN system health is monitored, THE system SHALL provide /health endpoint and detailed debug logging

### Requirement 8

**User Story:** As a quality assurance engineer, I want comprehensive error handling and logging, so that I can troubleshoot issues and maintain system reliability.

#### Acceptance Criteria

1. WHEN errors occur in AWS operations, THE system SHALL log with [DEBUG], [ERROR] prefixes and flush=True for real-time output
2. WHEN WebSocket connections fail, THE system SHALL implement reconnection logic with exponential backoff
3. WHEN LangGraph_Agent encounters exceptions, THE system SHALL continue processing and remove question_key from tracking set
4. WHERE debugging is needed, THE system SHALL provide detailed traceback.print_exc() and step-by-step operation logging
5. WHEN critical failures happen, THE system SHALL send error messages to WebSocket client and log full context