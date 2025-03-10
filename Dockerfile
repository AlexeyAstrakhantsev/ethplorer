# script1/Dockerfile
FROM mcr.microsoft.com/playwright/python:v1.40.0

WORKDIR /app

# Копируем файлы проекта
COPY parser-ethplorer-tag.py .
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Запускаем скрипт
CMD ["python", "parser-ethplorer-tag.py"]