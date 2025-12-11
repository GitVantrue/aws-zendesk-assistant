# AWS 월간 보안 점검 보고서 생성 가이드

## 적용 범위
이 컨텍스트는 다음 키워드가 포함된 질문에 적용됩니다:
- 보고서, 분석, 종합, 리포트, 요약, 감사보고서, 보안보고서, 월간점검, 정기점검

## 🔄 보고서 생성 프로세스

### 1단계: Raw 데이터 수집 (Python boto3)
Python 코드가 AWS API를 직접 호출하여 raw 데이터를 수집하고 `/tmp/reports/raw_security_data_{account_id}_{timestamp}.json` 파일로 저장합니다.

### 2단계: HTML 보고서 생성 (Python)
Python 코드가 Raw JSON 데이터를 읽어서 HTML 템플릿에 맞게 변환하여 월간 보안 점검 보고서를 생성합니다.

## 📊 월간 보안 점검 보고서 주요 항목

### 🖥️ EC2 인스턴스 점검 항목
1. **이름** (Name 태그)
2. **인스턴스 ID**
3. **인스턴스 타입** (t2.micro, m5.large 등)
4. **상태** (running/stopped)
5. **퍼블릭 IP** (있으면 보안 위험 표시)
6. **IMDSv2 강제 여부** (optional이면 ⚠️)
7. **상세 모니터링** (enabled/disabled)
8. **EBS 삭제 방지** (DeleteOnTermination: false 권장)

### 💾 S3 버킷 점검 항목
1. **버킷 이름**
2. **리전**
3. **암호화 여부** (AES256/KMS)
4. **버저닝 활성화** (Enabled/Suspended)
5. **퍼블릭 액세스 차단** (4가지 설정 모두 true 권장)
6. **생성일**

### 🗄️ RDS 인스턴스 점검 항목
1. **DB 식별자**
2. **엔진** (mariadb, postgres 등)
3. **인스턴스 타입**
4. **Multi-AZ 여부** ⚠️ (고가용성 - false면 위험)
5. **암호화 여부**
6. **백업 보관 기간** (권장: 30일, 최소: 7일)
7. **삭제 방지** (DeletionProtection: true 권장)
8. **퍼블릭 액세스 여부** (false 권장)
9. **상태** (available/stopped)

### ⚡ Lambda 함수 점검 항목
1. **함수 이름**
2. **런타임** (python3.x, nodejs 등)
3. **메모리**
4. **타임아웃**
5. **VPC 설정** (VPC 내부 실행 여부)
6. **환경 변수 암호화** (KMS 사용 권장)
7. **실행 역할** (최소 권한 원칙)
8. **마지막 수정일**

### 💿 EBS 볼륨 (암호화 미설정 항목만)
1. **볼륨 ID**
2. **크기**
3. **연결된 인스턴스**
4. **가용 영역**
5. **생성일**

### 🪣 S3 버킷 보안 이슈
1. **버저닝 미설정 버킷**
2. **퍼블릭 액세스 차단 미설정 버킷**
3. **암호화 미설정 버킷** (현재는 모두 암호화됨)

### 🔐 IAM 사용자 점검 항목
1. **사용자명**
2. **MFA 활성화 여부** ⚠️ (미설정 시 Critical)
3. **액세스 키 개수**
4. **액세스 키 생성일** (90일 이상이면 경고)

### 🛡️ 보안 그룹 위험 규칙
1. **보안 그룹 ID**
2. **이름**
3. **VPC**
4. **포트 번호**
5. **프로토콜**
6. **소스** (0.0.0.0/0이면 위험)
7. **위험도** (SSH/RDP는 Critical, 기타는 Medium/High)

### 📊 Trusted Advisor 카테고리별 집계
1. **보안** - error/warning 개수
2. **내결함성** - error/warning 개수
3. **비용 최적화** - warning 개수
4. **성능** - warning 개수

### 📋 CloudTrail 중요 이벤트 (월간)
1. **DeleteBucket** - S3 버킷 삭제 (Critical)
2. **TerminateInstances** - EC2 종료 (Critical)
3. **DeleteDBInstance** - RDS 삭제 (Critical)
4. **CreateAccessKey** - 액세스 키 생성 (High)
5. **PutBucketPolicy** - S3 정책 변경 (High)
6. **AuthorizeSecurityGroupIngress** - 보안 그룹 규칙 추가 (High)

