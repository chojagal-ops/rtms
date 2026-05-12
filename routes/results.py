# routes/results.py — 신뢰성 시험 결과서 CRUD + 엑셀 파싱

import os, tempfile
from io import BytesIO
from werkzeug.utils import secure_filename
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, current_app, send_from_directory, jsonify, send_file)
from flask_login import login_required, current_user
from models import db, TestRequest, TestItem, TestResult
from utils import parse_date, log_error, mail_result_notify

results_bp = Blueprint('results', __name__)

UPLOAD_FOLDER = 'static/uploads/results'
ALLOWED_EXT   = {'pdf', 'png', 'jpg', 'jpeg', 'xlsx', 'xls', 'docx', 'doc', 'zip', 'hwp'}


def _allowed(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT


def _save_file(file):
    if not file or file.filename == '':
        return None
    if not _allowed(file.filename):
        flash('허용되지 않는 파일 형식입니다.', 'warning')
        return None
    from datetime import datetime
    upload_dir = os.path.join(current_app.root_path, UPLOAD_FOLDER)
    os.makedirs(upload_dir, exist_ok=True)
    prefix = datetime.now().strftime('%Y%m%d%H%M%S_')
    fname  = prefix + secure_filename(file.filename)
    file.save(os.path.join(upload_dir, fname))
    return fname


def _parse_excel_result(filepath):
    """결과서 엑셀 파싱 → dict 반환"""
    import openpyxl
    try:
        wb = openpyxl.load_workbook(filepath, data_only=True)
        ws = wb.active
    except Exception:
        return None

    def cell(coord):
        v = ws[coord].value
        return str(v).strip() if v is not None else ''

    data = {
        'result_date':    cell('C4') or cell('D4'),
        'complete_date':  cell('F4'),
        'overall_result': '',
        'tester_name':    cell('F27'),
        'attach_doc_name': cell('C31'),
        # 시험 결과 항목 (행 23~25)
        'item_results': [],
    }
    for row_idx in range(23, 26):
        res    = cell(f'C{row_idx}')
        detail = cell(f'D{row_idx}')
        if res or detail:
            data['item_results'].append({'result': res, 'detail': detail})
    return data


def _form_to_result(res_obj, form, files=None):
    res_obj.result_date        = parse_date(form.get('result_date'))
    res_obj.complete_date      = parse_date(form.get('complete_date'))
    res_obj.test_complete_date = parse_date(form.get('test_complete_date'))
    res_obj.notify_date        = parse_date(form.get('notify_date'))
    res_obj.overall_result     = form.get('overall_result', '').strip()
    res_obj.summary            = form.get('summary', '').strip()
    res_obj.sample_returned    = form.get('sample_returned') == 'on'
    res_obj.tester_name        = form.get('tester_name', '').strip()
    res_obj.notifier_name      = form.get('notifier_name', '').strip()
    res_obj.report_attached    = form.get('report_attached') == 'on'
    res_obj.attach_doc_name    = form.get('attach_doc_name', '').strip()
    res_obj.notes              = form.get('notes', '').strip()
    if files:
        saved = _save_file(files.get('attachment'))
        if saved:
            res_obj.attachment = saved


# ── 결과서 목록 ─────────────────────────────────────────────
@results_bp.route('/results')
@login_required
def list_view():
    status_filter = request.args.get('status', '')
    try:
        q = TestRequest.query
        if status_filter:
            q = q.filter(TestRequest.status == status_filter)
        else:
            q = q.filter(TestRequest.status.in_(['접수완료', '시험중', '결과회신', '완료']))
        items = q.order_by(TestRequest.created_at.desc()).all()
    except Exception as e:
        log_error('결과서 목록 조회 오류', e)
        items = []
    return render_template('results/list.html', items=items, status_filter=status_filter)


# ── 결과서 등록/수정 ────────────────────────────────────────
@results_bp.route('/requests/<int:rid>/result/edit', methods=['GET', 'POST'])
@login_required
def edit(rid):
    """결과서 등록(신규) 또는 수정"""
    req_obj = db.get_or_404(TestRequest, rid)
    res_obj = req_obj.result   # None 이면 신규

    if request.method == 'POST':
        try:
            if res_obj is None:
                res_obj = TestResult(request_id=rid, created_by=current_user.id)
                db.session.add(res_obj)

            _form_to_result(res_obj, request.form, request.files)

            # 시험 항목별 결과 업데이트
            item_results = request.form.getlist('item_result')
            item_details = request.form.getlist('item_result_detail')
            for i, item in enumerate(req_obj.test_items):
                if i < len(item_results):
                    item.item_result  = item_results[i].strip()
                if i < len(item_details):
                    item.result_detail = item_details[i].strip()

            # 의뢰서 상태를 결과 회신으로 업데이트
            if res_obj.overall_result in ('적합', '부적합', '조건부적합'):
                req_obj.status = '결과회신'

            db.session.commit()
            flash('결과서가 저장되었습니다.', 'success')

            # 의뢰자 결과 통보 메일 발송 (비동기, overall_result 있을 때만)
            if res_obj.overall_result in ('적합', '부적합', '조건부적합'):
                try:
                    from models import User
                    creator = db.session.get(User, req_obj.created_by)
                    requester_email = creator.email if creator and creator.email else None
                    if requester_email:
                        base_url = request.url_root.rstrip('/')
                        mail_result_notify(req_obj, res_obj, requester_email, base_url)
                    else:
                        log_error('결과 통보 메일', Exception(f'의뢰자 이메일 없음 (user_id={req_obj.created_by})'))
                except Exception as e:
                    log_error('결과 통보 메일 발송 오류', e)

            return redirect(url_for('requests.detail', rid=rid))
        except Exception as e:
            db.session.rollback()
            log_error('결과서 저장 오류', e)
            flash('저장 중 오류가 발생했습니다.', 'danger')

    return render_template('results/form.html', req=req_obj, res=res_obj)


# ── 결과서 엑셀 파싱 ────────────────────────────────────────
@results_bp.route('/requests/<int:rid>/result/parse-excel', methods=['POST'])
@login_required
def parse_excel(rid):
    file = request.files.get('excel_file')
    if not file or file.filename == '':
        return jsonify({'ok': False, 'msg': '파일을 선택해주세요.'})
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ('xlsx', 'xls'):
        return jsonify({'ok': False, 'msg': 'xlsx / xls 파일만 지원합니다.'})

    with tempfile.NamedTemporaryFile(suffix=f'.{ext}', delete=False) as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name
    try:
        data = _parse_excel_result(tmp_path)
        if data is None:
            return jsonify({'ok': False, 'msg': '파일을 읽을 수 없습니다.'})
        return jsonify({'ok': True, 'data': data})
    except Exception as e:
        log_error('결과서 엑셀 파싱 오류', e)
        return jsonify({'ok': False, 'msg': '파싱 중 오류가 발생했습니다.'})
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


# ── 결과서 삭제 ─────────────────────────────────────────────
@results_bp.route('/requests/<int:rid>/result/delete', methods=['POST'])
@login_required
def delete(rid):
    req_obj = db.get_or_404(TestRequest, rid)
    if req_obj.result:
        try:
            db.session.delete(req_obj.result)
            req_obj.status = '시험중'
            db.session.commit()
            flash('결과서가 삭제되었습니다.', 'success')
        except Exception as e:
            db.session.rollback()
            log_error('결과서 삭제 오류', e)
            flash('삭제 중 오류가 발생했습니다.', 'danger')
    return redirect(url_for('requests.detail', rid=rid))


_RES_TEMPLATE_NET  = (r'\\192.168.10.3\품질팀\▣ SEC 무선'
                      r'\신뢰성 시험\신뢰성 시험 결과서 회신'
                      r'\신뢰성_시험_결과서_Rev.0_251113.xlsx')
# Render.com 등 클라우드 환경: static/excel_templates/ 에 파일을 커밋해두면 사용
_RES_TEMPLATE_LOCAL = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    'static', 'excel_templates', '신뢰성_시험_결과서_Rev.0_251113.xlsx'
)


