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
    timeout: int = 300
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
        cmd = ['/root/.local/bin/q', 'chat', '--no-interactive', prompt]
        
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
        if result.returncode == 0:
            raw_answer = result.stdout.strip()
            # Reference 코드와 동일한 출력 정리 적용
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
        else:
            error_msg = result.stderr.strip() or "Q CLI 실행 실패"
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
    Q CLI 실행을 위한 환경 변수 구성
    
    Args:
        credentials: AWS 자격증명
        
    Returns:
        환경 변수 딕셔너리
    """
    # 기본 환경 변수 복사
    env_vars = os.environ.copy()
    
    # AWS 자격증명 설정
    if credentials:
        env_vars.update(credentials)
        log_debug("AWS 자격증명 환경 변수 설정 완료")
    
    # 한국어 설정
    env_vars['LANG'] = 'ko_KR.UTF-8'
    env_vars['LC_ALL'] = 'ko_KR.UTF-8'
    
    return env_vars


def clean_q_cli_output(text: str) -> str:
    """
    Q CLI 출력 정리 - Reference 코드의 simple_clean_output 로직 재사용
    도구 사용 내역 제거하고 깔끔한 답변만 추출
    """
    # ANSI 색상 코드 제거
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    clean_text = ansi_escape.sub('', text)

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
        r'.*Preparing.*:.*'
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