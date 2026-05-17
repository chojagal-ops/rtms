# routes/standards.py — 시험 기준서 관리

import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, TestStandard
from utils import log_error

standards_bp = Blueprint('standards', __name__)

CRITERION_MARKERS = ['▶ 판정기준', '◆ 판정기준', '■ 판정기준', '● 판정기준',
                     '►판정기준', '▶판정기준', '▶ 합격기준', '◆ 합격기준']


def _split(full_text):
    """시험조건 전문에서 시험조건 / 판정기준 분리 (마커 포함 반환)"""
    if not full_text:
        return '', ''
    for marker in CRITERION_MARKERS:
        idx = full_text.find(marker)
        if idx != -1:
            return full_text[:idx].rstrip(), full_text[idx:]
    return full_text, ''


def _split_display(full_text):
    """편집 폼용 분리 — 판정기준에서 마커를 제거해 순수 내용만 반환"""
    cond, crit = _split(full_text)
    for marker in CRITERION_MARKERS:
        if crit.startswith(marker):
            crit = crit[len(marker):].lstrip('\n').strip()
            break
    return cond, crit


def _build_full(condition, criterion):
    """시험조건 + 판정기준 → condition_full 재조합"""
    cond = (condition or '').strip()
    crit = (criterion or '').strip()
    if not crit:
        return cond
    return cond + ('\n\n' if cond else '') + '▶ 판정기준\n' + crit


def _parse_standards_file(file):
    """Excel / CSV 파일 파싱 → (items, error_msg)"""
    filename = (file.filename or '').lower()
    rows = []

    try:
        if filename.endswith(('.xlsx', '.xls', '.xlsm')):
            import openpyxl
            wb = openpyxl.load_workbook(file, data_only=True)
            ws = wb.active
            for row in ws.iter_rows():
                rows.append([str(c.value).strip() if c.value is not None else '' for c in row])
        elif filename.endswith('.csv'):
            import csv, io
            content = file.read().decode('utf-8-sig', errors='replace')
            rows = [[c.strip() for c in r] for r in csv.reader(io.StringIO(content))]
        else:
            return None, '지원 형식: .xlsx, .xls, .csv'
    except Exception as e:
        return None, f'파일 읽기 오류: {e}'

    rows = [r for r in rows if any(c for c in r)]
    if not rows:
        return None, '파일에 데이터가 없습니다.'

    # 헤더 행 자동 감지
    FIELD_KW = {
        'std_no':           ['no', '번호', '순번', '항번', 'num', '#'],
        'book_name':        ['기준서', '기준서명'],
        'test_name':        ['시험항목', '항목명', '시험명', '항목', 'test'],
        'sample_qty':       ['시료수', '시료', 'sample', 'ea'],
        'condition_summary':['요약', 'summary', '조건요약'],
        'condition':        ['시험조건', '조건', '시험방법', 'condition', '방법'],
        'criterion':        ['판정기준', '합격기준', '기준', 'criterion', 'spec'],
    }

    header_idx, col_map, best = 0, {}, 0
    for i, row in enumerate(rows[:8]):
        rl = [c.lower() for c in row]
        cmap = {}
        for field, kws in FIELD_KW.items():
            for j, cell in enumerate(rl):
                if any(kw in cell for kw in kws):
                    cmap.setdefault(field, j)
        if len(cmap) > best:
            best, header_idx, col_map = len(cmap), i, cmap

    if best < 1:
        # 헤더 미감지 — 위치 기반 추측
        col_map = {'std_no': 0, 'test_name': 1}
        n = len(rows[0])
        if n >= 3: col_map['condition'] = 2
        if n >= 4: col_map['criterion'] = 3
        if n >= 5: col_map['sample_qty'] = 4
        header_idx = -1

    def get(row, field, default=''):
        idx = col_map.get(field)
        return row[idx].strip() if idx is not None and idx < len(row) else default

    items = []
    for row in rows[header_idx + 1:]:
        if not any(row):
            continue
        name = get(row, 'test_name')
        if not name:
            continue
        items.append({
            'book_name':        get(row, 'book_name', ''),
            'std_no':           get(row, 'std_no', ''),
            'test_name':        name,
            'sample_qty':       get(row, 'sample_qty', ''),
            'condition_summary':get(row, 'condition_summary', ''),
            'condition':        get(row, 'condition', ''),
            'criterion':        get(row, 'criterion', ''),
        })

    return (items, None) if items else (None, '시험항목명이 있는 행을 찾지 못했습니다.')


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
    # 기준서 목록 + 항목 수
    book_rows = db.session.query(TestStandard.book_name).distinct().order_by(TestStandard.book_name).all()
    books = [b[0] for b in book_rows if b[0]]
    book_counts = {}
    for b in books:
        book_counts[b] = TestStandard.query.filter_by(book_name=b).count()
    # 시험조건/판정기준 분리
    items = []
    for s in rows:
        cond, crit = _split(s.condition_full)
        items.append({'s': s, 'condition': cond, 'criterion': crit})
    return render_template('standards/list.html',
                           items=items, q=q, book=book, books=books,
                           book_counts=book_counts,
                           page=page, pages=pages, total=total)


