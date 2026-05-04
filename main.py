import random
import os
from dotenv import load_dotenv
from telebot import types, TeleBot, custom_filters
from telebot.storage import StateMemoryStorage
from telebot.handler_backends import State, StatesGroup
import database as db

load_dotenv()

print('Запуск бота...')

state_storage = StateMemoryStorage()
token_bot = os.getenv('TOKEN')
bot = TeleBot(token_bot, state_storage=state_storage)

class Command:
    ADD_WORD = 'Добавить слово ➕'
    DELETE_WORD = 'Удалить слово🔙'
    NEXT = 'Дальше ⏭'

class MyStates(StatesGroup):
    target_word = State()       # ожидаем выбор перевода
    translate_word = State()    # сохраняем перевод
    another_words = State()     # другие варианты
    add_english = State()       # ожидаем английское слово
    add_russian = State()       # ожидаем русское слово

user_buttons = {}  # список кнопок


def show_hint(*lines):
    """Объединяет строки в одно сообщение."""
    return '\n'.join(lines)


def show_target(data):
    """Формирует строку: английское -> русское."""
    return f"{data['target_word']} -> {data['translate_word']}"


def build_card(message):
    cid = message.chat.id
    uid = message.from_user.id

    # Получаем слова пользователя из БД
    all_words = db.get_words_for_user(uid)

    if len(all_words) < 4:
        bot.send_message(
            cid,
            "У вас меньше 4 слов. Добавьте ещё слова для игры!"
        )
        return

    # Выбираем случайное целевое слово
    target = random.choice(all_words)
    target_id, target_english, target_russian = target

    # Выбираем 3 случайных слова-дистрактора (не совпадающих с целевым)
    others = random.sample(
        [w for w in all_words if w[0] != target_id], 3
    )
    other_words = [w[1] for w in others]  # только английские слова

    # Строим кнопки
    markup = types.ReplyKeyboardMarkup(row_width=2)
    buttons = []

    target_btn = types.KeyboardButton(target_english)
    buttons.append(target_btn)

    other_btns = [types.KeyboardButton(w) for w in other_words]
    buttons.extend(other_btns)

    random.shuffle(buttons)

    next_btn = types.KeyboardButton(Command.NEXT)
    add_btn = types.KeyboardButton(Command.ADD_WORD)
    del_btn = types.KeyboardButton(Command.DELETE_WORD)
    buttons.extend([next_btn, add_btn, del_btn])

    # Сохраняем кнопки для этого пользователя
    user_buttons[cid] = buttons

    markup.add(*buttons)

    greeting = f"Выбери перевод слова:\n🇷🇺 {target_russian}"
    bot.send_message(cid, greeting, reply_markup=markup)

    # Сохраняем данные карточки в состояние
    bot.set_state(uid, MyStates.target_word, cid)
    with bot.retrieve_data(uid, cid) as data:
        data['target_word'] = target_english
        data['translate_word'] = target_russian
        data['other_words'] = other_words


@bot.message_handler(commands=['start'])
def start(message):
    """
    Обработчик команды /start.
    Регистрирует пользователя и показывает приветствие.
    """
    uid = message.from_user.id
    username = message.from_user.username or message.from_user.first_name

    # Добавляем пользователя в БД (если ещё нет)
    db.add_user(uid, username)

    bot.send_message(
        message.chat.id,
        f"👋 Привет, {username}!\n\n"
        "Я — бот для изучения английских слов.\n\n"
        "📖 Я буду показывать тебе русское слово,\n"
        "а ты выбирай правильный перевод на английский.\n\n"
        "Нажми /cards чтобы начать!"
    )


@bot.message_handler(commands=['cards'])
def create_cards(message):
    """Обработчик команды /cards — запускает карточки."""
    uid = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    db.add_user(uid, username)
    build_card(message)


@bot.message_handler(func=lambda m: m.text == Command.NEXT)
def next_cards(message):
    """Кнопка 'Дальше' — следующая карточка."""
    build_card(message)


