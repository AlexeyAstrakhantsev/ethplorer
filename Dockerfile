# script1/Dockerfile
FROM mcr.microsoft.com/playwright/python:v1.40.0

WORKDIR /app

# Копируем файлы проекта
COPY requirements.txt .
COPY src/ .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Устанавливаем playwright
RUN playwright install chromium

# Запускаем скрипт
CMD ["python", "parser-ethplorer-tag.py"]