import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST'),
        port=os.getenv('DB_PORT'),
        dbname=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD')
    )


def add_user(telegram_id: int, username: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO users (telegram_id, username)
        VALUES (%s, %s)
        ON CONFLICT (telegram_id) DO NOTHING
        """,
        (telegram_id, username)
    )
    conn.commit()
    cur.close()
    conn.close()


def get_user_id(telegram_id: int):
    """Возвращает внутренний id пользователя из таблицы users."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM users WHERE telegram_id = %s",
        (telegram_id,)
    )
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result[0] if result else None


def get_words_for_user(telegram_id: int):
    """
    Возвращает список слов, доступных пользователю.
    Исключает слова, которые пользователь удалил.
    Включает личные слова пользователя (добавленные им).
    """
    conn = get_connection()
    cur = conn.cursor()

    user_id = get_user_id(telegram_id)

    cur.execute(
        """
        SELECT w.id, w.english_word, w.russian_word
        FROM words w
        WHERE w.id NOT IN (
            SELECT uw.word_id
            FROM user_words uw
            WHERE uw.user_id = %s AND uw.is_deleted = TRUE
        )
        UNION
        SELECT w.id, w.english_word, w.russian_word
        FROM words w
        JOIN user_words uw ON w.id = uw.word_id
        WHERE uw.user_id = %s AND uw.is_deleted = FALSE
              AND w.id NOT IN (SELECT id FROM words WHERE id <= 10)
        """,
        (user_id, user_id)
    )

    words = cur.fetchall()
    cur.close()
    conn.close()
    return words  # список кортежей: (id, english, russian)


def add_word_for_user(telegram_id: int, english: str, russian: str):
    """
    Добавляет новое слово в общую таблицу words
    и связывает его с пользователем через user_words.
    """
    conn = get_connection()
    cur = conn.cursor()

    user_id = get_user_id(telegram_id)

    # Добавляем слово в общую таблицу
    cur.execute(
        """
        INSERT INTO words (english_word, russian_word)
        VALUES (%s, %s)
        RETURNING id
        """,
        (english.strip().capitalize(), russian.strip())
    )
    word_id = cur.fetchone()[0]

    # Связываем слово с пользователем
    cur.execute(
        """
        INSERT INTO user_words (user_id, word_id, is_deleted)
        VALUES (%s, %s, FALSE)
        ON CONFLICT (user_id, word_id) DO NOTHING
        """,
        (user_id, word_id)
    )

    conn.commit()
    cur.close()
    conn.close()
    return word_id


def delete_word_for_user(telegram_id: int, english_word: str):
    """
    Помечает слово как удалённое для конкретного пользователя.
    Другие пользователи слово по-прежнему видят.
    """
    conn = get_connection()
    cur = conn.cursor()

    user_id = get_user_id(telegram_id)

    # Находим id слова
    cur.execute(
        "SELECT id FROM words WHERE english_word = %s",
        (english_word,)
    )
    result = cur.fetchone()

    if result:
        word_id = result[0]
        cur.execute(
            """
            INSERT INTO user_words (user_id, word_id, is_deleted)
            VALUES (%s, %s, TRUE)
            ON CONFLICT (user_id, word_id)
            DO UPDATE SET is_deleted = TRUE
            """,
            (user_id, word_id)
        )
        conn.commit()

    cur.close()
    conn.close()


def count_user_words(telegram_id: int):
    """Считает количество слов, доступных пользователю."""
    words = get_words_for_user(telegram_id)
    return len(words)