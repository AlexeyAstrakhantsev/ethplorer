from playwright.sync_api import sync_playwright
import time
import json
import logging
from pathlib import Path
import os

class EthplorerParser:
    def __init__(self):
        self.base_url = "https://ethplorer.io"
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=True)
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        self.tags_file = "remaining_tags.txt"
        
        # Настройка логирования
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('parser.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def load_tags_from_file(self):
        """Загрузка списка тегов из файла"""
        if os.path.exists(self.tags_file):
            with open(self.tags_file, 'r', encoding='utf-8') as f:
                tags = [line.strip() for line in f if line.strip()]
            self.logger.info(f"Загружено {len(tags)} тегов из файла")
            return tags
        return []

    def save_tags_to_file(self, tags):
        """Сохранение списка тегов в файл"""
        with open(self.tags_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(tags))
        self.logger.info(f"Сохранено {len(tags)} тегов в файл")

    def remove_tag_from_file(self, tag):
        """Удаление обработанного тега из файла"""
        tags = self.load_tags_from_file()
        if tag in tags:
            tags.remove(tag)
            self.save_tags_to_file(tags)
            self.logger.info(f"Тег {tag} удален из файла")

    def get_tags(self):
        """Получение списка всех тегов"""
        # Сначала пробуем загрузить теги из файла
        existing_tags = self.load_tags_from_file()
        if existing_tags:
            return existing_tags

        tags = []
        try:
            self.logger.info("Начинаем получение списка тегов с сайта")
            self.page.goto(f"{self.base_url}/tag")
            self.page.wait_for_selector('.word-cloud-item a')
            
            tag_elements = self.page.query_selector_all('.word-cloud-item a')
            
            for tag in tag_elements:
                tag_text = tag.inner_text().strip()
                tags.append(tag_text)
            
            self.logger.info(f"Получено {len(tags)} тегов")
            self.save_tags_to_file(tags)
            return tags
            
        except Exception as e:
            self.logger.error(f"Ошибка при получении тегов: {e}")
            return []

    def get_tag_data(self, tag):
        """Получение данных по конкретному тегу"""
        data = []
        processed_addresses = set()  # Множество для отслеживания обработанных адресов
        
        try:
            self.logger.info(f"Начинаем обработку тега: {tag}")
            self.page.goto(f"{self.base_url}/tag/{tag}")
            
            while True:
                self.page.wait_for_selector('.d-flex.flex-column.flex-fill')
                time.sleep(1)
                
                address_blocks = self.page.query_selector_all('.d-flex.flex-column.flex-fill')
                
                if not address_blocks:
                    break
                
                for block in address_blocks:
                    try:
                        # Получаем адрес
                        address_element = block.query_selector('.tags-table-address .overflow-center-elips')
                        address = address_element.inner_text().strip() if address_element else ''
                        
                        # Пропускаем, если адрес уже обработан
                        if not address or address in processed_addresses:
                            continue
                        
                        # Добавляем адрес в множество обработанных
                        processed_addresses.add(address)
                        
                        # Получаем имя токена/контракта
                        name_element = block.query_selector('.tags-table-token a')
                        name = name_element.inner_text().strip() if name_element else ''
                        
                        # Получаем теги и убираем дубликаты через множество
                        tag_elements = block.query_selector_all('.tags-list .tag__public .tag_name')
                        address_tags = list(set(t.inner_text().strip() for t in tag_elements)) if tag_elements else []
                        
                        item = {
                            'name': name,
                            'address': address,
                            'tags': address_tags
                        }
                        data.append(item)
                        self.logger.debug(f"Добавлен адрес: {address[:10]}... с тегами: {', '.join(address_tags)}")
                    
                    except Exception as e:
                        self.logger.error(f"Ошибка при обработке блока адреса: {e}")
                        continue
                
                next_button = self.page.query_selector('li.page-item:not(.disabled) a.page-link span[aria-hidden="true"]:text("»")')
                if not next_button:
                    break
                
                next_button.click()
                time.sleep(1)
            
            self.logger.info(f"Завершена обработка тега {tag}, найдено записей: {len(data)}")
            return data
            
        except Exception as e:
            self.logger.error(f"Ошибка при получении данных тега {tag}: {e}")
            return []

    def append_to_json(self, data, filename='ethplorer_data.json'):
        """Добавление новых данных в JSON файл"""
        try:
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                existing_data = []
            
            existing_data.extend(data)
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=4)
            
            self.logger.info(f"Данные успешно сохранены в {filename}")
                
        except Exception as e:
            self.logger.error(f"Ошибка при сохранении данных: {e}")

    def save_to_json(self, data, filename='ethplorer_data.json'):
        """Сохранение данных в JSON для последующей записи в SQL"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            
    def close(self):
        """Закрытие браузера и playwright"""
        self.context.close()
        self.browser.close()
        self.playwright.stop()

def main():
    parser = EthplorerParser()
    try:
        # Получаем список тегов
        tags = parser.get_tags()
        parser.logger.info(f"Найдено тегов: {len(tags)}")
        
        # Собираем данные по каждому тегу
        for tag in tags:
            tag_data = parser.get_tag_data(tag)
            parser.append_to_json(tag_data)
            parser.logger.info(f"Обработан тег {tag}, найдено записей: {len(tag_data)}")
            parser.remove_tag_from_file(tag)
        
    except Exception as e:
        parser.logger.error(f"Критическая ошибка: {e}")
    finally:
        parser.close()

if __name__ == "__main__":
    main()