### 🔒 암호화 준수율 (목표: 100%)
1. **EBS 볼륨** - 암호화율
2. **S3 버킷** - 암호화율
3. **RDS 인스턴스** - 암호화율

### ⚠️ 즉시 조치 필요 항목 (Critical)
1. MFA 미설정 IAM 사용자
2. 0.0.0.0/0으로 SSH(22)/RDP(3389) 오픈된 보안 그룹
3. 암호화 미설정 리소스 (EBS/S3/RDS)
4. Multi-AZ 미설정 RDS (고가용성 부족)
5. 90일 이상 된 IAM 액세스 키

## 📝 Raw JSON 구조 (실제 수집 데이터)

```json
{
  "metadata": {
    "account_id": "701997720595",
    "report_date": "2025-11-27",
    "period_start": "2025-08-01",
    "period_end": "2025-08-31",
    "region": "ap-northeast-2"
  },
  "resources": {
    "ec2": {
      "summary": {"total": 16, "running": 16, "stopped": 0},
      "instances": [
        {
          "InstanceId": "i-xxx",
          "InstanceType": "t2.micro",
          "State": {"Name": "running"},
          "PublicIpAddress": "1.2.3.4",
          "Tags": [{"Key": "Name", "Value": "MyServer"}],
          "MetadataOptions": {"HttpTokens": "optional"},
          "Monitoring": {"State": "disabled"},
          "BlockDeviceMappings": [{"Ebs": {"DeleteOnTermination": false}}]
        }
      ]
    },
    "s3": {
      "summary": {"total": 20, "encrypted": 20, "public": 14},
      "buckets": [
        {
          "Name": "my-bucket",
          "Location": "ap-northeast-2",
          "Encryption": {"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]},
          "Versioning": {"Status": "Enabled"},
          "PublicAccessBlock": {"BlockPublicAcls": true, "IgnorePublicAcls": true}
        }
      ]
    },
    "rds": {
      "summary": {"total": 2},
      "instances": [
        {
          "DBInstanceIdentifier": "my-db",
          "Engine": "mariadb",
          "DBInstanceClass": "db.t3.medium",
          "MultiAZ": false,
          "StorageEncrypted": true,
          "BackupRetentionPeriod": 7,
          "DeletionProtection": true,
          "PubliclyAccessible": false,
          "DBInstanceStatus": "available"
        }
      ]
    }
  },
  "iam_security": {
    "users": {
      "total": 8,
      "mfa_enabled": 4,
      "details": [
        {
          "username": "admin-user",
          "mfa": false,
          "access_keys": [{"AccessKeyId": "AKIA...", "CreateDate": "2019-12-26T04:28:23+00:00"}]
        }
      ]
    },
    "issues": [
      {"severity": "critical", "type": "no_mfa", "user": "admin-user", "description": "MFA 미설정"}
    ]
  },
  "security_groups": {
    "total": 33,
    "risky": 66,
    "details": [
      {
        "id": "sg-xxx",
        "name": "web-sg",
        "vpc": "vpc-xxx",
        "risky_rules": [
          {"port": 22, "protocol": "tcp", "source": "0.0.0.0/0", "risk_level": "high"}
        ]
      }
    ]
  },
  "encryption": {
    "ebs": {"total": 17, "encrypted": 1, "unencrypted_volumes": ["vol-xxx"]},
    "s3": {"total": 20, "encrypted": 20, "encrypted_rate": 1.0},
    "rds": {"total": 2, "encrypted": 0, "encrypted_rate": 0.0}
  },
  "trusted_advisor": {
    "available": true,
    "checks": [
      {
        "category": "보안",
        "name": "Security Groups - Specific Ports Unrestricted",
        "status": "error",
        "flagged_resources": 43
      }
    ]
  },
  "cloudtrail_events": {
    "summary": {"period_days": 31, "total_critical_events": 0, "monitored_event_types": 10},
    "critical_events": {
      "DeleteBucket": {"severity": "critical", "category": "data_loss", "count": 0},
      "TerminateInstances": {"severity": "critical", "category": "service_disruption", "count": 0}
    }
  },
  "cloudwatch": {
    "summary": {"total": 6, "in_alarm": 1, "ok": 4, "insufficient_data": 1},
    "alarms": [...]
  }
}
```

## 🎯 HTML 템플릿 변수 (Python 코드가 생성)

