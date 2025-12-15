"""
로깅 설정 모듈
Reference 코드와 동일한 [DEBUG]/[ERROR] 프리픽스와 flush=True 설정
"""
import logging
import sys
from typing import Optional


class PrefixFormatter(logging.Formatter):
    """[DEBUG]/[ERROR] 프리픽스를 추가하는 커스텀 포매터"""
    
    def format(self, record):
        # 로그 레벨에 따른 프리픽스 설정
        if record.levelno >= logging.ERROR:
            prefix = "[ERROR]"
        elif record.levelno >= logging.WARNING:
            prefix = "[WARNING]"
        elif record.levelno >= logging.INFO:
            prefix = "[INFO]"
        else:
            prefix = "[DEBUG]"
        
        # 기본 포맷팅 후 프리픽스 추가
        formatted = super().format(record)
        return f"{prefix} {formatted}"


def setup_logging(level: str = "DEBUG") -> logging.Logger:
    """
    로깅 설정 초기화
    
    Args:
        level: 로그 레벨 (DEBUG, INFO, WARNING, ERROR)
    
    Returns:
        설정된 로거 인스턴스
    """
    # 로거 생성
    logger = logging.getLogger("aws_zendesk_assistant")
    logger.setLevel(getattr(logging, level.upper()))
    
    # 기존 핸들러 제거 (중복 방지)
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # 콘솔 핸들러 생성
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))
    
    # 커스텀 포매터 적용
    formatter = PrefixFormatter('%(message)s')
    console_handler.setFormatter(formatter)
    
    # 핸들러 추가
    logger.addHandler(console_handler)
    
    return logger


def get_logger() -> logging.Logger:
    """기존 로거 인스턴스 반환"""
    return logging.getLogger("aws_zendesk_assistant")


def log_debug(message: str, flush: bool = True) -> None:
    """DEBUG 로그 출력 (Reference 코드 스타일)"""
    logger = get_logger()
    logger.debug(message)
    if flush:
        sys.stdout.flush()


def log_error(message: str, flush: bool = True) -> None:
    """ERROR 로그 출력 (Reference 코드 스타일)"""
    logger = get_logger()
    logger.error(message)
    if flush:
        sys.stdout.flush()


def log_info(message: str, flush: bool = True) -> None:
    """INFO 로그 출력"""
    logger = get_logger()
    logger.info(message)
    if flush:
        sys.stdout.flush()