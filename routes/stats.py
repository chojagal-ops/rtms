# routes/stats.py — 통계 / 모니터링 (SQLite · PostgreSQL 공용)

import calendar
from datetime import date, timedelta
from flask import Blueprint, render_template, request
from flask_login import login_required
from sqlalchemy import func, extract
from models import db, TestRequest, TestResult
from utils import log_error

stats_bp = Blueprint('stats', __name__)


# ── 공용 헬퍼 ────────────────────────────────────────────
def _req_count(extra_filters=None):
    q = db.session.query(func.count(TestRequest.id))
    for f in (extra_filters or []):
        q = q.filter(f)
    return q.scalar() or 0


def _res_count(result_val, extra_filters=None):
    q = (db.session.query(func.count(TestResult.id))
         .join(TestRequest, TestRequest.id == TestResult.request_id)
         .filter(TestResult.overall_result == result_val))
    for f in (extra_filters or []):
        q = q.filter(f)
    return q.scalar() or 0


def _year_filter(y):
    """연도 필터 — extract() 는 SQLite·PostgreSQL 모두 지원"""
    return [extract('year', TestRequest.created_at) == y]


def _month_range_filter(y, m):
    """월 범위 필터 — 날짜 비교, DB 방언 무관"""
    first = date(y, m, 1)
    last  = date(y, m, calendar.monthrange(y, m)[1])
    return [
        TestRequest.created_at >= first,
        TestRequest.created_at <= last,
    ]


def _week_range_filter(start: date, end: date):
    return [
        TestRequest.created_at >= start,
        TestRequest.created_at <= end,
    ]


