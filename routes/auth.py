# routes/auth.py — 로그인 / 로그아웃 / 회원가입

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User
from utils import log_error

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
            if User.query.filter_by(username=username).first():
                flash('이미 사용 중인 아이디입니다.', 'danger')
                return redirect(url_for('auth.register'))
            user = User(
                username=username,
                name=request.form.get('name', '').strip(),
                department=request.form.get('department', '').strip(),
                is_approved=False,
            )
            user.set_password(request.form.get('password', ''))
            db.session.add(user)
            db.session.commit()
            flash('가입 신청이 완료되었습니다. 관리자 승인 후 로그인 가능합니다.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            log_error('회원가입 오류', e)
            flash('가입 중 오류가 발생했습니다.', 'danger')
    return render_template('register.html')


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
