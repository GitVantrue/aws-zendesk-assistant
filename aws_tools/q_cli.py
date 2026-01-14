"""
Q CLI 호출 유틸리티
Reference 코드의 Q CLI 호출 로직 재사용
"""
import subprocess
import os
import re
from typing import Dict, Optional, Any
from utils.logging_config import log_debug, log_error, log_info


async def call_q_cli(
    question: str,
    account_id: Optional[str] = None,
    credentials: Optional[Dict[str, str]] = None,
    context_file: Optional[str] = None,
    question_type: str = "general",
    timeout: int = 600
) -> Dict[str, Any]:
    """
    Q CLI 호출 (Reference 코드 로직 재사용)
    
    Args:
        question: 사용자 질문
        account_id: AWS 계정 ID
        credentials: AWS 자격증명
        context_file: 컨텍스트 파일 경로
        question_type: 질문 유형
        timeout: 타임아웃 (초)
        
    Returns:
        Q CLI 응답 결과
    """
    try:
        log_debug(f"Q CLI 호출 시작: {question_type}")
        
        # 1. 프롬프트 구성
        prompt = build_prompt(question, account_id, context_file, question_type)
        
        # 2. 환경 변수 설정
        env_vars = build_environment(credentials)
        
        # 3. Q CLI 명령어 구성
        cmd = ['/root/.local/bin/q', 'chat', '--no-interactive', '--trust-all-tools', prompt]
        
        log_debug(f"Q CLI 명령어: {' '.join(cmd[:3])}... (프롬프트 생략)")
        log_debug(f"타임아웃: {timeout}초")
        
        # 4. Q CLI 실행
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env_vars,
            timeout=timeout
        )
        
        log_debug(f"Q CLI 완료. 반환코드: {result.returncode}")
        
        # 5. 결과 처리
        raw_answer = result.stdout.strip() if result.stdout else ""
        
        if result.returncode == 0 and raw_answer:
            # 정상 성공
            clean_answer = clean_q_cli_output(raw_answer)
            log_info(f"Q CLI 성공: {len(clean_answer)} 문자 (원본: {len(raw_answer)})")
            
            return {
                "success": True,
                "answer": clean_answer,
                "question": question,
                "question_type": question_type,
                "account_id": account_id,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
        elif raw_answer:
            # returncode가 0이 아니지만 출력이 있는 경우 (Q CLI 특성상 가능)
            clean_answer = clean_q_cli_output(raw_answer)
            log_info(f"Q CLI 부분 성공 (코드: {result.returncode}): {len(clean_answer)} 문자")
            
            return {
                "success": True,
                "answer": clean_answer,
                "question": question,
                "question_type": question_type,
                "account_id": account_id,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
        else:
            # 실제 실패
            error_msg = result.stderr.strip() or f"Q CLI 실행 실패 (코드: {result.returncode})"
            log_error(f"Q CLI 실패: {error_msg}")
            
            return {
                "success": False,
                "error": error_msg,
                "question": question,
                "question_type": question_type,
                "account_id": account_id,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
            
    except subprocess.TimeoutExpired:
        log_error(f"Q CLI 타임아웃: {timeout}초 초과")
        return {
            "success": False,
            "error": f"Q CLI 실행 시간 초과 ({timeout}초)",
            "question": question,
            "question_type": question_type,
            "account_id": account_id
        }
    except Exception as e:
        log_error(f"Q CLI 호출 중 오류: {e}")
        return {
            "success": False,
            "error": f"Q CLI 호출 오류: {str(e)}",
            "question": question,
            "question_type": question_type,
            "account_id": account_id
        }


def build_prompt(
    question: str,
    account_id: Optional[str],
    context_file: Optional[str],
    question_type: str
) -> str:
    """
    Q CLI 프롬프트 구성
    
    Args:
        question: 사용자 질문
        account_id: AWS 계정 ID
        context_file: 컨텍스트 파일 경로
        question_type: 질문 유형
        
    Returns:
        구성된 프롬프트
    """
    # 기본 프롬프트
    prompt_parts = []
    
    # 컨텍스트 파일 로드
    if context_file and os.path.exists(context_file):
        try:
            with open(context_file, 'r', encoding='utf-8') as f:
                context_content = f.read()
                prompt_parts.append(f"다음 컨텍스트를 참고하여 답변해주세요:\n\n{context_content}\n\n")
                log_debug(f"컨텍스트 파일 로드: {context_file}")
        except Exception as e:
            log_error(f"컨텍스트 파일 로드 실패: {e}")
    
    # 계정 정보 추가
    if account_id:
        prompt_parts.append(f"AWS 계정 ID: {account_id}\n\n")
    
    # 사용자 질문
    prompt_parts.append(f"질문: {question}")
    
    # 질문 유형별 추가 지침
    if question_type == "general":
        prompt_parts.append("\n\n한국어로 자세하고 정확한 답변을 제공해주세요.")
    elif question_type == "cloudtrail":
        prompt_parts.append("\n\nCloudTrail 로그 분석 결과를 한국어로 제공해주세요.")
    elif question_type == "cloudwatch":
        prompt_parts.append("\n\nCloudWatch 메트릭 및 로그 분석 결과를 한국어로 제공해주세요.")
    
    return "".join(prompt_parts)


def build_environment(credentials: Optional[Dict[str, str]]) -> Dict[str, str]:
    """
    Q CLI 실행을 위한 환경 변수 구성 (Reference 코드 로직 적용)
    
    Args:
        credentials: AWS 자격증명
        
    Returns:
        환경 변수 딕셔너리
    """
    # 기본 환경 변수 복사
    env_vars = os.environ.copy()
    
    # AWS 자격증명 설정
    if credentials:
        # Reference 코드와 동일한 방식으로 자격증명 설정
        env_vars['AWS_ACCESS_KEY_ID'] = credentials.get('AWS_ACCESS_KEY_ID', '')
        env_vars['AWS_SECRET_ACCESS_KEY'] = credentials.get('AWS_SECRET_ACCESS_KEY', '')
        env_vars['AWS_SESSION_TOKEN'] = credentials.get('AWS_SESSION_TOKEN', '')
        env_vars['AWS_DEFAULT_REGION'] = 'ap-northeast-2'
        
        # Reference 코드와 동일한 추가 설정
        env_vars['AWS_EC2_METADATA_DISABLED'] = 'true'  # EC2 메타데이터 비활성화
        env_vars['AWS_SDK_LOAD_CONFIG'] = '0'  # 설정 파일 로드 비활성화
        
        log_debug("AWS 자격증명 환경 변수 설정 완료")
        log_debug(f"AWS_ACCESS_KEY_ID: {env_vars['AWS_ACCESS_KEY_ID'][:20]}...")
        log_debug(f"AWS_SESSION_TOKEN 존재: {bool(env_vars.get('AWS_SESSION_TOKEN'))}")
    
    # 한국어 설정
    env_vars['LANG'] = 'ko_KR.UTF-8'
    env_vars['LC_ALL'] = 'ko_KR.UTF-8'
    
    # MCP 서버 초기화 타임아웃 설정 (Reference 코드와 동일)
    env_vars['Q_MCP_INIT_TIMEOUT'] = '10000'  # 10초
    
    return env_vars


def clean_q_cli_output(text: str) -> str:
    """
    Q CLI 출력 정리 - Reference 코드의 simple_clean_output 로직 재사용
    도구 사용 내역 제거하고 깔끔한 답변만 추출
    """
    if not text or not text.strip():
        return "응답을 처리할 수 없습니다."
    
    # ANSI 색상 코드 및 특수 문자 제거
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    clean_text = ansi_escape.sub('', text)
    
    # 유니코드 박스 문자 및 로딩 애니메이션 제거
    clean_text = re.sub(r'[⢀-⣿]+', '', clean_text)  # Braille 패턴 (로딩 애니메이션)
    clean_text = re.sub(r'[╭╮╯╰─│┌┐└┘├┤┬┴┼]', '', clean_text)  # 박스 문자
    clean_text = re.sub(r'[•●○◦▪▫]', '', clean_text)  # 불릿 포인트

    # 도구 사용 및 명령어 실행 관련 라인 제거 패턴
    tool_patterns = [
        r'🛠️.*',
        r'●\s+.*',
        r'✓\s+.*',
        r'↳\s+Purpose:.*',
        r'Service name:.*',
        r'Operation name:.*',
        r'Parameters:.*',
        r'Region:.*',
        r'Label:.*',
        r'⋮.*',
        r'.*Using tool:.*',
        r'.*Running.*command:.*',
        r'.*Completed in.*',
        r'.*Execution.*',
        # MCP 서버 도구 호출 로그 패턴 추가
        r'.*Calling MCP tool.*',
        r'.*MCP server.*',
        r'.*Tool call:.*',
        r'.*Tool result:.*',
        r'.*Invoking tool.*',
        r'.*Tool invocation.*',
        r'.*MCP tool execution.*',
        r'.*Tool execution started.*',
        r'.*Tool execution completed.*',
        r'.*Sending tool request.*',
        r'.*Received tool response.*',
        r'.*Reading (file|directory):.*',
        r'.*Successfully read.*',
        r'.*I will run the following.*',
        r'^>.*',
        r'- Name:.*',
        r'- MaxItems:.*',
        r'- Bucket:.*',
        r'- UserName:.*',
        r'\+\s+\d+:.*',
        r'^\s*\d+:.*',
        r'^total \d+',
        r'^drwx.*',
        r'^-rw.*',
        r'^lrwx.*',
        r'^/root/.*',
        r'.*which:.*',
        r'.*pip.*install.*',
        r'.*apt.*update.*',
        r'.*yum.*install.*',
        r'.*git clone.*',
        r'.*bash: line.*',
        r'.*command not found.*',
        r'.*Package.*is already installed.*',
        r'.*Dependencies resolved.*',
        r'.*Transaction Summary.*',
        r'.*Downloading Packages.*',
        r'.*Running transaction.*',
        r'.*Installing.*:.*',
        r'.*Verifying.*:.*',
        r'.*Complete!.*',
        r'.*ERROR: Could not find.*',
        r'.*WARNING:.*pip version.*',
        r'.*Last metadata expiration.*',
        r'.*Nothing to do.*',
        r'.*fatal: destination path.*',
        r'.*cd /root.*',
        r'.*ls -la.*',
        r'.*A newer release.*',
        r'.*Available Versions.*',
        r'.*Run the following command.*',
        r'.*dnf upgrade.*',
        r'.*Release notes.*',
        r'.*Installed:.*',
        r'.*Total download size:.*',
        r'.*Installed size:.*',
        r'.*MB/s.*',
        r'.*kB.*00:00.*',
        r'.*Transaction check.*',
        r'.*Transaction test.*',
        r'.*Preparing.*:.*',
        # Q CLI 특화 패턴 추가
        r'.*Kiro CLI.*',
        r'.*Q Developer CLI.*',
        r'.*kiro\.dev.*',
        r'.*ctrl \+ j.*',
        r'.*ctrl \+ s.*',
        r'.*━+.*',
        r'.*You are chatting with.*',
        r'.*error: Tool approval required.*',
        r'.*Use --trust-all-tools.*',
        r'.*--no-interactive was specified.*',
        r'.*help all commands.*',
        r'.*fuzzy search.*',
        r'.*new lines.*',
        r'╭.*╮',
        r'│.*│',
        r'╰.*╯',
        # 추가 정리 패턴
        r'.*Requirement already satisfied.*',
        r'.*Collecting.*',
        r'.*Downloading.*',
        r'.*Successfully installed.*',
        r'.*Successfully uninstalled.*',
        r'.*Attempting uninstall.*',
        r'.*Found existing installation.*',
        r'.*WARNING: Running pip as.*',
        r'.*PythonDeprecationWarning.*',
        r'.*warnings\.warn.*',
        r'.*filters:.*',
        r'.*which aws.*',
        r'.*urllib3 available.*',
        r'.*boto3 available.*',
        r'.*python3 -c.*',
        r'.*import boto3.*',
        r'.*import json.*',
        r'.*from datetime.*',
        r'.*ec2 = boto3.*',
        r'.*try:.*',
        r'.*except.*',
        r'.*print\(.*',
        r'.*response = ec2.*',
        r'.*running_instances.*',
        r'.*for reservation.*',
        r'.*for instance.*',
        r'.*name_tag.*',
        r'.*if.*Tags.*',
        r'.*for tag.*',
        r'.*if tag.*Key.*',
        r'.*break.*',
        r'.*append.*',
        r'.*InstanceId.*',
        r'.*Name.*',
        r'.*InstanceType.*',
        r'.*State.*',
        r'.*LaunchTime.*',
        r'.*PrivateIpAddress.*',
        r'.*PublicIpAddress.*',
        r'.*VpcId.*',
        r'.*SubnetId.*',
        r'.*strftime.*',
        r'.*get\(.*',
        r'.*enumerate.*',
        r'.*curl -s.*',
        r'.*connect-timeout.*',
        r'.*meta-data.*',
        r'.*echo.*',
        r'.*sts = boto3.*',
        r'.*identity = sts.*',
        r'.*get_caller_identity.*',
        r'.*env \| grep.*',
        r'.*AWS_.*=.*',
        # AWS CLI 설치 및 실행 관련 패턴
        r'.*curl.*awscli.*',
        r'.*unzip.*awscliv2.*',
        r'.*aws/install.*',
        r'.*% Total.*',
        r'.*Dload.*Upload.*',
        r'.*Current.*Spent.*Left.*Speed.*',
        r'.*--:--:--.*',
        r'.*You can now run.*',
        r'.*aws --version.*',
        r'.*aws-cli/.*',
        r'.*Python/.*Linux/.*',
        r'.*exec-env/.*',
        # JSON 출력 관련 패턴
        r'^\s*\{.*',
        r'^\s*\}.*',
        r'^\s*".*":.*',
        r'^\s*\[.*',
        r'^\s*\].*',
        r'.*"ReservationId".*',
        r'.*"OwnerId".*',
        r'.*"Groups".*',
        r'.*"Instances".*',
        r'.*"Architecture".*',
        r'.*"BlockDeviceMappings".*',
        r'.*"ClientToken".*',
        r'.*"EbsOptimized".*',
        r'.*"EnaSupport".*',
        r'.*"Hypervisor".*',
        r'.*"IamInstanceProfile".*',
        r'.*"NetworkInterfaces".*',
        r'.*"Attachment".*',
        r'.*"AttachTime".*',
        r'.*"DeleteOnTermination".*',
        r'.*"Status".*',
        r'.*"VolumeId".*',
        r'.*"AttachmentId".*',
        r'.*"DeviceIndex".*',
        r'.*"NetworkCardIndex".*',
        r'.*"Description".*',
        r'.*"GroupId".*',
        r'.*"Ipv6Addresses".*',
        r'.*"MacAddress".*',
        r'.*"NetworkInterfaceId".*',
        r'.*"Primary".*',
        r'.*"SourceDestCheck".*',
        r'.*"InterfaceType".*',
        r'.*"Operator".*',
        r'.*"Managed".*',
        r'.*"RootDeviceType".*',
        r'.*"SecurityGroups".*',
        r'.*"Tags".*',
        r'.*"Value".*',
        r'.*"VirtualizationType".*',
        r'.*"CpuOptions".*',
        r'.*"CoreCount".*',
        r'.*"ThreadsPerCore".*',
        r'.*"CapacityReservationSpecification".*',
        r'.*"CapacityReservationPreference".*',
        r'.*"HibernationOptions".*',
        r'.*"Configured".*',
        r'.*"MetadataOptions".*',
        r'.*"HttpTokens".*',
        r'.*"HttpPutResponseHopLimit".*',
        r'.*"HttpEndpoint".*',
        r'.*"HttpProtocolIpv6".*',
        r'.*"InstanceMetadataTags".*',
        r'.*"EnclaveOptions".*',
        r'.*"Enabled".*',
        r'.*"BootMode".*',
        r'.*"PlatformDetails".*',
        r'.*"UsageOperation".*',
        r'.*"UsageOperationUpdateTime".*',
        r'.*"MaintenanceOptions".*',
        r'.*"AutoRecovery".*',
        r'.*"RebootMigration".*',
        r'.*"CurrentInstanceBootMode".*',
        r'.*"NetworkPerformanceOptions".*',
        r'.*"BandwidthWeighting".*',
        r'.*"ImageId".*',
        r'.*"Code".*',
        r'.*"AmiLaunchIndex".*',
        r'.*"ProductCodes".*',
        r'.*"Placement".*',
        r'.*"AvailabilityZoneId".*',
        r'.*"Tenancy".*',
        r'.*"AvailabilityZone".*',
        r'.*"Monitoring".*'
    ]

    lines = clean_text.split('\n')
    filtered_lines = []

    for line in lines:
        stripped = line.strip()
        
        # 불필요한 도구 실행 패턴 제거
        skip_line = False
        for pattern in tool_patterns:
            if re.match(pattern, stripped, re.IGNORECASE):
                skip_line = True
                break

        # 패턴에 매칭되지 않고 내용이 있는 줄만 유지
        if not skip_line and stripped:
            filtered_lines.append(stripped)

    # 결과 정리
    result = '\n'.join(filtered_lines)
    result = re.sub(r'\n{3,}', '\n\n', result)  # 연속된 빈 줄 정리

    return result.strip() if result.strip() else "응답을 처리할 수 없습니다."