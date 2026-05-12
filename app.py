# app.py — 신뢰성 시험 관리 시스템 (RTMS)
# 운용: Render.com (Gunicorn + PostgreSQL) / 로컬 개발 (Flask dev + SQLite)

import os
import time
import logging
from pathlib import Path
from flask import Flask
from flask_login import LoginManager
from dotenv import load_dotenv
from sqlalchemy import text, inspect as sql_inspect

load_dotenv(Path(__file__).parent / '.env')

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'rtms-dev-secret-change-in-prod')

# ── 데이터베이스 설정 ─────────────────────────────────────
BASE_DIR = Path(__file__).parent

# Render는 DATABASE_URL(PostgreSQL)을 주입. 없으면 로컬 SQLite
_db_url = os.environ.get('DATABASE_URL', f'sqlite:///{BASE_DIR / "data.db"}')
# Render의 postgres:// → SQLAlchemy 요구 postgresql://
if _db_url.startswith('postgres://'):
    _db_url = _db_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = _db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,          # 끊긴 연결 자동 감지
    'pool_recycle':  1800,          # 30분마다 연결 재활용
}
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024   # 업로드 최대 50MB

# ── 정적파일 캐시 버스팅 버전 ─────────────────────────────
# 서버 재시작마다 새 버전 → CSS/JS 변경이 브라우저에 즉시 반영
APP_VERSION = str(int(time.time()))

from models import db, User
db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view  = 'auth.login'
login_manager.login_message = '로그인이 필요합니다.'


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ── 템플릿 전역 변수 주입 ─────────────────────────────────
from constants import STATUS_META, REQUEST_STATUSES, OVERALL_RESULTS
from datetime import date as _date

@app.context_processor
def inject_globals():
    return dict(
        STATUS_META=STATUS_META,
        REQUEST_STATUSES=REQUEST_STATUSES,
        OVERALL_RESULTS=OVERALL_RESULTS,
        today=_date.today(),
        app_version=APP_VERSION,          # CSS/JS 캐시 버스팅용
    )


# ── Blueprint 등록 ────────────────────────────────────────
from routes.auth      import auth_bp
from routes.dashboard import dashboard_bp
from routes.requests  import requests_bp
from routes.results   import results_bp
from routes.ledger    import ledger_bp
from routes.stats     import stats_bp

app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(requests_bp)
app.register_blueprint(results_bp)
app.register_blueprint(ledger_bp)
app.register_blueprint(stats_bp)


# ── DB 마이그레이션 (컬럼 추가) ──────────────────────────
def migrate_db():
    """기존 DB에 새 컬럼이 없으면 자동 추가 (SQLite · PostgreSQL 공용)"""
    inspector = sql_inspect(db.engine)
    tables    = inspector.get_table_names()

    is_pg = _db_url.startswith('postgresql')

    def add_col(table, col, col_type):
        if table in tables:
            cols = [c['name'] for c in inspector.get_columns(table)]
            if col not in cols:
                with db.engine.connect() as conn:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {col} {col_type}'))
                    conn.commit()

    add_col('test_request', 'requester_position', 'VARCHAR(50)')
    add_col('test_result',  'summary',             'TEXT')
    add_col('test_result',  'notes',               'TEXT')
    add_col('test_result',  'tester_name',         'VARCHAR(50)')
    add_col('test_result',  'notifier_name',       'VARCHAR(50)')
    add_col('test_result',  'report_attached',     'BOOLEAN')
    add_col('test_result',  'attach_doc_name',     'TEXT')
    add_col('test_result',  'test_complete_date',  'DATE')
    add_col('test_result',  'notify_date',         'DATE')


def init_db():
    """테이블 생성 + 기본 관리자 계정 생성"""
    db.create_all()
    migrate_db()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', name='관리자',
                     department='품질팀', role='admin', is_approved=True)
        admin.set_password('admin1234')
        db.session.add(admin)
        db.session.commit()
        print('[RTMS] 기본 관리자 계정 생성: admin / admin1234')


# ── 앱 시작 시 DB 초기화 (Gunicorn 워커 포함) ───────────
with app.app_context():
    try:
        init_db()
    except Exception as e:
        print(f'[RTMS] DB 초기화 오류: {e}')


# ── 로컬 개발 실행 ────────────────────────────────────────
if __name__ == '__main__':
    import sys

    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

    logging.basicConfig(
        filename=BASE_DIR / 'error.log',
        level=logging.ERROR,
        format='%(asctime)s [%(levelname)s] %(message)s',
        encoding='utf-8',
    )

    port = int(os.environ.get('FLASK_PORT', 5001))
    print(f'[RTMS] 로컬 개발 서버 → http://0.0.0.0:{port}')
    # 로컬에서는 debug=True → 코드 변경 시 자동 재시작
    app.run(host='0.0.0.0', port=port, debug=True, use_reloader=True)
