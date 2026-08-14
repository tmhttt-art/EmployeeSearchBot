import asyncio
import shutil
from datetime import datetime
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from database import (
    ADMIN_ID,
    add_join_request,
    add_user,
    delete_join_request,
    delete_user_completely,
    get_join_request,
    get_join_reviewer_ids,
    get_setting,
    get_active_user_ids,
    get_recent_searches,
    get_statistics,
    get_user,
    get_user_statistics,
    is_bot_enabled,
    list_users,
    list_join_requests,
    log_search,
    set_setting,
    set_user_role,
    set_user_status,
)
from keyboards import (
    ADMIN_BUTTONS,
    JOIN_BUTTON,
    LOGS_BUTTON,
    SEARCH_BUTTON,
    REQUESTS_BUTTON,
    SETTINGS_BUTTON,
    STATS_BUTTON,
    STATUS_BUTTON,
    UPDATE_BUTTON,
    USERS_BUTTON,
    admin_keyboard,
    approver_keyboard,
    guest_keyboard,
    user_keyboard,
)
from search import DATA_DIR, EXCEL_FILE, employee_count, load_employee_file, reload_employees, search_employee


BASE_DIR = Path(__file__).resolve().parent
KEYBOARD_VERSION = "3"


def _is_active(user):
    return bool(user and user[4] == "Active")


def _is_admin(user):
    return bool(_is_active(user) and user[3] == "Admin")


def _is_reviewer(user):
    return bool(_is_active(user) and user[3] in {"Admin", "Approver"})


def _admin_allowed(update):
    user = get_user(update.effective_user.id)
    return _is_admin(user) and update.effective_user.id == ADMIN_ID


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    context.user_data.clear()

    if _is_admin(user):
        await update.message.reply_text(
            "👋 أهلاً بك مدير النظام.", reply_markup=admin_keyboard()
        )
        return

    if _is_reviewer(user):
        await update.message.reply_text(
            "🛡 أنت مسؤول قبول الطلبات. ستصلك طلبات الانضمام هنا لقبولها أو رفضها.",
            reply_markup=approver_keyboard(),
        )
        return

    if get_join_request(update.effective_user.id) is not None:
        await update.message.reply_text(
            "⏳ طلب انضمامك ما زال قيد المراجعة. لا يمكنك استخدام البوت حتى يوافق عليه أحد المسؤولين.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    if not is_bot_enabled():
        await update.message.reply_text("🛠 البوت متوقف مؤقتاً للصيانة. حاول لاحقاً.")
        return

    if user and not _is_active(user):
        await update.message.reply_text("⛔ تم تعطيل حسابك. راجع مدير النظام.")
        return

    if _is_active(user):
        context.user_data["waiting_search"] = False
        await update.message.reply_text(
            "👋 أهلاً بك. اختر عملية من القائمة.",
            reply_markup=user_keyboard(),
        )
        return

    await update.message.reply_text(
        "⛔ ليست لديك صلاحية لاستخدام البوت.\n\n"
        "اضغط الزر بالأسفل لإرسال طلب انضمام.",
        reply_markup=guest_keyboard(),
    )


async def _handle_guest(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    telegram_id = update.effective_user.id
    if text != JOIN_BUTTON:
        await update.message.reply_text(f"اضغط على زر {JOIN_BUTTON}.")
        return

    created = add_join_request(
        telegram_id,
        update.effective_user.username or "",
        update.effective_user.full_name,
    )
    if not created:
        await update.message.reply_text("⏳ لديك طلب انضمام قيد المراجعة بالفعل.")
        return

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ قبول", callback_data=f"approve:{telegram_id}"),
        InlineKeyboardButton("❌ رفض", callback_data=f"reject:{telegram_id}"),
    ]])
    notification = (
        "📥 طلب انضمام جديد\n\n"
        f"👤 {update.effective_user.full_name}\n"
        f"@{update.effective_user.username or '-'}\n"
        f"🆔 {telegram_id}"
    )
    for reviewer_id in get_join_reviewer_ids():
        try:
            await context.bot.send_message(
                chat_id=reviewer_id, text=notification, reply_markup=keyboard
            )
        except Exception:
            pass
    await update.message.reply_text("✅ تم إرسال طلبك إلى مدير النظام.")


async def _perform_search(update: Update, telegram_id: int, text: str):
    log_search(telegram_id, text)
    for message in search_employee(text):
        await update.message.reply_text(message)


