"""
AWS 월간 보고서 생성 모듈
Reference 코드의 collect_raw_security_data와 generate_html_report 기능을 재사용
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
    Reference 코드의 collect_raw_security_data 함수를 재사용
    
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
        
        # S3 요약 정보 계산
        total_buckets = len(buckets_raw)
        encrypted_buckets = sum(1 for b in buckets_raw if b.get('Encryption'))
        
        report_data['resources']['s3'] = {
            "summary": {
                "total": total_buckets,
                "encrypted": encrypted_buckets
            },
            "buckets": buckets_raw
        }
        print(f"[DEBUG] ✅ S3 수집 완료: {total_buckets}개 (암호화: {encrypted_buckets}개)", flush=True)
    except Exception as e:
        print(f"[ERROR] ❌ S3 수집 실패: {e}", flush=True)
        report_data['resources']['s3'] = {"summary": {"total": 0, "encrypted": 0}, "buckets": []}
    
    # 3. RDS 인스턴스 수집
    print(f"[DEBUG] 📦 RDS 인스턴스 수집 중...", flush=True)
    try:
        rds = session.client('rds', region_name=region)
        rds_response = rds.describe_db_instances()
        
        rds_instances = rds_response.get('DBInstances', [])
        
        report_data['resources']['rds'] = {
            "summary": {
                "total": len(rds_instances)
            },
            "instances": rds_instances
        }
        print(f"[DEBUG] ✅ RDS 수집 완료: {len(rds_instances)}개", flush=True)
    except Exception as e:
        print(f"[ERROR] ❌ RDS 수집 실패: {e}", flush=True)
        report_data['resources']['rds'] = {"summary": {"total": 0}, "instances": []}
    
    # 4. Lambda 함수 수집
    print(f"[DEBUG] 📦 Lambda 함수 수집 중...", flush=True)
    try:
        lambda_client = session.client('lambda', region_name=region)
        lambda_response = lambda_client.list_functions()
        
        lambda_functions = lambda_response.get('Functions', [])
        
        report_data['resources']['lambda'] = {
            "summary": {
                "total": len(lambda_functions)
            },
            "functions": lambda_functions
        }
        print(f"[DEBUG] ✅ Lambda 수집 완료: {len(lambda_functions)}개", flush=True)
    except Exception as e:
        print(f"[ERROR] ❌ Lambda 수집 실패: {e}", flush=True)
        report_data['resources']['lambda'] = {"summary": {"total": 0}, "functions": []}
    
    # 5. IAM 사용자 수집
    print(f"[DEBUG] 📦 IAM 사용자 수집 중...", flush=True)
    try:
        iam_users_response = iam.list_users()
        users_raw = iam_users_response.get('Users', [])
        
        # MFA 활성화 상태 확인
        users_with_mfa = []
        for user in users_raw:
            username = user['UserName']
            try:
                mfa_devices = iam.list_mfa_devices(UserName=username)
                user['MFADevices'] = mfa_devices.get('MFADevices', [])
                user['MFAEnabled'] = len(mfa_devices.get('MFADevices', [])) > 0
                users_with_mfa.append(user)
            except Exception as e:
                print(f"[DEBUG] 사용자 {username} MFA 확인 실패: {e}", flush=True)
                user['MFADevices'] = []
                user['MFAEnabled'] = False
                users_with_mfa.append(user)
        
        mfa_enabled_count = sum(1 for u in users_with_mfa if u.get('MFAEnabled', False))
        
        report_data['iam_security']['users'] = {
            "total": len(users_with_mfa),
            "mfa_enabled": mfa_enabled_count,
            "details": users_with_mfa
        }
        print(f"[DEBUG] ✅ IAM 사용자 수집 완료: {len(users_with_mfa)}개 (MFA: {mfa_enabled_count}개)", flush=True)
    except Exception as e:
        print(f"[ERROR] ❌ IAM 사용자 수집 실패: {e}", flush=True)
        report_data['iam_security']['users'] = {"total": 0, "mfa_enabled": 0, "details": []}
    
    # 6. 보안 그룹 수집
    print(f"[DEBUG] 📦 보안 그룹 수집 중...", flush=True)
    try:
        sg_response = ec2.describe_security_groups()
        security_groups = sg_response.get('SecurityGroups', [])
        
        # 위험한 보안 그룹 필터링 (0.0.0.0/0 허용)
        risky_sgs = []
        for sg in security_groups:
            for rule in sg.get('IpPermissions', []):
                for ip_range in rule.get('IpRanges', []):
                    if ip_range.get('CidrIp') == '0.0.0.0/0':
                        risky_sgs.append(sg)
                        break
                if sg in risky_sgs:
                    break
        
        report_data['security_groups'] = {
            "total": len(security_groups),
            "risky": len(risky_sgs),
            "details": risky_sgs
        }
        print(f"[DEBUG] ✅ 보안 그룹 수집 완료: {len(security_groups)}개 (위험: {len(risky_sgs)}개)", flush=True)
    except Exception as e:
        print(f"[ERROR] ❌ 보안 그룹 수집 실패: {e}", flush=True)
        report_data['security_groups'] = {"total": 0, "risky": 0, "details": []}
    
    # 7. EBS 볼륨 암호화 상태 수집
    print(f"[DEBUG] 📦 EBS 볼륨 수집 중...", flush=True)
    try:
        ebs_response = ec2.describe_volumes()
        volumes = ebs_response.get('Volumes', [])
        
        encrypted_volumes = sum(1 for v in volumes if v.get('Encrypted', False))
        
        report_data['encryption']['ebs'] = {
            "total": len(volumes),
            "encrypted": encrypted_volumes,
            "details": volumes
        }
        print(f"[DEBUG] ✅ EBS 볼륨 수집 완료: {len(volumes)}개 (암호화: {encrypted_volumes}개)", flush=True)
    except Exception as e:
        print(f"[ERROR] ❌ EBS 볼륨 수집 실패: {e}", flush=True)
        report_data['encryption']['ebs'] = {"total": 0, "encrypted": 0, "details": []}
    
    # 8. Trusted Advisor 수집 (Business/Enterprise 플랜 필요)
    print(f"[DEBUG] 📦 Trusted Advisor 수집 중...", flush=True)
    try:
        # Trusted Advisor 체크 목록 가져오기
        checks_response = support.describe_trusted_advisor_checks(language='en')
        checks = checks_response.get('checks', [])
        
        # 보안 관련 체크만 필터링
        security_checks = [c for c in checks if 'security' in c.get('category', '').lower()]
        
        # 각 체크의 결과 가져오기
        check_results = []
        for check in security_checks[:5]:  # 처음 5개만 (API 제한 고려)
            try:
                result = support.describe_trusted_advisor_check_result(
                    checkId=check['id'],
                    language='en'
                )
                check_results.append({
                    'check': check,
                    'result': result.get('result', {})
                })
            except Exception as e:
                print(f"[DEBUG] Trusted Advisor 체크 {check['name']} 실패: {e}", flush=True)
        
        report_data['trusted_advisor'] = {
            "available": True,
            "security_checks": len(security_checks),
            "results": check_results
        }
        print(f"[DEBUG] ✅ Trusted Advisor 수집 완료: {len(security_checks)}개 체크", flush=True)
    except Exception as e:
        print(f"[DEBUG] ⚠️ Trusted Advisor 수집 실패 (Business/Enterprise 플랜 필요): {e}", flush=True)
        report_data['trusted_advisor'] = {
            "available": False,
            "error": str(e),
            "security_checks": 0,
            "results": []
        }
    
    # 9. CloudTrail 이벤트 수집 (최근 7일)
    print(f"[DEBUG] 📦 CloudTrail 이벤트 수집 중...", flush=True)
    try:
        # UTC+9를 UTC로 변환
        from datetime import timezone
        
        # 시작/종료 날짜를 datetime으로 변환 (UTC+9 기준)
        start_dt = datetime.strptime(start_date_str, '%Y-%m-%d').replace(tzinfo=timezone(timedelta(hours=9)))
        end_dt = datetime.strptime(end_date_str, '%Y-%m-%d').replace(tzinfo=timezone(timedelta(hours=9)))
        
        # UTC로 변환
        start_utc = start_dt.astimezone(timezone.utc)
        end_utc = end_dt.astimezone(timezone.utc)
        
        # CloudTrail 이벤트 조회 (중요 이벤트만)
        critical_events = [
            'DeleteBucket', 'TerminateInstances', 'DeleteUser', 'CreateAccessKey',
            'DeleteAccessKey', 'AttachUserPolicy', 'DetachUserPolicy'
        ]
        
        all_events = []
        for event_name in critical_events:
            try:
                events_response = cloudtrail.lookup_events(
                    LookupAttributes=[
                        {
                            'AttributeKey': 'EventName',
                            'AttributeValue': event_name
                        }
                    ],
                    StartTime=start_utc,
                    EndTime=end_utc,
                    MaxItems=50  # 이벤트당 최대 50개
                )
                
                events = events_response.get('Events', [])
                all_events.extend(events)
                print(f"[DEBUG] {event_name}: {len(events)}개 이벤트", flush=True)
            except Exception as e:
                print(f"[DEBUG] CloudTrail 이벤트 {event_name} 조회 실패: {e}", flush=True)
        
        report_data['cloudtrail_events'] = {
            "period_start": start_date_str,
            "period_end": end_date_str,
            "total_events": len(all_events),
            "events": all_events
        }
        print(f"[DEBUG] ✅ CloudTrail 이벤트 수집 완료: {len(all_events)}개", flush=True)
    except Exception as e:
        print(f"[ERROR] ❌ CloudTrail 이벤트 수집 실패: {e}", flush=True)
        report_data['cloudtrail_events'] = {
            "period_start": start_date_str,
            "period_end": end_date_str,
            "total_events": 0,
            "events": []
        }
    
    # 10. CloudWatch 알람 수집
    print(f"[DEBUG] 📦 CloudWatch 알람 수집 중...", flush=True)
    try:
        alarms_response = cloudwatch.describe_alarms()
        alarms = alarms_response.get('MetricAlarms', [])
        
        # 알람 상태별 분류
        alarm_states = {}
        for alarm in alarms:
            state = alarm.get('StateValue', 'UNKNOWN')
            alarm_states[state] = alarm_states.get(state, 0) + 1
        
        report_data['cloudwatch'] = {
            "total_alarms": len(alarms),
            "states": alarm_states,
            "alarms": alarms
        }
        print(f"[DEBUG] ✅ CloudWatch 알람 수집 완료: {len(alarms)}개", flush=True)
    except Exception as e:
        print(f"[ERROR] ❌ CloudWatch 알람 수집 실패: {e}", flush=True)
        report_data['cloudwatch'] = {"total_alarms": 0, "states": {}, "alarms": []}
    
    # datetime 객체를 JSON 직렬화 가능한 형식으로 변환
    print(f"[DEBUG] 📝 datetime 객체 변환 중...", flush=True)
    report_data = convert_datetime_to_json_serializable(report_data)
    
    print(f"[DEBUG] ✅ 전체 데이터 수집 완료", flush=True)
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
        
        # CloudTrail 데이터 처리
        ct_data = data.get('cloudtrail_events', {})
        template_vars.update({
            'cloudtrail_days': 30,
            'cloudtrail_critical_rows': generate_cloudtrail_rows(ct_data.get('events', [])),
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
    """Trusted Advisor 데이터 처리"""
    if not ta_data.get('available', False):
        return {
            'ta_security_error': 0,
            'ta_security_warning': 0,
            'ta_fault_tolerance_error': 0,
            'ta_fault_tolerance_warning': 0,
            'ta_cost_warning': 0,
            'ta_performance_warning': 0,
        }
    
    # 실제 TA 데이터가 있으면 처리
    results = ta_data.get('results', [])
    summary = {
        'ta_security_error': 0,
        'ta_security_warning': 0,
        'ta_fault_tolerance_error': 0,
        'ta_fault_tolerance_warning': 0,
        'ta_cost_warning': 0,
        'ta_performance_warning': 0,
    }
    
    for result in results:
        check = result.get('check', {})
        check_result = result.get('result', {})
        category = check.get('category', '').lower()
        status = check_result.get('status', '').lower()
        
        if 'security' in category:
            if status == 'error':
                summary['ta_security_error'] += 1
            elif status == 'warning':
                summary['ta_security_warning'] += 1
        elif 'fault' in category:
            if status == 'error':
                summary['ta_fault_tolerance_error'] += 1
            elif status == 'warning':
                summary['ta_fault_tolerance_warning'] += 1
        elif 'cost' in category and status == 'warning':
            summary['ta_cost_warning'] += 1
        elif 'performance' in category and status == 'warning':
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
    """Trusted Advisor 에러 행 생성"""
    if not ta_data.get('available', False):
        return '<tr><td colspan="4" class="text-center text-muted">Trusted Advisor 데이터를 사용할 수 없습니다. (Business/Enterprise 플랜 필요)</td></tr>'
    
    results = ta_data.get('results', [])
    error_results = [r for r in results if r.get('result', {}).get('status', '').lower() == 'error']
    
    if not error_results:
        return '<tr><td colspan="4" class="text-center text-success">Error 상태의 항목이 없습니다.</td></tr>'
    
    rows = []
    for result in error_results[:10]:  # 최대 10개
        check = result.get('check', {})
        check_result = result.get('result', {})
        
        rows.append(f'''
        <tr>
            <td>{check.get('category', 'N/A')}</td>
            <td>{check.get('name', 'N/A')}</td>
            <td><span class="badge badge-critical">ERROR</span></td>
            <td>{len(check_result.get('flaggedResources', []))}</td>
        </tr>
        ''')
    
    return ''.join(rows)

def generate_cloudtrail_rows(events):
    """CloudTrail 이벤트 행 생성"""
    if not events:
        return '<tr><td colspan="5" class="text-center text-muted">분석 기간 중 중요 이벤트가 없습니다.</td></tr>'
    
    # 이벤트 타입별 분류
    event_summary = {}
    for event in events:
        event_name = event.get('EventName', 'Unknown')
        if event_name not in event_summary:
            event_summary[event_name] = {
                'count': 0,
                'severity': get_event_severity(event_name),
                'category': get_event_category(event_name)
            }
        event_summary[event_name]['count'] += 1
    
    rows = []
    for event_name, info in event_summary.items():
        severity_class = {
            'HIGH': 'critical',
            'MEDIUM': 'warning',
            'LOW': 'info'
        }.get(info['severity'], 'info')
        
        rows.append(f'''
        <tr>
            <td>{event_name}</td>
            <td><span class="badge badge-{severity_class}">{info['severity']}</span></td>
            <td>{info['category']}</td>
            <td>{info['count']}</td>
            <td>{get_event_description(event_name)}</td>
        </tr>
        ''')
    
    return ''.join(rows[:10])  # 최대 10개

def generate_cloudwatch_rows(alarms):
    """CloudWatch 알람 행 생성"""
    if not alarms:
        return '<tr><td colspan="4" class="text-center text-muted">CloudWatch 알람이 없습니다.</td></tr>'
    
    rows = []
    for alarm in alarms[:10]:  # 최대 10개
        name = alarm.get('AlarmName', 'N/A')
        state = alarm.get('StateValue', 'N/A')
        metric = alarm.get('MetricName', 'N/A')
        threshold = alarm.get('Threshold', 'N/A')
        
        state_class = {
            'OK': 'success',
            'ALARM': 'critical',
            'INSUFFICIENT_DATA': 'warning'
        }.get(state, 'secondary')
        
        rows.append(f'''
        <tr>
            <td>{name}</td>
            <td><span class="badge badge-{state_class}">{state}</span></td>
            <td>{metric}</td>
            <td>{threshold}</td>
        </tr>
        ''')
    
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

# HTML 생성 헬퍼 함수들
def generate_ec2_rows(instances):
    """EC2 인스턴스 테이블 행 생성"""
    if not instances:
        return "<tr><td colspan='5' class='text-center text-muted'>EC2 인스턴스가 없습니다.</td></tr>"
    
    rows = []
    for instance in instances[:10]:  # 최대 10개만 표시
        instance_id = instance.get('InstanceId', 'N/A')
        instance_type = instance.get('InstanceType', 'N/A')
        state = instance.get('State', {}).get('Name', 'N/A')
        
        # 태그에서 Name 찾기
        name = 'N/A'
        for tag in instance.get('Tags', []):
            if tag.get('Key') == 'Name':
                name = tag.get('Value', 'N/A')
                break
        
        # 상태에 따른 색상
        state_class = 'success' if state == 'running' else 'secondary'
        
        rows.append(f"""
        <tr>
            <td>{instance_id}</td>
            <td>{name}</td>
            <td>{instance_type}</td>
            <td><span class="badge badge-{state_class}">{state}</span></td>
            <td>{instance.get('LaunchTime', 'N/A')}</td>
        </tr>
        """)
    
    return ''.join(rows)

def generate_s3_rows(buckets):
    """S3 버킷 테이블 행 생성"""
    if not buckets:
        return "<tr><td colspan='4' class='text-center text-muted'>S3 버킷이 없습니다.</td></tr>"
    
    rows = []
    for bucket in buckets[:10]:  # 최대 10개만 표시
        name = bucket.get('Name', 'N/A')
        location = bucket.get('Location', 'us-east-1')
        encrypted = '✅' if bucket.get('Encryption') else '❌'
        versioning = '✅' if bucket.get('Versioning', {}).get('Status') == 'Enabled' else '❌'
        
        rows.append(f"""
        <tr>
            <td>{name}</td>
            <td>{location}</td>
            <td class="text-center">{encrypted}</td>
            <td class="text-center">{versioning}</td>
        </tr>
        """)
    
    return ''.join(rows)

def generate_rds_content(instances):
    """RDS 인스턴스 내용 생성"""
    if not instances:
        return "<p class='text-muted'>RDS 인스턴스가 없습니다.</p>"
    
    content = []
    for instance in instances[:5]:  # 최대 5개만 표시
        db_id = instance.get('DBInstanceIdentifier', 'N/A')
        engine = instance.get('Engine', 'N/A')
        multi_az = '✅' if instance.get('MultiAZ', False) else '❌'
        encrypted = '✅' if instance.get('StorageEncrypted', False) else '❌'
        
        content.append(f"""
        <div class="mb-2">
            <strong>{db_id}</strong> ({engine}) - Multi-AZ: {multi_az}, 암호화: {encrypted}
        </div>
        """)
    
    return ''.join(content)

def generate_lambda_content(functions):
    """Lambda 함수 내용 생성"""
    if not functions:
        return "<p class='text-muted'>Lambda 함수가 없습니다.</p>"
    
    content = []
    for func in functions[:5]:  # 최대 5개만 표시
        name = func.get('FunctionName', 'N/A')
        runtime = func.get('Runtime', 'N/A')
        
        content.append(f"""
        <div class="mb-2">
            <strong>{name}</strong> ({runtime})
        </div>
        """)
    
    return ''.join(content)

def generate_iam_users_rows(users):
    """IAM 사용자 테이블 행 생성"""
    if not users:
        return "<tr><td colspan='4' class='text-center text-muted'>IAM 사용자가 없습니다.</td></tr>"
    
    rows = []
    for user in users[:10]:  # 최대 10개만 표시
        username = user.get('UserName', 'N/A')
        created = user.get('CreateDate', 'N/A')
        mfa = '✅' if user.get('MFAEnabled', False) else '❌'
        last_used = user.get('PasswordLastUsed', 'N/A')
        
        rows.append(f"""
        <tr>
            <td>{username}</td>
            <td>{created}</td>
            <td class="text-center">{mfa}</td>
            <td>{last_used}</td>
        </tr>
        """)
    
    return ''.join(rows)

def generate_sg_risky_rows(security_groups):
    """위험한 보안 그룹 테이블 행 생성"""
    if not security_groups:
        return "<tr><td colspan='4' class='text-center text-success'>위험한 보안 그룹이 없습니다.</td></tr>"
    
    rows = []
    for sg in security_groups[:10]:  # 최대 10개만 표시
        sg_id = sg.get('GroupId', 'N/A')
        sg_name = sg.get('GroupName', 'N/A')
        description = sg.get('Description', 'N/A')
        
        # 위험한 규칙 찾기
        risky_rules = []
        for rule in sg.get('IpPermissions', []):
            for ip_range in rule.get('IpRanges', []):
                if ip_range.get('CidrIp') == '0.0.0.0/0':
                    port = rule.get('FromPort', 'All')
                    risky_rules.append(f"Port {port}")
        
        rules_text = ', '.join(risky_rules) if risky_rules else 'N/A'
        
        rows.append(f"""
        <tr>
            <td>{sg_id}</td>
            <td>{sg_name}</td>
            <td>{description}</td>
            <td class="text-danger">{rules_text}</td>
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