import os
import logging
from pathlib import Path
from typing import Optional, List, Dict
from dotenv import load_dotenv
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole

# Загружаем переменные окружения из .env в корне проекта
base_dir = Path(__file__).resolve().parent.parent.parent
env_path = base_dir / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

logger = logging.getLogger(__name__)


def ask_gigachat(
    prompt: str,
    file_path: Optional[str] = None,
    mime_type: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
    """Отправляет текстовый запрос с историей диалога и опциональным файлом (фото/аудио) к GigaChat API."""
    credentials = os.getenv("GIGACHAT_CREDENTIALS", "").strip()
    if not credentials or credentials == "your_gigachat_credentials_here":
        raise ValueError(
            "API-ключ GigaChat не настроен. Укажите актуальный GIGACHAT_CREDENTIALS в файле .env"
        )

    scope = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS").strip()
    model = os.getenv("GIGACHAT_MODEL", "GigaChat-2-Max").strip()
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

        # Обрабатываем вложенный файл (изображение или аудио)
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
                # Если файл не загрузился в GigaChat, дополним промпт информацией о файле
                prompt = (
                    f"{prompt}\n[Пользователь прикрепил файл: {filename}]"
                    if prompt
                    else f"[Пользователь прикрепил файл: {filename}]"
                )

        user_content = prompt or ("Что изображено на этом файле?" if attachments else "...")
        messages.append(
            Messages(
                role=MessagesRole.USER,
                content=user_content,
                attachments=attachments if attachments else None,
            )
        )

        chat_payload = Chat(messages=messages)
        response = giga.chat(chat_payload)

        if not response.choices:
            raise RuntimeError("GigaChat не вернул ответа.")

        answer = response.choices[0].message.content or ""
        return answer
