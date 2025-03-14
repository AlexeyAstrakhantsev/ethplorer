from datetime import datetime
import psycopg2
from psycopg2 import pool
from contextlib import contextmanager
import logging

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
                    # Сохраняем адрес
                    cur.execute("""
                        INSERT INTO addresses (address, name, icon, icon_url)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (address) 
                        DO UPDATE SET 
                            name = EXCLUDED.name,
                            icon = EXCLUDED.icon,
                            icon_url = EXCLUDED.icon_url
                        RETURNING id
                    """, (
                        address_data['address'],
                        address_data['name'],
                        address_data.get('icon_data'),  # Декодированные бинарные данные
                        address_data.get('icon_url')
                    ))
                    address_id = cur.fetchone()[0]
                    
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
                    logging.info(f"Successfully saved address {address_data['address']} to database")
                    
                except Exception as e:
                    conn.rollback()
                    logging.error(f"Error saving address to database: {str(e)}")
                    raise 