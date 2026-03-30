import sys
import re
import os
from PyQt6 import QtWidgets, uic
from PyQt6.QtWidgets import (
    QMessageBox, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QComboBox, QPushButton, QGroupBox, QScrollArea,
)
from PyQt6.QtCore import Qt, QRegularExpression, QSize
from PyQt6.QtGui import QPixmap, QIcon, QPainter, QRegularExpressionValidator, QColor

import mysql.connector
from mysql.connector import Error

DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "root",
    "database": "estudyo_db"
}

NULL_DISPLAY = "-NULL-"

class DBManager:
    def __init__(self):
        self.conn = None
        self._connect()
        self._init_schema()

    def _connect(self):
        try:
            cfg = {k: v for k, v in DB_CONFIG.items() if k != "database"}
            tmp = mysql.connector.connect(**cfg)
            cur = tmp.cursor()
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{DB_CONFIG['database']}` "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            tmp.commit(); cur.close(); tmp.close()
            self.conn = mysql.connector.connect(**DB_CONFIG)
            self.conn.autocommit = True
        except Error as exc:
            raise ConnectionError(
                f"Cannot connect to MySQL.\n\nError: {exc}\n\n"
                "Please check DB_CONFIG in estudyo_app.py and make sure MySQL is running."
            )

    def _cursor(self):
        if not self.conn or not self.conn.is_connected():
            self.conn = mysql.connector.connect(**DB_CONFIG)
            self.conn.autocommit = True
        return self.conn.cursor(dictionary=True)

    def _init_schema(self):
        cur = self._cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS colleges (
                code VARCHAR(20)  PRIMARY KEY,
                name VARCHAR(200) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS programs (
                code         VARCHAR(30)  PRIMARY KEY,
                name         VARCHAR(200) NOT NULL,
                college_code VARCHAR(20)  DEFAULT NULL,
                FOREIGN KEY (college_code) REFERENCES colleges(code)
                    ON UPDATE CASCADE ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id           VARCHAR(9)   PRIMARY KEY,
                first_name   VARCHAR(100) NOT NULL,
                last_name    VARCHAR(100) NOT NULL,
                gender       ENUM('Male','Female') NOT NULL,
                year_level   TINYINT      NOT NULL,
                program_code VARCHAR(30)  DEFAULT NULL,
                FOREIGN KEY (program_code) REFERENCES programs(code)
                    ON UPDATE CASCADE ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        for sql in [
            "CREATE INDEX IF NOT EXISTS idx_s_fname ON students(first_name)",
            "CREATE INDEX IF NOT EXISTS idx_s_lname ON students(last_name)",
            "CREATE INDEX IF NOT EXISTS idx_s_prog  ON students(program_code)",
            "CREATE INDEX IF NOT EXISTS idx_p_coll  ON programs(college_code)",
        ]:
            try: cur.execute(sql)
            except Exception:
                pass
        self.conn.commit(); cur.close()

    def _exec(self, sql, params=None):
        cur = self._cursor()
        cur.execute(sql, params or ()); self.conn.commit(); cur.close()

    def _fetch(self, sql, params=None):
        cur = self._cursor(); cur.execute(sql, params or ())
        rows = cur.fetchall(); cur.close(); return rows

    def _fetchone(self, sql, params=None):
        cur = self._cursor(); cur.execute(sql, params or ())
        row = cur.fetchone(); cur.close(); return row

    # Colleges
    def get_colleges(self, search="", search_field="all", sort_col="code", sort_dir="ASC", page=1, page_size=10):
        col = sort_col if sort_col in {"code", "name"} else "code"
        direction = "DESC" if sort_dir.upper() == "DESC" else "ASC"
        offset = (page - 1) * page_size
        where, params = "", []
        if search:
            s = f"%{search}%"
            if search_field == "code":
                where, params = "WHERE code LIKE %s", [s]
            elif search_field == "name":
                where, params = "WHERE name LIKE %s", [s]
            else:
                where = "WHERE code LIKE %s OR name LIKE %s"
                params = [s, s]
        total = self._fetchone(f"SELECT COUNT(*) as cnt FROM colleges {where}", params)["cnt"]
        rows  = self._fetch(
            f"SELECT * FROM colleges {where} ORDER BY {col} {direction} "
            f"LIMIT {page_size} OFFSET {offset}", params
        )
        return rows, total

    def get_all_colleges(self):
        return self._fetch("SELECT code, name FROM colleges ORDER BY code")

    def add_college(self, code, name):
        if self._fetchone("SELECT 1 FROM colleges WHERE code=%s", (code,)):
            raise ValueError(f"College code '{code}' already exists.")
        self._exec("INSERT INTO colleges(code, name) VALUES(%s,%s)", (code, name))

    def edit_college(self, old_code, new_code, new_name):
        if old_code != new_code and self._fetchone("SELECT 1 FROM colleges WHERE code=%s", (new_code,)):
            raise ValueError(f"College code '{new_code}' already exists.")
        self._exec("UPDATE colleges SET code=%s, name=%s WHERE code=%s", (new_code, new_name, old_code))

    def delete_college(self, code):
        self._exec("DELETE FROM colleges WHERE code=%s", (code,))

    def college_has_programs(self, code):
        return self._fetchone("SELECT COUNT(*) as cnt FROM programs WHERE college_code=%s", (code,))["cnt"] > 0

    # Programs
    def get_programs(self, search="", search_field="all", sort_col="code", sort_dir="ASC", page=1, page_size=10):
        col = sort_col if sort_col in {"code", "name", "college_code"} else "code"
        direction = "DESC" if sort_dir.upper() == "DESC" else "ASC"
        offset = (page - 1) * page_size
        where, params = "", []
        if search:
            s = f"%{search}%"
            if search_field == "code":
                where, params = "WHERE p.code LIKE %s", [s]
            elif search_field == "name":
                where, params = "WHERE p.name LIKE %s", [s]
            elif search_field == "college_code":
                where, params = "WHERE p.college_code LIKE %s", [s]
            else:
                where = "WHERE p.code LIKE %s OR p.name LIKE %s OR p.college_code LIKE %s"
                params = [s, s, s]
        total = self._fetchone(f"SELECT COUNT(*) as cnt FROM programs p {where}", params)["cnt"]
        rows  = self._fetch(
            f"SELECT p.code, p.name, COALESCE(p.college_code, '-NULL-') AS college_code "
            f"FROM programs p {where} ORDER BY {col} {direction} "
            f"LIMIT {page_size} OFFSET {offset}", params
        )
        return rows, total

    def get_all_programs(self):
        return self._fetch("SELECT code, name FROM programs ORDER BY code")

    def add_program(self, code, name, college_code):
        if self._fetchone("SELECT 1 FROM programs WHERE code=%s", (code,)):
            raise ValueError(f"Program code '{code}' already exists.")
        coll = college_code if college_code != NULL_DISPLAY else None
        self._exec("INSERT INTO programs(code, name, college_code) VALUES(%s,%s,%s)", (code, name, coll))

    def edit_program(self, old_code, new_code, new_name, new_college_code):
        if old_code != new_code and self._fetchone("SELECT 1 FROM programs WHERE code=%s", (new_code,)):
            raise ValueError(f"Program code '{new_code}' already exists.")
        coll = new_college_code if new_college_code != NULL_DISPLAY else None
        self._exec("UPDATE programs SET code=%s, name=%s, college_code=%s WHERE code=%s",
                   (new_code, new_name, coll, old_code))

    def delete_program(self, code):
        self._exec("DELETE FROM programs WHERE code=%s", (code,))

    def program_has_students(self, code):
        return self._fetchone("SELECT COUNT(*) as cnt FROM students WHERE program_code=%s", (code,))["cnt"] > 0

    # Students
    def get_students(self, search="", search_field="all",
                 sort_col="id", sort_dir="ASC", page=1, page_size=10):
        allowed = {"id", "first_name", "last_name", "gender", "year_level", "program_code"}
        col = sort_col if sort_col in allowed else "id"
        direction = "DESC" if sort_dir.upper() == "DESC" else "ASC"
        offset = (page - 1) * page_size
        where, params = "", []
        if search:
            s = f"%{search}%"
            if search_field == "id":
                where, params = "WHERE s.id LIKE %s", [s]
            elif search_field == "first_name":
                where, params = "WHERE s.first_name LIKE %s", [s]
            elif search_field == "last_name":
                where, params = "WHERE s.last_name LIKE %s", [s]
            elif search_field == "program_code":
                where, params = "WHERE COALESCE(s.program_code,'') LIKE %s", [s]
            else:
                where = ("WHERE s.id LIKE %s OR s.first_name LIKE %s "
                         "OR s.last_name LIKE %s OR COALESCE(s.program_code,'') LIKE %s")
                params = [s, s, s, s]
        total = self._fetchone(f"SELECT COUNT(*) as cnt FROM students s {where}", params)["cnt"]
        rows  = self._fetch(
            f"SELECT s.id, s.first_name, s.last_name, s.gender, s.year_level, "
            f"COALESCE(s.program_code, '-NULL-') AS program_code "
            f"FROM students s {where} ORDER BY {col} {direction} "
            f"LIMIT {page_size} OFFSET {offset}", params
        )
        return rows, total

    def add_student(self, sid, first_name, last_name, gender, program_code, year_level):
        if self._fetchone("SELECT 1 FROM students WHERE id=%s", (sid,)):
            raise ValueError(f"Student ID '{sid}' already exists.")
        prog = program_code if program_code != NULL_DISPLAY else None
        self._exec(
            "INSERT INTO students(id, first_name, last_name, gender, year_level, program_code) "
            "VALUES(%s,%s,%s,%s,%s,%s)",
            (sid, first_name, last_name, gender, int(year_level), prog)
        )

    def edit_student(self, old_id, new_id, first_name, last_name, gender, program_code, year_level):
        if old_id != new_id and self._fetchone("SELECT 1 FROM students WHERE id=%s", (new_id,)):
            raise ValueError(f"Student ID '{new_id}' already exists.")
        prog = program_code if program_code != NULL_DISPLAY else None
        self._exec(
            "UPDATE students SET id=%s, first_name=%s, last_name=%s, "
            "gender=%s, year_level=%s, program_code=%s WHERE id=%s",
            (new_id, first_name, last_name, gender, int(year_level), prog, old_id)
        )

    def delete_student(self, sid):
        self._exec("DELETE FROM students WHERE id=%s", (sid,))

def _apply_student_id_validator(le):
    rx = QRegularExpression(r"^\d{0,4}-?\d{0,4}$")
    le.setValidator(QRegularExpressionValidator(rx))
    def _fmt(text):
        digits = text.replace("-", "")
        if len(digits) > 4:
            fmted = digits[:4] + "-" + digits[4:8]
            if text != fmted:
                le.blockSignals(True); le.setText(fmted)
                le.setCursorPosition(len(fmted)); le.blockSignals(False)
    le.textChanged.connect(_fmt)

def _validate_sid(sid):
    return bool(re.fullmatch(r"\d{4}-\d{4}", sid))

def _apply_code_validator(le):
    rx = QRegularExpression(r"^[A-Za-z ()\s]*$")
    le.setValidator(QRegularExpressionValidator(rx))
    def _upper(t):
        if t != t.upper():
            le.blockSignals(True)
            le.setText(t.upper())
            le.blockSignals(False)
    le.textChanged.connect(_upper)

def _apply_name_validator(le):
    rx = QRegularExpression(r"^[A-Za-z ()\-'\s]*$")
    le.setValidator(QRegularExpressionValidator(rx))

DIALOG_STYLE = """
QDialog { background-color: #f0f7ff; }
QGroupBox {
    background-color: white; border: 1px solid #bbdefb; border-radius: 8px;
    margin-top: 14px; padding-top: 14px; font-weight: bold; color: #0d2c54; font-size: 13px;
}
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 4px 12px; color: #0d2c54; }
QLabel { color: #1a3a5c; font-weight: 600; font-size: 13px; }
QLineEdit, QComboBox { padding: 8px 12px; border: 1.5px solid #90caf9; border-radius: 6px;
    background-color: white; font-size: 13px; min-height: 32px; }
QLineEdit:focus, QComboBox:focus { border-color: #1976d2; }
QPushButton#btnSaveDialog { background-color: #1565c0; color: white; border-radius: 6px;
    padding: 9px 28px; font-size: 13px; font-weight: 700; }
QPushButton#btnSaveDialog:hover { background-color: #0d47a1; }
QPushButton#btnCancelDialog { background-color: #eceff1; color: #37474f; border-radius: 6px;
    padding: 9px 28px; font-size: 13px; font-weight: 600; }
QPushButton#btnCancelDialog:hover { background-color: #cfd8dc; }
"""

class _BaseDialog(QDialog):
    def __init__(self, parent, title):
        super().__init__(parent)
        self.setWindowTitle(title); self.setStyleSheet(DIALOG_STYLE); self.setMinimumWidth(460)
        self._layout = QVBoxLayout(self); self._layout.setSpacing(16); self._layout.setContentsMargins(20,20,20,20)

    def _add_buttons(self):
        row = QHBoxLayout(); row.addStretch()
        cancel = QPushButton("Cancel"); cancel.setObjectName("btnCancelDialog")
        save   = QPushButton("Save");   save.setObjectName("btnSaveDialog")
        row.addWidget(cancel); row.addWidget(save); self._layout.addLayout(row)
        save.clicked.connect(self._on_save); cancel.clicked.connect(self.reject)

    def _on_save(self): self.accept()


class StudentDialog(_BaseDialog):
    def __init__(self, parent, programs, student=None):
        super().__init__(parent, "Edit Student" if student else "Add Student")
        grp  = QGroupBox("Student Information"); form = QFormLayout(grp)
        form.setSpacing(10); form.setContentsMargins(16, 20, 16, 16)

        self.lineId      = QLineEdit(student["id"]         if student else "")
        self.lineFirst   = QLineEdit(student["first_name"] if student else "")
        self.lineLast    = QLineEdit(student["last_name"]  if student else "")
        self.comboGender = QComboBox(); self.comboGender.addItems(["Male", "Female"])
        self.comboYear   = QComboBox(); self.comboYear.addItems(["1", "2", "3", "4"])
        self.comboProgram = QComboBox()

        _apply_student_id_validator(self.lineId)
        _apply_name_validator(self.lineFirst)
        _apply_name_validator(self.lineLast)

        if not student:
            self.comboProgram.addItem("— No Program (NULL) —", NULL_DISPLAY)
        for p in programs:
            self.comboProgram.addItem(f"{p['code']} — {p['name']}", p["code"])

        if student:
            idx = self.comboGender.findText(student["gender"])
            if idx >= 0: self.comboGender.setCurrentIndex(idx)
            idx = self.comboYear.findText(str(student["year_level"]))
            if idx >= 0: self.comboYear.setCurrentIndex(idx)
            pc = student.get("program_code", NULL_DISPLAY)
            if pc == NULL_DISPLAY:
                self.comboProgram.insertItem(0, "— No Program (NULL) —", NULL_DISPLAY)
                self.comboProgram.setCurrentIndex(0)
                self.comboProgram.model().item(0).setEnabled(False)
            else:
                for i in range(self.comboProgram.count()):
                    if self.comboProgram.itemData(i) == pc:
                        self.comboProgram.setCurrentIndex(i); break
                    
        form.addRow("Student ID:",  self.lineId)
        form.addRow("First Name:",  self.lineFirst)
        form.addRow("Last Name:",   self.lineLast)
        form.addRow("Gender:",      self.comboGender)
        form.addRow("Year Level:",  self.comboYear)
        form.addRow("Program:",     self.comboProgram)
        self._layout.addWidget(grp); self._add_buttons()

    def _on_save(self):
        sid   = self.lineId.text().strip()
        first = self.lineFirst.text().strip()
        last  = self.lineLast.text().strip()
        if not all([sid, first, last]):
            QMessageBox.warning(self, "Input Error", "Please fill in all fields."); return
        if not _validate_sid(sid):
            QMessageBox.warning(self, "Invalid ID",
                "Student ID must be XXXX-XXXX (digits only, e.g. 2024-0001)."); return
        self.accept()

    def get_data(self):
        return {
            "id":           self.lineId.text().strip(),
            "first_name":   self.lineFirst.text().strip(),
            "last_name":    self.lineLast.text().strip(),
            "gender":       self.comboGender.currentText(),
            "year_level":   self.comboYear.currentText(),
            "program_code": self.comboProgram.currentData(),
        }


class CollegeDialog(_BaseDialog):
    def __init__(self, parent, college=None):
        super().__init__(parent, "Edit College" if college else "Add College")
        grp  = QGroupBox("College Information"); form = QFormLayout(grp)
        form.setSpacing(10); form.setContentsMargins(16, 20, 16, 16)
        self.lineCode = QLineEdit(college["code"] if college else "")
        self.lineName = QLineEdit(college["name"] if college else "")
        _apply_code_validator(self.lineCode)
        form.addRow("College Code:", self.lineCode)
        form.addRow("College Name:", self.lineName)
        self._layout.addWidget(grp); self._add_buttons()

    def _on_save(self):
        if not self.lineCode.text().strip() or not self.lineName.text().strip():
            QMessageBox.warning(self, "Input Error", "Please fill in all fields."); return
        self.accept()

    def get_data(self):
        return {"code": self.lineCode.text().strip(), "name": self.lineName.text().strip()}


class ProgramDialog(_BaseDialog):
    def __init__(self, parent, colleges, program=None):
        super().__init__(parent, "Edit Program" if program else "Add Program")
        grp  = QGroupBox("Program Information"); form = QFormLayout(grp)
        form.setSpacing(10); form.setContentsMargins(16, 20, 16, 16)
        self.lineCode = QLineEdit(program["code"] if program else "")
        self.lineName = QLineEdit(program["name"] if program else "")
        self.comboCollege = QComboBox()
        _apply_code_validator(self.lineCode); _apply_name_validator(self.lineName)
        if not program:
            self.comboCollege.addItem("— No College (NULL) —", NULL_DISPLAY)
        for c in colleges:
            self.comboCollege.addItem(f"{c['code']} — {c['name']}", c["code"])
        if program:
            cc = program.get("college_code", NULL_DISPLAY)
            if cc == NULL_DISPLAY:
                self.comboCollege.insertItem(0, "— No College (NULL) —", NULL_DISPLAY)
                self.comboCollege.setCurrentIndex(0)
                self.comboCollege.model().item(0).setEnabled(False)
            else:
                for i in range(self.comboCollege.count()):
                    if self.comboCollege.itemData(i) == cc:
                        self.comboCollege.setCurrentIndex(i); break
        form.addRow("Program Code:", self.lineCode)
        form.addRow("Program Name:", self.lineName)
        form.addRow("College:",      self.comboCollege)
        self._layout.addWidget(grp); self._add_buttons()

    def _on_save(self):
        if not self.lineCode.text().strip() or not self.lineName.text().strip():
            QMessageBox.warning(self, "Input Error", "Please fill in all fields."); return
        self.accept()

    def get_data(self):
        return {
            "code":         self.lineCode.text().strip(),
            "name":         self.lineName.text().strip(),
            "college_code": self.comboCollege.currentData(),
        }


class EstudyoApp(QtWidgets.QMainWindow):
    def __init__(self, db: DBManager):
        super().__init__()
        self.db = db
        uic.loadUi("estudyo_main.ui", self)
        self.setWindowTitle("Estudyo — Student Information System")
        if os.path.exists("icons/estudyo_logo.svg"):
            self.setWindowIcon(QIcon("icons/estudyo_logo.svg"))

        self._student_page = 1
        self._program_page = 1
        self._college_page = 1

        self._setup_ui()
        self._setup_connections()
        self._load_initial_data()
        self.show()

    def _setup_ui(self):
        if os.path.exists("icons/estudyo_logo.svg"):
            px = QPixmap("icons/estudyo_logo.svg").scaled(44, 44, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
            self.logoLabel.setPixmap(px)

        for btn_name, paths in [
            ("btnManage",   ["student.svg", "icons/student.svg"]),
            ("btnPrograms", ["program.svg", "icons/program.svg"]),
            ("btnColleges", ["college.svg", "icons/college.svg"]),
        ]:
            btn = getattr(self, btn_name, None)
            if not btn: continue
            for p in paths:
                if os.path.exists(p):
                    px = QPixmap(p)
                    painter = QPainter(px)
                    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
                    painter.fillRect(px.rect(), Qt.GlobalColor.white)
                    painter.end()
                    btn.setIcon(QIcon(px)); btn.setIconSize(QSize(20, 20)); break

        for tbl in [self.tableStudents, self.tablePrograms, self.tableColleges]:
            tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            tbl.setAlternatingRowColors(True)
            tbl.verticalHeader().setVisible(False)
            tbl.verticalHeader().setDefaultSectionSize(30)
            tbl.horizontalHeader().setStretchLastSection(False)
            tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            tbl.horizontalHeader().setMinimumSectionSize(60)
            tbl.horizontalHeader().setFixedHeight(36)

        _apply_student_id_validator(self.lineStudentId)
        _apply_code_validator(self.lineCollegeCode)
        _apply_code_validator(self.lineProgramCode)
        _apply_name_validator(self.lineProgramName)
        _apply_name_validator(self.lineFirstName)
        _apply_name_validator(self.lineLastName)
        self._populate_inline_combos()

        self.setMinimumSize(800, 600)
        self.resize(1000, 720)
        self._wrap_pages_scrollable()

    def _wrap_pages_scrollable(self):
        for i in range(self.stackedWidget.count()):
            page = self.stackedWidget.widget(i)
            old_layout = page.layout()
            if not old_layout:
                continue
            inner = QtWidgets.QWidget()
            inner.setObjectName(f"scrollInner_{i}")
            inner.setLayout(old_layout)
            scroll = QScrollArea()
            scroll.setWidget(inner)
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            new_layout = QVBoxLayout(page)
            new_layout.setContentsMargins(0, 0, 0, 0)
            new_layout.setSpacing(0)
            new_layout.addWidget(scroll)

    def _populate_inline_combos(self):
        self.comboProgramCode.clear()
        for p in self.db.get_all_programs():
            self.comboProgramCode.addItem(f"{p['code']} — {p['name']}", p["code"])

        self.comboCollegeCode.clear()
        for c in self.db.get_all_colleges():
            self.comboCollegeCode.addItem(f"{c['code']} — {c['name']}", c["code"])

    def _setup_connections(self):
        self.navButton.clicked.connect(self._nav_students)
        self.btnManage.clicked.connect(self._nav_add_student)
        self.btnPrograms.clicked.connect(self._nav_programs)
        self.btnColleges.clicked.connect(self._nav_colleges)

        self.btnSearch.clicked.connect(self._search_students)
        self.lineSearchInput.returnPressed.connect(self._search_students)
        self.lineSearchInput.textChanged.connect(lambda t: self._search_students() if t == "" else None)
        self.btnSort.clicked.connect(self._sort_students)
        self.btnEdit.clicked.connect(self._edit_student)
        self.btnDelete.clicked.connect(self._delete_student)
        self.tableStudents.doubleClicked.connect(self._edit_student)
        self.btnStudentPrev.clicked.connect(self._student_prev)
        self.btnStudentNext.clicked.connect(self._student_next)

        self.btnAddStudent.clicked.connect(self._add_student_inline)
        self.btnClearStudent.clicked.connect(self._clear_student_form)

        self.btnAddProgram.clicked.connect(self._add_program_inline)
        self.btnClearProgram.clicked.connect(self._clear_program_form)
        self.btnSearchProgram.clicked.connect(self._search_programs)
        self.lineSearchProgram.returnPressed.connect(self._search_programs)
        self.lineSearchProgram.textChanged.connect(lambda t: self._search_programs() if t == "" else None)
        self.comboProgramSearchField.currentIndexChanged.connect(self._search_programs)
        self.btnSortProgram.clicked.connect(self._sort_programs)
        self.btnEditProgram.clicked.connect(self._edit_program)
        self.btnDeleteProgram.clicked.connect(self._delete_program)
        self.tablePrograms.doubleClicked.connect(self._edit_program)
        self.btnProgramPrev.clicked.connect(self._program_prev)
        self.btnProgramNext.clicked.connect(self._program_next)

        self.btnAddCollege.clicked.connect(self._add_college_inline)
        self.btnClearCollege.clicked.connect(self._clear_college_form)
        self.btnSearchCollege.clicked.connect(self._search_colleges)
        self.lineSearchCollege.returnPressed.connect(self._search_colleges)
        self.lineSearchCollege.textChanged.connect(lambda t: self._search_colleges() if t == "" else None)
        self.comboCollegeSearchField.currentIndexChanged.connect(self._search_colleges)
        self.btnSortCollege.clicked.connect(self._sort_colleges)
        self.btnEditCollege.clicked.connect(self._edit_college)
        self.btnDeleteCollege.clicked.connect(self._delete_college)
        self.tableColleges.doubleClicked.connect(self._edit_college)
        self.btnCollegePrev.clicked.connect(self._college_prev)
        self.btnCollegeNext.clicked.connect(self._college_next)
        self.comboStudentPageSize.currentIndexChanged.connect(
            lambda: self._reset_and_load("student"))
        self.comboProgramPageSize.currentIndexChanged.connect(
            lambda: self._reset_and_load("program"))
        self.comboCollegePageSize.currentIndexChanged.connect(
            lambda: self._reset_and_load("college"))
        
    def _reset_and_load(self, kind):
        if kind == "student":
            self._student_page = 1
            self._load_students()
        elif kind == "program":
            self._program_page = 1
            self._load_programs()
        elif kind == "college":
            self._college_page = 1
            self._load_colleges()

    def _load_initial_data(self):
        self.stackedWidget.setCurrentIndex(0)
        self._set_nav_checked(0)
        self._load_students()

    # Navigation
    def _nav_students(self):
        self.stackedWidget.setCurrentIndex(0); self._set_nav_checked(0)
        self._load_students()

    def _nav_add_student(self):
        self.stackedWidget.setCurrentIndex(1); self._set_nav_checked(1)

    def _nav_programs(self):
        self.stackedWidget.setCurrentIndex(2); self._set_nav_checked(2)
        self._load_programs()

    def _nav_colleges(self):
        self.stackedWidget.setCurrentIndex(3); self._set_nav_checked(3)
        self._load_colleges()

    def _set_nav_checked(self, idx):
        for i, btn in enumerate([self.navButton, self.btnManage, self.btnPrograms, self.btnColleges]):
            btn.setChecked(i == idx)

    def _load_students(self):
        search = self.lineSearchInput.text().strip()
        field_map = {
            "Student ID": "id", "First Name": "first_name",
            "Last Name":  "last_name", "Program": "program_code",
        }
        search_field = field_map.get(self.comboSearchField.currentText(), "all")
        sort_map = {
            "Student ID": "id",       "First Name": "first_name",
            "Last Name":  "last_name","Program":    "program_code",
            "Year Level": "year_level","Gender":    "gender",
        }
        sort_col = sort_map.get(self.comboSortField.currentText(), "id")
        sort_dir = "DESC" if "DESC" in self.comboSortDir.currentText() else "ASC"
        page_size = int(self.comboStudentPageSize.currentText())

        rows, total = self.db.get_students(
            search=search, search_field=search_field,
            sort_col=sort_col, sort_dir=sort_dir, page=self._student_page,
            page_size=page_size
        )
        self._fill_table(self.tableStudents, rows,
            keys=["id", "first_name", "last_name", "program_code", "year_level", "gender"],
            null_cols={3})
        self._update_pagination(
            total, self._student_page,
            self.labelStudentPage, self.labelStudentTotal,
            self.btnStudentPrev,   self.btnStudentNext,
            "student", page_size=page_size
        )

    def _search_students(self):
        self._student_page = 1; self._load_students()

    def _sort_students(self):
        self._student_page = 1; self._load_students()

    def _student_prev(self):
        if self._student_page > 1:
            self._student_page -= 1; self._load_students()

    def _student_next(self):
        self._student_page += 1; self._load_students()

    def _add_student_inline(self):
        sid    = self.lineStudentId.text().strip()
        first  = self.lineFirstName.text().strip()
        last   = self.lineLastName.text().strip()
        gender = self.comboGender.currentText()
        year   = self.comboYearLevel.currentText()
        prog   = self.comboProgramCode.currentData() or NULL_DISPLAY

        if not all([sid, first, last]):
            QMessageBox.warning(self, "Input Error", "Please fill in Student ID, First Name, and Last Name.")
            return
        if not _validate_sid(sid):
            QMessageBox.warning(self, "Invalid ID",
                "Student ID must be XXXX-XXXX (digits only, e.g. 2024-0001).")
            return
        try:
            self.db.add_student(sid, first, last, gender, prog, year)
            QMessageBox.information(self, "Success", "Student added successfully.")
            self._clear_student_form(); self._load_students()
        except Exception as exc:
            QMessageBox.warning(self, "Error", str(exc))

    def _edit_student(self):
        sid = self._selected_col(self.tableStudents, 0)
        if not sid:
            QMessageBox.warning(self, "No Selection", "Please select a student to edit."); return
        row = self.db._fetchone(
            "SELECT id, first_name, last_name, gender, year_level, "
            "COALESCE(program_code,'-NULL-') AS program_code FROM students WHERE id=%s", (sid,)
        )
        if not row: return
        row["year_level"] = str(row["year_level"])
        dlg = StudentDialog(self, self.db.get_all_programs(), student=row)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            d = dlg.get_data()
            try:
                self.db.edit_student(row["id"], d["id"], d["first_name"], d["last_name"],
                                     d["gender"], d["program_code"], d["year_level"])
                self._load_students()
                QMessageBox.information(self, "Success", "Student updated.")
            except Exception as exc:
                QMessageBox.warning(self, "Error", str(exc))

    def _delete_student(self):
        sid = self._selected_col(self.tableStudents, 0)
        if not sid:
            QMessageBox.warning(self, "No Selection", "Please select a student to delete."); return
        reply = QMessageBox.question(self, "Confirm Delete", f"Delete student '{sid}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.db.delete_student(sid)
            self._load_students()
            QMessageBox.information(self, "Deleted", "Student deleted.")

    def _clear_student_form(self):
        self.lineStudentId.clear(); self.lineFirstName.clear(); self.lineLastName.clear()
        self.comboGender.setCurrentIndex(0); self.comboYearLevel.setCurrentIndex(0)
        self.comboProgramCode.setCurrentIndex(0)

    def _load_programs(self):
        search = self.lineSearchProgram.text().strip()
        field_map = {
            "Program Code": "code",
            "Program Name": "name",
            "College Code": "college_code",
        }
        search_field = field_map.get(self.comboProgramSearchField.currentText(), "all")
        sort_map = {"Program Code": "code", "Program Name": "name", "College Code": "college_code"}
        sort_col = sort_map.get(self.comboSortProgram.currentText(), "code")
        sort_dir = "DESC" if "DESC" in self.comboSortDirProgram.currentText() else "ASC"
        page_size = int(self.comboProgramPageSize.currentText())
        rows, total = self.db.get_programs(
            search=search, search_field=search_field, sort_col=sort_col, sort_dir=sort_dir,
            page=self._program_page, page_size=page_size
        )
        self._fill_table(self.tablePrograms, rows,
            keys=["code", "name", "college_code"], null_cols={2})
        self._update_pagination(
            total, self._program_page,
            self.labelProgramPage, self.labelProgramTotal,
            self.btnProgramPrev,   self.btnProgramNext,
            "program", page_size=page_size
        )

    def _search_programs(self):
        self._program_page = 1; self._load_programs()

    def _sort_programs(self):
        self._program_page = 1; self._load_programs()

    def _program_prev(self):
        if self._program_page > 1:
            self._program_page -= 1; self._load_programs()

    def _program_next(self):
        self._program_page += 1; self._load_programs()

    def _add_program_inline(self):
        code = self.lineProgramCode.text().strip()
        name = self.lineProgramName.text().strip()
        coll = self.comboCollegeCode.currentData() or NULL_DISPLAY
        if not all([code, name]):
            QMessageBox.warning(self, "Input Error", "Please fill in Program Code and Name."); return
        try:
            self.db.add_program(code, name, coll)
            QMessageBox.information(self, "Success", "Program added.")
            self._clear_program_form(); self._load_programs(); self._populate_inline_combos()
        except Exception as exc:
            QMessageBox.warning(self, "Error", str(exc))

    def _edit_program(self):
        code = self._selected_col(self.tablePrograms, 0)
        if not code:
            QMessageBox.warning(self, "No Selection", "Please select a program to edit."); return
        row = self.db._fetchone(
            "SELECT code, name, COALESCE(college_code,'-NULL-') AS college_code FROM programs WHERE code=%s",
            (code,)
        )
        if not row: return
        dlg = ProgramDialog(self, self.db.get_all_colleges(), program=row)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            d = dlg.get_data()
            try:
                self.db.edit_program(row["code"], d["code"], d["name"], d["college_code"])
                self._load_programs(); self._populate_inline_combos()
                QMessageBox.information(self, "Success", "Program updated.")
            except Exception as exc:
                QMessageBox.warning(self, "Error", str(exc))

    def _delete_program(self):
        code = self._selected_col(self.tablePrograms, 0)
        if not code:
            QMessageBox.warning(self, "No Selection", "Please select a program to delete."); return
        has = self.db.program_has_students(code)
        msg = f"Delete program '{code}'?"
        if has: msg += "\n\nStudents enrolled here will have their program set to NULL."
        reply = QMessageBox.question(self, "Confirm Delete", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.db.delete_program(code)
            self._load_programs(); self._load_students(); self._populate_inline_combos()
            QMessageBox.information(self, "Deleted", "Program deleted.")

    def _clear_program_form(self):
        self.lineProgramCode.clear(); self.lineProgramName.clear()
        self.comboCollegeCode.setCurrentIndex(0)

    def _load_colleges(self):
        search = self.lineSearchCollege.text().strip()
        field_map = {
            "College Code": "code",
            "College Name": "name",
        }
        search_field = field_map.get(self.comboCollegeSearchField.currentText(), "all")
        sort_map = {"College Code": "code", "College Name": "name"}
        sort_col = sort_map.get(self.comboSortCollege.currentText(), "code")
        sort_dir = "DESC" if "DESC" in self.comboSortDirCollege.currentText() else "ASC"
        page_size = int(self.comboCollegePageSize.currentText())
        rows, total = self.db.get_colleges(
            search=search, search_field=search_field, sort_col=sort_col, sort_dir=sort_dir,
            page=self._college_page, page_size=page_size
        )
        self._fill_table(self.tableColleges, rows, keys=["code", "name"])
        self._update_pagination(
            total, self._college_page,
            self.labelCollegePage, self.labelCollegeTotal,
            self.btnCollegePrev,   self.btnCollegeNext,
            "college", page_size=page_size
        )

    def _search_colleges(self):
        self._college_page = 1; self._load_colleges()

    def _sort_colleges(self):
        self._college_page = 1; self._load_colleges()

    def _college_prev(self):
        if self._college_page > 1:
            self._college_page -= 1; self._load_colleges()

    def _college_next(self):
        self._college_page += 1; self._load_colleges()

    def _add_college_inline(self):
        code = self.lineCollegeCode.text().strip()
        name = self.lineCollegeName.text().strip()
        if not all([code, name]):
            QMessageBox.warning(self, "Input Error", "Please fill in College Code and Name."); return
        try:
            self.db.add_college(code, name)
            QMessageBox.information(self, "Success", "College added.")
            self._clear_college_form(); self._load_colleges(); self._populate_inline_combos()
        except Exception as exc:
            QMessageBox.warning(self, "Error", str(exc))

    def _edit_college(self):
        code = self._selected_col(self.tableColleges, 0)
        if not code:
            QMessageBox.warning(self, "No Selection", "Please select a college to edit."); return
        row = self.db._fetchone("SELECT code, name FROM colleges WHERE code=%s", (code,))
        if not row: return
        dlg = CollegeDialog(self, college=row)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            d = dlg.get_data()
            try:
                self.db.edit_college(row["code"], d["code"], d["name"])
                self._load_colleges(); self._populate_inline_combos()
                QMessageBox.information(self, "Success", "College updated.")
            except Exception as exc:
                QMessageBox.warning(self, "Error", str(exc))

    def _delete_college(self):
        code = self._selected_col(self.tableColleges, 0)
        if not code:
            QMessageBox.warning(self, "No Selection", "Please select a college to delete."); return
        has = self.db.college_has_programs(code)
        msg = f"Delete college '{code}'?"
        if has: msg += "\n\nPrograms under this college will have their college set to NULL."
        reply = QMessageBox.question(self, "Confirm Delete", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.db.delete_college(code)
            self._load_colleges(); self._load_programs(); self._populate_inline_combos()
            QMessageBox.information(self, "Deleted", "College deleted.")

    def _clear_college_form(self):
        self.lineCollegeCode.clear(); self.lineCollegeName.clear()

    def _fill_table(self, tbl, rows, keys, null_cols=None):
        null_cols = null_cols or set()
        tbl.setRowCount(0)
        for r_data in rows:
            r = tbl.rowCount(); tbl.insertRow(r)
            tbl.setRowHeight(r, 30)
            for c, key in enumerate(keys):
                val = r_data.get(key)
                val = str(val) if val is not None else NULL_DISPLAY
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter)
                if c in null_cols and val == NULL_DISPLAY:
                    item.setForeground(QColor("#c62828"))
                    f = item.font(); f.setBold(True); item.setFont(f)
                tbl.setItem(r, c, item)
        
        tbl.setFixedHeight(36 + max(tbl.rowCount(), 1) * 30 + 2)
        tbl.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def _update_pagination(self, total, page, lbl_page, lbl_total, btn_prev, btn_next, kind, page_size=10):
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, total_pages)

        if kind == "student":   self._student_page = page
        elif kind == "program": self._program_page = page
        elif kind == "college": self._college_page = page
        lbl_page.setText(f"Page {page} of {total_pages}")
        lbl_total.setText(f"{total:,} {kind}{'s' if total != 1 else ''}")
        btn_prev.setEnabled(page > 1)
        btn_next.setEnabled(page < total_pages)

    def _selected_col(self, tbl, col):
        row = tbl.currentRow()
        if row < 0: return None
        item = tbl.item(row, col)
        return item.text() if item else None

def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")

    try:
        db = DBManager()
    except ConnectionError as exc:
        QMessageBox.critical(None, "Database Connection Error", str(exc))
        sys.exit(1)

    app._win = EstudyoApp(db)

    sys.exit(app.exec())

if __name__ == "__main__":
    main()