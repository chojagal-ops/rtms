# routes/nc.py — 부적합 관리 (NC Report / CAPA / 개선조치 / 재발방지)

from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, NCReport, NCAction, TestRequest
from utils import parse_date, log_error
from constants import NC_STATUSES, NC_CAUSE_CATEGORIES, NC_ACTION_TYPES, NC_SEVERITIES

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


def _form_to_analysis(nc, form):
    nc.cause_category  = form.get('cause_category', '').strip()
    nc.root_cause      = form.get('root_cause', '').strip()
    nc.analysis_method = form.get('analysis_method', '').strip()
    nc.analyzed_by     = form.get('analyzed_by', '').strip()
    nc.analysis_date   = parse_date(form.get('analysis_date'))


def _form_to_prevention(nc, form):
    nc.prevention_desc = form.get('prevention_desc', '').strip()
    nc.prevention_by   = form.get('prevention_by', '').strip()
    nc.prevention_date = parse_date(form.get('prevention_date'))


# ── 부적합 목록 (불량 등록) ─────────────────────────────────
@nc_bp.route('/nc')
@login_required
def list_view():
    status_f  = request.args.get('status', '')
    severity_f = request.args.get('severity', '')
    search    = request.args.get('q', '').strip()
    try:
        q = NCReport.query
        if status_f:
            q = q.filter(NCReport.status == status_f)
        if severity_f:
            q = q.filter(NCReport.severity == severity_f)
        if search:
            q = q.filter(db.or_(
                NCReport.nc_no.ilike(f'%{search}%'),
                NCReport.product_name.ilike(f'%{search}%'),
                NCReport.defect_type.ilike(f'%{search}%'),
                NCReport.detected_by.ilike(f'%{search}%'),
            ))
        items = q.order_by(NCReport.created_at.desc()).all()
    except Exception as e:
        log_error('부적합 목록 조회 오류', e)
        items = []
    return render_template('nc/list.html', items=items,
                           status_f=status_f, severity_f=severity_f, search=search,
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
                           NC_STATUSES=NC_STATUSES, NC_CAUSE_CATEGORIES=NC_CAUSE_CATEGORIES,
                           NC_SEVERITIES=NC_SEVERITIES)


# ── 부적합 상세 ─────────────────────────────────────────────
@nc_bp.route('/nc/<int:nid>')
@login_required
def detail(nid):
    nc = db.get_or_404(NCReport, nid)
    capa_list   = [a for a in nc.actions if a.action_type == 'CAPA']
    improve_list = [a for a in nc.actions if a.action_type == '개선조치']
    prevent_list = [a for a in nc.actions if a.action_type == '재발방지']
    return render_template('nc/detail.html', nc=nc,
                           capa_list=capa_list,
                           improve_list=improve_list,
                           prevent_list=prevent_list,
                           NC_STATUSES=NC_STATUSES,
                           NC_ACTION_TYPES=NC_ACTION_TYPES)


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
                           NC_STATUSES=NC_STATUSES, NC_CAUSE_CATEGORIES=NC_CAUSE_CATEGORIES,
                           NC_SEVERITIES=NC_SEVERITIES)


# ── 원인 분석 저장 ────────────────────────────────────────
@nc_bp.route('/nc/<int:nid>/analysis', methods=['POST'])
@login_required
def save_analysis(nid):
    nc = db.get_or_404(NCReport, nid)
    try:
        _form_to_analysis(nc, request.form)
        if nc.status == '등록':
            nc.status = '원인분석중'
        db.session.commit()
        flash('원인 분석이 저장되었습니다.', 'success')
    except Exception as e:
        db.session.rollback()
        log_error('원인 분석 저장 오류', e)
        flash('저장 중 오류가 발생했습니다.', 'danger')
    return redirect(url_for('nc.detail', nid=nid) + '#tab_analysis')


# ── 재발방지 저장 ─────────────────────────────────────────
@nc_bp.route('/nc/<int:nid>/prevention', methods=['POST'])
@login_required
def save_prevention(nid):
    nc = db.get_or_404(NCReport, nid)
    try:
        _form_to_prevention(nc, request.form)
        db.session.commit()
        flash('재발방지 내용이 저장되었습니다.', 'success')
    except Exception as e:
        db.session.rollback()
        log_error('재발방지 저장 오류', e)
        flash('저장 중 오류가 발생했습니다.', 'danger')
    return redirect(url_for('nc.detail', nid=nid) + '#tab_prevention')


