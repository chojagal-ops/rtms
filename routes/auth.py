# routes/auth.py — 로그인 / 로그아웃 / 회원가입

import os
import random
import string
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User, SysConfig, MailLog
from utils import log_error, mail_temp_password, send_mail
from constants import DEPARTMENTS

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/')
def index():
    """루트 접속 시 대시보드로 이동"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    return redirect(url_for('auth.login'))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username', '').strip()).first()
        if user and user.check_password(request.form.get('password', '')):
            if not user.is_approved:
                flash('관리자 승인 대기 중입니다. 관리자에게 문의하세요.', 'warning')
                return redirect(url_for('auth.login'))
            login_user(user, remember=request.form.get('remember') == 'on')
            return redirect(url_for('dashboard.index'))
        flash('아이디 또는 비밀번호가 올바르지 않습니다.', 'danger')
    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            username = request.form.get('username', '').strip()
            name     = request.form.get('name', '').strip()
            email    = request.form.get('email', '').strip()
            dept     = request.form.get('department', '').strip()
            password = request.form.get('password', '')
            password2 = request.form.get('password2', '')

            # 유효성 검사
            if not email:
                flash('이메일 주소는 필수 입력 항목입니다.', 'danger')
                return render_template('register.html', DEPARTMENTS=DEPARTMENTS)
            if not dept:
                flash('소속 팀을 선택해 주세요.', 'danger')
                return render_template('register.html', DEPARTMENTS=DEPARTMENTS)
            if password != password2:
                flash('비밀번호가 일치하지 않습니다.', 'danger')
                return render_template('register.html', DEPARTMENTS=DEPARTMENTS)
            if len(password) < 6:
                flash('비밀번호는 6자리 이상이어야 합니다.', 'danger')
                return render_template('register.html', DEPARTMENTS=DEPARTMENTS)
            if User.query.filter_by(username=username).first():
                flash('이미 사용 중인 아이디입니다.', 'danger')
                return render_template('register.html', DEPARTMENTS=DEPARTMENTS)

            user = User(
                username=username,
                name=name,
                email=email,
                department=dept,
                is_approved=False,
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash('가입 신청이 완료되었습니다. 관리자 승인 후 로그인 가능합니다.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            log_error('회원가입 오류', e)
            flash('가입 중 오류가 발생했습니다.', 'danger')
    return render_template('register.html', DEPARTMENTS=DEPARTMENTS)


# ── 비밀번호 찾기 ─────────────────────────────────────────
@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email    = request.form.get('email', '').strip()
        user = User.query.filter_by(username=username).first()
        # 보안: 아이디/이메일 불일치 여부를 구별하지 않고 동일 메시지
        if user and user.email and user.email.lower() == email.lower():
            try:
                # 임시 비밀번호 생성 (영문+숫자 8자리)
                chars = string.ascii_letters + string.digits
                temp_pw = ''.join(random.choices(chars, k=8))
                user.set_password(temp_pw)
                db.session.commit()
                mail_temp_password(user.name, user.username, temp_pw, user.email)
                flash('임시 비밀번호를 이메일로 발송했습니다. 받은 편지함을 확인해 주세요.', 'success')
                return redirect(url_for('auth.login'))
            except Exception as e:
                db.session.rollback()
                log_error('비밀번호 찾기 오류', e)
                flash('처리 중 오류가 발생했습니다. 관리자에게 문의하세요.', 'danger')
        else:
            # 존재하지 않는 계정도 동일 메시지 (정보 노출 방지)
            flash('입력하신 정보와 일치하는 계정이 없습니다.', 'warning')
    return render_template('forgot_password.html')


@auth_bp.route('/admin/users')
@login_required
def admin_users():
    """관리자 전용: 회원 승인 목록"""
    if current_user.role != 'admin':
        flash('관리자만 접근 가능합니다.', 'danger')
        return redirect(url_for('dashboard.index'))
    users = User.query.order_by(User.is_approved, User.created_at).all()
    return render_template('admin_users.html', users=users)


@auth_bp.route('/admin/users/<int:uid>/approve', methods=['POST'])
@login_required
def approve_user(uid):
    if current_user.role != 'admin':
        flash('관리자만 접근 가능합니다.', 'danger')
        return redirect(url_for('dashboard.index'))
    user = db.get_or_404(User, uid)
    try:
        user.is_approved = not user.is_approved
        db.session.commit()
        flash(f"{'승인' if user.is_approved else '승인 취소'} 완료: {user.name}", 'success')
    except Exception as e:
        db.session.rollback()
        log_error('사용자 승인 오류', e)
        flash('처리 중 오류가 발생했습니다.', 'danger')
    return redirect(url_for('auth.admin_users'))


@auth_bp.route('/admin/users/<int:uid>/reject', methods=['POST'])
@login_required
def reject_user(uid):
    """미승인 회원 거절 (삭제)"""
    if current_user.role != 'admin':
        flash('관리자만 접근 가능합니다.', 'danger')
        return redirect(url_for('dashboard.index'))
    if uid == current_user.id:
        flash('본인 계정은 거절할 수 없습니다.', 'warning')
        return redirect(url_for('auth.admin_users'))
    user = db.get_or_404(User, uid)
    try:
        name = user.name
        db.session.delete(user)
        db.session.commit()
        flash(f'가입 거절 완료: {name}', 'success')
    except Exception as e:
        db.session.rollback()
        log_error('회원 거절 오류', e)
        flash('처리 중 오류가 발생했습니다.', 'danger')
    return redirect(url_for('auth.admin_users'))


@auth_bp.route('/admin/users/<int:uid>/edit', methods=['GET', 'POST'])
@login_required
def admin_edit_user(uid):
    """관리자 전용: 회원 정보 수정"""
    if current_user.role != 'admin':
        flash('관리자만 접근 가능합니다.', 'danger')
        return redirect(url_for('dashboard.index'))
    user = db.get_or_404(User, uid)
    if request.method == 'POST':
        try:
            user.name       = request.form.get('name', '').strip() or user.name
            user.email      = request.form.get('email', '').strip() or None
            user.department = request.form.get('department', '').strip()
            # admin 계정 자신의 role은 변경 불가 (실수 방지)
            if user.username != 'admin':
                user.role = request.form.get('role', 'user')
            user.is_approved = request.form.get('is_approved') == 'on'
            new_pw = request.form.get('new_password', '').strip()
            if new_pw:
                if len(new_pw) < 6:
                    flash('비밀번호는 6자 이상이어야 합니다.', 'warning')
                    return render_template('admin_edit_user.html', u=user)
                user.set_password(new_pw)
            db.session.commit()
            flash(f'{user.name} 정보가 수정되었습니다.', 'success')
            return redirect(url_for('auth.admin_users'))
        except Exception as e:
            db.session.rollback()
            log_error('관리자 회원 수정 오류', e)
            flash('수정 중 오류가 발생했습니다.', 'danger')
    return render_template('admin_edit_user.html', u=user)


# ── 메일 발송 관리 (메인 진입점) ──────────────────────────
@auth_bp.route('/admin/mail')
@login_required
def admin_mail():
    """관리자 전용: 메일발송 설정 현황 및 테스트"""
    if current_user.role != 'admin':
        flash('관리자만 접근 가능합니다.', 'danger')
        return redirect(url_for('dashboard.index'))
    import os as _os
    _qa = _os.environ.get('QA_EMAIL', 'igm550@intops.co.kr')
    cfg = {
        'MAIL_SERVER':   _os.environ.get('MAIL_SERVER', ''),
        'MAIL_PORT':     _os.environ.get('MAIL_PORT', '587'),
        'MAIL_USERNAME': _os.environ.get('MAIL_USERNAME', ''),
        'MAIL_PASSWORD': '●●●●●●●●' if _os.environ.get('MAIL_PASSWORD') else '',
        'MAIL_USE_TLS':  _os.environ.get('MAIL_USE_TLS', 'true'),
        'QA_EMAIL':      _qa,
        'mail_request_enabled': SysConfig.get('mail_request_enabled', '1'),
        'mail_request_to':      SysConfig.get('mail_request_to', _qa),
        'mail_request_cc':      SysConfig.get('mail_request_cc', ''),
        'mail_result_enabled':  SysConfig.get('mail_result_enabled', '1'),
        'mail_result_cc':       SysConfig.get('mail_result_cc', _qa),
        'mail_nc_enabled':      SysConfig.get('mail_nc_enabled', '1'),
        'mail_nc_cc':           SysConfig.get('mail_nc_cc', 'igm550@intops.co.kr'),
    }
    configured = bool(_os.environ.get('MAIL_SERVER') and _os.environ.get('MAIL_USERNAME')
                      and _os.environ.get('MAIL_PASSWORD'))
    logs = MailLog.query.order_by(MailLog.sent_at.desc()).limit(100).all()
    return render_template('admin_mail.html', cfg=cfg, configured=configured, logs=logs)


@auth_bp.route('/admin/mail/test', methods=['POST'])
@login_required
def admin_mail_test():
    """관리자 전용: 테스트 메일 발송"""
    if current_user.role != 'admin':
        return jsonify({'ok': False, 'msg': '관리자만 가능합니다.'}), 403
    import os as _os
    to_email = request.form.get('to_email', '').strip()
    if not to_email:
        return jsonify({'ok': False, 'msg': '수신 이메일을 입력하세요.'})
    server   = _os.environ.get('MAIL_SERVER', '')
    username = _os.environ.get('MAIL_USERNAME', '')
    password = _os.environ.get('MAIL_PASSWORD', '')
    if not (server and username and password):
        return jsonify({'ok': False, 'msg': 'SMTP 환경변수가 설정되지 않았습니다.'})
    html = f"""<div style="font-family:'Malgun Gothic',sans-serif;max-width:500px;margin:0 auto;