# ── 라우트 ───────────────────────────────────────────────
@stats_bp.route('/stats')
@login_required
def index():
    today = date.today()
    view  = request.args.get('view',  'monthly')
    year  = request.args.get('year',  str(today.year))
    month = request.args.get('month', str(today.month))

    try:
        year_int  = int(year)
        month_int = int(month)
    except ValueError:
        year_int  = today.year
        month_int = today.month

    # 사용 가능한 연도 목록
    yr_rows = (db.session.query(extract('year', TestRequest.created_at).label('y'))
               .filter(TestRequest.created_at != None)
               .distinct()
               .order_by(extract('year', TestRequest.created_at).desc())
               .all())
    years = sorted({int(r.y) for r in yr_rows if r.y}, reverse=True) or [today.year]

    # ── 연도 KPI ─────────────────────────────────────────
    yf = _year_filter(year_int)

    total_year     = _req_count(yf)
    completed_year = _req_count(yf + [TestRequest.status == '완료'])
    hold_year      = _req_count(yf + [TestRequest.status == '보류'])
    active_year    = _req_count(yf + [TestRequest.status.in_(
                        ['접수대기', '접수완료', '시험중', '결과회신'])])
    coverage_rate  = round(completed_year / total_year * 100, 1) if total_year else 0

    pass_cnt     = _res_count('적합',       yf)
    fail_cnt     = _res_count('부적합',     yf)
    cond_cnt     = _res_count('조건부적합', yf)
    total_result = pass_cnt + fail_cnt + cond_cnt
    pass_rate    = round(pass_cnt / total_result * 100, 1) if total_result else 0

    # ── 월별 12개 ─────────────────────────────────────────
    monthly_labels = [f'{m}월' for m in range(1, 13)]
    monthly_total, monthly_done, monthly_active = [], [], []
    monthly_pass,  monthly_fail,  monthly_cond  = [], [], []

    for m in range(1, 13):
        mf = _month_range_filter(year_int, m)
        t = _req_count(mf)
        d = _req_count(mf + [TestRequest.status == '완료'])
        a = _req_count(mf + [TestRequest.status.in_(
                ['접수대기', '접수완료', '시험중', '결과회신'])])
        monthly_total.append(t)
        monthly_done.append(d)
        monthly_active.append(a)
        monthly_pass.append(_res_count('적합',       mf))
        monthly_fail.append(_res_count('부적합',     mf))
        monthly_cond.append(_res_count('조건부적합', mf))

    monthly_rate = [
        round(monthly_done[i] / monthly_total[i] * 100, 1) if monthly_total[i] else 0
        for i in range(12)
    ]

    # ── 주별 (선택 월) ───────────────────────────────────
    first_day = date(year_int, month_int, 1)
    last_day  = date(year_int, month_int, calendar.monthrange(year_int, month_int)[1])
    cur = first_day - timedelta(days=first_day.weekday())

    weekly_labels, weekly_total, weekly_done = [], [], []
    while cur <= last_day:
        wend = cur + timedelta(days=6)
        wf   = _week_range_filter(max(cur, first_day), min(wend, last_day))
        weekly_labels.append(
            f'{max(cur, first_day).strftime("%m/%d")}~{min(wend, last_day).strftime("%m/%d")}'
        )
        weekly_total.append(_req_count(wf))
        weekly_done.append(_req_count(wf + [TestRequest.status == '완료']))
        cur = wend + timedelta(days=1)

    weekly_rate = [
        round(weekly_done[i] / weekly_total[i] * 100, 1) if weekly_total[i] else 0
        for i in range(len(weekly_total))
    ]

    # ── 상태 분포 ─────────────────────────────────────────
    status_list   = ['접수대기', '접수완료', '시험중', '결과회신', '완료', '보류']
    status_counts = [_req_count(yf + [TestRequest.status == s]) for s in status_list]

    # ── 부서별 Top10 ──────────────────────────────────────
    dept_q = (db.session.query(TestRequest.request_dept, func.count(TestRequest.id).label('cnt'))
              .filter(*yf)
              .filter(TestRequest.request_dept != None, TestRequest.request_dept != '')
              .group_by(TestRequest.request_dept)
              .order_by(func.count(TestRequest.id).desc())
              .limit(10).all())
    dept_labels = [r[0] for r in dept_q]
    dept_counts = [r[1] for r in dept_q]

    # ── 제품별 Top10 ──────────────────────────────────────
    prod_q = (db.session.query(TestRequest.product_name, func.count(TestRequest.id).label('cnt'))
              .filter(*yf)
              .filter(TestRequest.product_name != None, TestRequest.product_name != '')
              .group_by(TestRequest.product_name)
              .order_by(func.count(TestRequest.id).desc())
              .limit(10).all())
    prod_labels = [r[0] for r in prod_q]
    prod_counts = [r[1] for r in prod_q]

    # ── 연도별 비교 (최근 5년) ────────────────────────────
    yearly_labels, yearly_total, yearly_done = [], [], []
    for y in sorted(years)[-5:]:
        yf2 = _year_filter(y)
        yearly_labels.append(f'{y}년')
        yearly_total.append(_req_count(yf2))
        yearly_done.append(_req_count(yf2 + [TestRequest.status == '완료']))

    return render_template(
        'stats.html',
        view=view, year=str(year_int), month=str(month_int), years=years,
        total_year=total_year, completed_year=completed_year,
        active_year=active_year, hold_year=hold_year,
        coverage_rate=coverage_rate,
        pass_cnt=pass_cnt, fail_cnt=fail_cnt, cond_cnt=cond_cnt,
        total_result=total_result, pass_rate=pass_rate,
        monthly_labels=monthly_labels,
        monthly_total=monthly_total, monthly_done=monthly_done,
        monthly_active=monthly_active, monthly_rate=monthly_rate,
        monthly_pass=monthly_pass, monthly_fail=monthly_fail, monthly_cond=monthly_cond,
        weekly_labels=weekly_labels,
        weekly_total=weekly_total, weekly_done=weekly_done, weekly_rate=weekly_rate,
        status_list=status_list, status_counts=status_counts,
        dept_labels=dept_labels, dept_counts=dept_counts,
        prod_labels=prod_labels, prod_counts=prod_counts,
        yearly_labels=yearly_labels, yearly_total=yearly_total, yearly_done=yearly_done,
        today=today,
    )