```json
{
  "metadata": { ... },
  "resources": { ... },
  "iam_security": {
    "users": { ... },
    "issues": [
      {
        "severity": "critical",
        "type": "no_mfa",
        "user": "admin-user",
        "description": "MFA 미설정",
        "risk_analysis": "MFA가 없으면 비밀번호만으로 계정 탈취 가능. 관리자 권한이므로 전체 인프라 위험",
        "remediation": "1. IAM 콘솔 → 사용자 선택 2. 보안 자격 증명 탭 3. MFA 디바이스 할당 4. 가상 MFA 디바이스 선택 5. QR 코드 스캔",
        "priority": "즉시 조치 필요"
      }
    ]
  },
  "security_groups": {
    "total": 10,
    "risky": 3,
    "details": [
      {
        "id": "sg-12345",
        "name": "web-server-sg",
        "risky_rules": [
          {
            "port": 22,
            "source": "0.0.0.0/0",
            "risk_level": "high",
            "attack_vector": "SSH 무차별 대입 공격, 사전 공격 가능",
            "impact": "서버 침투 시 데이터 유출, 랜섬웨어 감염 가능",
            "remediation": "소스를 회사 IP 대역(예: 1.2.3.0/24)으로 제한하거나 VPN을 통해서만 접근하도록 설정"
          }
        ]
      }
    ]
  },
  "trusted_advisor": {
    "available": true,
    "checks": [
      {
        "category": "보안",
        "name": "Security Group - Specific Ports Unrestricted",
        "status": "error",
        "flagged_resources": 5,
        "severity": "critical",
        "risk_description": "SSH(22), RDP(3389) 등 관리 포트가 전체 인터넷에 노출되어 무차별 대입 공격에 취약합니다",
        "business_impact": "서버 침투 시 데이터 유출, 서비스 중단, 컴플라이언스 위반 가능",
        "remediation_steps": [
          "1. EC2 콘솔 → 보안 그룹 메뉴",
          "2. 문제가 있는 보안 그룹 선택",
          "3. 인바운드 규칙 편집",
          "4. 소스를 특정 IP 대역으로 제한 (예: 회사 IP)",
          "5. 또는 AWS Systems Manager Session Manager 사용 권장"
        ],
        "priority": "즉시 조치"
      }
    ]
  },
  "cloudtrail_events": {
    "period_days": 30,
    "total_events": 1000,
    "critical_events": [
      {
        "event_name": "DeleteBucket",
        "user": "admin-user",
        "time": "2025-10-15 14:30:00",
        "source_ip": "1.2.3.4",
        "threat_level": "high",
        "analysis": "중요 데이터가 포함된 S3 버킷이 삭제되었습니다. 데이터 손실 및 서비스 중단 가능성",
        "recommended_action": "1. 버킷 버저닝 활성화로 실수 방지 2. MFA Delete 설정 3. CloudTrail 알람 설정하여 실시간 모니터링"
      }
    ]
  },
  "recommendations": [
    {
      "priority": "즉시 조치 (24시간 내)",
      "category": "보안",
      "title": "모든 IAM 사용자에 MFA 설정",
      "description": "3명의 IAM 사용자가 MFA를 설정하지 않았습니다",
      "affected_resources": ["admin-user", "dev-user", "ops-user"],
      "action_steps": ["IAM 콘솔에서 각 사용자 선택", "MFA 디바이스 할당", "가상 MFA 앱 사용 권장"],
      "expected_outcome": "계정 탈취 위험 90% 감소"
    }
  ]
}
```

## 🚀 보고서 생성 프로세스

### Python 코드 역할:
1. Raw JSON 데이터 수집 (Boto3 API 호출)
2. HTML 템플릿 변수 생성:
   - EC2 테이블 행 생성 (`ec2_rows`)
   - S3 테이블 행 생성 (`s3_rows`)
   - RDS 테이블 행 생성 (`rds_rows`)
   - IAM 사용자 행 생성 (`iam_users_rows`)
   - 보안 그룹 위험 규칙 행 생성 (`sg_risky_rows`)
   - Trusted Advisor 에러 행 생성 (`ta_error_rows`)
   - CloudTrail 중요 이벤트 행 생성 (`cloudtrail_critical_rows`)
   - CloudWatch 알람 행 생성 (`cloudwatch_alarm_rows`)
   - Critical 이슈 섹션 생성 (`critical_issues_section`)
3. HTML 템플릿에 변수 삽입
4. 최종 HTML 파일 생성: `/tmp/reports/security_report_{account_id}_{timestamp}.html`

### 보고서 활용:
- 매월 정기 보안 점검용
- 경영진 보고용
- 컴플라이언스 감사용
- 보안 개선 추적용
