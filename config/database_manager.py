"""
Database Manager for BMS Lot Tracking System
Centralized database operations and lot tracking queries
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from config.system_config import LOT_TRACKING_DB, LOT_MASTERLIST_DB, PROCESS_FLOW_CONFIG


class DatabaseManager:
    """Centralized database management for lot tracking"""
    
    def __init__(self):
        self.lot_tracking_db = LOT_TRACKING_DB
        self.lot_masterlist_db = LOT_MASTERLIST_DB
        self.process_flow_config = PROCESS_FLOW_CONFIG
        self._load_process_config()
    
    def _load_process_config(self):
        """Load process flow configuration from JSON"""
        try:
            with open(self.process_flow_config, 'r') as f:
                config = json.load(f)
                self.process_flow = config.get("process_flow", [])
                self.process_column_mapping = config.get("process_column_mapping", {})
        except FileNotFoundError:
            self.process_flow = []
            self.process_column_mapping = {}
        except json.JSONDecodeError:
            self.process_flow = []
            self.process_column_mapping = {}
    
    def get_connection(self, db_path: str):
        """Get database connection"""
        return sqlite3.connect(db_path)
    
    def get_all_active_lots(self) -> List[Dict]:
        """Get all active lots with their current process status"""
        try:
            conn = self.get_connection(self.lot_tracking_db)
            cursor = conn.cursor()
            
            query = """
                SELECT DISTINCT 
                    lot_number, 
                    sensor_id,
                    current_process,
                    lot_entry_proc_date
                FROM lot_tracking
                WHERE current_process IS NOT NULL
                ORDER BY lot_entry_proc_date DESC
            """
            
            cursor.execute(query)
            rows = cursor.fetchall()
            conn.close()
            
            lots = []
            for row in rows:
                lots.append({
                    'lot_number': row[0],
                    'sensor_id': row[1],
                    'current_process': row[2],
                    'entry_date': row[3]
                })
            
            return lots
        
        except Exception as e:
            print(f"Error fetching active lots: {e}")
            return []
    
    def get_lot_history(self, lot_number: str) -> Dict:
        """Get complete history of a specific lot"""
        try:
            conn = self.get_connection(self.lot_tracking_db)
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM lot_tracking WHERE lot_number=?", (lot_number,))
            columns = [description[0] for description in cursor.description]
            rows = cursor.fetchall()
            conn.close()
            
            if rows:
                # Convert to list of dictionaries
                history = []
                for row in rows:
                    history.append(dict(zip(columns, row)))
                return {'lot_number': lot_number, 'history': history}
            
            return {'lot_number': lot_number, 'history': []}
        
        except Exception as e:
            print(f"Error fetching lot history: {e}")
            return {'lot_number': lot_number, 'history': []}
    
    def get_lot_counts_by_process(self) -> Dict[str, int]:
        """Get count of lots at each process stage"""
        try:
            conn = self.get_connection(self.lot_tracking_db)
            cursor = conn.cursor()
            
            query = """
                SELECT current_process, COUNT(DISTINCT lot_number) as count
                FROM lot_tracking
                WHERE current_process IS NOT NULL
                GROUP BY current_process
            """
            
            cursor.execute(query)
            rows = cursor.fetchall()
            conn.close()
            
            process_counts = {}
            for row in rows:
                process_counts[row[0]] = row[1]
            
            return process_counts
        
        except Exception as e:
            print(f"Error fetching process counts: {e}")
            return {}
    
    def get_sensor_counts_by_process(self) -> Dict[str, int]:
        """Get count of sensors at each process stage"""
        try:
            conn = self.get_connection(self.lot_tracking_db)
            cursor = conn.cursor()
            
            query = """
                SELECT current_process, COUNT(DISTINCT sensor_id) as count
                FROM lot_tracking
                WHERE current_process IS NOT NULL
                GROUP BY current_process
            """
            
            cursor.execute(query)
            rows = cursor.fetchall()
            conn.close()
            
            process_counts = {}
            for row in rows:
                process_counts[row[0]] = row[1]
            
            return process_counts
        
        except Exception as e:
            print(f"Error fetching sensor counts: {e}")
            return {}
    
    def search_lots(self, search_term: str) -> List[Dict]:
        """Search for lots by lot number or sensor ID"""
        try:
            conn = self.get_connection(self.lot_tracking_db)
            cursor = conn.cursor()
            
            query = """
                SELECT DISTINCT 
                    lot_number, 
                    sensor_id,
                    current_process,
                    lot_entry_proc_date
                FROM lot_tracking
                WHERE lot_number LIKE ? OR sensor_id LIKE ?
                ORDER BY lot_entry_proc_date DESC
                LIMIT 50
            """
            
            search_pattern = f"%{search_term}%"
            cursor.execute(query, (search_pattern, search_pattern))
            rows = cursor.fetchall()
            conn.close()
            
            lots = []
            for row in rows:
                lots.append({
                    'lot_number': row[0],
                    'sensor_id': row[1],
                    'current_process': row[2],
                    'entry_date': row[3]
                })
            
            return lots
        
        except Exception as e:
            print(f"Error searching lots: {e}")
            return []
    
    def get_lot_details(self, lot_number: str, sensor_id: str = None) -> Optional[Dict]:
        """Get detailed information about a lot from masterlist"""
        try:
            conn = self.get_connection(self.lot_masterlist_db)
            cursor = conn.cursor()
            
            if sensor_id:
                cursor.execute("SELECT * FROM lot_masterlist WHERE lot_number=? AND sensor_id=?", 
                             (lot_number, sensor_id))
            else:
                cursor.execute("SELECT * FROM lot_masterlist WHERE lot_number=? LIMIT 1", 
                             (lot_number,))
            
            columns = [description[0] for description in cursor.description]
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return dict(zip(columns, row))
            
            return None
        
        except Exception as e:
            print(f"Error fetching lot details: {e}")
            return None
    
    def get_lot_info(self, lot_number: str) -> Optional[Dict]:
        """Get basic lot information to verify if lot exists"""
        try:
            # First check tracking database
            conn = self.get_connection(self.lot_tracking_db)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT lot_number, sensor_id, current_process 
                FROM lot_tracking 
                WHERE lot_number=? 
                LIMIT 1
            """, (lot_number,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    'lot_number': row[0],
                    'sensor_id': row[1],
                    'current_process': row[2],
                    'exists': True
                }
            
            # If not in tracking, check masterlist
            conn = self.get_connection(self.lot_masterlist_db)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT lot_number 
                FROM lot_masterlist 
                WHERE lot_number=? 
                LIMIT 1
            """, (lot_number,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    'lot_number': row[0],
                    'sensor_id': None,
                    'current_process': None,
                    'exists': True
                }
            
            return None
        
        except Exception as e:
            print(f"Error fetching lot info: {e}")
            return None
    
    def get_recent_activity(self, limit: int = 20) -> List[Dict]:
        """Get recent lot processing activity"""
        try:
            conn = self.get_connection(self.lot_tracking_db)
            cursor = conn.cursor()
            
            # Get all process columns that have timestamps
            query = """
                SELECT 
                    lot_number,
                    sensor_id,
                    current_process,
                    lot_entry_proc_date,
                    lot_entry_operator
                FROM lot_tracking
                WHERE lot_entry_proc_date IS NOT NULL
                ORDER BY lot_entry_proc_date DESC
                LIMIT ?
            """
            
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
            conn.close()
            
            activities = []
            for row in rows:
                activities.append({
                    'lot_number': row[0],
                    'sensor_id': row[1],
                    'process': row[2],
                    'timestamp': row[3],
                    'operator': row[4]
                })
            
            return activities
        
        except Exception as e:
            print(f"Error fetching recent activity: {e}")
            return []
    
    def get_production_statistics(self) -> Dict:
        """Get overall production statistics"""
        try:
            conn_tracking = self.get_connection(self.lot_tracking_db)
            cursor_tracking = conn_tracking.cursor()
            
            # Total lots
            cursor_tracking.execute("SELECT COUNT(DISTINCT lot_number) FROM lot_tracking")
            total_lots = cursor_tracking.fetchone()[0]
            
            # Total sensors
            cursor_tracking.execute("SELECT COUNT(DISTINCT sensor_id) FROM lot_tracking")
            total_sensors = cursor_tracking.fetchone()[0]
            
            # Lots in progress
            cursor_tracking.execute("""
                SELECT COUNT(DISTINCT lot_number) 
                FROM lot_tracking 
                WHERE current_process IS NOT NULL 
                AND current_process != 'Completed'
            """)
            lots_in_progress = cursor_tracking.fetchone()[0]
            
            # Completed lots (assuming final process or specific status)
            cursor_tracking.execute("""
                SELECT COUNT(DISTINCT lot_number) 
                FROM lot_tracking 
                WHERE current_process = 'Completed' OR current_process LIKE '%Shipment%'
            """)
            completed_lots = cursor_tracking.fetchone()[0]
            
            conn_tracking.close()
            
            return {
                'total_lots': total_lots,
                'total_sensors': total_sensors,
                'in_progress': lots_in_progress,
                'completed': completed_lots
            }
        
        except Exception as e:
            print(f"Error fetching statistics: {e}")
            return {
                'total_lots': 0,
                'total_sensors': 0,
                'in_progress': 0,
                'completed': 0
            }
    
    def validate_database_connection(self) -> Tuple[bool, str]:
        """Validate database connections"""
        try:
            # Test lot_tracking.db
            conn1 = self.get_connection(self.lot_tracking_db)
            conn1.close()
            
            # Test lot_masterlist.db
            conn2 = self.get_connection(self.lot_masterlist_db)
            conn2.close()
            
            return True, "Database connections successful"
        
        except Exception as e:
            return False, f"Database connection failed: {e}"
