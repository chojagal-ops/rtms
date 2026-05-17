# routes/nc.py — 부적합 관리

from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, NCReport, TestRequest
from utils import parse_date, log_error, mail_nc_notify
from constants import NC_STATUSES, NC_SEVERITIES

nc_bp = Blueprint('nc', __name__)


def _next_nc_no():
    """부적합 번호 채번 NC-YYYYMM-NNN"""
    today  = date.today()
    prefix = f'NC-{today.strftime("%Y%m")}'
    last   = (NCReport.query
              .filter(NCReport.nc_no.like(f'{prefix}%'))
              .order_by(NCReport.nc_no.desc()).first())
    seq = 1
    if last and last.nc_no:
        try:
            seq = int(last.nc_no.split('-')[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    return f'{prefix}-{seq:03d}'


def _form_to_nc(nc, form):
    # 시험의뢰자 정보
    nc.requester_name    = form.get('requester_name', '').strip()
    nc.requester_dept    = form.get('requester_dept', '').strip()
    nc.requester_contact = form.get('requester_contact', '').strip()
    nc.requester_email   = form.get('requester_email', '').strip()
    # 기본 정보
    nc.detection_date  = parse_date(form.get('detection_date'))
    nc.detected_by     = form.get('detected_by', '').strip()
    nc.product_name    = form.get('product_name', '').strip()
    nc.defect_type     = form.get('defect_type', '').strip()
    nc.defect_desc     = form.get('defect_desc', '').strip()
    qty = form.get('quantity', '').strip()
    nc.quantity        = int(qty) if qty.isdigit() else None
    nc.severity        = form.get('severity', '').strip()
    nc.dept            = form.get('dept', '').strip()
    nc.status          = form.get('status', nc.status or '등록')
    nc.notes           = form.get('notes', '').strip()
    rid = form.get('request_id', '').strip()
    nc.request_id      = int(rid) if rid.isdigit() else None



# ── 부적합 목록 (불량 등록) ─────────────────────────────────
@nc_bp.route('/nc')
@login_required
def list_view():
    status_f   = request.args.get('status', '')
    severity_f = request.args.get('severity', '')
    dept_f     = request.args.get('dept', '')
    search     = request.args.get('q', '').strip()
    try:
        q = NCReport.query
        if status_f:
            q = q.filter(NCReport.status == status_f)
        if severity_f:
            q = q.filter(NCReport.severity == severity_f)
        if dept_f:
            q = q.filter(NCReport.dept == dept_f)
        if search:
            q = q.filter(db.or_(
                NCReport.nc_no.ilike(f'%{search}%'),
                NCReport.product_name.ilike(f'%{search}%'),
                NCReport.defect_type.ilike(f'%{search}%'),
                NCReport.detected_by.ilike(f'%{search}%'),
            ))
        items = q.order_by(NCReport.created_at.desc()).all()
        depts = [r[0] for r in db.session.query(NCReport.dept)
                 .filter(NCReport.dept.isnot(None), NCReport.dept != '')
                 .distinct().order_by(NCReport.dept).all()]
    except Exception as e:
        log_error('부적합 목록 조회 오류', e)
        items = []
        depts = []
    return render_template('nc/list.html', items=items,
                           status_f=status_f, severity_f=severity_f,
                           dept_f=dept_f, depts=depts,
                           search=search,
                           NC_STATUSES=NC_STATUSES, NC_SEVERITIES=NC_SEVERITIES)


# ── 부적합 등록 ─────────────────────────────────────────────
@nc_bp.route('/nc/new', methods=['GET', 'POST'])
@login_required
def new():
    if request.method == 'POST':
        try:
            nc = NCReport(created_by=current_user.id,
                          nc_no=_next_nc_no(), status='등록')
            _form_to_nc(nc, request.form)
            db.session.add(nc)
            db.session.commit()
            try:
                base_url = request.host_url.rstrip('/')
                mail_nc_notify(nc, base_url)
            except Exception:
                pass
            flash(f'부적합 [{nc.nc_no}] 등록되었습니다.', 'success')
            return redirect(url_for('nc.detail', nid=nc.id))
        except Exception as e:
            db.session.rollback()
            log_error('부적합 등록 오류', e)
            flash('등록 중 오류가 발생했습니다.', 'danger')
    # 관련 의뢰서 목록 (부적합 결과인 것)
    recent_reqs = (TestRequest.query
                   .filter(TestRequest.result != None)
                   .order_by(TestRequest.created_at.desc()).limit(30).all())
    return render_template('nc/form.html', nc=None, recent_reqs=recent_reqs,
                           NC_STATUSES=NC_STATUSES,
                           NC_SEVERITIES=NC_SEVERITIES)


# ── 부적합 상세 ─────────────────────────────────────────────
@nc_bp.route('/nc/<int:nid>')
@login_required
def detail(nid):
    nc = db.get_or_404(NCReport, nid)
    return render_template('nc/detail.html', nc=nc, NC_STATUSES=NC_STATUSES)


# ── 부적합 수정 ─────────────────────────────────────────────
@nc_bp.route('/nc/<int:nid>/edit', methods=['GET', 'POST'])
@login_required
def edit(nid):
    nc = db.get_or_404(NCReport, nid)
    if request.method == 'POST':
        try:
            _form_to_nc(nc, request.form)
            db.session.commit()
            flash('수정되었습니다.', 'success')
            return redirect(url_for('nc.detail', nid=nid))
        except Exception as e:
            db.session.rollback()
            log_error('부적합 수정 오류', e)
            flash('수정 중 오류가 발생했습니다.', 'danger')
    recent_reqs = (TestRequest.query
                   .order_by(TestRequest.created_at.desc()).limit(30).all())
    return render_template('nc/form.html', nc=nc, recent_reqs=recent_reqs,
                           NC_STATUSES=NC_STATUSES,
                           NC_SEVERITIES=NC_SEVERITIES)



# ── NC 종료 처리 ──────────────────────────────────────────
@nc_bp.route('/nc/<int:nid>/close', methods=['POST'])
@login_required
def close_nc(nid):
    nc = db.get_or_404(NCReport, nid)
    try:
        nc.status = '종료'
        db.session.commit()
        flash(f'[{nc.nc_no}] 종료 처리되었습니다.', 'success')
    except Exception as e:
        db.session.rollback()
        log_error('NC 종료 오류', e)
        flash('처리 중 오류가 발생했습니다.', 'danger')
    return redirect(url_for('nc.detail', nid=nid))


# ── NC 삭제 ───────────────────────────────────────────────
@nc_bp.route('/nc/<int:nid>/delete', methods=['POST'])
@login_required
def delete(nid):
    nc = db.get_or_404(NCReport, nid)
    try:
        db.session.delete(nc)
        db.session.commit()
        flash('부적합 보고서가 삭제되었습니다.', 'success')
    except Exception as e:
        db.session.rollback()
        log_error('NC 삭제 오류', e)
        flash('삭제 중 오류가 발생했습니다.', 'danger')
    return redirect(url_for('nc.list_view'))