def _users_panel():
    rows = list_users(30)
    lines = ["👥 إدارة المستخدمين", ""]
    buttons = []
    for telegram_id, username, full_name, role, status, _ in rows:
        icon = "✅" if status == "Active" else "⛔"
        role_text = {
            "Admin": "المدير الرئيسي",
            "Approver": "مسؤول قبول",
            "User": "مستخدم",
        }.get(role, role)
        lines.append(f"{icon} {full_name} — {role_text}\n@{username or '-'} | {telegram_id}")
        if role != "Admin":
            action = "تعطيل" if status == "Active" else "تفعيل"
            role_action = "إلغاء مسؤول القبول" if role == "Approver" else "تعيين مسؤول قبول"
            buttons.append([
                InlineKeyboardButton(
                    f"{action}: {full_name[:24]}", callback_data=f"user_toggle:{telegram_id}"
                ),
                InlineKeyboardButton(
                    role_action, callback_data=f"role_toggle:{telegram_id}"
                ),
            ])
            buttons.append([
                InlineKeyboardButton(
                    f"🗑 حذف نهائي: {full_name[:24]}",
                    callback_data=f"delete_confirm:{telegram_id}",
                )
            ])
    buttons.append([InlineKeyboardButton("🔄 تحديث القائمة", callback_data="users_refresh")])
    return "\n\n".join(lines), InlineKeyboardMarkup(buttons)


def _settings_panel():
    enabled = is_bot_enabled()
    status = "يعمل ✅" if enabled else "وضع الصيانة 🛠"
    action = "🛑 إيقاف البوت للمستخدمين" if enabled else "▶️ تشغيل البوت للمستخدمين"
    callback_data = "maintenance_off" if enabled else "maintenance_on"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(action, callback_data=callback_data)],
        [InlineKeyboardButton("ℹ️ حالة النظام", callback_data="system_status")],
    ])
    return f"⚙️ إعدادات البوت\n\nالحالة الحالية: {status}", keyboard


def _requests_panel():
    rows = list_join_requests(30)
    if not rows:
        return "📩 لا توجد طلبات انضمام معلقة حالياً.", None
    lines = [f"📩 طلبات الانضمام المعلقة: {len(rows)}", ""]
    buttons = []
    for telegram_id, username, full_name, request_date in rows:
        lines.append(
            f"👤 {full_name}\n@{username or '-'} | {telegram_id}\n🕒 {request_date}"
        )
        buttons.append([
            InlineKeyboardButton("✅ قبول", callback_data=f"approve:{telegram_id}"),
            InlineKeyboardButton("❌ رفض", callback_data=f"reject:{telegram_id}"),
        ])
    return "\n\n".join(lines), InlineKeyboardMarkup(buttons)


async def on_startup(application):
    if get_setting("keyboard_version", "0") == KEYBOARD_VERSION:
        return
    for telegram_id in get_active_user_ids():
        try:
            await application.bot.send_message(
                chat_id=telegram_id,
                text="🆕 تم تحديث قائمة البوت. الأزرار الجديدة جاهزة للاستخدام.",
                reply_markup=user_keyboard(),
            )
        except Exception:
            pass
        await asyncio.sleep(0.05)
    for telegram_id in get_join_reviewer_ids():
        user = get_user(telegram_id)
        keyboard = admin_keyboard() if _is_admin(user) else approver_keyboard()
        try:
            await application.bot.send_message(
                chat_id=telegram_id,
                text="🆕 تم تحديث لوحة التحكم.",
                reply_markup=keyboard,
            )
        except Exception:
            pass
        await asyncio.sleep(0.05)
    set_setting("keyboard_version", KEYBOARD_VERSION)


