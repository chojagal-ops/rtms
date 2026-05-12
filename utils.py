# utils.py — 공통 도우미 함수

import logging
import os
import smtplib
import threading
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
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


# ── 이메일 발송 ──────────────────────────────────────────────
_MAIL_CFG_WARNED = False   # 설정 없음 경고 중복 방지


def send_mail(subject: str, to_emails, html_body: str, text_body: str = '') -> None:
    """비동기 이메일 발송 (daemon thread). 실패 시 로그만 기록, 앱 동작에 영향 없음.

    필수 환경변수:
        MAIL_SERVER   — SMTP 서버 (예: smtp.gmail.com)
        MAIL_PORT     — 포트 (기본 587)
        MAIL_USERNAME — 발신자 이메일 (로그인 ID)
        MAIL_PASSWORD — 앱 비밀번호 / SMTP 비밀번호
    선택:
        MAIL_USE_TLS  — true / false (기본 true)
    """
    global _MAIL_CFG_WARNED

    server   = os.environ.get('MAIL_SERVER', '').strip()
    username = os.environ.get('MAIL_USERNAME', '').strip()
    password = os.environ.get('MAIL_PASSWORD', '').strip()

    if not (server and username and password):
        if not _MAIL_CFG_WARNED:
            logging.warning('이메일 발송 건너뜀: MAIL_SERVER / MAIL_USERNAME / MAIL_PASSWORD 환경변수를 설정하세요.')
            _MAIL_CFG_WARNED = True
        return

    port    = int(os.environ.get('MAIL_PORT', '587'))
    use_tls = os.environ.get('MAIL_USE_TLS', 'true').lower() != 'false'

    if isinstance(to_emails, str):
        to_emails = [e.strip() for e in to_emails.split(',') if e.strip()]

    def _send():
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From']    = username
            msg['To']      = ', '.join(to_emails)
            if text_body:
                msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))

            with smtplib.SMTP(server, port, timeout=15) as smtp:
                smtp.ehlo()
                if use_tls:
                    smtp.starttls()
                    smtp.ehlo()
                smtp.login(username, password)
                smtp.sendmail(username, to_emails, msg.as_bytes())
            logging.info(f'이메일 발송 성공 → {to_emails} / {subject}')
        except Exception as exc:
            log_error(f'이메일 발송 실패 → {to_emails}', exc)

    threading.Thread(target=_send, daemon=True).start()


def mail_new_request(req_obj, base_url: str = '') -> None:
    """신규 의뢰서 등록 → 품질팀 알림 메일"""
    qa_email = os.environ.get('QA_EMAIL', 'igm550@intops.co.kr')
    fd = lambda d: d.strftime('%Y-%m-%d') if d else '-'
    items_html = ''.join(
        f'<tr><td style="padding:4px 8px;border:1px solid #e5e7eb;">{i+1}</td>'
        f'<td style="padding:4px 8px;border:1px solid #e5e7eb;">{ti.test_name or "-"}</td>'
        f'<td style="padding:4px 8px;border:1px solid #e5e7eb;font-size:12px;">{ti.test_condition or "-"}</td></tr>'
        for i, ti in enumerate(req_obj.test_items)
    )
    detail_url = f'{base_url}/requests/{req_obj.id}' if base_url else ''
    link_html  = f'<p><a href="{detail_url}" style="color:#f97316;">→ 시스템에서 확인하기</a></p>' if detail_url else ''

    html = f"""
<div style="font-family:'Segoe UI','Malgun Gothic',sans-serif;max-width:600px;margin:0 auto;">
  <div style="background:linear-gradient(135deg,#f97316,#ea580c);padding:24px 28px;border-radius:12px 12px 0 0;">
    <h2 style="color:#fff;margin:0;font-size:18px;">📬 신뢰성 시험 의뢰 접수 알림</h2>
    <p style="color:rgba(255,255,255,0.85);margin:6px 0 0;font-size:13px;">RTMS — 신뢰성 시험 관리 시스템</p>
  </div>
  <div style="background:#fff;padding:24px 28px;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 12px 12px;">
    <table style="width:100%;border-collapse:collapse;margin-bottom:16px;">
      <tr><td style="padding:6px 0;color:#6b7280;font-size:13px;width:110px;">의뢰번호</td>
          <td style="padding:6px 0;font-weight:700;color:#111;">{req_obj.request_no or '-'}</td></tr>
      <tr><td style="padding:6px 0;color:#6b7280;font-size:13px;">제품명</td>
          <td style="padding:6px 0;font-weight:600;">{req_obj.product_name or '-'} ({req_obj.model_code or '-'})</td></tr>
      <tr><td style="padding:6px 0;color:#6b7280;font-size:13px;">의뢰부서</td>
          <td style="padding:6px 0;">{req_obj.request_dept or '-'}</td></tr>
      <tr><td style="padding:6px 0;color:#6b7280;font-size:13px;">의뢰자</td>
          <td style="padding:6px 0;">{req_obj.requester_name or '-'} {req_obj.requester_position or ''}</td></tr>
      <tr><td style="padding:6px 0;color:#6b7280;font-size:13px;">완료희망일</td>
          <td style="padding:6px 0;">{fd(req_obj.deadline)}</td></tr>
      <tr><td style="padding:6px 0;color:#6b7280;font-size:13px;">우선순위</td>
          <td style="padding:6px 0;font-weight:700;color:{'#dc2626' if req_obj.priority=='상' else '#d97706' if req_obj.priority=='중' else '#374151'};">{req_obj.priority or '-'}</td></tr>
    </table>
    {'<h4 style="font-size:13px;color:#374151;margin:0 0 8px;">시험 항목</h4><table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px;"><thead><tr><th style="padding:6px 8px;background:#f9fafb;border:1px solid #e5e7eb;text-align:left;">No</th><th style="padding:6px 8px;background:#f9fafb;border:1px solid #e5e7eb;text-align:left;">항목명</th><th style="padding:6px 8px;background:#f9fafb;border:1px solid #e5e7eb;text-align:left;">시험조건</th></tr></thead><tbody>' + items_html + '</tbody></table>' if items_html else ''}
    {link_html}
    <p style="font-size:12px;color:#9ca3af;margin-top:20px;border-top:1px solid #f3f4f6;padding-top:12px;">
      본 메일은 RTMS 시스템에서 자동 발송된 메일입니다.
    </p>
  </div>
</div>"""

    send_mail(
        subject=f'[RTMS] 신뢰성 시험 의뢰 접수 — {req_obj.request_no} / {req_obj.product_name or ""}',
        to_emails=qa_email,
        html_body=html,
    )


