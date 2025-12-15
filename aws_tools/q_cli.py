"""
Q CLI 호출 유틸리티
Reference 코드의 Q CLI 호출 로직 재사용
"""
import subprocess
import os
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
            answer = result.stdout.strip()
            log_info(f"Q CLI 성공: {len(answer)} 문자")
            
            return {
                "success": True,
                "answer": answer,
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