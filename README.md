# Estudyo v2 — Simple Student Information System
### CCC151 - Information Management

---

## Overview

**Estudyo v2** is a desktop-based Student Information System built with Python and PyQt6. It allows users to manage student records, academic programs, and colleges through a clean GUI. Data is stored in a **MySQL database**.

---

## Features

- Add, edit, and delete students, programs, and colleges
- Student ID validation in `XXXX-XXXX` format
- Search and sort records by any field
- Paginated table
- Deleting a college/program sets affected records' reference to `-NULL-` (shown in red bold)

---

## Tech Stack

| Technology | Purpose |
|---|---|
| Python 3 | Core language |
| PyQt6 | GUI framework |
| MySQL | Database storage |
| mysql-connector-python | MySQL driver |

---

## Project Structure
```
├── estudyo_app.py        # Main application logic
├── estudyo_main.ui       # Qt Designer UI layout
├── icons/
│   ├── estudyo_logo.svg
│   ├── student.svg
│   ├── program.svg
│   └── college.svg
└── README.md
```