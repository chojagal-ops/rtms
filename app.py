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

from models import db, User, TestStandard, SysConfig, MailLog
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
    # 접수대기 건수 — 사이드바 배지용
    pending_count = 0
    try:
        from models import TestRequest
        pending_count = TestRequest.query.filter_by(status='접수대기').count()
    except Exception:
        pass
    return dict(
        STATUS_META=STATUS_META,
        REQUEST_STATUSES=REQUEST_STATUSES,
        OVERALL_RESULTS=OVERALL_RESULTS,
        today=_date.today(),
        app_version=APP_VERSION,          # CSS/JS 캐시 버스팅용
        pending_count=pending_count,      # 사이드바 배지
    )


# ── Blueprint 등록 ────────────────────────────────────────
from routes.auth      import auth_bp
from routes.dashboard import dashboard_bp
from routes.requests  import requests_bp
from routes.results   import results_bp
from routes.ledger    import ledger_bp
from routes.stats     import stats_bp
from routes.calendar  import calendar_bp
from routes.nc        import nc_bp
from routes.standards import standards_bp

app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(requests_bp)
app.register_blueprint(results_bp)
app.register_blueprint(ledger_bp)
app.register_blueprint(stats_bp)
app.register_blueprint(calendar_bp)
app.register_blueprint(nc_bp)
app.register_blueprint(standards_bp)


# ── DB 마이그레이션 (컬럼 추가) ──────────────────────────
def migrate_db():
    """기존 DB에 새 컬럼이 없으면 자동 추가 (SQLite · PostgreSQL 공용)"""
    inspector = sql_inspect(db.engine)
    tables    = inspector.get_table_names()

    is_pg = _db_url.startswith('postgresql')

    # PostgreSQL 예약어 테이블(user 등)은 따옴표로 감싸야 함
    _RESERVED = {'user', 'order', 'group', 'table', 'select'}

    def _safe(tbl):
        return f'"{tbl}"' if (is_pg and tbl.lower() in _RESERVED) else tbl

    def add_col(table, col, col_type):
        if table in tables:
            try:
                cols = [c['name'] for c in inspector.get_columns(table)]
                if col not in cols:
                    with db.engine.connect() as conn:
                        conn.execute(text(
                            f'ALTER TABLE {_safe(table)} ADD COLUMN {col} {col_type}'
                        ))
                        conn.commit()
                    print(f'[RTMS] 컬럼 추가: {table}.{col}')
            except Exception as e:
                print(f'[RTMS] 컬럼 추가 건너뜀 ({table}.{col}): {e}')

    add_col('test_request', 'requester_position', 'VARCHAR(50)')
    add_col('test_result',  'summary',             'TEXT')
    add_col('test_result',  'notes',               'TEXT')
    add_col('test_result',  'tester_name',         'VARCHAR(50)')
    add_col('test_result',  'notifier_name',       'VARCHAR(50)')
    add_col('test_result',  'report_attached',     'BOOLEAN')
    add_col('test_result',  'attach_doc_name',     'TEXT')
    add_col('test_result',  'test_complete_date',  'DATE')
    add_col('test_result',  'notify_date',         'DATE')
    add_col('test_result',  'qa_approver',         'VARCHAR(50)')
    add_col('user',         'email',               'VARCHAR(120)')
    add_col('test_request', 'test_type',           "VARCHAR(20) DEFAULT '신규시험'")
    add_col('test_request', 'retest_ref_id',       'INTEGER')

    # ── NC 테이블 시험의뢰자 컬럼 ────────────────────────────
    add_col('nc_report', 'requester_name',    'VARCHAR(50)')
    add_col('nc_report', 'requester_dept',    'VARCHAR(100)')
    add_col('nc_report', 'requester_contact', 'VARCHAR(50)')
    add_col('nc_report', 'requester_email',   'VARCHAR(120)')

    # ── NC 테이블 컬럼 (db.create_all 이후 보완용) ──────────
    # nc_report / nc_action 은 create_all 로 생성되므로 add_col 불필요
    # 기존 test_result의 합격/불합격 → 적합/부적합 데이터 마이그레이션
    try:
        with db.engine.connect() as conn:
            conn.execute(text(
                "UPDATE test_result SET overall_result='적합' WHERE overall_result='합격'"
            ))
            conn.execute(text(
                "UPDATE test_result SET overall_result='부적합' WHERE overall_result='불합격'"
            ))
            conn.execute(text(
                "UPDATE test_item SET item_result='적합' WHERE item_result='합격'"
            ))
            conn.execute(text(
                "UPDATE test_item SET item_result='부적합' WHERE item_result='불합격'"
            ))
            conn.commit()
    except Exception as e:
        print(f'[RTMS] 용어 마이그레이션 건너뜀: {e}')


def seed_test_standards():
    """MX 사출 기구부품 기준서 데이터 DB 적재 (최초 1회)"""
    from models import TestStandard
    if TestStandard.query.first():
        return  # 이미 데이터 있으면 건너뜀
    json_path = BASE_DIR / 'test_standards.json'
    if not json_path.exists():
        print('[RTMS] test_standards.json 없음 — 기준서 시드 건너뜀')
        return
    import json
    with open(json_path, encoding='utf-8') as f:
        items = json.load(f)
    for d in items:
        db.session.add(TestStandard(
            std_no=d.get('no'),
            test_name=d.get('name', ''),
            condition_full=d.get('full', ''),
            condition_summary=d.get('summary', ''),
            sample_qty=d.get('qty', ''),
        ))
    db.session.commit()
    print(f'[RTMS] 시험 기준서 {len(items)}개 항목 적재 완료')


def init_db():
    """테이블 생성 + 기본 관리자 계정 생성 + 기준서 시드"""
    db.create_all()
    migrate_db()
    seed_test_standards()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', name='관리자',
                     department='품질팀', role='admin', is_approved=True)
        admin.set_password('admin1234')
        db.session.add(admin)
        db.session.commit()
        print('[RTMS] 기본 관리자 계정 생성: admin / admin1234')
    # SysConfig 기본값 설정 (없는 키만)
    import os as _os
    _qa = _os.environ.get('QA_EMAIL', 'igm550@intops.co.kr')
    _defaults = {
        'mail_request_enabled': '1',
        'mail_request_to':      _qa,
        'mail_request_cc':      '',
        'mail_result_enabled':  '1',
        'mail_result_cc':       _qa,
        'mail_nc_enabled':      '1',
        'mail_nc_to':           _qa,
        'mail_nc_cc':           '',
    }
    for k, v in _defaults.items():
        if not SysConfig.query.get(k):
            db.session.add(SysConfig(key=k, value=v))
    db.session.commit()


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
