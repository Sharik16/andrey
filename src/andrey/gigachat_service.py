import os
import logging
from pathlib import Path
from typing import Optional, List, Dict
from dotenv import load_dotenv
from gigachat import GigaChat
from gigachat.exceptions import UnprocessableEntityError
from gigachat.models import Chat, Messages, MessagesRole

# Загружаем переменные окружения из .env в корне проекта
base_dir = Path(__file__).resolve().parent.parent.parent
env_path = base_dir / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "GigaChat-2-Max"
DEFAULT_VISION_MODEL = "GigaChat-2-Max"

# Модели GigaChat, которые умеют работать с изображениями
VISION_MODELS = {
    "GigaChat-2-Max",
    "GigaChat-2-Pro",
    "GigaChat-3-Pro",
    "GigaChat-3-Ultra",
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def _looks_like_image(file_path: Optional[str], mime_type: Optional[str]) -> bool:
    """Определяет, является ли вложение изображением."""
    if mime_type and mime_type.startswith("image/"):
        return True
    if file_path:
        return os.path.splitext(file_path)[1].lower() in IMAGE_EXTENSIONS
    return False


def ask_gigachat(
    prompt: str,
    file_path: Optional[str] = None,
    mime_type: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
    """Отправляет текстовый запрос с историей диалога и опциональным изображением к GigaChat API."""
    credentials = os.getenv("GIGACHAT_CREDENTIALS", "").strip()
    if not credentials or credentials == "your_gigachat_credentials_here":
        raise ValueError(
            "API-ключ GigaChat не настроен. Укажите актуальный GIGACHAT_CREDENTIALS в файле .env"
        )

    is_image = _looks_like_image(file_path, mime_type)

    scope = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS").strip()
    model = os.getenv("GIGACHAT_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL

    # Для картинок нужна мультимодальная модель — при необходимости
    # автоматически переключаемся на неё, даже если текстовая модель другая.
    if is_image and model not in VISION_MODELS:
        model = (
            os.getenv("GIGACHAT_VISION_MODEL", DEFAULT_VISION_MODEL).strip()
            or DEFAULT_VISION_MODEL
        )

    verify_ssl_val = os.getenv("GIGACHAT_VERIFY_SSL", "false").strip().lower()
    verify_ssl = verify_ssl_val in ("true", "1", "yes")

    with GigaChat(
        credentials=credentials,
        scope=scope,
        model=model,
        verify_ssl_certs=verify_ssl,
        timeout=120.0,
    ) as giga:
        messages = []

        # Добавляем предыдущие сообщения из истории (ограничиваем последние 10 для контекста)
        if history:
            for item in history[-10:]:
                role = (
                    MessagesRole.USER
                    if item.get("role") == "user"
                    else MessagesRole.ASSISTANT
                )
                content = item.get("content") or ""
                if content.strip():
                    messages.append(Messages(role=role, content=content))

        # Обрабатываем вложенное изображение
        attachments = []
        if file_path and os.path.exists(file_path):
            filename = os.path.basename(file_path)
            with open(file_path, "rb") as f:
                file_bytes = f.read()

            try:
                uploaded = giga.upload_file(
                    (filename, file_bytes, mime_type or "application/octet-stream")
                )
                attachments.append(uploaded.id_)
            except Exception as e:
                logger.warning("Не удалось загрузить файл в GigaChat: %s", e)
                if is_image:
                    # Без вложения модель не увидит картинку — лучше честно сообщить об ошибке
                    raise ValueError(
                        "Не удалось отправить изображение в GigaChat. "
                        "Поддерживаются форматы PNG и JPEG размером до 10 МБ."
                    ) from e
                # Если файл не загрузился в GigaChat, дополним промпт информацией о файле
                prompt = (
                    f"{prompt}\n[Пользователь прикрепил файл: {filename}]"
                    if prompt
                    else f"[Пользователь прикрепил файл: {filename}]"
                )

        user_content = prompt or (
            "Что изображено на этой картинке?" if is_image
            else ("Что изображено на этом файле?" if attachments else "...")
        )
        messages.append(
            Messages(
                role=MessagesRole.USER,
                content=user_content,
                attachments=attachments if attachments else None,
            )
        )

        chat_payload = Chat(messages=messages)
        try:
            response = giga.chat(chat_payload)
        except UnprocessableEntityError as e:
            if is_image and b"does not support image" in (e.content or b""):
                raise ValueError(
                    "Выбранная модель GigaChat не поддерживает изображения. "
                    "Укажите мультимодальную модель в GIGACHAT_VISION_MODEL "
                    "(например, GigaChat-2-Max) в файле .env"
                ) from e
            raise

        if not response.choices:
            raise RuntimeError("GigaChat не вернул ответа.")

        answer = response.choices[0].message.content or ""
        return answer
