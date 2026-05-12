# models.py — 신뢰성 시험 관리 시스템 데이터베이스 모델

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()


# ── 사용자 ──────────────────────────────────────────────────
class User(UserMixin, db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    username     = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    name         = db.Column(db.String(50), nullable=False)
    department   = db.Column(db.String(50), default='품질팀')
    role         = db.Column(db.String(20), default='user')   # admin / user
    is_approved  = db.Column(db.Boolean, default=False)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)


# ── 신뢰성 시험 의뢰서 ─────────────────────────────────────
class TestRequest(db.Model):
    __tablename__ = 'test_request'

    id               = db.Column(db.Integer, primary_key=True)
    request_no       = db.Column(db.String(50), unique=True)          # 의뢰번호

    # 날짜
    write_date       = db.Column(db.Date)                             # 작성일자
    deadline         = db.Column(db.Date)                             # 완료 희망일자

    # 섹션1: 의뢰 부서 및 담당자
    request_dept     = db.Column(db.String(100))                      # 의뢰부서
    requester_name   = db.Column(db.String(50))                       # 의뢰자 성명
    requester_position = db.Column(db.String(50))                     # 직책
    contact          = db.Column(db.String(50))                       # 연락처
    project_customer = db.Column(db.String(100))                      # 프로젝트/고객사

    # 섹션2: 제품 정보
    product_name     = db.Column(db.String(100))                      # 제품명
    model_code       = db.Column(db.String(100))                      # 모델명/코드
    product_type     = db.Column(db.String(50))                       # 제품 종류
    test_stage       = db.Column(db.String(50))                       # 시험단계
    change_content   = db.Column(db.Text)                             # 변경 내용

    # 섹션3: 시험 목적
    test_purpose     = db.Column(db.String(50))                       # 시험 목적 선택
    test_purpose_detail = db.Column(db.Text)                          # 상세 설명

    # 섹션4: 시편 정보
    sample_qty       = db.Column(db.Integer)                          # 시편 수량
    sample_state     = db.Column(db.String(50))                       # 상태
    sample_id_method = db.Column(db.Text)                             # 식별 방법
    sample_notes     = db.Column(db.Text)                             # 특이사항

    # 섹션7: 시험 일정
    req_start_date   = db.Column(db.Date)                             # 요청 시작일
    req_end_date     = db.Column(db.Date)                             # 요청 완료일
    priority         = db.Column(db.String(10))                       # 우선순위
    schedule_notes   = db.Column(db.Text)                             # 일정 요청

    # 섹션8: 시험 시 특이사항
    test_unit        = db.Column(db.Boolean, default=False)           # 단품 상태 시험
    test_package     = db.Column(db.Boolean, default=False)           # 포장 상태 시험
    test_assembly    = db.Column(db.Boolean, default=False)           # 조립 상태 시험
    other_conditions = db.Column(db.Text)                             # 기타

    # 섹션9: 첨부 문서
    attach_types     = db.Column(db.Text)                             # 첨부 유형 목록 (쉼표 구분)
    attach_doc_name  = db.Column(db.Text)                             # 첨부 문서명
    attachment       = db.Column(db.String(300))                      # 첨부파일

    # 섹션10: 의뢰 부서 승인
    writer_name      = db.Column(db.String(50))                       # 작성자
    dept_approver    = db.Column(db.String(50))                       # 승인자

    # 섹션11: 품질팀 승인
    receiver_name    = db.Column(db.String(50))                       # 접수자
    feasibility      = db.Column(db.String(20))                       # 시험 가능 여부
    review_opinion   = db.Column(db.Text)                             # 검토 의견
    qa_approver      = db.Column(db.String(50))                       # QA 승인자

    # 상태 관리
    status           = db.Column(db.String(20), default='접수대기')
    notes            = db.Column(db.Text)                             # 비고
    created_by       = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at       = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 관계
    test_items    = db.relationship('TestItem',      backref='request', lazy=True,
                                    cascade='all, delete-orphan', order_by='TestItem.item_no')
    criteria      = db.relationship('TestCriterion', backref='request', lazy=True,
                                    cascade='all, delete-orphan', order_by='TestCriterion.criterion_no')
    result        = db.relationship('TestResult', backref='request', lazy=True,
                                    cascade='all, delete-orphan', uselist=False)


# ── 시험 항목 (섹션5) ─────────────────────────────────────
class TestItem(db.Model):
    __tablename__ = 'test_item'
    id             = db.Column(db.Integer, primary_key=True)
    request_id     = db.Column(db.Integer, db.ForeignKey('test_request.id'), nullable=False)
    item_no        = db.Column(db.Integer, default=1)                 # 항목번호
    test_name      = db.Column(db.String(100))                        # 시험 항목
    test_condition = db.Column(db.Text)                               # 시험조건
    standard       = db.Column(db.String(100))                        # 규격
    # 결과서에서 입력
    item_result    = db.Column(db.String(20))                         # 합격/불합격/해당없음
    result_detail  = db.Column(db.Text)                               # 결과 상세


# ── 판정 기준 (섹션6) ─────────────────────────────────────
class TestCriterion(db.Model):
    __tablename__ = 'test_criterion'
    id               = db.Column(db.Integer, primary_key=True)
    request_id       = db.Column(db.Integer, db.ForeignKey('test_request.id'), nullable=False)
    criterion_no     = db.Column(db.Integer, default=1)
    criterion_type   = db.Column(db.String(30))                       # 기능/외관/성능/기타
    criterion_content = db.Column(db.Text)                            # 기준 내용


# ── 신뢰성 시험 결과서 ─────────────────────────────────────
class TestResult(db.Model):
    __tablename__ = 'test_result'
    id                 = db.Column(db.Integer, primary_key=True)
    request_id         = db.Column(db.Integer, db.ForeignKey('test_request.id'),
                                   nullable=False, unique=True)
    result_date        = db.Column(db.Date)                           # 작성일자
    complete_date      = db.Column(db.Date)                           # 완료 일자
    test_complete_date = db.Column(db.Date)                           # 시험 완료일
    notify_date        = db.Column(db.Date)                           # 통보일
    overall_result     = db.Column(db.String(20))                     # 합격/불합격/조건부합격
    summary            = db.Column(db.Text)                           # 결과 요약
    sample_returned    = db.Column(db.Boolean, default=False)         # 시료 전달 여부
    tester_name        = db.Column(db.String(50))                     # 시험자
    notifier_name      = db.Column(db.String(50))                     # 통보자
    report_attached    = db.Column(db.Boolean, default=False)         # 시험 성적서 첨부
    attach_doc_name    = db.Column(db.Text)                           # 첨부 문서명
    attachment         = db.Column(db.String(300))                    # 첨부파일
    notes              = db.Column(db.Text)
    created_by         = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at         = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at         = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
