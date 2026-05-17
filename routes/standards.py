# routes/standards.py — 시험 기준서 관리

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, TestStandard
from utils import log_error

standards_bp = Blueprint('standards', __name__)


def _split(full_text):
    """시험조건 전문에서 시험조건/판정기준 분리"""
    if not full_text:
        return '', ''
    for marker in ['▶ 판정기준', '◆ 판정기준', '■ 판정기준', '● 판정기준',
                   '►판정기준', '▶판정기준', '▶ 합격기준', '◆ 합격기준']:
        idx = full_text.find(marker)
        if idx != -1:
            return full_text[:idx].rstrip(), full_text[idx:]
    return full_text, ''


@standards_bp.route('/standards')
@login_required
def list_view():
    q    = request.args.get('q', '').strip()
    book = request.args.get('book', '').strip()
    page = int(request.args.get('page', 1))
    per  = 30
    query = TestStandard.query
    if book:
        query = query.filter(TestStandard.book_name == book)
    if q:
        query = query.filter(
            db.or_(
                TestStandard.test_name.ilike(f'%{q}%'),
                TestStandard.condition_summary.ilike(f'%{q}%'),
                TestStandard.condition_full.ilike(f'%{q}%'),
            )
        )
    total = query.count()
    rows  = query.order_by(TestStandard.std_no).offset((page-1)*per).limit(per).all()
    pages = (total + per - 1) // per
    # 기준서 목록 (필터 드롭다운용)
    book_rows = db.session.query(TestStandard.book_name).distinct().order_by(TestStandard.book_name).all()
    books = [b[0] for b in book_rows if b[0]]
    # 시험조건/판정기준 분리
    items = []
    for s in rows:
        cond, crit = _split(s.condition_full)
        items.append({'s': s, 'condition': cond, 'criterion': crit})
    return render_template('standards/list.html',
                           items=items, q=q, book=book, books=books,
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
                book_name        = request.form.get('book_name', '').strip() or 'MX기구부품기준서',
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
    book_rows = db.session.query(TestStandard.book_name).distinct().order_by(TestStandard.book_name).all()
    books = [b[0] for b in book_rows if b[0]]
    return render_template('standards/form.html', item=None, books=books)


@standards_bp.route('/standards/<int:sid>/edit', methods=['GET', 'POST'])
@login_required
def edit(sid):
    if current_user.role != 'admin':
        flash('관리자만 수정할 수 있습니다.', 'danger')
        return redirect(url_for('standards.list_view'))
    std = db.get_or_404(TestStandard, sid)
    if request.method == 'POST':
        try:
            std.book_name         = request.form.get('book_name', '').strip() or 'MX기구부품기준서'
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
    book_rows = db.session.query(TestStandard.book_name).distinct().order_by(TestStandard.book_name).all()
    books = [b[0] for b in book_rows if b[0]]
    return render_template('standards/form.html', item=std, books=books)


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
