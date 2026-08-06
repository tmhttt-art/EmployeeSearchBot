import pandas as pd

# تحميل ملف الإكسل مرة وحدة عند تشغيل البوت
df = pd.read_excel("EmployeeDB.xlsx", dtype=str)

# تنظيف البيانات
df["Full_name"] = df["Full_name"].fillna("").str.strip()
df["Emp_NUB"] = df["Emp_NUB"].fillna("").str.strip()


def search_employee(name):
    result = df[df["Full_name"].str.contains(name, case=False, na=False)]

    if result.empty:
        return "❌ لم يتم العثور على أي موظف"

    text = ""

    for _, row in result.iterrows():
        text += (
            f"👤 {row['Full_name']}\n"
            f"🆔 {row['Emp_NUB']}\n\n"
        )

    return text