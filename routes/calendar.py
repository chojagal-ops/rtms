# routes/calendar.py — 시험 일정 캘린더

from datetime import date
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from models import db, TestRequest
from utils import log_error

calendar_bp = Blueprint('calendar', __name__)

# 상태별 캘린더 색상
STATUS_COLOR = {
    '접수대기': '#f59e0b',
    '접수완료': '#3b82f6',
    '시험중':   '#ca8a04',
    '결과회신': '#16a34a',
    '완료':     '#94a3b8',
    '보류':     '#6b7280',
}


@calendar_bp.route('/calendar')
@login_required
def index():
    return render_template('calendar.html')


@calendar_bp.route('/calendar/events.json')
@login_required
def events():
    """FullCalendar용 이벤트 JSON — ?start=YYYY-MM-DD&end=YYYY-MM-DD"""
    today = date.today()
    result = []

    try:
        items = TestRequest.query.filter(
            TestRequest.status != None,
            db.or_(
                TestRequest.req_start_date != None,
                TestRequest.req_end_date   != None,
                TestRequest.deadline       != None,
            )
        ).all()
    except Exception as e:
        log_error('캘린더 이벤트 조회 오류', e)
        return jsonify([])

    for item in items:
        color  = STATUS_COLOR.get(item.status, '#94a3b8')
        no     = item.request_no or f'ID-{item.id}'
        pname  = item.product_name or '-'
        title  = f'{no} | {pname}'

        # ① 시험 기간 바 (req_start_date ~ req_end_date)
        if item.req_start_date and item.req_end_date:
            result.append({
                'id':    f'period_{item.id}',
                'title': title,
                'start': item.req_start_date.isoformat(),
                'end':   item.req_end_date.isoformat(),
                'color': color,
                'extendedProps': {
                    'rid':    item.id,
                    'type':   'period',
                    'status': item.status,
                    'dept':   item.request_dept   or '',
                    'person': item.requester_name or '',
                    'prio':   item.priority       or '',
                },
            })
        elif item.req_start_date:
            # 시작일만 있으면 단일 점
            result.append({
                'id':    f'start_{item.id}',
                'title': f'▶ {title}',
                'start': item.req_start_date.isoformat(),
                'color': color,
                'extendedProps': {
                    'rid':    item.id,
                    'type':   'start',
                    'status': item.status,
                    'dept':   item.request_dept   or '',
                    'person': item.requester_name or '',
                    'prio':   item.priority       or '',
                },
            })

        # ② 완료 희망일 마커
        if item.deadline:
            overdue   = (item.deadline < today and item.status not in ('완료', '보류'))
            dl_color  = '#dc2626' if overdue else '#f97316'
            dl_prefix = '⚠️' if overdue else '⏰'
            result.append({
                'id':      f'dl_{item.id}',
                'title':   f'{dl_prefix} {no} 마감',
                'start':   item.deadline.isoformat(),
                'allDay':  True,
                'color':   dl_color,
                'display': 'list-item',
                'extendedProps': {
                    'rid':    item.id,
                    'type':   'deadline',
                    'status': item.status,
                    'dept':   item.request_dept   or '',
                    'person': item.requester_name or '',
                    'prio':   item.priority       or '',
                },
            })

    return jsonify(result)
