from telegram import ReplyKeyboardMarkup


SEARCH_BUTTON = "🔎 البحث عن موظف"
USERS_BUTTON = "👥 إدارة المستخدمين"
LOGS_BUTTON = "📋 سجل البحث"
UPDATE_BUTTON = "📥 تحديث قاعدة البيانات"
STATS_BUTTON = "📈 الإحصائيات"
SETTINGS_BUTTON = "⚙️ الإعدادات"
JOIN_BUTTON = "📩 إرسال طلب انضمام"
REQUESTS_BUTTON = "📩 طلبات الانضمام"
STATUS_BUTTON = "ℹ️ حالة البوت"

ADMIN_BUTTONS = {
    SEARCH_BUTTON,
    USERS_BUTTON,
    LOGS_BUTTON,
    UPDATE_BUTTON,
    STATS_BUTTON,
    SETTINGS_BUTTON,
    REQUESTS_BUTTON,
}


def admin_keyboard():
    return ReplyKeyboardMarkup(
        [
            [SEARCH_BUTTON],
            [REQUESTS_BUTTON],
            [USERS_BUTTON, LOGS_BUTTON],
            [UPDATE_BUTTON, STATS_BUTTON],
            [SETTINGS_BUTTON],
        ],
        resize_keyboard=True,
    )


def guest_keyboard():
    return ReplyKeyboardMarkup([[JOIN_BUTTON]], resize_keyboard=True)


def user_keyboard():
    return ReplyKeyboardMarkup(
        [[SEARCH_BUTTON], [STATS_BUTTON, STATUS_BUTTON]],
        resize_keyboard=True,
    )


def approver_keyboard():
    return ReplyKeyboardMarkup([[REQUESTS_BUTTON]], resize_keyboard=True)
