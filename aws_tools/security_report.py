"""
AWS 월간 보고서 생성 모듈
Reference 코드의 완전한 데이터 수집 로직을 WebSocket 환경에 맞게 적용
"""

import os
import json
import boto3
from datetime import datetime, timedelta, date
import subprocess
import traceback

def convert_datetime_to_json_serializable(obj):
    """
    datetime 객체를 JSON 직렬화 가능한 형식으로 변환하는 재귀 함수
    
    Args:
        obj: 변환할 Python 객체 (dict, list, datetime 등)
    
    Returns:
        JSON 직렬화 가능한 객체
    """
    if isinstance(obj, (datetime, date)):
        # datetime 또는 date 객체를 ISO 8601 형식 문자열로 변환
        return obj.isoformat()
    elif isinstance(obj, dict):
        # 딕셔너리의 모든 값을 재귀적으로 변환
        return {key: convert_datetime_to_json_serializable(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        # 리스트의 모든 요소를 재귀적으로 변환
        return [convert_datetime_to_json_serializable(item) for item in obj]
    elif isinstance(obj, tuple):
        # 튜플을 리스트로 변환하고 재귀적으로 처리
        return [convert_datetime_to_json_serializable(item) for item in obj]
    elif isinstance(obj, set):
        # 세트를 리스트로 변환하고 재귀적으로 처리
        return [convert_datetime_to_json_serializable(item) for item in obj]
    else:
        # 기타 타입은 그대로 반환 (str, int, float, bool, None 등)
        return obj

def collect_raw_security_data(account_id, start_date_str, end_date_str, region='ap-northeast-2', credentials=None):
    """
    boto3를 사용하여 AWS raw 보안 데이터를 수집 (Q CLI 분석용)
    Reference 코드의 완전한 collect_raw_security_data 함수
    
    Args:
        account_id (str): AWS 계정 ID
        start_date_str (str): 시작 날짜 (YYYY-MM-DD) - UTC+9 기준
        end_date_str (str): 종료 날짜 (YYYY-MM-DD) - UTC+9 기준
        region (str): AWS 리전
        credentials (dict): AWS 자격증명 (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN)
    
    Returns:
        dict: Raw 보안 데이터 JSON
    """
    print(f"[DEBUG] ✅ boto3로 raw 데이터 수집 시작: 계정 {account_id}, 리전 {region}", flush=True)
    print(f"[DEBUG] 분석 기간: {start_date_str} ~ {end_date_str} (UTC+9)", flush=True)
    
    # 자격증명 가져오기 (파라미터 우선, 없으면 환경 변수)
    if credentials:
        access_key = credentials.get('AWS_ACCESS_KEY_ID')
        secret_key = credentials.get('AWS_SECRET_ACCESS_KEY')
        session_token = credentials.get('AWS_SESSION_TOKEN')
    else:
        access_key = os.environ.get('AWS_ACCESS_KEY_ID')
        secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
        session_token = os.environ.get('AWS_SESSION_TOKEN')
    
    print(f"[DEBUG] 자격증명 확인: ACCESS_KEY={access_key[:20] if access_key else 'None'}..., SESSION_TOKEN={'있음' if session_token else '없음'}", flush=True)
    
    # boto3 세션 생성 (환경 변수의 임시 자격증명 사용)
    session = boto3.Session(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        aws_session_token=session_token,
        region_name=region
    )
    
    # boto3 클라이언트 생성
    ec2 = session.client('ec2', region_name=region)
    s3 = session.client('s3', region_name=region)
    iam = session.client('iam', region_name=region)
    support = session.client('support', region_name='us-east-1')  # TA는 us-east-1만 지원
    cloudtrail = session.client('cloudtrail', region_name=region)
    cloudwatch = session.client('cloudwatch', region_name=region)
    
    print(f"[DEBUG] boto3 클라이언트 생성 완료 (임시 자격증명 사용)", flush=True)
    
    report_data = {
        "metadata": {
            "account_id": account_id,
            "report_date": datetime.now().strftime("%Y-%m-%d"),
            "period_start": start_date_str,
            "period_end": end_date_str,
            "region": region
        },
        "resources": {},
        "iam_security": {},
        "security_groups": {},
        "encryption": {},
        "trusted_advisor": {},
        "cloudtrail_events": {},
        "cloudwatch": {},
        "recommendations": []
    }
    
    # 1. EC2 인스턴스 수집 (Raw 데이터 저장)
    print(f"[DEBUG] 📦 EC2 인스턴스 수집 중...", flush=True)
    try:
        ec2_response = ec2.describe_instances()
        
        # Raw 인스턴스 데이터 추출 (모든 필드 포함)
        instances_raw = []
        for reservation in ec2_response['Reservations']:
            for instance in reservation['Instances']:
                instances_raw.append(instance)
        
        # 요약 정보 계산
        total = len(instances_raw)
        running = sum(1 for i in instances_raw if i['State']['Name'] == 'running')
        stopped = sum(1 for i in instances_raw if i['State']['Name'] == 'stopped')
        
        report_data['resources']['ec2'] = {
            "summary": {
                "total": total,
                "running": running,
                "stopped": stopped
            },
            "instances": instances_raw  # Raw 데이터 (datetime 변환은 나중에 일괄 처리)
        }
        print(f"[DEBUG] ✅ EC2 수집 완료: {total}개 (running: {running}, stopped: {stopped})", flush=True)
    except Exception as e:
        print(f"[ERROR] ❌ EC2 수집 실패: {e}", flush=True)
        report_data['resources']['ec2'] = {"summary": {"total": 0, "running": 0, "stopped": 0}, "instances": []}
    
    # 2. S3 버킷 수집 (Raw 데이터 + 추가 정보)
    print(f"[DEBUG] 📦 S3 버킷 수집 중...", flush=True)
    try:
        s3_response = s3.list_buckets()
        buckets_raw = []
        
        for bucket in s3_response['Buckets']:
            bucket_name = bucket['Name']
            bucket_data = bucket.copy()  # 기본 정보 복사
            
            try:
                # 버킷 리전 확인
                location = s3.get_bucket_location(Bucket=bucket_name)
                bucket_data['Location'] = location.get('LocationConstraint') or 'us-east-1'
                
                # 암호화 확인
                try:
                    encryption_response = s3.get_bucket_encryption(Bucket=bucket_name)
                    bucket_data['Encryption'] = encryption_response.get('ServerSideEncryptionConfiguration')
                except:
                    bucket_data['Encryption'] = None
                
                # 버저닝 확인
                try:
                    versioning_response = s3.get_bucket_versioning(Bucket=bucket_name)
                    bucket_data['Versioning'] = versioning_response
                except:
                    bucket_data['Versioning'] = None
                
                # 퍼블릭 액세스 블록 확인
                try:
                    public_access_response = s3.get_public_access_block(Bucket=bucket_name)
                    bucket_data['PublicAccessBlock'] = public_access_response.get('PublicAccessBlockConfiguration')
                except:
                    bucket_data['PublicAccessBlock'] = None  # 블록 설정 없음 = 퍼블릭 가능
                
                buckets_raw.append(bucket_data)
            except Exception as e:
                print(f"[DEBUG] 버킷 {bucket_name} 상세 정보 수집 실패: {e}", flush=True)
                buckets_raw.append(bucket_data)  # 기본 정보라도 저장
        
        # 요약 정보 계산
        encrypted_count = sum(1 for b in buckets_raw if b.get('Encryption') is not None)
        public_count = sum(1 for b in buckets_raw if b.get('PublicAccessBlock') is None)
        
        report_data['resources']['s3'] = {
            "summary": {
                "total": len(buckets_raw),
                "encrypted": encrypted_count,
                "public": public_count
            },
            "buckets": buckets_raw  # Raw 데이터 (모든 버킷, 모든 필드)
        }
        print(f"[DEBUG] ✅ S3 수집 완료: {len(buckets_raw)}개 (암호화: {encrypted_count}, 퍼블릭: {public_count})", flush=True)
    except Exception as e:
        print(f"[ERROR] ❌ S3 수집 실패: {e}", flush=True)
        report_data['resources']['s3'] = {"summary": {"total": 0, "encrypted": 0, "public": 0}, "buckets": []}
    
    # 3. Lambda 함수 수집 (Raw 데이터 저장)
    print(f"[DEBUG] 📦 Lambda 함수 수집 중...", flush=True)
    try:
        lambda_client = session.client('lambda', region_name=region)
        lambda_response = lambda_client.list_functions()
        functions_raw = lambda_response.get('Functions', [])
        
        report_data['resources']['lambda'] = {
            "summary": {
                "total": len(functions_raw)
            },
            "functions": functions_raw  # Raw 데이터 (모든 필드 포함)
        }
        print(f"[DEBUG] ✅ Lambda 수집 완료: {len(functions_raw)}개", flush=True)
    except Exception as e:
        print(f"[ERROR] ❌ Lambda 수집 실패: {e}", flush=True)
        report_data['resources']['lambda'] = {"summary": {"total": 0}, "functions": []}
    
    # 4. RDS 인스턴스 수집 (Raw 데이터 저장 - Multi-AZ, 엔진, 백업 등 모든 정보 포함)
    print(f"[DEBUG] 📦 RDS 인스턴스 수집 중...", flush=True)
    try:
        rds_client = session.client('rds', region_name=region)
        rds_response = rds_client.describe_db_instances()
        db_instances_raw = rds_response.get('DBInstances', [])
        
        report_data['resources']['rds'] = {
            "summary": {
                "total": len(db_instances_raw)
            },
            "instances": db_instances_raw  # Raw 데이터 (Multi-AZ, Engine, BackupRetentionPeriod 등 모두 포함)
        }
        print(f"[DEBUG] ✅ RDS 수집 완료: {len(db_instances_raw)}개", flush=True)
    except Exception as e:
        print(f"[ERROR] ❌ RDS 수집 실패: {e}", flush=True)
        report_data['resources']['rds'] = {"summary": {"total": 0}, "instances": []}
    
    # 5. IAM 사용자 수집
    print(f"[DEBUG] 📦 IAM 사용자 수집 중...", flush=True)
    try:
        iam_response = iam.list_users()
        users = []
        issues = []
        
        for user in iam_response['Users']:
            username = user['UserName']
            
            # MFA 확인
            mfa_devices = iam.list_mfa_devices(UserName=username)
            has_mfa = len(mfa_devices['MFADevices']) > 0
            
            # 액세스 키 확인
            access_keys = iam.list_access_keys(UserName=username)
            
            users.append({
                "username": username,
                "mfa": has_mfa,
                "access_keys": access_keys['AccessKeyMetadata'],
                "policies": [],
                "groups": []
            })
            
            # MFA 미설정 이슈
            if not has_mfa:
                issues.append({
                    "severity": "critical",
                    "type": "no_mfa",
                    "user": username,
                    "description": "MFA 미설정"
                })
        
        report_data['iam_security'] = {
            "users": {
                "total": len(users),
                "mfa_enabled": sum(1 for u in users if u['mfa']),
                "details": users
            },
            "issues": issues
        }
        print(f"[DEBUG] ✅ IAM 수집 완료: {len(users)}명 (MFA 활성화: {sum(1 for u in users if u['mfa'])}명)", flush=True)
    except Exception as e:
        print(f"[ERROR] ❌ IAM 수집 실패: {e}", flush=True)
        report_data['iam_security'] = {"users": {"total": 0, "mfa_enabled": 0, "details": []}, "issues": []}
    
    # 6. 보안 그룹 수집
    print(f"[DEBUG] 📦 보안 그룹 수집 중...", flush=True)
    try:
        sg_response = ec2.describe_security_groups()
        risky_sgs = []
        total_risky_rules = 0
        
        for sg in sg_response['SecurityGroups']:
            risky_rules = []
            for rule in sg.get('IpPermissions', []):
                for ip_range in rule.get('IpRanges', []):
                    if ip_range.get('CidrIp') == '0.0.0.0/0':
                        port = rule.get('FromPort', 'all')
                        risky_rules.append({
                            "port": port,
                            "protocol": rule.get('IpProtocol', 'all'),
                            "source": "0.0.0.0/0",
                            "risk_level": "high" if port in [22, 3389, 3306, 5432] else "medium",
                            "description": f"포트 {port} 전체 오픈"
                        })
            
            if risky_rules:
                risky_sgs.append({
                    "id": sg['GroupId'],
                    "name": sg['GroupName'],
                    "vpc": sg.get('VpcId', 'N/A'),
                    "risky_rules": risky_rules
                })
                total_risky_rules += len(risky_rules)
        
        report_data['security_groups'] = {
            "total": len(sg_response['SecurityGroups']),
            "risky": total_risky_rules,
            "details": risky_sgs[:5]  # 처음 5개만 표시
        }
        print(f"[DEBUG] ✅ 보안 그룹 수집 완료: {len(sg_response['SecurityGroups'])}개 (위험 규칙: {total_risky_rules}개)", flush=True)
    except Exception as e:
        print(f"[ERROR] ❌ 보안 그룹 수집 실패: {e}", flush=True)
        report_data['security_groups'] = {"total": 0, "risky": 0, "details": []}
    
    # 7. 암호화 상태 수집
    print(f"[DEBUG] 📦 암호화 상태 수집 중...", flush=True)
    try:
        volumes_response = ec2.describe_volumes()
        volumes = volumes_response['Volumes']
        encrypted_volumes = [v for v in volumes if v.get('Encrypted', False)]
        unencrypted_volumes = [v['VolumeId'] for v in volumes if not v.get('Encrypted', False)]
        
        # S3, RDS 요약 정보 가져오기 (새 구조 반영)
        s3_total = report_data['resources']['s3']['summary']['total']
        s3_encrypted = report_data['resources']['s3']['summary']['encrypted']
        rds_total = report_data['resources']['rds']['summary']['total']
        
        # RDS 암호화 상태 계산
        rds_instances = report_data['resources']['rds'].get('instances', [])
        rds_encrypted = sum(1 for instance in rds_instances if instance.get('StorageEncrypted', False))
        rds_encrypted_rate = rds_encrypted / rds_total if rds_total > 0 else 0.0
        
        report_data['encryption'] = {
            "ebs": {
                "total": len(volumes),
                "encrypted": len(encrypted_volumes),
                "unencrypted_volumes": unencrypted_volumes[:16]  # 처음 16개만
            },
            "s3": {
                "total": s3_total,
                "encrypted": s3_encrypted,
                "encrypted_rate": s3_encrypted / s3_total if s3_total > 0 else 0.0
            },
            "rds": {
                "total": rds_total,
                "encrypted": rds_encrypted,
                "encrypted_rate": rds_encrypted_rate
            }
        }
        print(f"[DEBUG] ✅ 암호화 수집 완료: EBS {len(encrypted_volumes)}/{len(volumes)} 암호화됨", flush=True)
    except Exception as e:
        print(f"[ERROR] ❌ 암호화 상태 수집 실패: {e}", flush=True)
        report_data['encryption'] = {"ebs": {"total": 0, "encrypted": 0, "unencrypted_volumes": []}, "s3": {"total": 0, "encrypted": 0, "encrypted_rate": 0.0}, "rds": {"total": 0, "encrypted": 0, "encrypted_rate": 0.0}}
    
    # 8. Trusted Advisor 수집 (가장 중요!)
    print(f"[DEBUG] 🔍 Trusted Advisor 수집 중... (이게 핵심!)", flush=True)
    try:
        # TA 체크 목록 가져오기
        ta_checks_response = support.describe_trusted_advisor_checks(language='en')
        checks = ta_checks_response['checks']
        print(f"[DEBUG] TA 전체 체크 개수: {len(checks)}개", flush=True)
        
        ta_results = []
        for check in checks:
            check_id = check['id']
            check_name = check['name']
            check_category = check['category']
            
            try:
                # 각 체크 결과 가져오기
                result_response = support.describe_trusted_advisor_check_result(checkId=check_id, language='en')
                result = result_response['result']
                
                status = result['status']
                flagged_resources = len(result.get('flaggedResources', []))
                
                # 문제가 있는 체크만 포함
                if status in ['warning', 'error'] and flagged_resources > 0:
                    # 한글 번역
                    category_kr = {
                        'security': '보안',
                        'cost_optimizing': '비용 최적화',
                        'performance': '성능',
                        'fault_tolerance': '내결함성',
                        'service_limits': '서비스 한도'
                    }.get(check_category, check_category)
                    
                    ta_results.append({
                        "category": category_kr,
                        "name": check_name,  # 영문 그대로 (한글 번역은 템플릿에서)
                        "status": status,
                        "flagged_resources": flagged_resources,
                        "details": []  # 상세 정보는 생략 (개수만 표시)
                    })
                    print(f"[DEBUG] TA 이슈 발견: [{category_kr}] {check_name} - {flagged_resources}개", flush=True)
            except Exception as e:
                print(f"[DEBUG] TA 체크 {check_name} 결과 수집 실패: {e}", flush=True)
        
        report_data['trusted_advisor'] = {
            "available": True,
            "checks": ta_results
        }
        print(f"[DEBUG] ✅ Trusted Advisor 수집 완료: {len(ta_results)}개 이슈 발견!", flush=True)
    except Exception as e:
        print(f"[ERROR] ❌ Trusted Advisor 수집 실패: {e}", flush=True)
        import traceback
        traceback.print_exc()
        report_data['trusted_advisor'] = {"available": False, "checks": []}
    
    # 9. CloudTrail 이벤트 수집 (정확한 기간, UTC+9)
    print(f"[DEBUG] 📦 CloudTrail 이벤트 수집 중 ({start_date_str} ~ {end_date_str})...", flush=True)
    try:
        from datetime import datetime as dt, timezone
        
        # UTC+9 (한국 시간) 적용
        kst = timezone(timedelta(hours=9))
        
        # 시작일 00:00:00 KST → UTC 변환
        start_time_kst = dt.strptime(start_date_str, "%Y-%m-%d").replace(hour=0, minute=0, second=0, tzinfo=kst)
        start_time_utc = start_time_kst.astimezone(timezone.utc)
        
        # 종료일 23:59:59 KST → UTC 변환
        end_time_kst = dt.strptime(end_date_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=kst)
        end_time_utc = end_time_kst.astimezone(timezone.utc)
        
        print(f"[DEBUG] CloudTrail 조회 기간 (UTC): {start_time_utc} ~ {end_time_utc}", flush=True)
        
        # 보안 관점에서 중요한 이벤트 목록 (우선순위 순)
        critical_events = {
            # 🔴 Critical - 데이터 손실 및 서비스 중단
            'DeleteBucket': {'severity': 'critical', 'category': 'data_loss', 'description': 'S3 버킷 삭제'},
            'DeleteDBInstance': {'severity': 'critical', 'category': 'data_loss', 'description': 'RDS 인스턴스 삭제'},
            'TerminateInstances': {'severity': 'critical', 'category': 'service_disruption', 'description': 'EC2 인스턴스 종료'},
            'DeleteUser': {'severity': 'critical', 'category': 'account_security', 'description': 'IAM 사용자 삭제'},
            'DeleteAccessKey': {'severity': 'critical', 'category': 'account_security', 'description': 'IAM 액세스 키 삭제'},
            
            # 🟡 High - 보안 설정 변경
            'PutBucketPolicy': {'severity': 'high', 'category': 'permission_change', 'description': 'S3 버킷 정책 변경'},
            'AuthorizeSecurityGroupIngress': {'severity': 'high', 'category': 'network_security', 'description': '보안 그룹 인바운드 규칙 추가'},
            'CreateAccessKey': {'severity': 'high', 'category': 'account_security', 'description': '새 액세스 키 생성'},
            'PutUserPolicy': {'severity': 'high', 'category': 'permission_change', 'description': 'IAM 사용자 정책 변경'},
            'AttachUserPolicy': {'severity': 'high', 'category': 'permission_change', 'description': 'IAM 사용자 정책 연결'},
        }
        
        # 각 중요 이벤트별로 수집
        critical_events_data = {}
        total_collected = 0
        
        for event_name, event_info in critical_events.items():
            print(f"[DEBUG] 🔍 {event_name} 이벤트 조회 중...", flush=True)
            
            try:
                # 해당 이벤트만 조회 (최대 50개)
                events_response = cloudtrail.lookup_events(
                    StartTime=start_time_utc,
                    EndTime=end_time_utc,
                    LookupAttributes=[
                        {'AttributeKey': 'EventName', 'AttributeValue': event_name}
                    ],
                    MaxResults=50
                )
                
                events = events_response.get('Events', [])
                
                if events:
                    critical_events_data[event_name] = {
                        'severity': event_info['severity'],
                        'category': event_info['category'],
                        'description': event_info['description'],
                        'count': len(events),
                        'events': events  # Raw 이벤트 데이터
                    }
                    total_collected += len(events)
                    print(f"[DEBUG] ✅ {event_name}: {len(events)}개 발견", flush=True)
                else:
                    # 이벤트가 없어도 기록 (0건)
                    critical_events_data[event_name] = {
                        'severity': event_info['severity'],
                        'category': event_info['category'],
                        'description': event_info['description'],
                        'count': 0,
                        'events': []
                    }
                    
            except Exception as e:
                print(f"[DEBUG] ⚠️ {event_name} 조회 실패: {e}", flush=True)
                critical_events_data[event_name] = {
                    'severity': event_info['severity'],
                    'category': event_info['category'],
                    'description': event_info['description'],
                    'count': 0,
                    'events': [],
                    'error': str(e)
                }
        
        period_days = (end_time_kst - start_time_kst).days + 1
        
        report_data['cloudtrail_events'] = {
            "summary": {
                "period_days": period_days,
                "total_critical_events": total_collected,
                "monitored_event_types": len(critical_events)
            },
            "critical_events": critical_events_data  # 이벤트 타입별로 구조화된 데이터
        }
        print(f"[DEBUG] ✅ CloudTrail 중요 이벤트 수집 완료: {total_collected}개 ({period_days}일간)", flush=True)
    except Exception as e:
        print(f"[ERROR] ❌ CloudTrail 수집 실패: {e}", flush=True)
        import traceback
        traceback.print_exc()
        report_data['cloudtrail_events'] = {"summary": {"period_days": 30, "total_critical_events": 0, "monitored_event_types": 0}, "critical_events": {}}
    
    # 10. CloudWatch 알람 수집 (Raw 데이터 저장)
    print(f"[DEBUG] 📦 CloudWatch 알람 수집 중...", flush=True)
    try:
        alarms_response = cloudwatch.describe_alarms()
        alarms_raw = alarms_response['MetricAlarms']
        
        # 요약 정보 계산
        total = len(alarms_raw)
        in_alarm = sum(1 for a in alarms_raw if a['StateValue'] == 'ALARM')
        ok = sum(1 for a in alarms_raw if a['StateValue'] == 'OK')
        insufficient_data = sum(1 for a in alarms_raw if a['StateValue'] == 'INSUFFICIENT_DATA')
        
        report_data['cloudwatch'] = {
            "summary": {
                "total": total,
                "in_alarm": in_alarm,
                "ok": ok,
                "insufficient_data": insufficient_data
            },
            "alarms": alarms_raw  # Raw 데이터 (AlarmName, StateValue, MetricName, Threshold 등 모든 필드)
        }
        print(f"[DEBUG] ✅ CloudWatch 수집 완료: {total}개 알람 (ALARM: {in_alarm}, OK: {ok})", flush=True)
    except Exception as e:
        print(f"[ERROR] ❌ CloudWatch 수집 실패: {e}", flush=True)
        report_data['cloudwatch'] = {"summary": {"total": 0, "in_alarm": 0, "ok": 0, "insufficient_data": 0}, "alarms": []}
    
    # 11. 권장사항 생성
    print(f"[DEBUG] 📝 권장사항 생성 중...", flush=True)
    recommendations = []
    
    # MFA 권장사항
    if report_data['iam_security']['users']['mfa_enabled'] < report_data['iam_security']['users']['total']:
        recommendations.append({
            "priority": "critical",
            "category": "security",
            "title": "모든 IAM 사용자에 MFA 설정 필요",
            "description": f"{report_data['iam_security']['users']['total'] - report_data['iam_security']['users']['mfa_enabled']}명의 IAM 사용자가 MFA를 설정하지 않았습니다.",
            "affected_resources": [u['username'] for u in report_data['iam_security']['users']['details'] if not u['mfa']],
            "action": "모든 IAM 사용자에 대해 MFA를 활성화하고 정기적으로 검토하세요."
        })
    
    # 보안 그룹 권장사항
    if report_data['security_groups']['risky'] > 0:
        recommendations.append({
            "priority": "critical",
            "category": "security",
            "title": "보안 그룹 규칙 강화 필요",
            "description": f"{report_data['security_groups']['risky']}개의 위험한 보안 그룹 규칙이 발견되었습니다.",
            "affected_resources": [sg['id'] for sg in report_data['security_groups']['details']],
            "action": "보안 그룹 규칙을 검토하고 필요한 IP 범위로만 제한하세요."
        })
    
    # EBS 암호화 권장사항
    if report_data['encryption']['ebs']['total'] > 0 and report_data['encryption']['ebs']['encrypted'] < report_data['encryption']['ebs']['total']:
        recommendations.append({
            "priority": "high",
            "category": "security",
            "title": "EBS 볼륨 암호화 활성화",
            "description": f"{report_data['encryption']['ebs']['total'] - report_data['encryption']['ebs']['encrypted']}개의 EBS 볼륨이 암호화되지 않았습니다.",
            "affected_resources": report_data['encryption']['ebs']['unencrypted_volumes'][:5],
            "action": "새로운 EBS 볼륨에 대해 기본 암호화를 활성화하고 기존 볼륨을 암호화된 볼륨으로 마이그레이션하세요."
        })
    
    # S3 암호화 권장사항 (새 구조 반영)
    s3_total = report_data['resources']['s3']['summary']['total']
    s3_encrypted = report_data['resources']['s3']['summary']['encrypted']
    if s3_total > 0 and s3_encrypted < s3_total:
        # 암호화되지 않은 버킷 찾기
        unencrypted_buckets = [b['Name'] for b in report_data['resources']['s3']['buckets'] if b.get('Encryption') is None]
        recommendations.append({
            "priority": "high",
            "category": "security",
            "title": "S3 버킷 암호화 설정",
            "description": f"{s3_total - s3_encrypted}개의 S3 버킷이 암호화되지 않았습니다.",
            "affected_resources": unencrypted_buckets[:5],
            "action": "모든 S3 버킷에 대해 서버 측 암호화(SSE)를 활성화하세요."
        })
    
    report_data['recommendations'] = recommendations
    print(f"[DEBUG] ✅ 권장사항 생성 완료: {len(recommendations)}개", flush=True)
    
    print(f"[DEBUG] 🎉 boto3 데이터 수집 완료! 정확한 데이터를 수집했습니다.", flush=True)
    
    # datetime 객체를 JSON 직렬화 가능한 형식으로 변환
    print(f"[DEBUG] 📝 datetime 객체 변환 중...", flush=True)
    report_data = convert_datetime_to_json_serializable(report_data)
    print(f"[DEBUG] ✅ datetime 변환 완료", flush=True)
    
    return report_data

def generate_html_report(json_file_path):
    """
    JSON 데이터를 월간 보안 점검 HTML 보고서로 변환
    Reference 코드에서 복사한 함수 (Flask 의존성 제거)
    """
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # HTML 템플릿 읽기
        template_path = os.path.join(os.path.dirname(__file__), '..', 'reference_templates', 'json_report_template.html')
        with open(template_path, 'r', encoding='utf-8') as f:
            template = f.read()

        # 기본 메타데이터
        metadata = data.get('metadata', {})
        
        # 템플릿 변수 생성
        template_vars = {
            'account_id': metadata.get('account_id', 'Unknown'),
            'region': metadata.get('region', 'ap-northeast-2'),
            'report_date': metadata.get('report_date', ''),
            'period_start': metadata.get('period_start', ''),
            'period_end': metadata.get('period_end', ''),
        }
        
        # EC2 데이터 처리
        ec2_data = data.get('resources', {}).get('ec2', {})
        template_vars.update({
            'ec2_total': ec2_data.get('summary', {}).get('total', 0),
            'ec2_running': ec2_data.get('summary', {}).get('running', 0),
            'ec2_stopped': ec2_data.get('summary', {}).get('stopped', 0),
            'ec2_rows': generate_ec2_rows(ec2_data.get('instances', [])),
        })
        
        # S3 데이터 처리
        s3_data = data.get('resources', {}).get('s3', {})
        s3_total = s3_data.get('summary', {}).get('total', 0)
        s3_encrypted = s3_data.get('summary', {}).get('encrypted', 0)
        s3_encrypted_rate = round((s3_encrypted / max(s3_total, 1)) * 100, 1) if s3_total > 0 else 0
        
        template_vars.update({
            's3_total': s3_total,
            's3_encrypted': s3_encrypted,
            's3_encrypted_rate': s3_encrypted_rate,
            's3_rows': generate_s3_rows(s3_data.get('buckets', [])),
        })
        
        # RDS 데이터 처리
        rds_data = data.get('resources', {}).get('rds', {})
        rds_instances = rds_data.get('instances', [])
        rds_multi_az = sum(1 for instance in rds_instances if instance.get('MultiAZ', False))
        template_vars.update({
            'rds_total': rds_data.get('summary', {}).get('total', 0),
            'rds_multi_az': rds_multi_az,
            'rds_content': generate_rds_content(rds_instances),
        })
        
        # Lambda 데이터 처리
        lambda_data = data.get('resources', {}).get('lambda', {})
        template_vars.update({
            'lambda_total': lambda_data.get('summary', {}).get('total', 0),
            'lambda_content': generate_lambda_content(lambda_data.get('functions', [])),
        })
        
        # IAM 데이터 처리
        iam_data = data.get('iam_security', {})
        iam_users = iam_data.get('users', {})
        iam_total = iam_users.get('total', 0)
        iam_mfa_enabled = iam_users.get('mfa_enabled', 0)
        iam_mfa_rate = round((iam_mfa_enabled / max(iam_total, 1)) * 100, 1) if iam_total > 0 else 0
        
        template_vars.update({
            'iam_users_total': iam_total,
            'iam_mfa_enabled': iam_mfa_enabled,
            'iam_mfa_rate': iam_mfa_rate,
            'iam_users_rows': generate_iam_users_rows(iam_users.get('details', [])),
        })
        
        # 보안 그룹 데이터 처리
        sg_data = data.get('security_groups', {})
        template_vars.update({
            'sg_total': sg_data.get('total', 0),
            'sg_risky': sg_data.get('risky', 0),
            'sg_risky_rows': generate_sg_risky_rows(sg_data.get('details', [])),
        })
        
        # 암호화 데이터 처리
        encryption_data = data.get('encryption', {})
        ebs_data = encryption_data.get('ebs', {})
        rds_encryption = encryption_data.get('rds', {})
        
        ebs_total = ebs_data.get('total', 0)
        ebs_encrypted = ebs_data.get('encrypted', 0)
        ebs_rate = round((ebs_encrypted / max(ebs_total, 1)) * 100, 1) if ebs_total > 0 else 0
        
        # RDS 암호화 계산
        rds_encrypted_count = sum(1 for instance in rds_instances if instance.get('StorageEncrypted', False))
        rds_encrypted_rate = round((rds_encrypted_count / max(len(rds_instances), 1)) * 100, 1) if rds_instances else 0
        
        template_vars.update({
            'ebs_total': ebs_total,
            'ebs_encrypted': ebs_encrypted,
            'ebs_rate': ebs_rate,
            'rds_encrypted': rds_encrypted_count,
            'rds_encrypted_rate': rds_encrypted_rate,
        })
        
        # 준수율 클래스 설정
        template_vars.update({
            'ebs_compliance_class': get_compliance_class(ebs_rate),
            's3_compliance_class': get_compliance_class(s3_encrypted_rate),
            'rds_compliance_class': get_compliance_class(rds_encrypted_rate),
        })
        
        # Critical 이슈 계산
        critical_issues = calculate_critical_issues(data)
        template_vars.update({
            'critical_issues_count': len(critical_issues),
            'critical_issues_section': generate_critical_issues_section(critical_issues),
        })
        
        # Trusted Advisor 데이터 처리
        ta_data = data.get('trusted_advisor', {})
        ta_summary = process_trusted_advisor_data(ta_data)
        template_vars.update(ta_summary)
        
        # CloudTrail 데이터 처리 (Reference 구조 사용)
        ct_data = data.get('cloudtrail_events', {})
        ct_summary = ct_data.get('summary', {})
        ct_critical_events = ct_data.get('critical_events', {})
        
        template_vars.update({
            'cloudtrail_days': ct_summary.get('period_days', 30),
            'cloudtrail_critical_rows': generate_cloudtrail_rows(ct_critical_events),
        })
        
        # CloudWatch 데이터 처리
        cw_data = data.get('cloudwatch', {})
        cw_alarms = cw_data.get('alarms', [])
        cw_states = cw_data.get('states', {})
        
        template_vars.update({
            'cloudwatch_alarms_total': cw_data.get('total_alarms', 0),
            'cloudwatch_alarms_in_alarm': cw_states.get('ALARM', 0),
            'cloudwatch_alarms_ok': cw_states.get('OK', 0),
            'cloudwatch_alarms_insufficient': cw_states.get('INSUFFICIENT_DATA', 0),
            'cloudwatch_alarm_rows': generate_cloudwatch_rows(cw_alarms),
        })
        
        # 기타 섹션들
        template_vars.update({
            'ebs_unencrypted_section': generate_ebs_unencrypted_section(ebs_data),
            's3_security_issues_section': generate_s3_security_issues_section(s3_data.get('buckets', [])),
            'ta_error_rows': generate_ta_error_rows(ta_data),
        })
        
        # 템플릿에 변수 적용
        html_content = template.format(**template_vars)
        
        # HTML 파일 저장
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        html_filename = f"security_report_{metadata.get('account_id', 'unknown')}_{timestamp}.html"
        html_file_path = os.path.join('/tmp/reports', html_filename)
        
        os.makedirs('/tmp/reports', exist_ok=True)
        with open(html_file_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"[DEBUG] ✅ HTML 보고서 생성 완료: {html_file_path}", flush=True)
        return html_file_path
        
    except Exception as e:
        print(f"[ERROR] ❌ HTML 보고서 생성 실패: {str(e)}", flush=True)
        traceback.print_exc()
        return None

# 헬퍼 함수들 (Reference 코드에서 복사)
def get_compliance_class(rate):
    """준수율에 따른 CSS 클래스 반환"""
    if rate < 50:
        return 'critical'
    elif rate < 80:
        return 'warning'
    else:
        return ''

def calculate_critical_issues(data):
    """Critical 이슈 계산"""
    issues = []
    
    # 보안 그룹 위험 규칙
    sg_risky = data.get('security_groups', {}).get('risky', 0)
    if sg_risky > 0:
        issues.append(f"위험한 보안 그룹 규칙 {sg_risky}개")
    
    # MFA 미설정 사용자
    iam_users = data.get('iam_security', {}).get('users', {})
    iam_total = iam_users.get('total', 0)
    iam_mfa = iam_users.get('mfa_enabled', 0)
    if iam_total > 0 and iam_mfa < iam_total:
        issues.append(f"MFA 미설정 사용자 {iam_total - iam_mfa}명")
    
    # 암호화 미설정 리소스
    ebs_data = data.get('encryption', {}).get('ebs', {})
    ebs_unencrypted = ebs_data.get('total', 0) - ebs_data.get('encrypted', 0)
    if ebs_unencrypted > 0:
        issues.append(f"암호화 미설정 EBS 볼륨 {ebs_unencrypted}개")
    
    return issues

def generate_critical_issues_section(issues):
    """Critical 이슈 섹션 생성"""
    if not issues:
        return ''
    
    content = '<div class="alert-box critical">'
    content += '<h4>⚠️ 즉시 조치 필요 항목</h4>'
    content += '<ul>'
    for issue in issues:
        content += f'<li>{issue}</li>'
    content += '</ul>'
    content += '</div>'
    
    return content

def process_trusted_advisor_data(ta_data):
    """Trusted Advisor 데이터 처리 (Reference 구조 사용)"""
    if not ta_data.get('available', False):
        return {
            'ta_security_error': 0,
            'ta_security_warning': 0,
            'ta_fault_tolerance_error': 0,
            'ta_fault_tolerance_warning': 0,
            'ta_cost_warning': 0,
            'ta_performance_warning': 0,
        }
    
    # Reference 구조: checks 배열에서 직접 처리
    checks = ta_data.get('checks', [])
    summary = {
        'ta_security_error': 0,
        'ta_security_warning': 0,
        'ta_fault_tolerance_error': 0,
        'ta_fault_tolerance_warning': 0,
        'ta_cost_warning': 0,
        'ta_performance_warning': 0,
    }
    
    for check in checks:
        category = check.get('category', '').lower()
        status = check.get('status', '').lower()
        
        if '보안' in category or 'security' in category:
            if status == 'error':
                summary['ta_security_error'] += 1
            elif status == 'warning':
                summary['ta_security_warning'] += 1
        elif '내결함성' in category or 'fault' in category:
            if status == 'error':
                summary['ta_fault_tolerance_error'] += 1
            elif status == 'warning':
                summary['ta_fault_tolerance_warning'] += 1
        elif '비용' in category or 'cost' in category and status == 'warning':
            summary['ta_cost_warning'] += 1
        elif '성능' in category or 'performance' in category and status == 'warning':
            summary['ta_performance_warning'] += 1
    
    return summary

def generate_ebs_unencrypted_section(ebs_data):
    """EBS 미암호화 섹션 생성"""
    unencrypted = ebs_data.get('total', 0) - ebs_data.get('encrypted', 0)
    if unencrypted == 0:
        return ''
    
    return f'''
    <div class="section">
        <h2>⚠️ EBS 볼륨 (암호화 미설정) ({unencrypted}개)</h2>
        <div class="alert-box">
            <h4>보안 권장사항</h4>
            <p>암호화되지 않은 EBS 볼륨 {unencrypted}개가 발견되었습니다. 데이터 보호를 위해 암호화를 활성화하세요.</p>
        </div>
    </div>
    '''

def generate_s3_security_issues_section(buckets):
    """S3 보안 이슈 섹션 생성"""
    public_buckets = []
    for bucket in buckets:
        if not bucket.get('PublicAccessBlock'):
            public_buckets.append(bucket.get('Name', 'Unknown'))
    
    if not public_buckets:
        return ''
    
    return f'''
    <div class="section">
        <h2>⚠️ S3 버킷 (보안 이슈) ({len(public_buckets)}개)</h2>
        <div class="alert-box">
            <h4>퍼블릭 액세스 가능 버킷</h4>
            <ul>
                {"".join([f"<li>{bucket}</li>" for bucket in public_buckets[:5]])}
            </ul>
        </div>
    </div>
    '''

def generate_ta_error_rows(ta_data):
    """Trusted Advisor 에러 행 생성 (Reference 구조 사용)"""
    if not ta_data.get('available', False):
        return '<tr><td colspan="4" class="no-data">Trusted Advisor 데이터를 사용할 수 없습니다. (Business/Enterprise 플랜 필요)</td></tr>'
    
    checks = ta_data.get('checks', [])
    error_checks = [c for c in checks if c.get('status', '').lower() == 'error']
    
    if not error_checks:
        return '<tr><td colspan="4" class="text-center text-success">Error 상태의 항목이 없습니다.</td></tr>'
    
    rows = []
    for check in error_checks[:10]:  # 최대 10개
        category = check.get('category', 'N/A')
        name = check.get('name', 'N/A')
        flagged_resources = check.get('flagged_resources', 0)
        
        rows.append(f"""
        <tr>
            <td>{category}</td>
            <td>{name}</td>
            <td><span class="badge badge-error">ERROR</span></td>
            <td>{flagged_resources}</td>
        </tr>
        """)
    
    return ''.join(rows)

def generate_cloudtrail_rows(critical_events_data):
    """CloudTrail 중요 이벤트 행 생성 (Reference 구조 사용)"""
    if not critical_events_data:
        return '<tr><td colspan="5" class="no-data">분석 기간 중 중요 이벤트가 없습니다</td></tr>'
    
    rows = []
    for event_name, event_data in critical_events_data.items():
        count = event_data.get('count', 0)
        if count > 0:  # 이벤트가 있는 것만 표시
            severity = event_data.get('severity', 'medium')
            category = event_data.get('category', 'other')
            description = event_data.get('description', event_name)
            
            severity_class = {
                'critical': 'error',
                'high': 'warning',
                'medium': 'info'
            }.get(severity, 'info')
            
            rows.append(f"""
            <tr>
                <td><strong>{event_name}</strong></td>
                <td><span class="badge badge-{severity_class}">{severity.upper()}</span></td>
                <td>{category}</td>
                <td>{count}</td>
                <td>{description}</td>
            </tr>
            """)
    
    if not rows:
        return '<tr><td colspan="5" class="no-data">분석 기간 중 중요 이벤트가 없습니다</td></tr>'
    
    return ''.join(rows[:10])  # 최대 10개

def generate_cloudwatch_rows(alarms):
    """CloudWatch 알람 행 생성"""
    if not alarms:
        return '<tr><td colspan="4" class="no-data">CloudWatch 알람이 없습니다</td></tr>'
    
    rows = []
    for alarm in alarms[:10]:  # 최대 10개
        name = alarm.get('AlarmName', 'N/A')
        state = alarm.get('StateValue', 'N/A')
        metric = alarm.get('MetricName', 'N/A')
        threshold = alarm.get('Threshold', 'N/A')
        
        state_class = {
            'OK': 'ok',
            'ALARM': 'error',
            'INSUFFICIENT_DATA': 'warning'
        }.get(state, 'info')
        
        rows.append(f"""
        <tr>
            <td><strong>{name}</strong></td>
            <td><span class="badge badge-{state_class}">{state}</span></td>
            <td>{metric}</td>
            <td>{threshold}</td>
        </tr>
        """)
    
    return ''.join(rows)

def get_event_severity(event_name):
    """이벤트 심각도 반환"""
    high_severity = ['DeleteBucket', 'TerminateInstances', 'DeleteUser', 'DeleteAccessKey']
    medium_severity = ['CreateAccessKey', 'AttachUserPolicy', 'DetachUserPolicy']
    
    if event_name in high_severity:
        return 'HIGH'
    elif event_name in medium_severity:
        return 'MEDIUM'
    else:
        return 'LOW'

def get_event_category(event_name):
    """이벤트 카테고리 반환"""
    if 'User' in event_name or 'Policy' in event_name or 'AccessKey' in event_name:
        return 'IAM'
    elif 'Bucket' in event_name:
        return 'S3'
    elif 'Instance' in event_name:
        return 'EC2'
    else:
        return 'Other'

def get_event_description(event_name):
    """이벤트 설명 반환"""
    descriptions = {
        'DeleteBucket': 'S3 버킷 삭제',
        'TerminateInstances': 'EC2 인스턴스 종료',
        'DeleteUser': 'IAM 사용자 삭제',
        'CreateAccessKey': 'IAM 액세스 키 생성',
        'DeleteAccessKey': 'IAM 액세스 키 삭제',
        'AttachUserPolicy': 'IAM 정책 연결',
        'DetachUserPolicy': 'IAM 정책 분리'
    }
    return descriptions.get(event_name, '기타 이벤트')

# HTML 생성 헬퍼 함수들 (Reference 코드에서 완전히 복사)
def generate_ec2_rows(instances):
    """EC2 인스턴스 테이블 행 생성"""
    if not instances:
        return '<tr><td colspan="8" class="no-data">EC2 인스턴스가 없습니다</td></tr>'
    
    rows = []
    for instance in instances:
        name = next((tag['Value'] for tag in instance.get('Tags', []) if tag['Key'] == 'Name'), instance.get('InstanceId', 'N/A'))
        instance_id = instance.get('InstanceId', 'N/A')
        instance_type = instance.get('InstanceType', 'N/A')
        state = instance.get('State', {}).get('Name', 'N/A')
        public_ip = instance.get('PublicIpAddress', '없음')
        
        # IMDSv2 설정
        metadata_options = instance.get('MetadataOptions', {})
        imdsv2 = metadata_options.get('HttpTokens', 'optional')
        imdsv2_class = 'ok' if imdsv2 == 'required' else 'warning'
        
        # 상세 모니터링
        monitoring = instance.get('Monitoring', {}).get('State', 'disabled')
        monitoring_class = 'ok' if monitoring == 'enabled' else 'warning'
        
        # EBS 삭제 방지
        delete_protection = 'N/A'
        for bdm in instance.get('BlockDeviceMappings', []):
            if bdm.get('Ebs', {}).get('DeleteOnTermination') == False:
                delete_protection = '설정됨'
                break
        else:
            delete_protection = '미설정'
        
        delete_class = 'ok' if delete_protection == '설정됨' else 'warning'
        
        rows.append(f"""
        <tr>
            <td><strong>{name}</strong></td>
            <td>{instance_id}</td>
            <td>{instance_type}</td>
            <td><span class="badge badge-{'ok' if state == 'running' else 'warning'}">{state}</span></td>
            <td class="{'warning' if public_ip != '없음' else 'ok'}">{public_ip}</td>
            <td class="{imdsv2_class}">{imdsv2}</td>
            <td class="{monitoring_class}">{monitoring}</td>
            <td class="{delete_class}">{delete_protection}</td>
        </tr>
        """)
    
    return ''.join(rows)

def generate_s3_rows(buckets):
    """S3 버킷 테이블 행 생성"""
    if not buckets:
        return '<tr><td colspan="6" class="no-data">S3 버킷이 없습니다</td></tr>'
    
    rows = []
    for bucket in buckets:
        name = bucket.get('Name', 'N/A')
        location = bucket.get('Location', 'N/A')
        
        # 암호화 설정
        encryption = bucket.get('Encryption', {})
        if encryption.get('Rules'):
            encryption_status = '설정됨'
            encryption_class = 'ok'
        else:
            encryption_status = '미설정'
            encryption_class = 'error'
        
        # 버저닝 설정
        versioning = bucket.get('Versioning', {})
        versioning_status = versioning.get('Status', '미설정')
        versioning_class = 'ok' if versioning_status == 'Enabled' else 'warning'
        
        # 퍼블릭 액세스 차단
        public_access = bucket.get('PublicAccessBlock')
        if public_access and all([
            public_access.get('BlockPublicAcls', False),
            public_access.get('IgnorePublicAcls', False),
            public_access.get('BlockPublicPolicy', False),
            public_access.get('RestrictPublicBuckets', False)
        ]):
            public_status = '차단됨'
            public_class = 'ok'
        else:
            public_status = '미차단'
            public_class = 'error'
        
        creation_date = bucket.get('CreationDate', 'N/A')
        if creation_date != 'N/A':
            creation_date = creation_date.split('T')[0]
        
        rows.append(f"""
        <tr>
            <td><strong>{name}</strong></td>
            <td>{location}</td>
            <td class="{encryption_class}">{encryption_status}</td>
            <td class="{versioning_class}">{versioning_status}</td>
            <td class="{public_class}">{public_status}</td>
            <td>{creation_date}</td>
        </tr>
        """)
    
    return ''.join(rows)

def generate_rds_content(instances):
    """RDS 인스턴스 콘텐츠 생성"""
    if not instances:
        return '<div class="no-data">RDS 인스턴스가 없습니다</div>'
    
    rows = []
    for instance in instances:
        db_id = instance.get('DBInstanceIdentifier', 'N/A')
        engine = instance.get('Engine', 'N/A')
        db_class = instance.get('DBInstanceClass', 'N/A')
        multi_az = instance.get('MultiAZ', False)
        encrypted = instance.get('StorageEncrypted', False)
        backup_retention = instance.get('BackupRetentionPeriod', 0)
        deletion_protection = instance.get('DeletionProtection', False)
        public_access = instance.get('PubliclyAccessible', False)
        status = instance.get('DBInstanceStatus', 'N/A')
        
        rows.append(f"""
        <tr>
            <td><strong>{db_id}</strong></td>
            <td>{engine}</td>
            <td>{db_class}</td>
            <td class="{'ok' if multi_az else 'error'}">{'예' if multi_az else '아니오'}</td>
            <td class="{'ok' if encrypted else 'error'}">{'예' if encrypted else '아니오'}</td>
            <td class="{'ok' if backup_retention >= 30 else 'warning' if backup_retention >= 7 else 'error'}">{backup_retention}일</td>
            <td class="{'ok' if deletion_protection else 'warning'}">{'예' if deletion_protection else '아니오'}</td>
            <td class="{'error' if public_access else 'ok'}">{'예' if public_access else '아니오'}</td>
            <td><span class="badge badge-{'ok' if status == 'available' else 'warning'}">{status}</span></td>
        </tr>
        """)
    
    table = f"""
    <table>
        <thead>
            <tr>
                <th>DB 식별자</th>
                <th>엔진</th>
                <th>타입</th>
                <th>Multi-AZ</th>
                <th>암호화</th>
                <th>백업 보관</th>
                <th>삭제 방지</th>
                <th>퍼블릭 액세스</th>
                <th>상태</th>
            </tr>
        </thead>
        <tbody>
            {''.join(rows)}
        </tbody>
    </table>
    """
    
    return table

def generate_lambda_content(functions):
    """Lambda 함수 콘텐츠 생성"""
    if not functions:
        return '<div class="no-data">Lambda 함수가 없습니다</div>'
    
    # Lambda 함수 목록을 HTML 테이블로 생성
    rows = []
    for func in functions:
        function_name = func.get('FunctionName', 'N/A')
        runtime = func.get('Runtime', 'N/A')
        memory_size = func.get('MemorySize', 'N/A')
        timeout = func.get('Timeout', 'N/A')
        last_modified = func.get('LastModified', 'N/A')
        
        # 날짜 포맷팅
        if last_modified != 'N/A':
            try:
                from datetime import datetime
                # ISO 8601 형식 파싱
                dt = datetime.fromisoformat(last_modified.replace('Z', '+00:00'))
                last_modified = dt.strftime('%Y-%m-%d %H:%M')
            except:
                pass
        
        # 런타임 상태 체크 (deprecated 런타임 확인)
        deprecated_runtimes = ['python2.7', 'python3.6', 'nodejs8.10', 'nodejs10.x', 'dotnetcore2.1', 'ruby2.5']
        runtime_class = 'warning' if runtime in deprecated_runtimes else 'ok'
        
        rows.append(f"""
        <tr>
            <td><strong>{function_name}</strong></td>
            <td class="{runtime_class}">{runtime}</td>
            <td>{memory_size} MB</td>
            <td>{timeout}초</td>
            <td>{last_modified}</td>
        </tr>
        """)
    
    table_html = f"""
    <table class="resource-table">
        <thead>
            <tr>
                <th>함수명</th>
                <th>런타임</th>
                <th>메모리</th>
                <th>타임아웃</th>
                <th>최종 수정일</th>
            </tr>
        </thead>
        <tbody>
            {''.join(rows)}
        </tbody>
    </table>
    """
    
    return table_html

def generate_iam_users_rows(users):
    """IAM 사용자 테이블 행 생성"""
    if not users:
        return '<tr><td colspan="5" class="no-data">IAM 사용자가 없습니다</td></tr>'
    
    rows = []
    for user in users:
        username = user.get('username', 'N/A')
        mfa = user.get('mfa', False)
        access_keys = user.get('access_keys', [])
        
        key_count = len(access_keys)
        key_date = 'N/A'
        key_age_class = 'ok'
        
        if access_keys:
            oldest_key = min(access_keys, key=lambda k: k.get('CreateDate', ''))
            key_date = oldest_key.get('CreateDate', 'N/A')
            if key_date != 'N/A':
                key_date = key_date.split('T')[0]
                from datetime import datetime, timedelta
                try:
                    create_date = datetime.strptime(key_date, '%Y-%m-%d')
                    if datetime.now() - create_date > timedelta(days=90):
                        key_age_class = 'warning'
                except:
                    pass
        
        security_issues = []
        if not mfa:
            security_issues.append('MFA 미설정')
        if key_count > 1:
            security_issues.append('다중 액세스 키')
        if key_age_class == 'warning':
            security_issues.append('오래된 키')
        
        security_status = ', '.join(security_issues) if security_issues else '양호'
        security_class = 'error' if security_issues else 'ok'
        
        rows.append(f"""
        <tr>
            <td><strong>{username}</strong></td>
            <td class="{'ok' if mfa else 'error'}">{'활성화' if mfa else '미설정'}</td>
            <td>{key_count}개</td>
            <td class="{key_age_class}">{key_date}</td>
            <td class="{security_class}">{security_status}</td>
        </tr>
        """)
    
    return ''.join(rows)

def generate_sg_risky_rows(security_groups):
    """위험한 보안 그룹 테이블 행 생성"""
    if not security_groups:
        return '<tr><td colspan="4" class="no-data">위험한 보안 그룹이 없습니다</td></tr>'
    
    rows = []
    for sg in security_groups:
        sg_id = sg.get('id', 'N/A')
        sg_name = sg.get('name', 'N/A')
        vpc = sg.get('vpc', 'N/A')
        risky_rules = sg.get('risky_rules', [])
        
        rules_text = []
        for rule in risky_rules:
            port = rule.get('port', 'all')
            protocol = rule.get('protocol', 'all')
            risk_level = rule.get('risk_level', 'medium')
            rules_text.append(f"{protocol}:{port} ({risk_level})")
        
        rules_display = ', '.join(rules_text) if rules_text else 'N/A'
        
        rows.append(f"""
        <tr>
            <td><strong>{sg_id}</strong></td>
            <td>{sg_name}</td>
            <td>{vpc}</td>
            <td class="error">{rules_display}</td>
        </tr>
        """)
    
    return ''.join(rows)

def generate_ta_content(results):
    """Trusted Advisor 내용 생성"""
    if not results:
        return "<p class='text-muted'>Trusted Advisor 데이터를 사용할 수 없습니다. (Business/Enterprise 플랜 필요)</p>"
    
    content = []
    for result in results[:5]:  # 최대 5개만 표시
        check = result.get('check', {})
        check_result = result.get('result', {})
        
        name = check.get('name', 'N/A')
        status = check_result.get('status', 'N/A')
        
        status_class = {
            'ok': 'success',
            'warning': 'warning', 
            'error': 'danger'
        }.get(status.lower(), 'secondary')
        
        content.append(f"""
        <div class="mb-2">
            <span class="badge badge-{status_class}">{status.upper()}</span>
            <strong>{name}</strong>
        </div>
        """)
    
    return ''.join(content)

def generate_cloudtrail_content(events):
    """CloudTrail 이벤트 내용 생성"""
    if not events:
        return "<p class='text-muted'>분석 기간 중 중요 이벤트가 없습니다.</p>"
    
    content = []
    for event in events[:10]:  # 최대 10개만 표시
        event_name = event.get('EventName', 'N/A')
        username = event.get('Username', 'N/A')
        event_time = event.get('EventTime', 'N/A')
        
        content.append(f"""
        <div class="mb-2">
            <strong>{event_name}</strong> by {username} at {event_time}
        </div>
        """)
    
    return ''.join(content)

def generate_cloudwatch_content(alarms):
    """CloudWatch 알람 내용 생성"""
    if not alarms:
        return "<p class='text-muted'>CloudWatch 알람이 없습니다.</p>"
    
    content = []
    for alarm in alarms[:10]:  # 최대 10개만 표시
        name = alarm.get('AlarmName', 'N/A')
        state = alarm.get('StateValue', 'N/A')
        
        state_class = {
            'OK': 'success',
            'ALARM': 'danger',
            'INSUFFICIENT_DATA': 'warning'
        }.get(state, 'secondary')
        
        content.append(f"""
        <div class="mb-2">
            <span class="badge badge-{state_class}">{state}</span>
            <strong>{name}</strong>
        </div>
        """)
    
    return ''.join(content)

def analyze_security_data_with_qcli(json_file_path, credentials=None):
    """
    수집된 보안 데이터를 Q CLI로 분석하여 구조화된 인사이트 생성
    
    Args:
        json_file_path (str): 수집된 raw 데이터 JSON 파일 경로
        credentials (dict): AWS 자격증명
    
    Returns:
        dict: Q CLI 분석 결과가 포함된 데이터
    """
    try:
        print(f"[DEBUG] 📊 Q CLI로 보안 데이터 분석 시작: {json_file_path}", flush=True)
        
        # 기존 JSON 데이터 로드
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 월간 보고서 컨텍스트 파일 경로
        context_file = '/root/core_contexts/security_report.md'
        
        # Q CLI 분석을 위한 프롬프트 생성
        analysis_prompt = f"""
다음은 AWS 계정 {data.get('metadata', {}).get('account_id', 'Unknown')}의 보안 데이터입니다.
분석 기간: {data.get('metadata', {}).get('period_start', 'N/A')} ~ {data.get('metadata', {}).get('period_end', 'N/A')}

=== 수집된 데이터 ===
{json.dumps(data, indent=2, ensure_ascii=False)}

=== 분석 요청 ===
위 데이터를 바탕으로 다음 형식의 JSON으로 보안 분석 결과를 제공해주세요:

{{
  "security_report": {{
    "executive_summary": {{
      "overall_score": 85,
      "critical_issues": 2,
      "high_issues": 5,
      "medium_issues": 8,
      "recommendations_count": 10
    }},
    "detailed_analysis": {{
      "ec2_security": {{
        "score": 80,
        "issues": ["보안 그룹에서 0.0.0.0/0 허용", "암호화되지 않은 EBS 볼륨"],
        "recommendations": ["보안 그룹 규칙 검토", "EBS 암호화 활성화"]
      }},
      "s3_security": {{
        "score": 90,
        "issues": ["퍼블릭 액세스 허용 버킷"],
        "recommendations": ["버킷 정책 검토", "암호화 설정"]
      }},
      "iam_security": {{
        "score": 75,
        "issues": ["MFA 미설정 사용자", "과도한 권한"],
        "recommendations": ["MFA 강제 설정", "최소 권한 원칙 적용"]
      }},
      "network_security": {{
        "score": 70,
        "issues": ["위험한 보안 그룹 규칙"],
        "recommendations": ["보안 그룹 정리", "네트워크 ACL 검토"]
      }},
      "compliance": {{
        "score": 85,
        "frameworks": ["SOC2", "ISO27001"],
        "gaps": ["로깅 부족", "암호화 정책"]
      }}
    }},
    "recommendations": [
      {{
        "priority": "HIGH",
        "category": "IAM",
        "title": "MFA 설정 강화",
        "description": "모든 IAM 사용자에 대해 MFA를 강제 설정하세요.",
        "impact": "계정 보안 크게 향상",
        "effort": "Medium"
      }}
    ]
  }}
}}

한국어로 상세하고 실용적인 분석을 제공해주세요.
"""
        
        # Q CLI 실행을 위한 환경 변수 설정
        env = os.environ.copy()
        if credentials:
            env.update({
                'AWS_ACCESS_KEY_ID': credentials.get('AWS_ACCESS_KEY_ID', ''),
                'AWS_SECRET_ACCESS_KEY': credentials.get('AWS_SECRET_ACCESS_KEY', ''),
                'AWS_SESSION_TOKEN': credentials.get('AWS_SESSION_TOKEN', ''),
                'AWS_DEFAULT_REGION': 'ap-northeast-2',
                'AWS_EC2_METADATA_DISABLED': 'true'
            })
        
        # Q CLI 명령어 구성
        q_cli_path = '/root/.local/bin/q'
        cmd = [
            q_cli_path, 'chat',
            '--no-interactive',
            '--trust-all-tools',
            analysis_prompt
        ]
        
        print(f"[DEBUG] Q CLI 명령어 실행: {' '.join(cmd[:3])}... (프롬프트 생략)", flush=True)
        
        # 컨텍스트 파일이 있으면 로드
        if os.path.exists(context_file):
            with open(context_file, 'r', encoding='utf-8') as f:
                context_content = f.read()
            print(f"[DEBUG] 컨텍스트 파일 로드: {context_file}", flush=True)
            # 컨텍스트를 프롬프트에 추가
            cmd[-1] = f"{context_content}\n\n{analysis_prompt}"
        
        # Q CLI 실행
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5분 타임아웃
            env=env
        )
        
        print(f"[DEBUG] Q CLI 완료. 반환코드: {result.returncode}", flush=True)
        
        if result.returncode != 0:
            print(f"[ERROR] Q CLI 실패: {result.stderr}", flush=True)
            # 실패시 기본 분석 결과 반환
            data['analysis'] = {
                "error": "Q CLI 분석 실패",
                "raw_output": result.stderr,
                "security_report": {
                    "executive_summary": {
                        "overall_score": 0,
                        "critical_issues": 0,
                        "high_issues": 0,
                        "medium_issues": 0,
                        "recommendations_count": 0
                    }
                }
            }
            return data
        
        # Q CLI 출력에서 JSON 추출
        output = result.stdout.strip()
        print(f"[DEBUG] Q CLI 출력 길이: {len(output)} 문자", flush=True)
        
        # JSON 부분만 추출 (```json과 ``` 사이의 내용)
        json_match = None
        if '```json' in output:
            start = output.find('```json') + 7
            end = output.find('```', start)
            if end != -1:
                json_text = output[start:end].strip()
                try:
                    json_match = json.loads(json_text)
                except json.JSONDecodeError as e:
                    print(f"[DEBUG] JSON 파싱 실패: {e}", flush=True)
        
        # JSON이 없으면 전체 출력에서 JSON 찾기
        if not json_match:
            try:
                # 출력 전체를 JSON으로 파싱 시도
                json_match = json.loads(output)
            except json.JSONDecodeError:
                print(f"[DEBUG] 전체 출력에서 JSON 파싱 실패", flush=True)
        
        if json_match:
            print(f"[DEBUG] ✅ Q CLI 분석 결과 파싱 성공", flush=True)
            data['analysis'] = json_match
        else:
            print(f"[DEBUG] ⚠️ JSON 파싱 실패, raw 출력 저장", flush=True)
            data['analysis'] = {
                "raw_output": output,
                "parsed": False,
                "security_report": {
                    "executive_summary": {
                        "overall_score": 0,
                        "critical_issues": 0,
                        "high_issues": 0,
                        "medium_issues": 0,
                        "recommendations_count": 0
                    }
                }
            }
        
        # 분석된 데이터를 다시 파일에 저장
        with open(json_file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"[DEBUG] ✅ Q CLI 분석 완료 및 저장", flush=True)
        return data
        
    except subprocess.TimeoutExpired:
        print(f"[ERROR] ❌ Q CLI 분석 타임아웃 (300초)", flush=True)
        return data
    except Exception as e:
        print(f"[ERROR] ❌ Q CLI 분석 실패: {e}", flush=True)
        traceback.print_exc()
        return data

def normalize_security_report_json(data):
    """
    Q CLI가 생성한 JSON을 템플릿 형식으로 변환
    Reference 코드의 normalize_security_report_json 함수를 재사용
    
    Args:
        data (dict): Q CLI 분석 결과 데이터
    
    Returns:
        dict: 정규화된 데이터
    """
    try:
        print(f"[DEBUG] 📝 월간 보고서 JSON 정규화 시작", flush=True)
        
        # security_report 래퍼가 있는 경우 언래핑
        if 'analysis' in data and isinstance(data['analysis'], dict):
            analysis = data['analysis']
            if 'security_report' in analysis and isinstance(analysis['security_report'], dict):
                print(f"[DEBUG] security_report 래퍼 감지, 언래핑", flush=True)
                security_report = analysis['security_report']
                
                # 기존 데이터에 분석 결과 병합
                if 'executive_summary' in security_report:
                    data['executive_summary'] = security_report['executive_summary']
                
                if 'detailed_analysis' in security_report:
                    data['detailed_analysis'] = security_report['detailed_analysis']
                
                if 'recommendations' in security_report:
                    data['recommendations'] = security_report['recommendations']
        
        print(f"[DEBUG] ✅ JSON 정규화 완료", flush=True)
        return data
        
    except Exception as e:
        print(f"[ERROR] ❌ JSON 정규화 실패: {e}", flush=True)
        return data
def generate_security_report(account_id, start_date_str, end_date_str, region='ap-northeast-2', credentials=None):
    """
    전체 월간 보고서 생성 워크플로우
    1. Raw 데이터 수집 (boto3)
    2. Q CLI 분석
    3. HTML 보고서 생성
    
    Args:
        account_id (str): AWS 계정 ID
        start_date_str (str): 시작 날짜 (YYYY-MM-DD)
        end_date_str (str): 종료 날짜 (YYYY-MM-DD)
        region (str): AWS 리전
        credentials (dict): AWS 자격증명
    
    Returns:
        dict: 결과 정보 (json_path, html_path, success)
    """
    try:
        print(f"[DEBUG] 🚀 월간 보고서 생성 시작: 계정 {account_id}", flush=True)
        
        # 1. Raw 데이터 수집
        print(f"[DEBUG] 1️⃣ Raw 데이터 수집 중...", flush=True)
        raw_data = collect_raw_security_data(
            account_id=account_id,
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            region=region,
            credentials=credentials
        )
        
        # 2. JSON 파일 저장
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        json_filename = f"security_data_{account_id}_{timestamp}.json"
        
        # /tmp/reports 디렉터리 생성
        os.makedirs('/tmp/reports', exist_ok=True)
        json_file_path = os.path.join('/tmp/reports', json_filename)
        
        with open(json_file_path, 'w', encoding='utf-8') as f:
            json.dump(raw_data, f, indent=2, ensure_ascii=False)
        
        print(f"[DEBUG] ✅ Raw 데이터 저장 완료: {json_file_path}", flush=True)
        
        # 3. Q CLI 분석
        print(f"[DEBUG] 2️⃣ Q CLI 분석 중...", flush=True)
        analyzed_data = analyze_security_data_with_qcli(
            json_file_path=json_file_path,
            credentials=credentials
        )
        
        # 4. JSON 정규화
        print(f"[DEBUG] 3️⃣ JSON 정규화 중...", flush=True)
        normalized_data = normalize_security_report_json(analyzed_data)
        
        # 정규화된 데이터 다시 저장
        with open(json_file_path, 'w', encoding='utf-8') as f:
            json.dump(normalized_data, f, indent=2, ensure_ascii=False)
        
        # 5. HTML 보고서 생성
        print(f"[DEBUG] 4️⃣ HTML 보고서 생성 중...", flush=True)
        html_file_path = generate_html_report(json_file_path)
        
        if html_file_path:
            print(f"[DEBUG] ✅ 월간 보고서 생성 완료!", flush=True)
            print(f"[DEBUG] JSON: {json_file_path}", flush=True)
            print(f"[DEBUG] HTML: {html_file_path}", flush=True)
            
            return {
                "success": True,
                "json_path": json_file_path,
                "html_path": html_file_path,
                "account_id": account_id,
                "period": f"{start_date_str} ~ {end_date_str}"
            }
        else:
            print(f"[ERROR] ❌ HTML 보고서 생성 실패", flush=True)
            return {
                "success": False,
                "json_path": json_file_path,
                "html_path": None,
                "error": "HTML 보고서 생성 실패"
            }
            
    except Exception as e:
        print(f"[ERROR] ❌ 월간 보고서 생성 실패: {e}", flush=True)
        traceback.print_exc()
        return {
            "success": False,
            "json_path": None,
            "html_path": None,
            "error": str(e)
        }

def get_report_url(html_file_path, base_url="http://localhost:8000"):
    """
    HTML 보고서 파일의 웹 접근 URL 생성
    
    Args:
        html_file_path (str): HTML 파일 경로
        base_url (str): 기본 URL
    
    Returns:
        str: 웹 접근 가능한 URL
    """
    if not html_file_path or not os.path.exists(html_file_path):
        return None
    
    # /tmp/reports/ 경로에서 파일명만 추출
    filename = os.path.basename(html_file_path)
    url = f"{base_url}/reports/{filename}"
    
    print(f"[DEBUG] 📊 보고서 URL 생성: {url}", flush=True)
    return url