padding:28px;border:1px solid #e5e7eb;border-radius:12px;background:#fff;">
  <div style="background:linear-gradient(135deg,#f97316,#ea580c);padding:16px 20px;border-radius:8px;margin-bottom:20px;">
    <h2 style="color:#fff;margin:0;font-size:16px;">✅ RTMS 테스트 메일 발송 성공</h2>
  </div>
  <p style="font-size:14px;color:#374151;">SMTP 설정이 정상적으로 작동하고 있습니다.</p>
  <table style="font-size:13px;color:#6b7280;margin-top:12px;">
    <tr><td style="padding:4px 12px 4px 0;">발신 서버</td><td style="font-weight:600;color:#111;">{server}</td></tr>
    <tr><td style="padding:4px 12px 4px 0;">발신 계정</td><td style="font-weight:600;color:#111;">{username}</td></tr>
  </table>
</div>"""
    try:
        send_mail('[RTMS] 테스트 메일 — SMTP 설정 확인', to_email, html)
        return jsonify({'ok': True, 'msg': f'{to_email} 으로 테스트 메일을 발송했습니다.'})
    except Exception as e:
        log_error('테스트 메일 발송 오류', e)
        return jsonify({'ok': False, 'msg': f'발송 오류: {e}'})


@auth_bp.route('/admin/mail-settings', methods=['GET', 'POST'])
@login_required
def admin_mail_settings():
    """관리자 전용: 메일 발송 설정 (기능별 ON/OFF + 수신자)"""
    if current_user.role != 'admin':
        flash('관리자만 접근 가능합니다.', 'danger')
        return redirect(url_for('dashboard.index'))
    if request.method == 'POST':
        try:
            for key in ('mail_request_enabled', 'mail_result_enabled', 'mail_nc_enabled'):
                SysConfig.set(key, '1' if request.form.get(key) == 'on' else '0')
            for key in ('mail_request_to', 'mail_request_cc', 'mail_result_cc', 'mail_nc_cc'):
                SysConfig.set(key, request.form.get(key, '').strip())
            flash('메일 설정이 저장되었습니다.', 'success')
        except Exception as e:
            db.session.rollback()
            log_error('메일 설정 저장 오류', e)
            flash('저장 중 오류가 발생했습니다.', 'danger')
        return redirect(url_for('auth.admin_mail'))
    return redirect(url_for('auth.admin_mail'))


@auth_bp.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def profile_edit():
    """본인 회원 정보 수정"""
    if request.method == 'POST':
        try:
            name  = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip()
            dept  = request.form.get('department', '').strip()
            cur_pw  = request.form.get('current_password', '')
            new_pw  = request.form.get('new_password', '').strip()
            new_pw2 = request.form.get('new_password2', '').strip()

            # 비밀번호 변경 요청 시 현재 비밀번호 확인
            if new_pw:
                if not current_user.check_password(cur_pw):
                    flash('현재 비밀번호가 올바르지 않습니다.', 'danger')
                    return render_template('profile_edit.html')
                if new_pw != new_pw2:
                    flash('새 비밀번호가 일치하지 않습니다.', 'danger')
                    return render_template('profile_edit.html')
                if len(new_pw) < 6:
                    flash('비밀번호는 6자 이상이어야 합니다.', 'warning')
                    return render_template('profile_edit.html')
                current_user.set_password(new_pw)

            current_user.name       = name or current_user.name
            current_user.email      = email or None
            current_user.department = dept
            db.session.commit()
            flash('회원 정보가 수정되었습니다.', 'success')
            return redirect(url_for('auth.profile_edit'))
        except Exception as e:
            db.session.rollback()
            log_error('프로필 수정 오류', e)
            flash('수정 중 오류가 발생했습니다.', 'danger')
    return render_template('profile_edit.html')


@auth_bp.route('/admin/mail-log')
@login_required
def admin_mail_log():
    """관리자 전용: 메일 발송 이력 + 기능별 ON/OFF"""
    if current_user.role != 'admin':
        flash('관리자만 접근 가능합니다.', 'danger')
        return redirect(url_for('dashboard.index'))
    import os as _os
    _qa = _os.environ.get('QA_EMAIL', 'igm550@intops.co.kr')
    cfg = {
        'mail_request_enabled': SysConfig.get('mail_request_enabled', '1'),
        'mail_request_to':      SysConfig.get('mail_request_to', _qa),
        'mail_request_cc':      SysConfig.get('mail_request_cc', ''),
        'mail_result_enabled':  SysConfig.get('mail_result_enabled', '1'),
        'mail_result_cc':       SysConfig.get('mail_result_cc', _qa),
        'mail_nc_enabled':      SysConfig.get('mail_nc_enabled', '1'),
        'mail_nc_cc':           SysConfig.get('mail_nc_cc', 'igm550@intops.co.kr'),
    }
    logs = MailLog.query.order_by(MailLog.sent_at.desc()).limit(200).all()
    return render_template('admin_mail_log.html', cfg=cfg, logs=logs)


@auth_bp.route('/admin/mail-log/settings', methods=['POST'])
@login_required
def admin_mail_log_settings():
    """메일 발송 관리 페이지에서 설정 저장"""
    if current_user.role != 'admin':
        flash('관리자만 접근 가능합니다.', 'danger')
        return redirect(url_for('dashboard.index'))
    try:
        for key in ('mail_request_enabled', 'mail_result_enabled', 'mail_nc_enabled'):
            SysConfig.set(key, '1' if request.form.get(key) == 'on' else '0')
        for key in ('mail_request_to', 'mail_request_cc',
                    'mail_result_cc',
                    'mail_nc_cc'):
            SysConfig.set(key, request.form.get(key, '').strip())
        flash('메일 설정이 저장되었습니다.', 'success')
    except Exception as e:
        db.session.rollback()
        log_error('메일 설정 저장 오류', e)
        flash('저장 중 오류가 발생했습니다.', 'danger')
    return redirect(url_for('auth.admin_mail_log'))