# ── 조치 등록 (CAPA / 개선조치) ─────────────────────────
@nc_bp.route('/nc/<int:nid>/action/new', methods=['POST'])
@login_required
def new_action(nid):
    nc = db.get_or_404(NCReport, nid)
    try:
        action = NCAction(nc_id=nid)
        action.action_type    = request.form.get('action_type', 'CAPA')
        action.action_desc    = request.form.get('action_desc', '').strip()
        action.responsible    = request.form.get('responsible', '').strip()
        action.due_date       = parse_date(request.form.get('due_date'))
        action.effectiveness  = request.form.get('effectiveness', '').strip()
        action.status         = request.form.get('action_status', '계획')
        db.session.add(action)
        # NC 상태 업데이트
        if action.action_type == 'CAPA' and nc.status in ('등록', '원인분석중'):
            nc.status = 'CAPA진행'
        elif action.action_type == '개선조치' and nc.status == 'CAPA진행':
            nc.status = '개선완료'
        db.session.commit()
        flash(f'{action.action_type} 조치가 등록되었습니다.', 'success')
    except Exception as e:
        db.session.rollback()
        log_error('조치 등록 오류', e)
        flash('등록 중 오류가 발생했습니다.', 'danger')
    return redirect(url_for('nc.detail', nid=nid))


# ── 조치 완료 처리 ─────────────────────────────────────────
@nc_bp.route('/nc/action/<int:aid>/complete', methods=['POST'])
@login_required
def complete_action(aid):
    action = db.get_or_404(NCAction, aid)
    try:
        action.status          = '완료'
        action.completion_date = date.today()
        action.effectiveness   = request.form.get('effectiveness', action.effectiveness or '').strip()
        db.session.commit()
        flash('조치 완료 처리되었습니다.', 'success')
    except Exception as e:
        db.session.rollback()
        log_error('조치 완료 오류', e)
        flash('처리 중 오류가 발생했습니다.', 'danger')
    return redirect(url_for('nc.detail', nid=action.nc_id))


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


# ── 뷰별 필터 라우트 ─────────────────────────────────────
@nc_bp.route('/nc/analysis')
@login_required
def view_analysis():
    """원인 분석 현황"""
    items = NCReport.query.filter(
        NCReport.status.in_(['등록', '원인분석중'])
    ).order_by(NCReport.created_at.desc()).all()
    return render_template('nc/list.html', items=items,
                           status_f='원인분석중', severity_f='', search='',
                           NC_STATUSES=NC_STATUSES, NC_SEVERITIES=NC_SEVERITIES,
                           page_title='🔍 원인 분석 현황')


@nc_bp.route('/nc/capa')
@login_required
def view_capa():
    """CAPA 현황"""
    actions = NCAction.query.filter_by(action_type='CAPA').order_by(NCAction.created_at.desc()).all()
    return render_template('nc/actions.html', actions=actions,
                           view_type='CAPA', page_title='🔧 CAPA 관리')


@nc_bp.route('/nc/improvement')
@login_required
def view_improvement():
    """개선조치 관리 — NC 목록 + 의뢰자별 개선조치 입력"""
    status_f = request.args.get('status', '')
    search   = request.args.get('q', '').strip()
    try:
        q = NCReport.query
        if status_f:
            q = q.filter(NCReport.status == status_f)
        if search:
            q = q.filter(db.or_(
                NCReport.nc_no.ilike(f'%{search}%'),
                NCReport.product_name.ilike(f'%{search}%'),
                NCReport.requester_name.ilike(f'%{search}%'),
                NCReport.requester_dept.ilike(f'%{search}%'),
            ))
        items = q.order_by(NCReport.created_at.desc()).all()
    except Exception as e:
        log_error('개선조치 목록 조회 오류', e)
        items = []
    return render_template('nc/improvement_list.html', items=items,
                           status_f=status_f, search=search,
                           NC_STATUSES=NC_STATUSES, NC_SEVERITIES=NC_SEVERITIES,
                           page_title='📈 개선조치 관리')


@nc_bp.route('/nc/prevention')
@login_required
def view_prevention():
    """재발방지 현황"""
    items = NCReport.query.filter(
        NCReport.prevention_desc != None,
        NCReport.prevention_desc != ''
    ).order_by(NCReport.created_at.desc()).all()
    return render_template('nc/list.html', items=items,
                           status_f='', severity_f='', search='',
                           NC_STATUSES=NC_STATUSES, NC_SEVERITIES=NC_SEVERITIES,
                           page_title='🛡️ 재발방지 관리')
