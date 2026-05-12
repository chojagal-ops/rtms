# utils.py — 공통 도우미 함수

import logging
from datetime import datetime
from pathlib import Path

LOG_PATH = Path(__file__).parent / 'error.log'

logging.basicConfig(
    filename=str(LOG_PATH),
    level=logging.ERROR,
    format='%(asctime)s [%(levelname)s] %(message)s',
    encoding='utf-8',
)


def log_error(context: str, exc: Exception) -> None:
    """오류 상세를 error.log 에 기록 (사용자에게는 한국어 메시지만 표시)"""
    logging.error(f'{context}: {exc}', exc_info=True)


def parse_date(value: str):
    """YYYY-MM-DD 문자열 → date 객체. 잘못된 값이면 None"""
    if value:
        try:
            return datetime.strptime(value.strip(), '%Y-%m-%d').date()
        except ValueError:
            return None
    return None


def fmt_date(d) -> str:
    """date 객체 → 'YYYY-MM-DD' 문자열"""
    return d.strftime('%Y-%m-%d') if d else ''


def make_request_no(seq: int, dept_code: str, requester_initials: str, date_str: str) -> str:
    """의뢰번호 자동 채번: RTN-{부서코드}-{이니셜}-{날짜}-{순번:02d}"""
    return f'RTN-{dept_code.upper()}-{requester_initials.upper()}-{date_str}-{seq:02d}'
