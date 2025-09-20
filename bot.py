import logging
logging.basicConfig(level=logging.INFO)
import sqlite3
import os
import requests
from datetime import datetime, timedelta
import pandas as pd
from config import TOKEN, OPENROUTER_API_KEY, OPENROUTER_API_URL, OPENROUTER_MODEL
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, ConversationHandler, filters

async def get_ai_response(prompt: str) -> str:
    """Получение ответа от AI через OpenRouter"""
    try:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://your-site.com",
            "X-Title": "Financial Bot"
        }

        payload = {
            "model": OPENROUTER_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 500
        }

        response = requests.post(OPENROUTER_API_URL, headers=headers, json=payload, timeout=15)
        response.raise_for_status()

        return response.json()["choices"][0]["message"]["content"]

    except Exception as e:
        return f"❌ Ошибка AI: {str(e)}"

async def ai_financial_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Улучшенный AI-анализ финансов с персонализацией"""
    user_id = update.effective_user.id

    db_path = os.path.join(os.path.expanduser("~"), 'finance.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Получаем больше данных для анализа
    cursor.execute('SELECT SUM(amount) FROM transactions WHERE user_id = ? AND type = "income"', (user_id,))
    income = cursor.fetchone()[0] or 0

    cursor.execute('SELECT SUM(amount) FROM transactions WHERE user_id = ? AND type = "expense"', (user_id,))
    expense = cursor.fetchone()[0] or 0

    # Статистика за последний месяц (исправленный подход)
    current_month = datetime.now().strftime('%Y-%m')
    cursor.execute('''
        SELECT SUM(amount) FROM transactions
        WHERE user_id = ? AND type = "income" AND strftime('%Y-%m', date) = ?
    ''', (user_id, current_month))
    income_month = cursor.fetchone()[0] or 0

    cursor.execute('''
        SELECT SUM(amount) FROM transactions
        WHERE user_id = ? AND type = "expense" AND strftime('%Y-%m', date) = ?
    ''', (user_id, current_month))
    expense_month = cursor.fetchone()[0] or 0

    # Детальная статистика по категориям
    cursor.execute('''
        SELECT category, SUM(amount), COUNT(*)
        FROM transactions
        WHERE user_id = ? AND type = 'expense'
        GROUP BY category
        ORDER BY SUM(amount) DESC
    ''', (user_id,))
    categories = cursor.fetchall()

    # Самые крупные recent траты
    cursor.execute('''
        SELECT category, amount, description, date
        FROM transactions
        WHERE user_id = ? AND type = 'expense'
        ORDER BY amount DESC
        LIMIT 3
    ''', (user_id,))
    largest_expenses = cursor.fetchall()

    conn.close()

    # Создаем более детальный и персонализированный промпт
    prompt = f"""
    Ты - персональный финансовый консультант. Проанализируй финансовую ситуацию пользователя и дай КОНКРЕТНЫЕ рекомендации.

    БАЗОВАЯ СТАТИСТИКА:
    - Общие доходы: {income:,.2f} руб
    - Общие расходы: {expense:,.2f} руб
    - Общий баланс: {income - expense:,.2f} руб
    - Доходы за текущий месяц: {income_month:,.2f} руб
    - Расходы за текущий месяц: {expense_month:,.2f} руб
    - Месячный баланс: {income_month - expense_month:,.2f} руб

    ДЕТАЛИЗАЦИЯ РАСХОДОВ:
    {chr(10).join([f'- {cat}: {amount:,.2f} руб ({count} операций, {(amount/expense*100):.1f}% от общих расходов)' for cat, amount, count in categories]) if expense > 0 else 'Нет данных о расходах'}

    САМЫЕ КРУПНЫЕ ТРАТЫ:
    {chr(10).join([f'- {cat}: {amount:,.2f} руб ({desc or "без описания"})' for cat, amount, desc, date in largest_expenses]) if largest_expenses else 'Нет данных о крупных тратах'}

    Проанализируй эту информацию и дай КОНКРЕТНЫЕ рекомендации:

    1. ФИНАНСОВОЕ ЗДОРОВЬЕ:
    - Оцени текущую ситуацию (хорошо/плохо/нормально)
    - Укажи самые проблемные зоны
    - Отметь сильные стороны

    2. КОНКРЕТНЫЕ ДЕЙСТВИЯ (для ЕГО ситуации):
    - 3 самых эффективных способа сократить расходы ИМЕННО в его случае
    - Как оптимизировать самые затратные категории
    - Практические шаги по увеличению накоплений

    3. ПЕРСОНАЛЬНЫЕ СОВЕТЫ:
    - Исходя из его паттернов трат
    - Реальные achievable цели на ближайший месяц
    - Конкретные суммы для экономии/накопления

    Избегай общих фраз вроде "ведите бюджет" или "откладывайте 10%". Будь максимально конкретным и практичным. Ответ на русском.
    """

    await update.message.reply_text("🤖 Глубоко анализирую ваши финансы... Это займет 15-20 секунд")

    try:
        analysis = await get_ai_response(prompt)

        # Очищаем текст от неправильного Markdown форматирования
        def clean_markdown(text):
            # Убираем незакрытые Markdown символы
            text = text.replace('*', '').replace('_', '').replace('`', '').replace('~', '')
            # Убираем другие потенциально проблемные символы
            text = text.replace('[', '').replace(']', '').replace('(', '').replace(')', '')
            return text

        # Очищаем анализ от проблемного форматирования
        clean_analysis = clean_markdown(analysis)

        # Простое и надежное разбиение на части
        if len(clean_analysis) > 4000:
            parts = []
            current_part = "📊 ДЕТАЛЬНЫЙ AI-АНАЛИЗ ВАШИХ ФИНАНСОВ:\n\n"

            sentences = clean_analysis.split('. ')
            for sentence in sentences:
                if len(current_part) + len(sentence) > 4000:
                    parts.append(current_part)
                    current_part = sentence + ". "
                else:
                    current_part += sentence + ". "

            if current_part:
                parts.append(current_part)

            # Отправляем первую часть
            await update.message.reply_text(parts[0])
            # Отправляем остальные части
            for part in parts[1:]:
                await update.message.reply_text(part)

        else:
            await update.message.reply_text(
                f"📊 ДЕТАЛЬНЫЙ AI-АНАЛИЗ ВАШИХ ФИНАНСОВ:\n\n{clean_analysis}"
            )

    except Exception as e:
        logging.error(f"AI analysis error: {str(e)}")
        await update.message.reply_text("❌ Произошла ошибка при анализе. Попробуйте позже.")

async def ai_financial_tip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Улучшенные персонализированные финансовые советы"""
    user_id = update.effective_user.id

    db_path = os.path.join(os.path.expanduser("~"), 'finance.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Получаем данные пользователя для персонализации
    cursor.execute('SELECT SUM(amount) FROM transactions WHERE user_id = ? AND type = "expense"', (user_id,))
    total_expense = cursor.fetchone()[0] or 0

    cursor.execute('''
        SELECT category, SUM(amount)
        FROM transactions
        WHERE user_id = ? AND type = 'expense'
        GROUP BY category
        ORDER BY SUM(amount) DESC
        LIMIT 1
    ''', (user_id,))
    top_category = cursor.fetchone()

    # Количество операций
    cursor.execute('SELECT COUNT(*) FROM transactions WHERE user_id = ?', (user_id,))
    total_transactions = cursor.fetchone()[0] or 0

    conn.close()

    # Создаем персонализированный промпт
    prompt = f"""
    Дай ОДИН конкретный, практичный и НЕОБЫЧНЫЙ финансовый совет для этого пользователя.

    КОНТЕКСТ ПОЛЬЗОВАТЕЛЯ:
    - Общие расходы: {total_expense:,.2f} руб
    - Самая затратная категория: {top_category[0] if top_category else 'не определена'} ({top_category[1]:,.2f} руб if top_category else 0)
    - Всего операций: {total_transactions}

    ТРЕБОВАНИЯ К СОВЕТУ:
    - Должен быть КОНКРЕТНЫМ и actionable (что делать прямо сейчас)
    - НЕОБЫЧНЫМ (избегай банальных советов вроде "ведите бюджет" или "откладывайте 10%")
    - Практичным и легко implementable
    - Мотивирующим и позитивным
    - Максимум 2 предложения
    - Учитывай его финансовые привычки

    ПРИМЕРЫ ХОРОШИХ СОВЕТОВ:
    "Попробуйте правило 24 часов - перед любой незапланированной покупкой ждите сутки"
    "Создайте отдельный счет для развлечений с фиксированным лимитом на месяц"
    "Автоматизируйте перевод 15% от каждого дохода на накопительный счет"

    Ответ на русском. Только совет, без вступлений.
    """

    await update.message.reply_text("💡 Генерирую персональный совет для вас...")

    try:
        tip = await get_ai_response(prompt)
        await update.message.reply_text(
            f"💡 *ПЕРСОНАЛЬНЫЙ ФИНАНСОВЫЙ СОВЕТ:*\n\n{tip}",
            parse_mode='Markdown'
        )
    except Exception as e:
        # Fallback совет если AI не ответит
        fallback_tips = [
            "💡 Попробуйте 'правило 72 часов' - перед крупной покупкой ждите 3 дня",
            "💡 Создайте 'буферный фонд' на мелкие расходы чтобы избежать импульсных покупок",
            "💡 Автоматизируйте накопления - настройте автоматический перевод 10% с каждого дохода",
            "💡 Анализируйте подписки - отмените хотя бы одну неиспользуемую на этот месяц",
            "💡 Используйте кэшбэк-сервисы - даже 5% возврата дадут заметную экономию за год"
        ]
        import random
        await update.message.reply_text(random.choice(fallback_tips))


def init_db():
    db_path = os.path.join(os.path.expanduser("~"), 'finance.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            type TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            date TIMESTAMP NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_main_keyboard():
    return ReplyKeyboardMarkup([
        ['💵 Добавить доход', '💰 Добавить расход'],
        ['📊 Статистика', '📋 Детальный отчет'],
        ['🤖 AI-анализ', '💡 Совет от AI'],
        ['📊 Excel отчет', '🗑️ Удалить данные'],
        ['❓ Помощь']
    ], resize_keyboard=True)

def get_period_keyboard():
    return ReplyKeyboardMarkup([
        ['📅 Сегодня', '📅 Неделя'],
        ['📅 Месяц', '📅 Полгода'],
        ['📅 Год', '📅 Все время'],
        ['↩️ Назад']
    ], resize_keyboard=True)

AMOUNT, CATEGORY, DESCRIPTION = range(3)

INCOME_CATEGORIES = ['💼 Зарплата', '👨‍💻 Фриланс', '🎁 Подарок', '📈 Инвестиции', '🏆 Премия', '📱 Прочее']
EXPENSE_CATEGORIES = ['🍔 Еда', '🚗 Транспорт', '🏠 Жилье', '🎬 Развлечения', '🏥 Здоровье', '🎓 Образование', '👕 Одежда', '📱 Прочее']

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я твой финансовый помощник!\n"
        "Я помогу тебе вести учет денег 💰\n\n"
        "Выбери действие:",
        reply_markup=get_main_keyboard()
    )

async def add_income(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💵 Введите сумму дохода (или '↩️ Назад' для отмены):",
        reply_markup=get_back_keyboard()
    )
    context.user_data['type'] = 'income'
    return AMOUNT

async def add_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💰 Введите сумму расхода (или '↩️ Назад' для отмена):",
        reply_markup=get_back_keyboard()
    )
    context.user_data['type'] = 'expense'
    return AMOUNT

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    # Проверяем, не нажал ли пользователь "Назад"
    if text == '↩️ Назад':
        await update.message.reply_text(
            "Операция отменена.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

    try:
        amount = float(text.replace(',', '.'))
        context.user_data['amount'] = amount

        transaction_type = context.user_data['type']
        categories = INCOME_CATEGORIES if transaction_type == 'income' else EXPENSE_CATEGORIES

        keyboard = []
        for i in range(0, len(categories), 2):
            if i + 1 < len(categories):
                keyboard.append([categories[i], categories[i+1]])
            else:
                keyboard.append([categories[i]])

        keyboard.append(['↩️ Назад'])  # Добавляем кнопку назад

        await update.message.reply_text(
            "📂 Выберите категорию:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return CATEGORY

    except ValueError:
        await update.message.reply_text(
            "❌ Пожалуйста, введите число (например: 1500 или 99.99) или нажмите '↩️ Назад' для отмены:",
            reply_markup=get_back_keyboard()
        )
        return AMOUNT

async def get_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    category = update.message.text

    if category == '↩️ Назад':
        await update.message.reply_text(
            "Операция отменена.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

    # Проверяем, что выбрана валидная категория
    transaction_type = context.user_data['type']
    valid_categories = INCOME_CATEGORIES if transaction_type == 'income' else EXPENSE_CATEGORIES

    if category not in valid_categories:
        await update.message.reply_text(
            "❌ Пожалуйста, выберите категорию из списка или нажмите '↩️ Назад' для отмены:",
            reply_markup=get_back_keyboard()
        )
        return CATEGORY

    context.user_data['category'] = category
    await update.message.reply_text(
        "💬 Введите описание (или нажмите /skip чтобы пропустить, или '↩️ Назад' для отмены):",
        reply_markup=get_back_keyboard()
    )
    return DESCRIPTION

async def get_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    description = update.message.text

    # Проверяем, не нажал ли пользователь "Назад"
    if description == '↩️ Назад':
        await update.message.reply_text(
            "Операция отменена.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

    await save_transaction(update, context, description)
    return ConversationHandler.END

async def skip_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await save_transaction(update, context, "")
    return ConversationHandler.END

async def save_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE, description: str):
    db_path = os.path.join(os.path.expanduser("~"), 'finance.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO transactions (user_id, amount, type, category, description, date)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (update.effective_user.id, context.user_data['amount'],
          context.user_data['type'], context.user_data['category'],
          description, datetime.now()))

    conn.commit()
    conn.close()

    transaction_type = "доход" if context.user_data['type'] == 'income' else "расход"
    emoji = "💵" if context.user_data['type'] == 'income' else "💰"

    await update.message.reply_text(
        f"{emoji} {transaction_type.capitalize()} {context.user_data['amount']} руб. "
        f"в категории '{context.user_data['category']}' добавлен!\n\n"
        f"📝 Описание: {description if description else 'нет'}",
        reply_markup=get_main_keyboard()
    )

async def show_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_path = os.path.join(os.path.expanduser("~"), 'finance.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute('SELECT SUM(amount) FROM transactions WHERE user_id = ? AND type = "income"', (update.effective_user.id,))
    income = cursor.fetchone()[0] or 0

    cursor.execute('SELECT SUM(amount) FROM transactions WHERE user_id = ? AND type = "expense"', (update.effective_user.id,))
    expense = cursor.fetchone()[0] or 0

    cursor.execute('''
        SELECT category, SUM(amount)
        FROM transactions
        WHERE user_id = ? AND type = 'expense'
        GROUP BY category
        ORDER BY SUM(amount) DESC
    ''', (update.effective_user.id,))
    expense_by_category = cursor.fetchall()

    conn.close()

    report = "📊 *ОБЩАЯ СТАТИСТИКА*\n\n"
    report += f"💵 *Доходы:* {income:,.2f} руб.\n"
    report += f"💰 *Расходы:* {expense:,.2f} руб.\n"
    report += f"⚖️ *Баланс:* {income - expense:,.2f} руб.\n\n"

    if expense_by_category:
        report += "📈 *РАСХОДЫ ПО КАТЕГОРИЯМ:*\n"
        for category, amount in expense_by_category:
            percentage = (amount / expense * 100) if expense > 0 else 0
            report += f"• {category}: {amount:,.2f} руб. ({percentage:.1f}%)\n"

    await update.message.reply_text(report, parse_mode='Markdown')

async def detailed_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_path = os.path.join(os.path.expanduser("~"), 'finance.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT type, amount, category, description, date
        FROM transactions
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 10
    ''', (update.effective_user.id,))
    recent_transactions = cursor.fetchall()

    conn.close()

    if not recent_transactions:
        await update.message.reply_text("📭 У вас пока нет операций")
        return

    report = "📋 *ПОСЛЕДНИЕ ОПЕРАЦИИ:*\n\n"

    for i, (tr_type, amount, category, description, date) in enumerate(recent_transactions, 1):
        emoji = "💵" if tr_type == 'income' else "💰"
        type_text = "Доход" if tr_type == 'income' else "Расход"
        date_str = datetime.strptime(date, '%Y-%m-%d %H:%M:%S.%f').strftime('%d.%m.%Y %H:%M')

        report += f"{i}. {emoji} *{type_text}: {amount:,.2f} руб.*\n"
        report += f"   🏷️ {category}\n"
        if description:
            report += f"   📝 {description}\n"
        report += f"   🕒 {date_str}\n\n"

    await update.message.reply_text(report, parse_mode='Markdown')

async def generate_excel_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запрос периода для Excel отчета"""
    await update.message.reply_text(
        "📊 Выберите период для отчета:",
        reply_markup=get_period_keyboard()
    )
    context.user_data['awaiting_period'] = True

async def create_excel_file(user_id: int, period: str) -> str:
    """Создание Excel файла с данными за указанный период"""
    db_path = os.path.join(os.path.expanduser("~"), 'finance.db')
    conn = sqlite3.connect(db_path)

    # Определяем дату начала в зависимости от периода
    now = datetime.now()
    if period == 'today':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == 'week':
        start_date = now - timedelta(days=7)
    elif period == 'month':
        start_date = now - timedelta(days=30)
    elif period == 'half_year':
        start_date = now - timedelta(days=180)
    elif period == 'year':
        start_date = now - timedelta(days=365)
    else:  # all_time
        start_date = datetime(2000, 1, 1)

    # Получаем данные из базы
    query = '''
        SELECT date, type, category, amount, description
        FROM transactions
        WHERE user_id = ? AND date >= ?
        ORDER BY date DESC
    '''

    df = pd.read_sql_query(query, conn, params=(user_id, start_date))
    conn.close()

    if df.empty:
        return None

    # Преобразуем дату
    df['date'] = pd.to_datetime(df['date'])
    df['Дата'] = df['date'].dt.strftime('%d.%m.%Y %H:%M')

    # Переименовываем колонки для лучшей читаемости
    df = df.rename(columns={
        'type': 'Тип',
        'category': 'Категория',
        'amount': 'Сумма',
        'description': 'Описание'
    })

    # Создаем Excel файл
    filename = f"finance_report_{user_id}_{period}.xlsx"
    filepath = os.path.join(os.path.expanduser("~"), filename)

    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
        # ===== ЛИСТ 1: ДЕТАЛЬНЫЕ ДАННЫЕ =====
        detailed_df = df[['Дата', 'Тип', 'Категория', 'Сумма', 'Описание']].copy()
        detailed_df['Тип'] = detailed_df['Тип'].map({'income': 'Доход', 'expense': 'Расход'})
        detailed_df.to_excel(writer, sheet_name='Детальные данные', index=False)

        # Форматирование листа с детальными данными
        worksheet = writer.sheets['Детальные данные']

        # Устанавливаем ширину колонок
        column_widths = [20, 10, 15, 15, 30]
        for i, width in enumerate(column_widths, 1):
            worksheet.column_dimensions[chr(64 + i)].width = width

        # Добавляем заголовки жирным шрифтом
        for col_num, value in enumerate(detailed_df.columns, 1):
            cell = worksheet.cell(row=1, column=col_num)
            cell.font = cell.font.copy(bold=True)

        # Добавляем форматирование для сумм
        for row in range(2, len(detailed_df) + 2):
            cell = worksheet.cell(row=row, column=4)  # Колонка Сумма
            cell.number_format = '#,##0.00" руб"'

            # Цветовое кодирование: доходы - зеленый, расходы - красный
            type_cell = worksheet.cell(row=row, column=2)  # Колонка Тип
            if type_cell.value == 'Доход':
                cell.font = cell.font.copy(color='FF008000')  # Зеленый
            else:
                cell.font = cell.font.copy(color='FFFF0000')  # Красный

        # ===== ЛИСТ 2: СВОДКА ПО КАТЕГОРИЯМ =====
        summary = df.groupby(['Тип', 'Категория']).agg({
            'Сумма': ['sum', 'count']
        }).round(2)
        summary.columns = ['Сумма', 'Количество операций']
        summary = summary.reset_index()
        summary['Тип'] = summary['Тип'].map({'income': 'Доход', 'expense': 'Расход'})

        summary.to_excel(writer, sheet_name='Сводка по категориям', index=False)

        # Форматирование листа сводки
        worksheet_summary = writer.sheets['Сводка по категориям']

        # Ширина колонок
        column_widths_summary = [10, 15, 15, 20]
        for i, width in enumerate(column_widths_summary, 1):
            worksheet_summary.column_dimensions[chr(64 + i)].width = width

        # Жирные заголовки
        for col_num, value in enumerate(summary.columns, 1):
            cell = worksheet_summary.cell(row=1, column=col_num)
            cell.font = cell.font.copy(bold=True)

        # Форматирование сумм
        for row in range(2, len(summary) + 2):
            cell = worksheet_summary.cell(row=row, column=3)  # Колонка Сумма
            cell.number_format = '#,##0.00" руб"'

            cell = worksheet_summary.cell(row=row, column=4)  # Колонка Количество операций
            cell.number_format = '0'

        # ===== ЛИСТ 3: ОБЩАЯ СТАТИСТИКА =====
        stats = df.groupby('Тип').agg({
            'Сумма': ['sum', 'count', 'mean', 'max', 'min']
        }).round(2)
        stats.columns = ['Общая сумма', 'Количество операций', 'Средняя сумма', 'Максимальная сумма', 'Минимальная сумма']
        stats = stats.reset_index()
        stats['Тип'] = stats['Тип'].map({'income': 'Доход', 'expense': 'Расход'})

        # Добавляем итоги
        total_income = stats[stats['Тип'] == 'Доход']['Общая сумма'].sum()
        total_expense = stats[stats['Тип'] == 'Расход']['Общая сумма'].sum()
        balance = total_income - total_expense

        stats.to_excel(writer, sheet_name='Общая статистика', index=False)

        # Форматирование листа статистики
        worksheet_stats = writer.sheets['Общая статистика']

        # Ширина колонок
        column_widths_stats = [15, 15, 20, 15, 20, 20]
        for i, width in enumerate(column_widths_stats, 1):
            worksheet_stats.column_dimensions[chr(64 + i)].width = width

        # Жирные заголовки
        for col_num, value in enumerate(stats.columns, 1):
            cell = worksheet_stats.cell(row=1, column=col_num)
            cell.font = cell.font.copy(bold=True)

        # Форматирование чисел
        for row in range(2, len(stats) + 2):
            for col in range(2, 7):  # Колонки с числами
                cell = worksheet_stats.cell(row=row, column=col)
                if col == 3:  # Количество операций
                    cell.number_format = '0'
                else:
                    cell.number_format = '#,##0.00" руб"'

        # Добавляем строку с балансом
        balance_row = len(stats) + 3
        worksheet_stats.cell(row=balance_row, column=1, value='БАЛАНС:').font = cell.font.copy(bold=True)
        worksheet_stats.cell(row=balance_row, column=2, value=balance).number_format = '#,##0.00" руб"'

        if balance >= 0:
            worksheet_stats.cell(row=balance_row, column=2).font = cell.font.copy(color='FF008000')
        else:
            worksheet_stats.cell(row=balance_row, column=2).font = cell.font.copy(color='FFFF0000')

    return filepath

async def handle_period_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора периода для Excel отчета"""
    if not context.user_data.get('awaiting_period'):
        return

    period_mapping = {
        '📅 Сегодня': 'today',
        '📅 Неделя': 'week',
        '📅 Месяц': 'month',
        '📅 Полгода': 'half_year',
        '📅 Год': 'year',
        '📅 Все время': 'all_time'
    }

    user_choice = update.message.text

    if user_choice == '↩️ Назад':
        await update.message.reply_text(
            "Операция отменена.",
            reply_markup=get_main_keyboard()
        )
        context.user_data.pop('awaiting_period', None)
        return

    if user_choice not in period_mapping:
        await update.message.reply_text(
            "❌ Пожалуйста, выберите период из списка:",
            reply_markup=get_period_keyboard()
        )
        return

    period_key = period_mapping[user_choice]

    await update.message.reply_text(
        f"📊 Генерирую Excel отчет за {user_choice.lower()}...",
        reply_markup=ReplyKeyboardRemove()
    )

    try:
        filepath = await create_excel_file(update.effective_user.id, period_key)

        if filepath is None:
            await update.message.reply_text(
                "❌ Нет данных за выбранный период.",
                reply_markup=get_main_keyboard()
            )
        else:
            # Отправляем файл пользователю
            with open(filepath, 'rb') as file:
                await update.message.reply_document(
                    document=file,
                    caption=f"📊 Excel отчет за {user_choice.lower()}\n\n"
                        "Файл содержит 3 листа:\n"
                        "📋 • Детальные данные - все операции с датами\n"
                        "📈 • Сводка по категориям - группировка по типам и категориям\n"
                        "📊 • Общая статистика - ключевые метрики и баланс\n\n"
                        "💡 Файл автоматически отформатирован для удобного чтения",
                    reply_markup=get_main_keyboard()
                )

            # Удаляем временный файл
            os.remove(filepath)

    except Exception as e:
        logging.error(f"Excel generation error: {str(e)}")
        await update.message.reply_text(
            "❌ Произошла ошибка при генерации отчета. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )

    context.user_data.pop('awaiting_period', None)

async def clear_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = ReplyKeyboardMarkup([
        ['✅ Да, очистить', '❌ Нет, отмена']
    ], resize_keyboard=True)

    await update.message.reply_text(
        "⚠️ *ВНИМАНИЕ!*\n\n"
        "Вы уверены что хотите удалить ВСЕ данные?\n"
        "Это действие нельзя отменить!",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )
    context.user_data['awaiting_confirm'] = True

async def confirm_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == '✅ Да, очистить':
        db_path = os.path.join(os.path.expanduser("~"), 'finance.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute('DELETE FROM transactions WHERE user_id = ?', (update.effective_user.id,))
        conn.commit()
        conn.close()

        await update.message.reply_text(
            "🗑️ Все данные успешно удалены!",
            reply_markup=get_main_keyboard()
        )
    else:
        await update.message.reply_text(
            "❌ Очистка отменена",
            reply_markup=get_main_keyboard()
        )

    context.user_data.pop('awaiting_confirm', None)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
🤖 *ФИНАНСОВЫЙ ПОМОЩНИК - СПРАВКА*

*Основные команды:*
💵 *Добавить доход* - записать полученные деньги
💰 *Добавить расход* - записать потраченные деньги
📊 *Статистика* - общая статистика доходов/расходов
📋 *Детальный отчет* - последние 10 операций
📊 *Excel отчет* - выгрузка данных в Excel файл
🤖 *AI-анализ* - анализ ваших финансов с рекомендациями
💡 *Совет от AI* - случайный полезный совет
🗑️ *Удалить данные* - удалить все записи

*Периоды для Excel отчета:*
📅 Сегодня - операции за сегодня
📅 Неделя - операции за последние 7 дней
📅 Месяц - операции за последние 30 дней
📅 Полгода - операции за последние 180 дней
📅 Год - операции за последние 365 дней
📅 Все время - все доступные данные
    """

    await update.message.reply_text(help_text, parse_mode='Markdown')

def get_back_keyboard():
    return ReplyKeyboardMarkup([['↩️ Назад']], resize_keyboard=True)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Операция отменена.",
        reply_markup=get_main_keyboard()
    )
    return ConversationHandler.END

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_confirm'):
        await confirm_clear(update, context)
    elif context.user_data.get('awaiting_period'):
        await handle_period_selection(update, context)
    else:
        await update.message.reply_text(
            "Выберите действие из меню:",
            reply_markup=get_main_keyboard()
        )

def main():
    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex('^💵 Добавить доход$'), add_income),
            MessageHandler(filters.Regex('^💰 Добавить расход$'), add_expense)
        ],
        states={
            AMOUNT: [
                MessageHandler(filters.Regex('^↩️ Назад$'), cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount)
            ],
            CATEGORY: [
                MessageHandler(filters.Regex('^↩️ Назад$'), cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_category)
            ],
            DESCRIPTION: [
                MessageHandler(filters.Regex('^↩️ Назад$'), cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_description),
                CommandHandler('skip', skip_description)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('cancel', cancel))
    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.Regex('^📊 Статистика$'), show_statistics))
    application.add_handler(MessageHandler(filters.Regex('^📋 Детальный отчет$'), detailed_report))
    application.add_handler(MessageHandler(filters.Regex('^📊 Excel отчет$'), generate_excel_report))
    application.add_handler(MessageHandler(filters.Regex('^🗑️ Удалить данные$'), clear_data))
    application.add_handler(MessageHandler(filters.Regex('^❓ Помощь$'), help_command))
    application.add_handler(MessageHandler(filters.Regex('^🤖 AI-анализ$'), ai_financial_analysis))
    application.add_handler(MessageHandler(filters.Regex('^💡 Совет от AI$'), ai_financial_tip))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Бот запущен! Идите в Telegram и напишите /start вашему боту")
    print("Для остановки нажмите Ctrl+C")

    application.run_polling()

if __name__ == '__main__':
    main()