def _res_template_path():
    """네트워크 공유 → 로컬 번들 순서로 템플릿 경로 반환. 없으면 None."""
    for p in (_RES_TEMPLATE_NET, _RES_TEMPLATE_LOCAL):
        if os.path.isfile(p):
            return p
    return None


# ── 결과서 엑셀 내보내기 (원본 양식 기반) ──────────────────
@results_bp.route('/requests/<int:rid>/result/export-excel')
@login_required
def export_excel(rid):
    import openpyxl
    from openpyxl.styles import Alignment
    from datetime import datetime as dt

    req_obj = db.get_or_404(TestRequest, rid)
    res_obj = req_obj.result

    tpl = _res_template_path()
    if not tpl:
        flash('템플릿 파일을 찾을 수 없습니다. '
              'static/excel_templates/ 폴더에 결과서 양식 파일을 넣어주세요.', 'danger')
        return redirect(url_for('requests.detail', rid=rid))
    try:
        wb = openpyxl.load_workbook(tpl)
    except Exception as e:
        log_error('결과서 템플릿 로드 실패', e)
        flash('템플릿 파일을 불러올 수 없습니다.', 'danger')
        return redirect(url_for('requests.detail', rid=rid))

    ws = wb.active
    lw = Alignment(horizontal='left', vertical='center', wrap_text=True)

    def w(addr, val):
        c = ws[addr]
        c.value = str(val) if val else ''
        c.alignment = lw

    fd = lambda d: d.strftime('%Y-%m-%d') if d else ''

    # ── 의뢰서 참조 정보 (결과서 상단)
    w('C3', req_obj.request_no)
    w('C4', fd(res_obj.result_date) if res_obj else '')
    w('F4', fd(res_obj.complete_date) if res_obj else '')
    w('C6', req_obj.request_dept)
    w('C7', f"{req_obj.requester_name or ''} / {getattr(req_obj, 'requester_position', '') or ''}")
    w('C9', req_obj.contact)
    w('C10', req_obj.project_customer)
    w('F6', req_obj.product_name)
    w('F7', req_obj.model_code)
    w('F8', req_obj.product_type)
    w('F9', req_obj.test_stage)
    w('F10', req_obj.change_content)
    w('C12', req_obj.test_purpose)
    w('C13', req_obj.test_purpose_detail)
    w('F12', (str(req_obj.sample_qty) + '개') if req_obj.sample_qty else '')
    w('F13', req_obj.sample_state)
    w('F14', req_obj.sample_id_method)
    w('F15', req_obj.sample_notes)

    # ── 시험 항목 (결과서 템플릿은 단일 대형 셀 row 18)
    items = req_obj.test_items
    names_str = '\n'.join(ti.test_name or '' for ti in items)
    conds_str = '\n'.join(ti.test_condition or '' for ti in items)
    stds_str  = '\n'.join(ti.standard or '' for ti in items)
    w('C18', names_str)
    w('D18', conds_str)
    w('F18', stds_str)

    # ── 판정 기준 (row 21 단일 대형 셀)
    crits_str = '\n'.join(
        f"{cr.criterion_type or ''}: {cr.criterion_content or ''}"
        for cr in req_obj.criteria
    )
    w('C21', crits_str)

    # ── 시험 결과 (rows 24~25, 항목별)
    if res_obj:
        # row 24: 종합판정 + 첫 번째 항목 결과
        overall = res_obj.overall_result or ''
        item0_result = items[0].item_result if items else ''
        item0_detail = items[0].result_detail if items else ''
        w('C24', f"종합: {overall}\n{item0_result}" if overall else item0_result)
        w('D24', f"{res_obj.summary or ''}\n{item0_detail}" if res_obj.summary else item0_detail)

        # row 25: 두 번째 항목 이후
        remaining_results = '\n'.join(
            f"{ti.test_name or ''}: {ti.item_result or ''}" for ti in items[1:]
        )
        remaining_details = '\n'.join(ti.result_detail or '' for ti in items[1:])
        w('C25', remaining_results)
        w('D25', remaining_details)

        # ── 완료/통보 정보 (row 26)
        w('C26', f"시험완료: {fd(res_obj.test_complete_date)}\n통보: {fd(res_obj.notify_date)}")

        # ── 시료반환 / 시험자·통보자 (row 27)
        w('C27', 'YES' if res_obj.sample_returned else 'NO')
        w('F27', f"{res_obj.tester_name or ''} / {res_obj.notifier_name or ''}")

        # ── 성적서 첨부 / 첨부문서 (rows 29, 31)
        w('C29', 'YES' if res_obj.report_attached else 'NO')
        w('C31', res_obj.attach_doc_name or '')

    out = BytesIO()
    wb.save(out)
    out.seek(0)
    fname = f'신뢰성_시험_결과서_{req_obj.request_no or rid}_{dt.now().strftime("%Y%m%d")}.xlsx'
    return send_file(out, as_attachment=True, download_name=fname,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


# ── 파일 다운로드 ────────────────────────────────────────────
@results_bp.route('/results/uploads/<filename>')
@login_required
def download_file(filename):
    upload_dir = os.path.join(current_app.root_path, UPLOAD_FOLDER)
    return send_from_directory(upload_dir, filename, as_attachment=True)