async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    user = get_user(telegram_id)
    text = update.message.text.strip()

    if _is_reviewer(user) and not _is_admin(user):
        if text == REQUESTS_BUTTON:
            panel, keyboard = _requests_panel()
            await update.message.reply_text(panel, reply_markup=keyboard)
        else:
            await update.message.reply_text(
                "🛡 صلاحيتك مخصصة لقبول ورفض طلبات الانضمام فقط.",
                reply_markup=approver_keyboard(),
            )
        return


    if get_join_request(telegram_id) is not None:
        await update.message.reply_text(
            "⏳ طلب انضمامك ما زال قيد المراجعة. انتظر موافقة أحد المسؤولين.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    if _is_active(user) and not _is_admin(user) and text == STATUS_BUTTON:
        status = "يعمل بصورة طبيعية ✅" if is_bot_enabled() else "متوقف للصيانة 🛠"
        await update.message.reply_text(
            f"ℹ️ حالة البوت: {status}", reply_markup=user_keyboard()
        )
        return

    if not _is_admin(user) and not is_bot_enabled():
        await update.message.reply_text("🛠 البوت متوقف مؤقتاً للصيانة. حاول لاحقاً.")
        return

    if user and not _is_active(user):
        await update.message.reply_text("⛔ تم تعطيل حسابك. راجع مدير النظام.")
        return

    if not user:
        await _handle_guest(update, context, text)
        return

    if not _is_admin(user):
        if text == SEARCH_BUTTON:
            context.user_data["waiting_search"] = True
            await update.message.reply_text("✍️ اكتب اسم الموظف أو رقمه الوظيفي.")
        elif text == STATS_BUTTON:
            context.user_data["waiting_search"] = False
            stats = get_user_statistics(telegram_id)
            last = stats["last_search"]
            last_text = f"{last[0]} — {last[1]}" if last else "لا يوجد"
            await update.message.reply_text(
                "📈 إحصائياتك\n\n"
                f"🔎 مجموع عمليات بحثك: {stats['total']}\n"
                f"📅 عمليات بحثك اليوم: {stats['today']}\n"
                f"🕒 آخر بحث: {last_text}\n"
                f"📚 عدد سجلات الموظفين: {employee_count()}"
            )
        elif context.user_data.get("waiting_search", False):
            await _perform_search(update, telegram_id, text)
        else:
            await update.message.reply_text(
                "اختر البحث أو الإحصائيات من القائمة.", reply_markup=user_keyboard()
            )
        return

    if context.user_data.get("waiting_search", False) and text not in ADMIN_BUTTONS:
        await _perform_search(update, telegram_id, text)
        return

    if text in ADMIN_BUTTONS:
        context.user_data.clear()

    if text == SEARCH_BUTTON:
        context.user_data["waiting_search"] = True
        await update.message.reply_text("✍️ اكتب اسم الموظف أو رقمه الوظيفي.")
    elif text == USERS_BUTTON:
        panel, keyboard = _users_panel()
        await update.message.reply_text(panel, reply_markup=keyboard)
    elif text == REQUESTS_BUTTON:
        panel, keyboard = _requests_panel()
        await update.message.reply_text(panel, reply_markup=keyboard)
    elif text == LOGS_BUTTON:
        rows = get_recent_searches(20)
        if not rows:
            await update.message.reply_text("📋 سجل البحث فارغ حالياً.")
            return
        lines = ["📋 آخر 20 عملية بحث", ""]
        for telegram_id, full_name, searched_name, search_time in rows:
            clean_query = searched_name.replace("\n", " ")
            lines.append(f"🔎 {clean_query}\n👤 {full_name} ({telegram_id})\n🕒 {search_time}")
        await update.message.reply_text("\n\n".join(lines))
    elif text == STATS_BUTTON:
        stats = get_statistics()
        top = stats["top_search"]
        top_text = f"{top[0]} ({top[1]} مرات)" if top else "لا يوجد"
        await update.message.reply_text(
            "📈 إحصائيات البوت\n\n"
            f"👥 المستخدمون النشطون: {stats['active_users']}\n"
            f"⛔ المستخدمون المعطلون: {stats['inactive_users']}\n"
            f"📩 طلبات قيد الانتظار: {stats['pending_requests']}\n"
            f"🔎 إجمالي عمليات البحث: {stats['total_searches']}\n"
            f"📅 عمليات بحث اليوم: {stats['today_searches']}\n"
            f"👤 مستخدمون بحثوا: {stats['unique_searchers']}\n"
            f"🏆 الأكثر بحثاً: {top_text}\n"
            f"📚 عدد سجلات الموظفين: {employee_count()}"
        )
    elif text == UPDATE_BUTTON:
        context.user_data["waiting_excel"] = True
        await update.message.reply_text(
            "📥 أرسل الآن ملف Excel الجديد بصيغة .xlsx.\n\n"
            "يجب أن يحتوي على العمودين Full_name و Emp_NUB."
        )
    elif text == SETTINGS_BUTTON:
        panel, keyboard = _settings_panel()
        await update.message.reply_text(panel, reply_markup=keyboard)
    else:
        await update.message.reply_text("اختر عملية من القائمة.")


async def documents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _admin_allowed(update):
        await update.message.reply_text("⛔ غير مصرح لك برفع قاعدة البيانات.")
        return
    if not context.user_data.get("waiting_excel"):
        await update.message.reply_text("اختر أولاً 📥 تحديث قاعدة البيانات.")
        return

    document = update.message.document
    if not document.file_name or not document.file_name.lower().endswith(".xlsx"):
        await update.message.reply_text("❌ الملف غير مقبول. أرسل ملفاً بصيغة .xlsx فقط.")
        return

    temp_file = BASE_DIR / ".employee-upload.xlsx"
    try:
        telegram_file = await document.get_file()
        await telegram_file.download_to_drive(custom_path=str(temp_file))
        new_frame = load_employee_file(temp_file)
        if new_frame.empty:
            raise ValueError("ملف Excel لا يحتوي على موظفين")

        backup_dir = DATA_DIR / "data_backups"
        backup_dir.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(EXCEL_FILE, backup_dir / f"EmployeeDB-{stamp}.xlsx")
        temp_file.replace(EXCEL_FILE)
        total = reload_employees()
        context.user_data["waiting_excel"] = False
        await update.message.reply_text(
            f"✅ تم تحديث قاعدة البيانات بنجاح.\n\n📚 عدد السجلات: {total}"
        )
    except Exception as error:
        if temp_file.exists():
            temp_file.unlink()
        await update.message.reply_text(
            f"❌ لم يتم تحديث قاعدة البيانات، وبقي الملف القديم كما هو.\n\nالسبب: {error}"
        )


async def _handle_join_request(query, context, action, telegram_id):
    request = get_join_request(telegram_id)
    if request is None:
        await query.edit_message_text("ℹ️ تمت معالجة هذا الطلب مسبقاً.")
        return
    _, username, full_name, _ = request
    if action == "approve":
        add_user(telegram_id, username, full_name, role="User", status="Active")
        delete_join_request(telegram_id)
        try:
            await context.bot.send_message(
                chat_id=telegram_id,
                text="✅ تمت الموافقة على طلبك.\n\nيمكنك الآن استخدام البوت.",
                reply_markup=user_keyboard(),
            )
        except Exception:
            pass
        await query.edit_message_text(f"✅ تمت الموافقة على:\n\n👤 {full_name}")
    else:
        delete_join_request(telegram_id)
        try:
            await context.bot.send_message(chat_id=telegram_id, text="❌ تم رفض طلب الانضمام.")
        except Exception:
            pass
        await query.edit_message_text("❌ تم رفض طلب الانضمام.")


async def _notify_maintenance_finished(context):
    for telegram_id in get_active_user_ids():
        try:
            await context.bot.send_message(
                chat_id=telegram_id,
                text="✅ انتهت الصيانة، يمكنك استخدام البوت الآن.",
                reply_markup=user_keyboard(),
            )
        except Exception:
            pass
        await asyncio.sleep(0.05)


async def _notify_maintenance_started(context):
    for telegram_id in get_active_user_ids():
        try:
            await context.bot.send_message(
                chat_id=telegram_id,
                text="🛠 دخل البوت الآن في حالة الصيانة. سنبلغك عند عودته للعمل.",
                reply_markup=user_keyboard(),
            )
        except Exception:
            pass
        await asyncio.sleep(0.05)


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if data.startswith(("approve:", "reject:")):
        actor = get_user(update.effective_user.id)
        if not _is_reviewer(actor):
            await query.answer("غير مصرح لك بمعالجة الطلبات.", show_alert=True)
            return
        action, raw_id = data.split(":", 1)
        if not raw_id.isdigit():
            await query.answer("طلب غير صالح.", show_alert=True)
            return
        await query.answer()
        await _handle_join_request(query, context, action, int(raw_id))
        return

    if not _admin_allowed(update):
        await query.answer("هذا الإجراء متاح للمدير الرئيسي فقط.", show_alert=True)
        return

    if data == "users_refresh":
        await query.answer()
        panel, keyboard = _users_panel()
        try:
            await query.edit_message_text(panel, reply_markup=keyboard)
        except BadRequest as error:
            if "Message is not modified" not in str(error):
                raise
        return

    if data.startswith("user_toggle:"):
        raw_id = data.split(":", 1)[1]
        if not raw_id.isdigit():
            await query.answer("مستخدم غير صالح.", show_alert=True)
            return
        target = get_user(int(raw_id))
        if not target or target[3] == "Admin":
            await query.answer("لا يمكن تعديل هذا المستخدم.", show_alert=True)
            return
        new_status = "Inactive" if target[4] == "Active" else "Active"
        set_user_status(target[0], new_status)
        await query.answer("تم تحديث حالة المستخدم.")
        panel, keyboard = _users_panel()
        await query.edit_message_text(panel, reply_markup=keyboard)
        return

    if data.startswith("role_toggle:"):
        raw_id = data.split(":", 1)[1]
        if not raw_id.isdigit():
            await query.answer("مستخدم غير صالح.", show_alert=True)
            return
        target = get_user(int(raw_id))
        if not target or target[3] == "Admin":
            await query.answer("لا يمكن تعديل دور هذا المستخدم.", show_alert=True)
            return
        new_role = "User" if target[3] == "Approver" else "Approver"
        set_user_role(target[0], new_role)
        await query.answer("تم تحديث صلاحية المستخدم.")
        try:
            if new_role == "Approver":
                await context.bot.send_message(
                    chat_id=target[0],
                    text=(
                        "🛡 تم تعيينك مسؤولاً لقبول طلبات الانضمام.\n\n"
                        "ستصلك الطلبات هنا، وصلاحيتك مقتصرة على القبول والرفض."
                    ),
                    reply_markup=approver_keyboard(),
                )
            else:
                await context.bot.send_message(
                    chat_id=target[0],
                    text="ℹ️ تم إلغاء صلاحية مسؤول القبول. يمكنك استخدام البوت كمستخدم.",
                    reply_markup=user_keyboard(),
                )
        except Exception:
            pass
        panel, keyboard = _users_panel()
        await query.edit_message_text(panel, reply_markup=keyboard)
        return

    if data.startswith("delete_confirm:"):
        raw_id = data.split(":", 1)[1]
        if not raw_id.isdigit():
            await query.answer("مستخدم غير صالح.", show_alert=True)
            return
        target = get_user(int(raw_id))
        if not target or target[3] == "Admin":
            await query.answer("لا يمكن حذف هذا المستخدم.", show_alert=True)
            return
        await query.answer()
        await query.edit_message_text(
            "⚠️ تأكيد الحذف النهائي\n\n"
            f"👤 {target[2]}\n"
            f"🆔 {target[0]}\n\n"
            "سيتم حذف الحساب وسجل بحثه بالكامل. هل أنت متأكد؟",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "🗑 نعم، احذف نهائياً", callback_data=f"delete_execute:{target[0]}"
                ),
                InlineKeyboardButton("↩️ إلغاء", callback_data="delete_cancel"),
            ]]),
        )
        return

    if data.startswith("delete_execute:"):
        raw_id = data.split(":", 1)[1]
        if not raw_id.isdigit():
            await query.answer("مستخدم غير صالح.", show_alert=True)
            return
        target = get_user(int(raw_id))
        if not target or target[3] == "Admin":
            await query.answer("لا يمكن حذف هذا المستخدم.", show_alert=True)
            return
        deleted = delete_user_completely(target[0])
        if not deleted:
            await query.answer("تعذر حذف المستخدم.", show_alert=True)
            return
        await query.answer("تم حذف المستخدم نهائياً.")
        await query.edit_message_text(
            f"🗑 تم حذف المستخدم نهائياً:\n\n👤 {target[2]}\n🆔 {target[0]}"
        )
        try:
            await context.bot.send_message(
                chat_id=target[0],
                text=(
                    "ℹ️ تم حذف حسابك من البوت.\n\n"
                    "يمكنك تقديم طلب انضمام جديد إذا أردت استخدامه مرة أخرى."
                ),
                reply_markup=guest_keyboard(),
            )
        except Exception:
            pass
        return

    if data == "delete_cancel":
        await query.answer("تم إلغاء الحذف.")
        panel, keyboard = _users_panel()
        await query.edit_message_text(panel, reply_markup=keyboard)
        return

    if data in {"maintenance_on", "maintenance_off"}:
        enabled = data == "maintenance_on"
        set_setting("bot_enabled", "1" if enabled else "0")
        if enabled:
            context.application.create_task(
                _notify_maintenance_finished(context),
                name="maintenance-finished-notification",
            )
        else:
            context.application.create_task(
                _notify_maintenance_started(context),
                name="maintenance-started-notification",
            )
        await query.answer("تم تشغيل البوت." if enabled else "تم تفعيل وضع الصيانة.")
        panel, keyboard = _settings_panel()
        await query.edit_message_text(panel, reply_markup=keyboard)
        return

    if data == "system_status":
        await query.answer()
        stats = get_statistics()
        status = "يعمل ✅" if is_bot_enabled() else "وضع الصيانة 🛠"
        await query.edit_message_text(
            "ℹ️ حالة النظام\n\n"
            f"حالة البوت: {status}\n"
            f"سجلات الموظفين: {employee_count()}\n"
            f"المستخدمون النشطون: {stats['active_users']}\n"
            f"إجمالي البحث: {stats['total_searches']}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ رجوع للإعدادات", callback_data="settings_back")
            ]]),
        )
        return

    if data == "settings_back":
        await query.answer()
        panel, keyboard = _settings_panel()
        await query.edit_message_text(panel, reply_markup=keyboard)
        return

    await query.answer("أمر غير معروف.", show_alert=True)
