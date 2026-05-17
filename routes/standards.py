# routes/standards.py — 시험 기준서 관리

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, TestStandard
from utils import log_error

standards_bp = Blueprint('standards', __name__)


@standards_bp.route('/standards')
@login_required
def list_view():
    q    = request.args.get('q', '').strip()
    page = int(request.args.get('page', 1))
    per  = 20
    query = TestStandard.query
    if q:
        query = query.filter(
            db.or_(
                TestStandard.test_name.ilike(f'%{q}%'),
                TestStandard.condition_summary.ilike(f'%{q}%'),
            )
        )
    total   = query.count()
    items   = query.order_by(TestStandard.std_no).offset((page-1)*per).limit(per).all()
    pages   = (total + per - 1) // per
    return render_template('standards/list.html',
                           items=items, q=q,
                           page=page, pages=pages, total=total)


@standards_bp.route('/standards/new', methods=['GET', 'POST'])
@login_required
def new():
    if current_user.role != 'admin':
        flash('관리자만 등록할 수 있습니다.', 'danger')
        return redirect(url_for('standards.list_view'))
    if request.method == 'POST':
        try:
            std = TestStandard(
                std_no           = request.form.get('std_no') or None,
                test_name        = request.form.get('test_name', '').strip(),
                condition_full   = request.form.get('condition_full', '').strip(),
                condition_summary= request.form.get('condition_summary', '').strip(),
                sample_qty       = request.form.get('sample_qty', '').strip(),
            )
            if std.std_no:
                std.std_no = int(std.std_no)
            db.session.add(std)
            db.session.commit()
            flash(f'기준서 [{std.test_name}] 등록 완료.', 'success')
            return redirect(url_for('standards.list_view'))
        except Exception as e:
            db.session.rollback()
            log_error('기준서 등록 오류', e)
            flash('등록 중 오류가 발생했습니다.', 'danger')
    return render_template('standards/form.html', item=None)


@standards_bp.route('/standards/<int:sid>/edit', methods=['GET', 'POST'])
@login_required
def edit(sid):
    if current_user.role != 'admin':
        flash('관리자만 수정할 수 있습니다.', 'danger')
        return redirect(url_for('standards.list_view'))
    std = db.get_or_404(TestStandard, sid)
    if request.method == 'POST':
        try:
            std.std_no            = int(request.form.get('std_no')) if request.form.get('std_no') else None
            std.test_name         = request.form.get('test_name', '').strip()
            std.condition_full    = request.form.get('condition_full', '').strip()
            std.condition_summary = request.form.get('condition_summary', '').strip()
            std.sample_qty        = request.form.get('sample_qty', '').strip()
            db.session.commit()
            flash(f'기준서 [{std.test_name}] 수정 완료.', 'success')
            return redirect(url_for('standards.list_view'))
        except Exception as e:
            db.session.rollback()
            log_error('기준서 수정 오류', e)
            flash('수정 중 오류가 발생했습니다.', 'danger')
    return render_template('standards/form.html', item=std)


@standards_bp.route('/standards/<int:sid>/delete', methods=['POST'])
@login_required
def delete(sid):
    if current_user.role != 'admin':
        flash('관리자만 삭제할 수 있습니다.', 'danger')
        return redirect(url_for('standards.list_view'))
    std = db.get_or_404(TestStandard, sid)
    try:
        name = std.test_name
        db.session.delete(std)
        db.session.commit()
        flash(f'기준서 [{name}] 삭제 완료.', 'success')
    except Exception as e:
        db.session.rollback()
        log_error('기준서 삭제 오류', e)
        flash('삭제 중 오류가 발생했습니다.', 'danger')
    return redirect(url_for('standards.list_view'))
