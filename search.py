import re
import os
import shutil
import unicodedata
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR)).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
EXCEL_FILE = DATA_DIR / "EmployeeDB.xlsx"
SEED_EXCEL_FILE = BASE_DIR / "EmployeeDB.xlsx"
REQUIRED_COLUMNS = {"Full_name", "Emp_NUB"}
MAX_MESSAGE_LENGTH = 3900


def load_employee_file(path=EXCEL_FILE):
    frame = pd.read_excel(path, dtype=str)
    missing = REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing required Excel columns: {', '.join(sorted(missing))}")
    frame = frame[["Full_name", "Emp_NUB"]].copy()
    frame["Full_name"] = frame["Full_name"].fillna("").str.strip()
    frame["Emp_NUB"] = frame["Emp_NUB"].fillna("").str.strip()
    return frame


def ensure_employee_file():
    if EXCEL_FILE.exists():
        return
    if SEED_EXCEL_FILE.exists() and SEED_EXCEL_FILE != EXCEL_FILE:
        shutil.copy2(SEED_EXCEL_FILE, EXCEL_FILE)
        return
    raise FileNotFoundError(f"Employee database not found: {EXCEL_FILE}")


def _normalize_arabic(value):
    value = unicodedata.normalize("NFKD", str(value))
    value = "".join(char for char in value if not unicodedata.combining(char))
    return value.translate(str.maketrans({
        "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
        "ى": "ي", "ـ": "",
    })).casefold().strip()


ensure_employee_file()
df = load_employee_file()
normalized_names = df["Full_name"].map(_normalize_arabic)


def reload_employees():
    global df, normalized_names
    df = load_employee_file()
    normalized_names = df["Full_name"].map(_normalize_arabic)
    return len(df)


def employee_count():
    return len(df)


def _split_messages(entries):
    messages = []
    current = ""
    for entry in entries:
        if current and len(current) + len(entry) > MAX_MESSAGE_LENGTH:
            messages.append(current.rstrip())
            current = ""
        current += entry
    if current:
        messages.append(current.rstrip())
    return messages


def search_employee(text):
    query = text.strip()
    if not query:
        return ["⚠️ اكتب اسم الموظف أو رقمه الوظيفي."]

    if query.isdigit():
        result = df[df["Emp_NUB"].str.contains(re.escape(query), case=False, na=False, regex=True)]
    else:
        words = [word for word in _normalize_arabic(query).split() if word]
        if not words:
            return ["⚠️ اكتب اسماً صحيحاً للبحث."]
        mask = normalized_names.notna()
        for word in words:
            mask &= normalized_names.str.contains(re.escape(word), na=False, regex=True)
        result = df[mask]

    if result.empty:
        return ["❌ لم يتم العثور على أي موظف."]

    entries = [
        f"👤 {row.Full_name}\n🆔 {row.Emp_NUB}\n\n"
        for row in result.itertuples(index=False)
    ]
    return _split_messages(entries)
