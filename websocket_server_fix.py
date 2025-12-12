#!/usr/bin/env python3
"""
generate_html_report 함수 - 수정 버전
"""

def generate_html_report(data):
    """JSON 데이터를 월간 보안 점검 HTML 보고서로 변환
    
    Args:
        data (dict): 보안 데이터 딕셔너리
    
    Returns:
        str: HTML 보고서 콘텐츠 또는 None
    """
    try:
        # data가 dict인지 확인
        if not isinstance(data, dict):
            raise TypeError(f"data는 dict여야 하는데 {type(data)}입니다")
        
        print(f"[DEBUG] HTML 보고서 생성 시작", flush=True)
        
        # datetime 객체를 JSON 직렬화 가능한 형식으로 변환
        data = convert_datetime_to_json_serializable(data)

        # HTML 템플릿 읽기
        # 현재 스크립트 디렉토리 기준으로 템플릿 경로 설정
        script_dir = os.path.dirname(os.path.abspath(__file__))
        template_path = os.path.join(script_dir, 'templates', 'json_report_template.html')
        
        print(f"[DEBUG] 템플릿 경로: {template_path}", flush=True)
        
        # 템플릿 파일 로드 (필수)
        if not os.path.exists(template_path):
            print(f"[ERROR] 템플릿 파일 없음: {template_path}", flush=True)
            raise FileNotFoundError(f"템플릿 파일을 찾을 수 없습니다: {template_path}")
        
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                template = f.read()
            print(f"[DEBUG] 템플릿 파일에서 로드 완료 (크기: {len(template)} bytes)", flush=True)
        except Exception as e:
            print(f"[ERROR] 템플릿 파일 로드 실패: {e}", flush=True)
            raise
        
        # 템플릿이 없으면 에러
        if not template:
            raise ValueError("템플릿이 비어있습니다")
        
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
        
        template_vars.update({
            'ebs_total': ebs_total,
            'ebs_encrypted': ebs_encrypted,
            'ebs_rate': ebs_rate,
            'rds_encrypted': rds_encryption.get('encrypted', 0),
            'rds_encrypted_rate': round(rds_encryption.get('encrypted_rate', 0) * 100, 1),
        })
        
        # 준수율 클래스 설정
        template_vars.update({
            'ebs_compliance_class': get_compliance_class(template_vars['ebs_rate']),
            's3_compliance_class': get_compliance_class(template_vars['s3_encrypted_rate']),
            'rds_compliance_class': get_compliance_class(template_vars['rds_encrypted_rate']),
        })
        
        # Critical 이슈 계산
        critical_issues = calculate_critical_issues(data)
        template_vars.update({
            'critical_issues_count': len(critical_issues),
            'critical_issues_section': generate_critical_issues_section(critical_issues),
        })
        
        # Trusted Advisor 데이터 처리
        ta_data = data.get('trusted_advisor', {})
        ta_summary = process_trusted_advisor_data(ta_data.get('checks', []))
        template_vars.update(ta_summary)
        
        # CloudTrail 데이터 처리
        ct_data = data.get('cloudtrail_events', {})
        template_vars.update({
            'cloudtrail_days': ct_data.get('summary', {}).get('period_days', 31),
            'cloudtrail_critical_rows': generate_cloudtrail_rows(ct_data.get('critical_events', {})),
        })
        
        # CloudWatch 데이터 처리
        cw_data = data.get('cloudwatch', {})
        cw_summary = cw_data.get('summary', {})
        template_vars.update({
            'cloudwatch_alarms_total': cw_summary.get('total', 0),
            'cloudwatch_alarms_in_alarm': cw_summary.get('in_alarm', 0),
            'cloudwatch_alarms_ok': cw_summary.get('ok', 0),
            'cloudwatch_alarms_insufficient': cw_summary.get('insufficient_data', 0),
            'cloudwatch_alarm_rows': generate_cloudwatch_rows(cw_data.get('alarms', [])),
        })
        
        # EBS 미암호화 섹션
        template_vars['ebs_unencrypted_section'] = generate_ebs_unencrypted_section(ebs_data)
        
        # S3 보안 이슈 섹션
        template_vars['s3_security_issues_section'] = generate_s3_security_issues_section(s3_data.get('buckets', []))
        
        # 템플릿에 변수 적용
        html_content = template.format(**template_vars)
        
        print(f"[DEBUG] ✅ HTML 보고서 콘텐츠 생성 완료 (크기: {len(html_content)} bytes)", flush=True)
        return html_content
        
    except Exception as e:
        print(f"[ERROR] ❌ HTML 보고서 생성 실패: {str(e)}", flush=True)
        import traceback
        print(f"[ERROR] {traceback.format_exc()}", flush=True)
        return None