@standards_bp.route('/standards/new', methods=['GET', 'POST'])
@login_required
def new():
    if current_user.role != 'admin':
        flash('관리자만 등록할 수 있습니다.', 'danger')
        return redirect(url_for('standards.list_view'))
    if request.method == 'POST':
        try:
            condition_full = _build_full(
                request.form.get('condition', ''),
                request.form.get('criterion', ''),
            )
            std = TestStandard(
                book_name        = request.form.get('book_name', '').strip() or 'MX기구부품기준서',
                std_no           = request.form.get('std_no') or None,
                test_name        = request.form.get('test_name', '').strip(),
                condition_full   = condition_full,
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
    preset_book = request.args.get('book', '').strip()
    return render_template('standards/form.html', item=None, books=books,
                           preset_book=preset_book, condition='', criterion='')


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
            std.condition_full    = _build_full(
                request.form.get('condition', ''),
                request.form.get('criterion', ''),
            )
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
    condition, criterion = _split_display(std.condition_full)
    return render_template('standards/form.html', item=std, books=books,
                           preset_book='', condition=condition, criterion=criterion)


@standards_bp.route('/standards/import', methods=['GET', 'POST'])
@login_required
def import_file():
    if current_user.role != 'admin':
        flash('관리자만 가능합니다.', 'danger')
        return redirect(url_for('standards.list_view'))
    if request.method == 'POST':
        file = request.files.get('file')
        if not file or not file.filename:
            flash('파일을 선택해주세요.', 'danger')
            return redirect(request.url)
        items, error = _parse_standards_file(file)
        if error:
            flash(error, 'danger')
            return redirect(request.url)
        book_rows = db.session.query(TestStandard.book_name).distinct().order_by(TestStandard.book_name).all()
        books = [b[0] for b in book_rows if b[0]]
        return render_template('standards/import_preview.html',
                               items=items, books=books,
                               items_json=json.dumps(items, ensure_ascii=False))
    return render_template('standards/import.html')


@standards_bp.route('/standards/import/confirm', methods=['POST'])
@login_required
def import_confirm():
    if current_user.role != 'admin':
        flash('관리자만 가능합니다.', 'danger')
        return redirect(url_for('standards.list_view'))
    try:
        items = json.loads(request.form.get('items_json', '[]'))
        book_override = request.form.get('book_name_override', '').strip()
        count = 0
        for item in items:
            if not item.get('test_name'):
                continue
            std_no_val = item.get('std_no', '')
            std = TestStandard(
                book_name        = book_override or item.get('book_name') or 'MX기구부품기준서',
                std_no           = int(std_no_val) if str(std_no_val).isdigit() else None,
                test_name        = item['test_name'],
                condition_full   = _build_full(item.get('condition', ''), item.get('criterion', '')),
                condition_summary= item.get('condition_summary', ''),
                sample_qty       = item.get('sample_qty', ''),
            )
            db.session.add(std)
            count += 1
        db.session.commit()
        flash(f'{count}개 항목 일괄 등록 완료.', 'success')
    except Exception as e:
        db.session.rollback()
        log_error('기준서 일괄 등록 오류', e)
        flash(f'등록 오류: {e}', 'danger')
    return redirect(url_for('standards.list_view'))


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