def mail_result_notify(req_obj, res_obj, requester_email: str, base_url: str = '') -> None:
    """결과 등록 → 의뢰자 결과 통보 메일"""
    if not requester_email:
        return
    fd = lambda d: d.strftime('%Y-%m-%d') if d else '-'
    result_color = {'합격': '#16a34a', '불합격': '#dc2626', '조건부합격': '#d97706'}.get(
        res_obj.overall_result or '', '#374151')
    detail_url = f'{base_url}/requests/{req_obj.id}' if base_url else ''
    link_html  = f'<p><a href="{detail_url}" style="color:#f97316;">→ 시스템에서 결과 확인하기</a></p>' if detail_url else ''

    html = f"""
<div style="font-family:'Segoe UI','Malgun Gothic',sans-serif;max-width:600px;margin:0 auto;">
  <div style="background:linear-gradient(135deg,#f97316,#ea580c);padding:24px 28px;border-radius:12px 12px 0 0;">
    <h2 style="color:#fff;margin:0;font-size:18px;">📊 신뢰성 시험 결과 통보</h2>
    <p style="color:rgba(255,255,255,0.85);margin:6px 0 0;font-size:13px;">RTMS — 신뢰성 시험 관리 시스템</p>
  </div>
  <div style="background:#fff;padding:24px 28px;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 12px 12px;">
    <div style="background:#f8fafc;border-radius:10px;padding:16px 20px;margin-bottom:20px;text-align:center;">
      <div style="font-size:13px;color:#6b7280;margin-bottom:6px;">종합 판정 결과</div>
      <div style="font-size:28px;font-weight:900;color:{result_color};">{res_obj.overall_result or '-'}</div>
    </div>
    <table style="width:100%;border-collapse:collapse;margin-bottom:16px;">
      <tr><td style="padding:6px 0;color:#6b7280;font-size:13px;width:110px;">의뢰번호</td>
          <td style="padding:6px 0;font-weight:700;">{req_obj.request_no or '-'}</td></tr>
      <tr><td style="padding:6px 0;color:#6b7280;font-size:13px;">제품명</td>
          <td style="padding:6px 0;font-weight:600;">{req_obj.product_name or '-'}</td></tr>
      <tr><td style="padding:6px 0;color:#6b7280;font-size:13px;">모델명</td>
          <td style="padding:6px 0;">{req_obj.model_code or '-'}</td></tr>
      <tr><td style="padding:6px 0;color:#6b7280;font-size:13px;">시험 완료일</td>
          <td style="padding:6px 0;">{fd(res_obj.test_complete_date)}</td></tr>
      <tr><td style="padding:6px 0;color:#6b7280;font-size:13px;">통보일</td>
          <td style="padding:6px 0;">{fd(res_obj.notify_date)}</td></tr>
      <tr><td style="padding:6px 0;color:#6b7280;font-size:13px;">시험자</td>
          <td style="padding:6px 0;">{res_obj.tester_name or '-'}</td></tr>
      <tr><td style="padding:6px 0;color:#6b7280;font-size:13px;">통보자</td>
          <td style="padding:6px 0;">{res_obj.notifier_name or '-'}</td></tr>
    </table>
    {'<div style="background:#f8fafc;padding:12px 16px;border-radius:8px;font-size:13px;margin-bottom:16px;"><strong>결과 요약:</strong> ' + res_obj.summary + '</div>' if res_obj.summary else ''}
    {link_html}
    <p style="font-size:12px;color:#9ca3af;margin-top:20px;border-top:1px solid #f3f4f6;padding-top:12px;">
      본 메일은 RTMS 시스템에서 자동 발송된 메일입니다. 문의사항은 품질팀으로 연락 바랍니다.
    </p>
  </div>
</div>"""

    send_mail(
        subject=f'[RTMS] 신뢰성 시험 결과 통보 — {req_obj.request_no} / {req_obj.product_name or ""} [{res_obj.overall_result or ""}]',
        to_emails=requester_email,
        html_body=html,
    )
