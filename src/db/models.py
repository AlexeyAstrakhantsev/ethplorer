from datetime import datetime
import psycopg2
from psycopg2 import pool
from contextlib import contextmanager
import logging
import json

class Database:
    def __init__(self, config):
        self.pool = psycopg2.pool.SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            **config
        )
        
    @contextmanager
    def get_connection(self):
        conn = self.pool.getconn()
        try:
            yield conn
        finally:
            self.pool.putconn(conn)

class AddressRepository:
    def __init__(self, db):
        self.db = db

    def save_address(self, address_data):
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                try:
                    # Создаем копию данных для логов без icon_data
                    loggable_data = {k: v for k, v in address_data.items() if k != 'icon_data'}
                    
                    # Логирование перед сохранением
                    logging.debug(f"Сохранение адреса: {address_data['address']}")
                    logging.debug(f"Данные для сохранения: {json.dumps(loggable_data, default=str, indent=2)}")
                    
                    # Сохраняем адрес в основную таблицу
                    cur.execute("""
                        INSERT INTO addresses (address, name, icon, icon_url)
                        VALUES (%s, %s, %s::bytea, %s)
                        ON CONFLICT (address) 
                        DO UPDATE SET 
                            name = EXCLUDED.name,
                            icon = EXCLUDED.icon::bytea,
                            icon_url = EXCLUDED.icon_url
                        RETURNING id
                    """, (
                        address_data['address'],
                        address_data['name'],
                        address_data.get('icon_data'),
                        address_data.get('icon_url')
                    ))
                    address_id = cur.fetchone()[0]
                    logging.debug(f"Saved to addresses table, got id: {address_id}")
                    
                    # Сохраняем в unified_addresses
                    tags = address_data.get('tags', [])
                    address_name = address_data['name'] if address_data['name'] else (tags[0] if tags else '')
                    
                    logging.debug(f"Preparing unified_addresses data: address={address_data['address']}, name={address_name}")
                    
                    cur.execute("""
                        INSERT INTO unified_addresses (address, address_name, type, source)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (address) 
                        DO UPDATE SET 
                            address_name = EXCLUDED.address_name,
                            type = EXCLUDED.type,
                            source = EXCLUDED.source
                        RETURNING id
                    """, (
                        address_data['address'],
                        address_name,
                        "",  # Передаем пустую строку вместо None для поля type
                        "ethplorer.io tag"
                    ))
                    unified_id = cur.fetchone()[0]
                    logging.debug(f"Saved to unified_addresses, got id: {unified_id}")
                    
                    # Сохраняем теги
                    if 'tags' in address_data:
                        for tag in address_data['tags']:
                            # Добавляем тег если его нет
                            cur.execute("""
                                INSERT INTO tags (tag)
                                VALUES (%s)
                                ON CONFLICT (tag) DO UPDATE SET tag = EXCLUDED.tag
                                RETURNING id
                            """, (tag,))
                            tag_id = cur.fetchone()[0]
                            
                            # Связываем адрес с тегом
                            cur.execute("""
                                INSERT INTO address_tags (address_id, tag_id)
                                VALUES (%s, %s)
                                ON CONFLICT (address_id, tag_id) DO NOTHING
                            """, (address_id, tag_id))
                    
                    conn.commit()
                    logging.debug(f"Successfully saved address {address_data['address']} to all tables")
                    
                    # Логирование после сохранения
                    logging.debug(f"Успешно сохранено {len(address_data.get('tags', []))} тегов для адреса {address_data['address']}")
                    
                except Exception as e:
                    conn.rollback()
                    logging.error(f"Error saving address to database: {str(e)}")
                    raise 