@bot.message_handler(func=lambda m: m.text == Command.DELETE_WORD)
def delete_word(message):
    """
    Кнопка 'Удалить слово'.
    Удаляет текущее слово для этого пользователя.
    """
    uid = message.from_user.id
    cid = message.chat.id

    with bot.retrieve_data(uid, cid) as data:
        word_to_delete = data.get('target_word', '')

    if word_to_delete:
        db.delete_word_for_user(uid, word_to_delete)
        bot.send_message(
            cid,
            f"🗑 Слово «{word_to_delete}» удалено из вашего списка.\n"
            f"📚 Слов в вашем словаре: {db.count_user_words(uid)}"
        )
        build_card(message)
    else:
        bot.send_message(cid, "Нет активного слова для удаления.")


@bot.message_handler(func=lambda m: m.text == Command.ADD_WORD)
def add_word_start(message):
    """
    Кнопка 'Добавить слово'.
    Запрашивает английское слово у пользователя.
    """
    cid = message.chat.id
    uid = message.from_user.id

    bot.set_state(uid, MyStates.add_english, cid)
    bot.send_message(
        cid,
        "✏️ Введи новое слово на английском:",
        reply_markup=types.ReplyKeyboardRemove()
    )


@bot.message_handler(
    state=MyStates.add_english,
    content_types=['text']
)
def add_word_english(message):
    """
    Получаем английское слово и запрашиваем перевод.
    """
    cid = message.chat.id
    uid = message.from_user.id

    with bot.retrieve_data(uid, cid) as data:
        data['new_english'] = message.text.strip()

    bot.set_state(uid, MyStates.add_russian, cid)
    bot.send_message(
        cid,
        f"Отлично! Теперь введи перевод «{message.text}» на русском:"
    )


@bot.message_handler(
    state=MyStates.add_russian,
    content_types=['text']
)
def add_word_russian(message):
    """
    Получаем русский перевод и сохраняем слово в БД.
    """
    cid = message.chat.id
    uid = message.from_user.id

    with bot.retrieve_data(uid, cid) as data:
        english = data.get('new_english', '')

    russian = message.text.strip()

    if english and russian:
        db.add_word_for_user(uid, english, russian)
        count = db.count_user_words(uid)
        bot.send_message(
            cid,
            f"✅ Слово «{english} — {russian}» добавлено!\n"
            f"📚 Всего слов в вашем словаре: {count}"
        )
    else:
        bot.send_message(cid, "Что-то пошло не так. Попробуй ещё раз.")

    # Возвращаемся к карточкам
    bot.set_state(uid, MyStates.target_word, cid)
    build_card(message)


@bot.message_handler(
    func=lambda message: True,
    content_types=['text']
)
def message_reply(message):
    """
    Проверяет ответ пользователя на карточке.
    """
    text = message.text
    cid = message.chat.id
    uid = message.from_user.id

    if text in [Command.NEXT, Command.ADD_WORD, Command.DELETE_WORD]:
        return

    markup = types.ReplyKeyboardMarkup(row_width=2)
    buttons = user_buttons.get(cid, [])

    with bot.retrieve_data(uid, cid) as data:
        target_word = data.get('target_word', '')

        if text == target_word:
            # Правильный ответ
            hint = show_hint(
                "Отлично!❤",
                show_target(data)
            )
        else:
            # Неправильный ответ — помечаем кнопку крестиком
            for btn in buttons:
                if btn.text == text:
                    btn.text = text + ' ❌'
                    break
            hint = show_hint(
                "Допущена ошибка!",
                f"Попробуй ещё раз вспомнить слово 🇷🇺 {data.get('translate_word', '')}"
            )

    markup.add(*buttons)
    bot.send_message(cid, hint, reply_markup=markup)


bot.add_custom_filter(custom_filters.StateFilter(bot))
bot.infinity_polling(skip_pending=True)







