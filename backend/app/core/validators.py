import re


def normalize_phone(raw: str) -> str:
    """Номер без плюса считаем российским: '8 (999) 123-45-67' даёт '+79991234567'."""
    cleaned = raw.strip()
    digits = re.sub(r"\D", "", cleaned)
    if not digits:
        raise ValueError("Укажите номер телефона цифрами.")
    if not cleaned.startswith("+"):
        if len(digits) == 11 and digits[0] in "78":
            digits = "7" + digits[1:]
        elif len(digits) == 10:
            digits = "7" + digits
    if not 10 <= len(digits) <= 15:
        raise ValueError("Некорректный номер телефона. Пример: +79991234567")
    return "+" + digits


COMMON_PASSWORDS = {
    "12345678", "123456789", "1234567890", "11111111", "00000000", "87654321",
    "password", "password1", "password123", "qwerty123", "qwertyui", "qwertyuiop",
    "iloveyou", "admin123", "welcome1", "letmein1", "abc12345", "q1w2e3r4",
    "йцукенгш", "йцукен123", "пароль123", "qazwsxedc",
}  # fmt: skip


def validate_password_strength(password: str, email: str | None = None) -> str:
    if len(password) < 8:
        raise ValueError("Пароль слишком короткий: нужно минимум 8 символов.")
    if len(password.encode()) > 72:
        raise ValueError("Пароль слишком длинный: максимум 72 байта.")
    if not re.search(r"[A-Za-zА-Яа-яЁё]", password):
        raise ValueError("Добавьте в пароль хотя бы одну букву.")
    if not re.search(r"\d", password):
        raise ValueError("Добавьте в пароль хотя бы одну цифру.")
    if len(set(password)) < 4:
        raise ValueError("Пароль слишком однообразный.")
    if password.lower() in COMMON_PASSWORDS:
        raise ValueError("Этот пароль слишком популярный. Придумайте другой.")
    if email:
        local = email.split("@")[0].lower()
        if len(local) >= 4 and local in password.lower():
            raise ValueError("Не используйте в пароле свой email или его часть.")
    return password
