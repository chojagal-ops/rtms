# routes/dashboard.py — 대시보드 (통계 요약)

from flask import Blueprint, render_template
from flask_login import login_required
from datetime import date
from models import db, TestRequest, TestResult
from utils import log_error

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/dashboard')
@login_required
def index():
    try:
        today = date.today()

        total     = TestRequest.query.count()
        pending   = TestRequest.query.filter_by(status='접수대기').count()
        accepted  = TestRequest.query.filter_by(status='접수완료').count()
        testing   = TestRequest.query.filter_by(status='시험중').count()
        replied   = TestRequest.query.filter_by(status='결과회신').count()
        completed = TestRequest.query.filter_by(status='완료').count()
        hold      = TestRequest.query.filter_by(status='보류').count()

        # 최근 15건 의뢰
        recent = (TestRequest.query
                  .order_by(TestRequest.created_at.desc())
                  .limit(15).all())

        # 결과 판정 통계
        pass_cnt = TestResult.query.filter_by(overall_result='합격').count()
        fail_cnt = TestResult.query.filter_by(overall_result='불합격').count()
        cond_cnt = TestResult.query.filter_by(overall_result='조건부합격').count()

        # 최근 결과 상세 (결과서가 있는 의뢰 최근 10건)
        recent_results = (TestRequest.query
                          .join(TestResult, TestRequest.id == TestResult.request_id)
                          .order_by(TestResult.result_date.desc())
                          .limit(10).all())

        # 마감 임박 의뢰 (오늘 기준 7일 이내, 미완료)
        from datetime import timedelta
        deadline_soon = (TestRequest.query
                         .filter(TestRequest.deadline != None)
                         .filter(TestRequest.deadline <= today + timedelta(days=7))
                         .filter(TestRequest.deadline >= today)
                         .filter(~TestRequest.status.in_(['완료', '보류']))
                         .order_by(TestRequest.deadline.asc())
                         .all())

        # 기간 초과 의뢰
        overdue = (TestRequest.query
                   .filter(TestRequest.deadline != None)
                   .filter(TestRequest.deadline < today)
                   .filter(~TestRequest.status.in_(['완료', '보류']))
                   .count())

    except Exception as e:
        log_error('대시보드 조회 오류', e)
        today = date.today()
        total = pending = accepted = testing = replied = completed = hold = 0
        pass_cnt = fail_cnt = cond_cnt = 0
        recent = []
        recent_results = []
        deadline_soon = []
        overdue = 0

    return render_template(
        'dashboard.html',
        total=total, pending=pending, accepted=accepted,
        testing=testing, replied=replied, completed=completed, hold=hold,
        pass_cnt=pass_cnt, fail_cnt=fail_cnt, cond_cnt=cond_cnt,
        recent=recent,
        recent_results=recent_results,
        deadline_soon=deadline_soon,
        overdue=overdue,
        today=today,
    )
