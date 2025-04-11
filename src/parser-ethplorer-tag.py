from playwright.sync_api import sync_playwright
import time
import json
import logging
from pathlib import Path
import os
import aiohttp
import base64
from datetime import datetime
from db.models import Database, AddressRepository

class EthplorerParser:
    def __init__(self):
        self.base_url = os.getenv('BASE_URL', 'https://ethplorer.io')
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=os.getenv('PLAYWRIGHT_HEADLESS', 'true').lower() == 'true'
        )
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        
        # Настройка логирования
        logging.basicConfig(
            level=getattr(logging, os.getenv('PARSER_LOG_LEVEL', 'INFO')),
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(f"data/{os.getenv('LOG_FILE', 'parser.log')}"),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

        # Инициализация базы данных
        db_config = {
            'dbname': os.getenv('DB_NAME'),
            'user': os.getenv('DB_USER'),
            'password': os.getenv('DB_PASSWORD'),
            'host': os.getenv('DB_HOST'),
            'port': os.getenv('DB_PORT')
        }
        self.logger.info(f"Подключение к БД: {db_config}")
        self.db = Database(db_config)
        self.address_repository = AddressRepository(self.db)
        


    def get_tags(self):
        """Получение списка всех тегов с сайта"""
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
            return tags
            
        except Exception as e:
            self.logger.error(f"Ошибка при получении тегов: {e}")
            return []

    def get_tag_data(self, tag):
        """Получение данных по конкретному тегу"""
        processed_addresses = set()
        tag_counter = 0
        current_page = 1

        try:
            self.logger.info(f"Начинаем обработку тега: {tag}")
            self.page.goto(f"{self.base_url}/tag/{tag}")
            self.page.wait_for_selector('tbody tr', timeout=10000)  # Ждем загрузки таблицы
            
            while True:
                # Ожидаем обновления данных после пагинации
                self.page.wait_for_load_state("networkidle")
                time.sleep(1)

                # Получаем все блоки адресов
                address_blocks = self.page.query_selector_all('tbody tr')
                
                for block in address_blocks:
                    try:
                        # Получаем адрес
                        address_element = block.query_selector('.tags-table-address .overflow-center-elips')
                        address = address_element.inner_text().strip() if address_element else ''
                        
                        # Пропускаем дубликаты
                        if not address or address in processed_addresses:
                            continue
                        
                        processed_addresses.add(address)
                        
                        # Получаем контейнер тегов
                        tags_container = block.query_selector('span.tags-list')
                        if not tags_container:
                            self.logger.debug(f"Теги не найдены для адреса: {address}")
                            continue
                        
                        # Собираем все теги (включая иконки)
                        tag_elements = tags_container.query_selector_all('.tag__public')
                        address_tags = []
                        
                        for t in tag_elements:
                            try:
                                tag_text = None  # Инициализируем переменную
                                href = None      # Добавляем инициализацию href
                                
                                # Вариант 1: Текстовый тег
                                text_element = t.query_selector('.tag_name')
                                if text_element:
                                    tag_text = text_element.inner_text().strip()
                                
                                # Вариант 2: data-tag атрибут
                                if not tag_text:
                                    tag_text = t.get_attribute('data-tag') or ''
                                    tag_text = tag_text.strip()
                                
                                # Вариант 3: Извлечение из URL
                                if not tag_text:
                                    href = t.get_attribute('href')  # Теперь href определен
                                    if href and '/tag/' in href:
                                        tag_text = href.split('/tag/')[-1].split('?')[0].strip()
                                
                                if tag_text:
                                    address_tags.append(tag_text)
                                    tag_counter += 1
                                    self.logger.debug(
                                        f"Тэг найден: {tag_text} | Источник: "
                                        f"text={bool(text_element)}, "
                                        f"data-tag={bool(t.get_attribute('data-tag'))}, "
                                        f"href={bool(href)}"
                                    )
                                    
                            except Exception as e:
                                self.logger.error(f"Ошибка обработки тега: {str(e)}")
                                continue
                        
                        # Логируем результат
                        self.logger.debug(f"Адрес: {address[:8]}... | Теги: {len(address_tags)}")
                        
                        # Получаем имя токена/контракта
                        name_element = block.query_selector('.tags-table-token a')
                        name = name_element.inner_text().strip() if name_element else ''
                        
                        # Получаем иконку
                        icon_data = None
                        icon_url = None
                        icon_element = block.query_selector('.tags-table-token-icon')
                        if icon_element:
                            icon_url = icon_element.get_attribute('src')
                            if icon_url:
                                if icon_url.startswith('/'):
                                    icon_url = f"{self.base_url}{icon_url}"
                                try:
                                    response = self.context.request.get(icon_url)
                                    if response.ok:
                                        icon_data = response.body()
                                except Exception as e:
                                    self.logger.error(f"Ошибка при получении иконки {icon_url}: {e}")
                        
                        # Сохраняем данные в базу
                        data = {
                            'address': address,
                            'name': name,
                            'icon_url': icon_url,
                            'icon_data': icon_data,
                            'tags': address_tags
                        }
                        
                        # Логируем без icon_data
                        self.logger.info(f"Сохранен адрес: {address[:20]}... с тегами: {', '.join(address_tags)}")
                        self.logger.debug(f"Данные адреса (без icon_data): {json.dumps({k:v for k,v in data.items() if k != 'icon_data'}, default=str)}")
                        
                        self.address_repository.save_address(data)
                        
                        # После сбора тегов для адреса:
                        tag_counter += len(address_tags)
                    
                    except Exception as e:
                        self.logger.error(f"Ошибка обработки блока: {e}")
                        continue

                # Обработка пагинации
                next_button = self.page.query_selector(
                    'li.page-item:not(.disabled) a.page-link:has-text("»")'
                )
                
                if not next_button:
                    self.logger.info("Достигнут конец страниц")
                    break
                    
                try:
                    next_button.click()
                    current_page += 1
                    self.logger.info(f"Переход на страницу {current_page}")
                    self.page.wait_for_load_state("networkidle")
                    time.sleep(2)  # Даем время на загрузку
                except Exception as e:
                    self.logger.error(f"Ошибка пагинации: {e}")
                    break

            # Финализируем логирование
            self.logger.info(f"Обработано страниц: {current_page}")
            self.logger.info(f"Всего уникальных адресов: {len(processed_addresses)}")
            self.logger.info(f"Всего тегов сохранено: {tag_counter}")
            self.logger.info(f"Среднее тегов на адрес: {tag_counter/len(processed_addresses) if processed_addresses else 0:.2f}")
        
        except Exception as e:
            self.logger.error(f"Критическая ошибка: {e}")

    def append_to_json(self, data, filename='data/ethplorer_data.json'):
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

    def save_to_json(self, data, filename='data/ethplorer_data.json'):
        """Сохранение данных в JSON для последующей записи в SQL"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            
    def close(self):
        """Закрытие браузера и playwright"""
        self.context.close()
        self.browser.close()
        self.playwright.stop()

    async def process_address(self, address):
        try:
            await self.page.goto(f"{self.base_url}/address/{address}")
            await self.page.wait_for_load_state('networkidle')
            
            # Получаем иконку
            icon_data = None
            icon_url = None
            icon_element = await self.page.query_selector('.tags-table-token-icon')
            if icon_element:
                icon_url = await icon_element.get_attribute('src')
                if icon_url:
                    if icon_url.startswith('/'):
                        icon_url = f"{self.base_url}{icon_url}"
                    async with aiohttp.ClientSession() as session:
                        async with session.get(icon_url) as response:
                            if response.status == 200:
                                icon_data = await response.read()  # Теперь сохраняем как bytes

            # Получаем название и описание
            name = await self.get_text_content('.address-name-text')
            
            # Получаем теги
            tags = []
            tag_elements = await self.page.query_selector_all('.tag-item')
            for tag_element in tag_elements:
                tag_text = await tag_element.text_content()
                tags.append(tag_text.strip())

            data = {
                'address': address,
                'name': name,
                'icon_url': icon_url,
                'icon_data': icon_data,
                'tags': tags
            }
            
            # Сохраняем в базу данных
            self.address_repository.save_address(data)
            
            logging.info(f"Successfully processed address: {address}")
            return True
            
        except Exception as e:
            logging.error(f"Error processing address {address}: {str(e)}")
            return False

    def run(self):
        try:
            # Получаем тег из переменных окружения
            test_tag = os.getenv('TEST_TAG')
            tags = [test_tag] if test_tag else self.get_tags()
            
            self.logger.info(f"Режим работы: {'ТЕСТОВЫЙ' if test_tag else 'ПРОД'}") 
            self.logger.info(f"Найдено тегов: {len(tags)}")
            
            if not tags:
                self.logger.info("Теги не найдены. Завершение работы.")
                return
            
            # Собираем данные по каждому тегу
            for tag in tags:
                self.get_tag_data(tag)
                self.logger.info(f"Обработан тег {tag}")
            
            self.logger.info("Все теги обработаны. Завершение работы.")
        
        except Exception as e:
            self.logger.error(f"Критическая ошибка: {e}")
        finally:
            self.close()
            os._exit(0)

if __name__ == "__main__":
    parser = EthplorerParser()
    parser.run()
